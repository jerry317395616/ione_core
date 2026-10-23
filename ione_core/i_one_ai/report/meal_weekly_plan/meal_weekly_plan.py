from ione_core import meal_planning


def execute(filters=None):
	return meal_planning.weekly_report_data(filters)
