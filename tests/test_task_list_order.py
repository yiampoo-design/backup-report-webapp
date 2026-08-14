from __future__ import annotations

import unittest

from csv_report import ACTIVE_BACKUP_TASK_LIST_ORDER, order_rows_like_task_list


class TaskListOrderTests(unittest.TestCase):
    def test_csv_rows_follow_dsm_task_list_and_are_renumbered(self):
        rows = [
            {"No.": "1", "Backup Task": "ERP-WEB_Backup_APCHE_PHP_WebApp_0000", "Size": "A"},
            {"No.": "2", "Backup Task": "EXPRESS_Backup_Full_0000", "Size": "B"},
            {"No.": "3", "Backup Task": "STOCK_Backup_APP_SQLBak_0000", "Size": "C"},
            {"No.": "4", "Backup Task": "ERP-DB_Backup_SQLBak_0000", "Size": "D"},
        ]
        ordered = order_rows_like_task_list(rows)
        self.assertEqual(
            [row["Backup Task"] for row in ordered],
            ACTIVE_BACKUP_TASK_LIST_ORDER[:4],
        )
        self.assertEqual([row["No."] for row in ordered], ["1", "2", "3", "4"])
        self.assertEqual([row["Size"] for row in ordered], ["C", "B", "A", "D"])
        self.assertEqual([row["_csv_no"] for row in ordered], ["3", "2", "1", "4"])

    def test_unknown_tasks_are_appended_in_original_csv_order(self):
        rows = [
            {"No.": "1", "Backup Task": "NEW_TASK_B"},
            {"No.": "2", "Backup Task": "EXPRESS_Backup_Full_0000"},
            {"No.": "3", "Backup Task": "NEW_TASK_A"},
        ]
        ordered = order_rows_like_task_list(rows)
        self.assertEqual(
            [row["Backup Task"] for row in ordered],
            ["EXPRESS_Backup_Full_0000", "NEW_TASK_B", "NEW_TASK_A"],
        )


if __name__ == "__main__":
    unittest.main()
