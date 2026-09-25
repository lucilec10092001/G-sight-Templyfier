from io import BytesIO
import unittest

from openpyxl import Workbook, load_workbook

from templyfier.smart import (
    audit_input_plan,
    build_smart_toplines,
    inspect_smart_package,
    proposal_to_row,
)


class ConsolidatedPairedTests(unittest.TestCase):
    @staticmethod
    def source_bytes():
        workbook = Workbook()
        total = workbook.active
        total.title = "TOTAL"
        total["A5"], total["B5"] = "Variable", "Metric"
        products = [
            (3, "Benchmark 1", "50 - B1", "A"),
            (4, "Candidate 1", "50 - C1", "B"),
            (5, "Benchmark 2", "50 - B2", "C"),
            (6, "Candidate 2", "50 - C2", "D"),
        ]
        for col, name, sample, letter in products:
            total.cell(3, col).value = name
            total.cell(4, col).value = sample
            total.cell(5, col).value = letter
        for row, metric, values in (
            (8, "Mean", [5.0, 5.5, 4.8, 5.1]),
            (9, "Top Box", [0.2, 0.3, 0.1, 0.2]),
            (10, "Top 2 Boxes", [0.5, 0.7, 0.4, 0.6]),
            (11, "Bottom 2 Boxes", [0.1, 0.0, 0.2, 0.1]),
        ):
            total.cell(row, 1).value = "Q-1-Overall liking"
            total.cell(row, 2).value = metric
            for offset, value in enumerate(values, 3):
                total.cell(row, offset).value = value
        boost = workbook.copy_worksheet(total)
        boost.title = "BOOST"
        boost["E4"] = "0 - B2"
        boost["F4"] = "0 - C2"
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def test_one_workbook_expands_sheets_and_accepts_variable_pair_counts(self):
        raw = self.source_bytes()
        info = inspect_smart_package([("ALL SPLITS.xlsx", raw)])
        self.assertEqual(info.study_format, "HUT / in-use")
        self.assertTrue(info.suggested_test_type.startswith("Paired"))
        self.assertEqual([item.split_name for item in info.inputs], ["TOTAL", "BOOST"])
        self.assertEqual([len(item.product_keys) for item in info.inputs], [4, 2])
        audit = audit_input_plan(
            info, ["TOTAL", "BOOST"], (), test_type="Paired", automatic_exports=False
        )
        self.assertTrue(audit["ready"], audit["blockers"])

        rows = [proposal_to_row(item) for item in info.questions]
        data, report = build_smart_toplines(
            [("ALL SPLITS.xlsx", raw)], rows,
            split_names=["TOTAL", "BOOST"], benchmark_positions=(),
            standard_metrics=("Mean", "Top Box", "Top 2 Boxes", "Bottom 2 Boxes"),
            include_screeners=False, test_type="Paired",
        )
        output = load_workbook(BytesIO(data), data_only=False)
        self.assertEqual(output.sheetnames, ["TOTAL", "BOOST"])
        self.assertEqual(report["pairs_by_split"], {"TOTAL": 2, "BOOST": 1})
        self.assertEqual(output["TOTAL"]["E7"].value, "=D7-C7")
        self.assertEqual(output["BOOST"]["E7"].value, "=D7-C7")


if __name__ == "__main__":
    unittest.main()
