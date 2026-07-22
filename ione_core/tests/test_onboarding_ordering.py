import unittest

from ione_core.onboarding_ordering import normalize_step_order


def step(name, sequence, idx):
	return {"name": name, "step_code": name, "sequence": sequence, "idx": idx}


class TestOnboardingOrdering(unittest.TestCase):
	def test_new_step_is_inserted_at_requested_position(self):
		previous = [step("welcome", 1, 1), step("industry", 2, 2), step("profile", 3, 3)]
		current = [step("welcome", 1, 1), step("industry", 2, 2), step("profile", 3, 3), step("type", 2, 4)]

		ordered = normalize_step_order(current, previous)

		self.assertEqual([row["step_code"] for row in ordered], ["welcome", "type", "industry", "profile"])
		self.assertEqual([row["sequence"] for row in ordered], [1, 2, 3, 4])

	def test_existing_step_can_move_to_any_position(self):
		previous = [step("welcome", 1, 1), step("industry", 2, 2), step("profile", 3, 3)]
		current = [step("welcome", 1, 1), step("industry", 2, 2), step("profile", 1, 3)]

		ordered = normalize_step_order(current, previous)

		self.assertEqual([row["step_code"] for row in ordered], ["profile", "welcome", "industry"])
		self.assertEqual([row["idx"] for row in ordered], [1, 2, 3])

	def test_gaps_are_removed_after_deletion(self):
		previous = [step("welcome", 1, 1), step("industry", 2, 2), step("profile", 3, 3)]
		current = [step("welcome", 1, 1), step("profile", 3, 2)]

		ordered = normalize_step_order(current, previous)

		self.assertEqual([row["step_code"] for row in ordered], ["welcome", "profile"])
		self.assertEqual([row["sequence"] for row in ordered], [1, 2])
