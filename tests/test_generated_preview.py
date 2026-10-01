from io import BytesIO
import unittest

from openpyxl import Workbook

from smart_ui import _generated_workbook_preview


class GeneratedPreviewTests(unittest.TestCase):
    def test_preview_reads_actual_sheets_values_and_formulas_with_limits(self):
        workbook = Workbook()
        topline = workbook.active
        topline.title = "TOTAL"
        topline["A1"] = "Question"
        topline["B1"] = "Score"
        topline["A2"] = "Overall liking"
        topline["B2"] = 6.4
        topline["C2"] = "=B2-5"
        workbook.create_sheet("Screeners")["A1"] = "Gender"
        payload = BytesIO()
        workbook.save(payload)

        names, previews, dimensions = _generated_workbook_preview(
            payload.getvalue(), max_rows=2, max_columns=2
        )

        self.assertEqual(names, ("TOTAL", "Screeners"))
        self.assertEqual(dimensions["TOTAL"], (2, 3))
        self.assertEqual(previews["TOTAL"].iloc[1]["A"], "Overall liking")
        self.assertEqual(previews["TOTAL"].iloc[1]["B"], 6.4)
        self.assertNotIn("C", previews["TOTAL"].columns)


if __name__ == "__main__":
    unittest.main()
