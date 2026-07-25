import unittest
from types import SimpleNamespace

from ione_core.flow_policy import (
	MODE_ALL,
	MODE_CONFIRM,
	MODE_SELECTED,
	ExecutionDecision,
	apply_runtime_policy,
)


class TestFlowExecutionPolicy(unittest.TestCase):
	def _session(self):
		return SimpleNamespace(
			_runtime=SimpleNamespace(
				tools=[
					SimpleNamespace(name="create", requires_confirmation=True),
					SimpleNamespace(name="delete", requires_confirmation=True),
				]
			)
		)

	def test_selected_tools_only_remove_their_confirmation(self):
		session = self._session()
		decision = ExecutionDecision(
			policy="POLICY-1",
			mode=MODE_SELECTED,
			auto_tools=frozenset({"create"}),
		)

		self.assertFalse(apply_runtime_policy(session, decision))
		self.assertFalse(session._runtime.tools[0].requires_confirmation)
		self.assertTrue(session._runtime.tools[1].requires_confirmation)

	def test_all_mode_uses_flow_auto_approve(self):
		session = self._session()
		decision = ExecutionDecision(policy="POLICY-1", mode=MODE_ALL)

		self.assertTrue(apply_runtime_policy(session, decision))
		self.assertTrue(session._runtime.tools[0].requires_confirmation)

	def test_confirm_mode_keeps_flow_defaults(self):
		session = self._session()
		decision = ExecutionDecision(policy="POLICY-1", mode=MODE_CONFIRM)

		self.assertFalse(apply_runtime_policy(session, decision))
		self.assertTrue(session._runtime.tools[0].requires_confirmation)
