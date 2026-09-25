import unittest

from question_editor import _apply_selected_metrics, _apply_table_metric_edit
from .test_client_memory import row


class QuestionEditorUiTests(unittest.TestCase):
    def test_direct_table_metric_edit_updates_one_question(self):
        target = row(metrics=["Mean", "Top Box", "Top 2 Boxes"], selected=["Mean"])
        _apply_table_metric_edit(target, "Standard", ["Mean", "Top 2 Boxes"], {})
        self.assertEqual(target["Selected metrics"], ["Mean", "Top 2 Boxes"])

    def test_type_change_uses_existing_type_recipe(self):
        target = row(
            "Q-standard", kind="Standard", metrics=["1-A", "2-B", "3-C"], selected=[]
        )
        listing = row(
            "Q-listing", kind="Listing", metrics=["1-A", "2-B", "3-C"],
            selected=["1-A", "3-C"],
        )
        _apply_table_metric_edit(
            target, "Listing", target["Selected metrics"], {"Listing": listing}
        )
        self.assertEqual(target["Type"], "Listing")
        self.assertEqual(target["Selected metrics"], ["1-A", "3-C"])

    def test_single_selected_question_updates_metrics_and_excel_names(self):
        rows = [row(metrics=["Mean", "Top Box"], selected=["Mean"])]
        changed, skipped = _apply_selected_metrics(
            rows, [rows[0]["Question ID"]], ["Top Box"], {"Top Box": "TB"}
        )
        self.assertEqual(skipped, [])
        self.assertEqual(changed[0]["Selected metrics"], ["Top Box"])
        self.assertEqual(changed[0]["Metric labels"], {"Top Box": "TB"})

    def test_selected_cata_rows_match_the_equivalent_response_code(self):
        rows = [
            row("Q-1-Floral", kind="CATA", metrics=["1-No", "2-Floral"], selected=["1-No"]),
            row("Q-2-Fruity", kind="CATA", metrics=["1-No", "2-Fruity"], selected=["1-No"]),
        ]
        changed, skipped = _apply_selected_metrics(
            rows, [item["Question ID"] for item in rows], ["2-Floral"]
        )
        self.assertEqual(skipped, [])
        self.assertEqual(changed[0]["Selected metrics"], ["2-Floral"])
        self.assertEqual(changed[1]["Selected metrics"], ["2-Fruity"])

    def test_unsafe_multi_question_match_leaves_target_recipe_unchanged(self):
        rows = [
            row("Q-1", metrics=["Mean", "Top 3 Boxes"], selected=["Mean"]),
            row("Q-2", metrics=["Mean", "Top Box"], selected=["Top Box"]),
        ]
        changed, skipped = _apply_selected_metrics(
            rows, [item["Question ID"] for item in rows], ["Top 3 Boxes"]
        )
        self.assertEqual(skipped, ["Q-2"])
        self.assertEqual(changed[1]["Selected metrics"], ["Top Box"])


if __name__ == "__main__":
    unittest.main()
