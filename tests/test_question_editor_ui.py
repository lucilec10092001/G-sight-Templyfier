import unittest

import pandas as pd

from question_editor import (
    _apply_group_wide_table_edits, _apply_selected_metrics, _apply_table_metric_edit,
    _selected_cell_changes,
)
from .test_client_memory import row
from smart_ui import _question_output_signature


class QuestionEditorUiTests(unittest.TestCase):
    def test_edit_together_detects_one_stage_edit_on_selected_rows(self):
        original = [
            {"Edit together": False, "G-Sight question": "Q-1", "Stage": "Wet", "Status": "Ready"},
            {"Edit together": False, "G-Sight question": "Q-2", "Stage": "Wet", "Status": "Ready"},
        ]
        edited = [dict(original[0], **{"Edit together": True, "Stage": "Dry"}),
                  dict(original[1], **{"Edit together": True})]
        self.assertEqual(
            _selected_cell_changes(original, edited, ["Q-1", "Q-2"]),
            {"Stage": [("Q-1", "Dry")]},
        )

    def test_edit_outside_selected_rows_is_not_shared(self):
        original = [
            {"Edit together": False, "G-Sight question": "Q-1", "Stage": "Wet", "Status": "Ready"},
            {"Edit together": False, "G-Sight question": "Q-2", "Stage": "Wet", "Status": "Ready"},
        ]
        edited = [dict(original[0], **{"Edit together": True}),
                  dict(original[1], **{"Stage": "Dry"})]
        self.assertEqual(_selected_cell_changes(original, edited, ["Q-1"]), {})

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

    def test_renaming_one_group_cell_keeps_all_group_members_together(self):
        rows = [
            dict(row("Q-1"), **{"Group ID": "old", "Display label": "Fragrance characteristics",
                                "Metric label": "Floral", "Section": "PRODUCT BENEFITS"}),
            dict(row("Q-2"), **{"Group ID": "old", "Display label": "Fragrance characteristics",
                                "Metric label": "Fresh", "Section": "PRODUCT BENEFITS"}),
        ]
        original = [
            {"G-Sight question": "Q-1", "Group": "Fragrance characteristics",
             "Section": "PRODUCT BENEFITS"},
            {"G-Sight question": "Q-2", "Group": "Fragrance characteristics",
             "Section": "PRODUCT BENEFITS"},
        ]
        edited = [dict(original[0], Group="Fragrance attributes", Section="FRAGRANCE"), original[1]]
        changed = [dict(item) for item in rows]
        # The directly edited row has already been updated by the table loop.
        changed[0].update({"Display label": "Fragrance attributes", "Section": "FRAGRANCE",
                           "Group ID": "new"})
        _apply_group_wide_table_edits(changed, rows, original, edited)
        self.assertEqual({item["Display label"] for item in changed}, {"Fragrance attributes"})
        self.assertEqual({item["Section"] for item in changed}, {"FRAGRANCE"})
        self.assertEqual(len({item["Group ID"] for item in changed}), 1)

    def test_download_signature_changes_for_order_labels_and_sections(self):
        base = pd.DataFrame([
            {"Question ID": "Q-1", "Order": 1, "Display label": "Old", "Section": "OLD"},
            {"Question ID": "Q-2", "Order": 2, "Display label": "Second", "Section": "OLD"},
        ])
        signatures = {_question_output_signature(base)}
        reordered = base.iloc[::-1].copy()
        reordered["Order"] = [1, 2]
        signatures.add(_question_output_signature(reordered))
        renamed = base.copy()
        renamed.loc[0, "Display label"] = "New"
        signatures.add(_question_output_signature(renamed))
        moved = base.copy()
        moved.loc[0, "Section"] = "NEW"
        signatures.add(_question_output_signature(moved))
        self.assertEqual(len(signatures), 4)


if __name__ == "__main__":
    unittest.main()

