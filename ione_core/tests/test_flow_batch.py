from types import SimpleNamespace
from unittest import TestCase

from ione_core.flow_batch import (
	BATCH_POLICY_MARKER,
	MAX_ITERATIONS,
	MAX_MUTATING_CALLS,
	MAX_RECORDS_PER_BATCH,
	apply_batch_execution_guard,
	append_batch_policy,
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
					"records": [{"description": str(index)} for index in range(MAX_RECORDS_PER_BATCH)],
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

	def test_repeated_call_is_skipped_and_forces_summary(self):
		runtime = FakeRuntime()
		state = apply_batch_execution_guard(runtime)
		call = SimpleNamespace(name="read", arguments={"doctype": "Company"})

		self.assertEqual(runtime._invoke(call)["status"], "ok")
		self.assertEqual(runtime._invoke(call)["status"], "skipped_duplicate")
		self.assertEqual(len(runtime.invocations), 1)
		self.assertTrue(state.force_summary)

	def test_rejects_more_than_ten_records_without_writing(self):
		runtime = FakeRuntime()
		state = apply_batch_execution_guard(runtime)
		call = SimpleNamespace(
			name="update",
			arguments={"doctype": "Customer", "names": [str(i) for i in range(11)]},
		)

		result = runtime._invoke(call)
		self.assertEqual(result["status"], "record_limit")
		self.assertEqual(runtime.invocations, [])
		self.assertTrue(state.force_summary)
