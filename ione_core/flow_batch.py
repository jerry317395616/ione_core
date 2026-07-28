from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

BATCH_POLICY_MARKER = "[I-ONE BATCH EXECUTION POLICY]"
MAX_MUTATING_CALLS = 1
MAX_TOTAL_CALLS = 6
MAX_ITERATIONS = 8
MAX_TOOL_PHASE_SECONDS = 70
MAX_MUTATION_ARGUMENT_BYTES = 256 * 1024
MAX_CONTINUATION_SUMMARY_CHARS = 12_000

MUTATING_TOOLS = frozenset({"create", "update", "delete", "run_action", "execute"})
CONTINUATION_INPUTS = frozenset({"继续", "继续执行", "下一批", "继续下一批"})

BATCH_POLICY = f"""
{BATCH_POLICY_MARKER}
Treat one user message as exactly one finite batch:
- Execute at most {MAX_MUTATING_CALLS} mutating tool call in this turn.
- There is no fixed record-count limit. Choose the batch size from record complexity,
  validation cost, and tool payload size instead of defaulting to ten records.
- Put a coherent set of simple records into one create/update/delete call when safe.
- Use at most {MAX_TOTAL_CALLS} tool calls in total, including discovery and reads.
- Never repeat a tool call with identical arguments.
- Immediately stop using tools after the first successful mutating call.
- Do not start another module or another batch after that call is complete.
- Keep discovery focused: use filters, ordering, and pagination to find only the next
  unprocessed records. Do not repeatedly read the same first page.
- When the user says "继续", resume the first concrete unfinished operation from the
  preceding verified summary and perform a real write in this turn. Do not merely
  repeat counts, plans, or the previous answer. If the operation is complete or safe
  field values cannot be determined, say so explicitly and do not invent them.
- When the time or call budget is reached, stop using tools and report verified
  successes, skips, and failures. Tell the user to send "继续" for the next batch.
- A broad request such as "continue all modules" does not authorize an endless loop.
- Never use execute to bypass the single-write, time, payload, or call budgets.
""".strip()

CONTINUATION_INSTRUCTION = """
Continue the first concrete unfinished operation from the preceding verified batch
summary. This turn must perform one real mutating tool call unless the operation is
already complete or the database does not contain enough information to write safely.
Use targeted filters, ordering, and pagination to select the next unprocessed records.
Do not repeat the previous answer or an identical read. Do not invent critical business
values merely to fill a batch. Select an adaptive batch size based on record complexity
and submit the coherent batch in one mutating call. Report only the actual tool result.
""".strip()


@dataclass
class BatchExecutionState:
	total_calls: int = 0
	mutating_calls: int = 0
	duplicate_calls: int = 0
	force_summary: bool = False
	seen_calls: set[str] = field(default_factory=set)
	started_at: float = 0.0
	clock: Callable[[], float] = time.monotonic

	@property
	def elapsed(self) -> float:
		return max(0.0, self.clock() - self.started_at)


def append_batch_policy(instructions: str | None) -> str:
	instructions = (instructions or "").strip()
	if BATCH_POLICY_MARKER in instructions:
		instructions = instructions.split(BATCH_POLICY_MARKER, 1)[0].rstrip()
	return f"{instructions}\n\n{BATCH_POLICY}".strip()


def prepare_continuation_prompt(session: Any, input: str) -> bool:
	"""Use a compact, action-oriented prompt for terse continuation messages."""
	if not is_continuation_input(input):
		return False

	original_builder = session._build_prompt_messages

	def build_prompt() -> list[dict[str, Any]]:
		return compact_continuation_messages(original_builder())

	session._build_prompt_messages = build_prompt
	return True


def compact_continuation_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Keep the system policy and last verified summary, not the full tool transcript."""
	system = next((dict(message) for message in messages if message.get("role") == "system"), None)
	current_user_index = next(
		(index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"),
		None,
	)

	previous_summary = None
	if current_user_index is not None:
		for message in reversed(messages[:current_user_index]):
			if (
				message.get("role") == "assistant"
				and message.get("content")
				and not message.get("tool_calls")
			):
				previous_summary = str(message["content"])[-MAX_CONTINUATION_SUMMARY_CHARS:]
				break

	compacted: list[dict[str, Any]] = []
	if system:
		compacted.append(system)
	if previous_summary:
		compacted.extend(
			[
				{
					"role": "user",
					"content": "The following is the verified summary from the preceding batch.",
				},
				{"role": "assistant", "content": previous_summary},
			]
		)
	compacted.append({"role": "user", "content": CONTINUATION_INSTRUCTION})
	return compacted


def is_continuation_input(input: str | None) -> bool:
	return bool(input and input.strip() in CONTINUATION_INPUTS)


def apply_batch_execution_guard(
	runtime: Any,
	*,
	clock: Callable[[], float] = time.monotonic,
) -> BatchExecutionState:
	"""Bound a Flow runtime by time, calls, payload size, and one write phase."""
	current = getattr(runtime, "_ione_batch_guard_state", None)
	if current is not None:
		return current

	state = BatchExecutionState(started_at=clock(), clock=clock)
	original_invoke = runtime._invoke
	original_chat = runtime.model.chat

	def guarded_invoke(call: Any) -> Any:
		name = str(getattr(call, "name", "") or "")
		arguments = getattr(call, "arguments", None)
		state.total_calls += 1
		signature = json.dumps(
			{"name": name, "arguments": arguments},
			sort_keys=True,
			ensure_ascii=False,
			default=str,
		)

		if signature in state.seen_calls:
			state.duplicate_calls += 1
			if name in MUTATING_TOOLS or state.total_calls >= MAX_TOTAL_CALLS:
				state.force_summary = True
			return {
				"status": "skipped_duplicate",
				"message": (
					"Identical tool call already ran in this turn. Use different filters or "
					"pagination; do not repeat the same request."
				),
			}

		state.seen_calls.add(signature)

		if name not in MUTATING_TOOLS and state.elapsed >= MAX_TOOL_PHASE_SECONDS:
			state.force_summary = True
			return {
				"status": "time_budget",
				"message": (
					f"The {MAX_TOOL_PHASE_SECONDS}-second tool budget is exhausted. "
					"No write was attempted by this call; summarize the verified results."
				),
			}

		if name in MUTATING_TOOLS and _argument_size(arguments) > MAX_MUTATION_ARGUMENT_BYTES:
			state.force_summary = True
			return {
				"status": "payload_limit",
				"message": (
					"The mutating request is too large for reliable transport. Split it by "
					"record complexity or field set and retry in the next turn. No records changed."
				),
			}

		if name in MUTATING_TOOLS and state.mutating_calls >= MAX_MUTATING_CALLS:
			state.force_summary = True
			return {
				"status": "batch_limit",
				"message": f"Batch write limit ({MAX_MUTATING_CALLS}) reached. Stop and summarize.",
			}

		result = original_invoke(call)
		if name in MUTATING_TOOLS:
			state.mutating_calls += 1
			state.force_summary = True
		if state.total_calls >= MAX_TOTAL_CALLS:
			state.force_summary = True
		return result

	def guarded_chat(messages: list[dict[str, Any]], *, tools: Any = None, **kwargs: Any) -> Any:
		if state.total_calls and state.elapsed >= MAX_TOOL_PHASE_SECONDS:
			state.force_summary = True
		if not state.force_summary:
			return original_chat(messages, tools=tools, **kwargs)

		final_messages = [
			*messages,
			{"role": "user", "content": _finalize_instruction(state)},
		]
		return original_chat(final_messages, tools=None, **kwargs)

	runtime._invoke = guarded_invoke
	runtime.model.chat = guarded_chat
	runtime.instructions = append_batch_policy(runtime.instructions)
	runtime.max_iterations = min(runtime.max_iterations, MAX_ITERATIONS)
	runtime._ione_batch_guard_state = state
	return state


def _argument_size(arguments: Any) -> int:
	try:
		return len(json.dumps(arguments, ensure_ascii=False, default=str).encode("utf-8"))
	except (TypeError, ValueError):
		return MAX_MUTATION_ARGUMENT_BYTES + 1


def _finalize_instruction(state: BatchExecutionState) -> str:
	if state.mutating_calls:
		status = "A mutating tool call ran in this turn."
	else:
		status = "No mutating tool call ran in this turn. State that clearly and give the exact blocker."
	return f"""
The tool phase for this turn is finished. {status} Do not call, simulate, or propose
another tool call. Summarize only verified tool results from this turn, including
successes, skipped duplicates, and failures. Never claim that records changed unless
the tool result confirms it. End by saying that the user can send "继续" for the next
adaptive batch when unfinished work remains.
""".strip()
