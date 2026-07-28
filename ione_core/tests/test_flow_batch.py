from types import SimpleNamespace
from unittest import TestCase

from ione_core.flow_batch import (
	BATCH_POLICY_MARKER,
	MAX_ITERATIONS,
	MAX_MUTATING_CALLS,
	MAX_MUTATION_ARGUMENT_BYTES,
	MAX_TOOL_PHASE_SECONDS,
	apply_batch_execution_guard,
	append_batch_policy,
	compact_continuation_messages,
	prepare_continuation_prompt,
)


class FakeModel:
	def __init__(self):
		self.calls = []

	def chat(self, messages, *, tools=None, **kwargs):
		self.calls.append({"messages": messages, "tools": tools, "kwargs": kwargs})
		return "response"


class FakeRuntime:
	def __init__(self):
		self.model = FakeModel()
		self.instructions = "Base instructions"
		self.max_iterations = 40
		self.invocations = []

	def _invoke(self, call):
		self.invocations.append(call)
		return {"status": "ok"}


class TestFlowBatchGuard(TestCase):
	def test_appends_policy_once(self):
		once = append_batch_policy("Base")
		twice = append_batch_policy(once)

		self.assertIn(BATCH_POLICY_MARKER, once)
		self.assertEqual(once, twice)

	def test_stops_tools_after_mutating_batch_limit(self):
		runtime = FakeRuntime()
		state = apply_batch_execution_guard(runtime)

		result = runtime._invoke(
			SimpleNamespace(
				name="create",
				arguments={
					"doctype": "ToDo",
					"records": [{"description": str(index)} for index in range(75)],
				},
			)
		)
		self.assertEqual(result["status"], "ok")

		skipped = runtime._invoke(
			SimpleNamespace(name="create", arguments={"doctype": "ToDo", "records": [{}]})
		)
		self.assertEqual(skipped["status"], "batch_limit")
		self.assertEqual(len(runtime.invocations), MAX_MUTATING_CALLS)
		self.assertTrue(state.force_summary)

		runtime.model.chat([{"role": "tool", "content": "{}"}], tools=[{"name": "create"}], stream=True)
		last_call = runtime.model.calls[-1]
		self.assertIsNone(last_call["tools"])
		self.assertIn("tool phase", last_call["messages"][-1]["content"])
		self.assertTrue(last_call["kwargs"]["stream"])
		self.assertEqual(runtime.max_iterations, MAX_ITERATIONS)

	def test_repeated_read_is_skipped_without_ending_the_turn(self):
		runtime = FakeRuntime()
		state = apply_batch_execution_guard(runtime)
		call = SimpleNamespace(name="read", arguments={"doctype": "Company"})

		self.assertEqual(runtime._invoke(call)["status"], "ok")
		self.assertEqual(runtime._invoke(call)["status"], "skipped_duplicate")
		self.assertEqual(len(runtime.invocations), 1)
		self.assertFalse(state.force_summary)

	def test_large_record_batch_is_not_limited_by_record_count(self):
		runtime = FakeRuntime()
		call = SimpleNamespace(
			name="update",
			arguments={"doctype": "Customer", "names": [str(i) for i in range(100)]},
		)

		apply_batch_execution_guard(runtime)
		self.assertEqual(runtime._invoke(call)["status"], "ok")
		self.assertEqual(len(runtime.invocations), 1)

	def test_rejects_oversized_mutation_payload(self):
		runtime = FakeRuntime()
		state = apply_batch_execution_guard(runtime)
		call = SimpleNamespace(
			name="create",
			arguments={
				"doctype": "ToDo",
				"records": [{"description": "x" * (MAX_MUTATION_ARGUMENT_BYTES + 1)}],
			},
		)

		result = runtime._invoke(call)
		self.assertEqual(result["status"], "payload_limit")
		self.assertEqual(runtime.invocations, [])
		self.assertTrue(state.force_summary)

	def test_time_budget_stops_more_discovery_without_blocking_first_write(self):
		now = [0.0]
		runtime = FakeRuntime()
		state = apply_batch_execution_guard(runtime, clock=lambda: now[0])
		now[0] = MAX_TOOL_PHASE_SECONDS + 1

		read_result = runtime._invoke(SimpleNamespace(name="read", arguments={"doctype": "Item"}))
		self.assertEqual(read_result["status"], "time_budget")
		self.assertTrue(state.force_summary)

	def test_continuation_prompt_keeps_only_last_verified_summary(self):
		messages = [
			{"role": "system", "content": "policy"},
			{"role": "user", "content": "create records"},
			{"role": "assistant", "tool_calls": [{"id": "1"}]},
			{"role": "tool", "content": "x" * 50_000},
			{"role": "assistant", "content": "Created 30 records; 70 remain."},
			{"role": "user", "content": "继续"},
		]

		compacted = compact_continuation_messages(messages)
		self.assertEqual([row["role"] for row in compacted], ["system", "user", "assistant", "user"])
		self.assertNotIn("x" * 100, str(compacted))
		self.assertIn("Created 30 records", compacted[2]["content"])
		self.assertIn("one real mutating tool call", compacted[-1]["content"])

	def test_prepare_continuation_prompt_leaves_other_inputs_unchanged(self):
		session = SimpleNamespace(_build_prompt_messages=lambda: [{"role": "user", "content": "hello"}])
		self.assertFalse(prepare_continuation_prompt(session, "检查数据"))
		self.assertTrue(prepare_continuation_prompt(session, "继续"))
		self.assertIn("one real mutating tool call", session._build_prompt_messages()[-1]["content"])
