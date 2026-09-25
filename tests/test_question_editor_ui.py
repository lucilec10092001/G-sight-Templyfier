import unittest

from question_editor import _apply_selected_metrics
from .test_client_memory import row


class QuestionEditorUiTests(unittest.TestCase):
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
