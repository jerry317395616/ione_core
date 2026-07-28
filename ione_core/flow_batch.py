from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

BATCH_POLICY_MARKER = "[I-ONE BATCH EXECUTION POLICY]"
MAX_MUTATING_CALLS = 10
MAX_TOTAL_CALLS = 14
MAX_ITERATIONS = 16

MUTATING_TOOLS = frozenset({"create", "update", "delete", "run_action", "execute"})

BATCH_POLICY = f"""
{BATCH_POLICY_MARKER}
Treat one user message as exactly one finite batch:
- Process at most {MAX_MUTATING_CALLS} records or mutating tool calls in this turn.
- Use at most {MAX_TOTAL_CALLS} tool calls in total, including discovery and reads.
- Never repeat a tool call with identical arguments.
- Do not start another module or another batch after this batch is complete.
- When the batch limit is reached, stop using tools and report verified successes,
  skips, and failures. Tell the user to send "继续" for the next batch.
- A broad request such as "continue all modules" does not authorize an endless loop.
- Never use execute to bypass these limits or to create more than 10 records.
""".strip()

FINALIZE_INSTRUCTION = """
The tool phase for this turn is finished. Do not call, simulate, or propose another
tool call. Summarize only the verified tool results from this turn, including
successes, skipped duplicates, and failures. End by saying that the user can send
"继续" to process the next batch.
""".strip()


@dataclass
class BatchExecutionState:
	total_calls: int = 0
	mutating_calls: int = 0
	force_summary: bool = False
	seen_calls: set[str] = field(default_factory=set)


def append_batch_policy(instructions: str | None) -> str:
	instructions = (instructions or "").strip()
	if BATCH_POLICY_MARKER in instructions:
		return instructions
	return f"{instructions}\n\n{BATCH_POLICY}".strip()


def apply_batch_execution_guard(runtime: Any) -> BatchExecutionState:
	"""Bound a Flow runtime to one finite, idempotent batch per user turn."""
	current = getattr(runtime, "_ione_batch_guard_state", None)
	if current is not None:
		return current

	state = BatchExecutionState()
	original_invoke = runtime._invoke
	original_chat = runtime.model.chat

	def guarded_invoke(call: Any) -> Any:
		name = str(getattr(call, "name", "") or "")
		arguments = getattr(call, "arguments", None)
		signature = json.dumps(
			{"name": name, "arguments": arguments},
			sort_keys=True,
			ensure_ascii=False,
			default=str,
		)

		if signature in state.seen_calls:
			state.force_summary = True
			return {
				"status": "skipped_duplicate",
				"message": "Identical tool call already ran in this batch. Stop and summarize.",
			}

		state.seen_calls.add(signature)
		state.total_calls += 1

		if name in MUTATING_TOOLS and state.mutating_calls >= MAX_MUTATING_CALLS:
			state.force_summary = True
			return {
				"status": "batch_limit",
				"message": f"Batch write limit ({MAX_MUTATING_CALLS}) reached. Stop and summarize.",
			}

		result = original_invoke(call)
		if name in MUTATING_TOOLS:
			state.mutating_calls += 1
			if state.mutating_calls >= MAX_MUTATING_CALLS:
				state.force_summary = True
		if state.total_calls >= MAX_TOTAL_CALLS:
			state.force_summary = True
		return result

	def guarded_chat(messages: list[dict[str, Any]], *, tools: Any = None, **kwargs: Any) -> Any:
		if not state.force_summary:
			return original_chat(messages, tools=tools, **kwargs)

		final_messages = [*messages, {"role": "user", "content": FINALIZE_INSTRUCTION}]
		return original_chat(final_messages, tools=None, **kwargs)

	runtime._invoke = guarded_invoke
	runtime.model.chat = guarded_chat
	runtime.instructions = append_batch_policy(runtime.instructions)
	runtime.max_iterations = min(runtime.max_iterations, MAX_ITERATIONS)
	runtime._ione_batch_guard_state = state
	return state
