import unittest

from ione_core.onboarding_defaults import get_default_onboarding_flow_data


class TestOnboardingDefaults(unittest.TestCase):
	def setUp(self):
		self.flow = get_default_onboarding_flow_data()

	def test_step_and_option_codes_are_unique(self):
		step_codes = [row["step_code"] for row in self.flow["steps"]]
		option_keys = [(row["step_code"], row["option_code"]) for row in self.flow["options"]]
		self.assertEqual(len(step_codes), len(set(step_codes)))
		self.assertEqual(len(option_keys), len(set(option_keys)))

	def test_every_option_references_a_step(self):
		step_codes = {row["step_code"] for row in self.flow["steps"]}
		self.assertTrue(all(row["step_code"] in step_codes for row in self.flow["options"]))

	def test_required_question_steps_have_options(self):
		steps_with_options = {row["step_code"] for row in self.flow["options"]}
		for step in self.flow["steps"]:
			if step.get("required"):
				self.assertIn(step["step_code"], steps_with_options)
