from io import BytesIO
import unittest

from openpyxl import Workbook

from templyfier.smart import (
    _embedded_data_sheets,
    cmr_benchmark_positions,
    match_cmr_products,
)


class CmrMatchingTests(unittest.TestCase):
    def test_composite_gsight_headers_use_explicit_cmr_benchmark_type(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append([
            "CMR code", "Formula code", "Fantasy name", "Formula description",
            "Formula type", "Fr-Land ID",
        ])
        sheet.append(["A26", "", "Benchmark A", "", "Benchmark", 356897])
        sheet.append(["B35", "", "Benchmark B", "", "benchmark", "355433.0"])
        sheet.append(["C91", "UAH132BUA", "Candidate C", "", "Candidate", ""])
        payload = BytesIO()
        workbook.save(payload)

        matches = match_cmr_products(
            ("A26356897", "B35355433", "C9108UAH132BUA"),
            ("A26 356897", "B35 355433", "C91 0.8% UAH132BUA"),
            payload.getvalue(),
        )

        self.assertEqual([item.score for item in matches], [99, 99, 99])
        self.assertEqual(cmr_benchmark_positions(matches), (0, 1))

    def test_stage_named_two_tailed_sheet_excludes_companion_views(self):
        workbook = Workbook()
        two_tailed = workbook.active
        two_tailed.title = "NEAT 2_TAILED"
        one_tailed = workbook.create_sheet("NEAT 1_TAILED")
        delta = workbook.create_sheet("NEAT DELTA")
        for sheet in (two_tailed, one_tailed, delta):
            sheet["A5"], sheet["B5"] = "Variable", "Metric"
            sheet["C3"], sheet["C4"], sheet["C5"] = "Product A", "100 - A", "A"
            sheet["E3"], sheet["E4"], sheet["E5"] = "Product B", "100 - B", "B"
            for row, metric in enumerate(("Mean", "Top Box", "Top 2 Boxes"), 6):
                sheet.cell(row, 1, "Q1")
                sheet.cell(row, 2, metric)
                sheet.cell(row, 3, 5.0)
                sheet.cell(row, 5, 5.5)

        self.assertEqual(
            [sheet.title for sheet in _embedded_data_sheets(workbook)],
            ["NEAT 2_TAILED"],
        )


if __name__ == "__main__":
    unittest.main()
