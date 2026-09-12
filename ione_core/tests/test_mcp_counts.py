import inspect
from unittest import TestCase
from unittest.mock import patch

import frappe
from ione_core.mcp import tools


class TestMCPCounts(TestCase):
    def test_count_restores_request_on_failure(self):
        previous = frappe.local.form_dict
        with patch('frappe.desk.reportview.get_count', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                tools._permission_aware_count('Student', {})
        self.assertIs(frappe.local.form_dict, previous)

    def test_page_count_is_not_total(self):
        with patch.object(tools, 'ensure_doctype_permission'), patch.object(tools, 'permitted_fields'), patch.object(tools, 'safe_filters', return_value={}), patch.object(tools, 'safe_fields', return_value=['name']), patch.object(tools, 'validate_order_by', return_value='name asc'), patch.object(tools, '_permission_aware_count', return_value=257), patch.object(frappe, 'get_list', return_value=[{'name': str(i)} for i in range(21)]):
            result = inspect.unwrap(tools.frappe_list_documents)('Student')
        self.assertEqual(result['count'], 20)
        self.assertEqual(result['page_count'], 20)
        self.assertEqual(result['total_count'], 257)
        self.assertTrue(result['has_more'])
        self.assertEqual(result['next_start'], 20)

    def test_denied_doctype_cannot_count(self):
        with patch.object(tools, 'ensure_doctype_permission', side_effect=frappe.PermissionError), patch.object(tools, '_permission_aware_count') as count:
            with self.assertRaises(frappe.PermissionError):
                inspect.unwrap(tools.frappe_count_documents)('Student')
            count.assert_not_called()

    def test_filters_passed_to_count(self):
        with patch.object(tools, 'ensure_doctype_permission'), patch.object(tools, 'permitted_fields'), patch.object(tools, 'safe_filters', return_value={'enabled': 1}), patch.object(tools, '_permission_aware_count', return_value=257) as count:
            result = inspect.unwrap(tools.frappe_count_documents)('Student', {'enabled': 1})
        count.assert_called_once_with('Student', {'enabled': 1})
        self.assertEqual(result['total_count'], 257)
        self.assertEqual(result['permission_scope'], 'current_user')
