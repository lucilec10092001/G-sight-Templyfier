import unittest

from question_editor import _exact_metric_selection, _metric_text, _parse_metric_text


class QuestionEditorUiTests(unittest.TestCase):
    def test_metric_text_round_trip_uses_user_friendly_semicolons(self):
        metrics = ["Mean", "Top Box", "Bottom 2 Boxes"]
        self.assertEqual(_parse_metric_text(_metric_text(metrics)), metrics)

    def test_direct_metric_edit_keeps_source_spelling(self):
        available = ["Moyenne", "Top Box", "Top 2 Boxes"]
        self.assertEqual(
            _exact_metric_selection("Moyenne; Top 2 Boxes", available),
            ["Moyenne", "Top 2 Boxes"],
        )

    def test_direct_metric_edit_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            _exact_metric_selection("Mean; Invented metric", ["Mean", "Top Box"])


if __name__ == "__main__":
    unittest.main()
