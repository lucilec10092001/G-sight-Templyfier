from types import SimpleNamespace
import unittest

from smart_ui import _cmr_benchmark_keys, _cmr_product_reference


class CmrProductReferenceTests(unittest.TestCase):
    @staticmethod
    def item(filename, role, keys):
        return SimpleNamespace(
            filename=filename,
            role=role,
            product_keys=tuple(keys),
        )

    def test_reduced_first_split_does_not_pair_its_codes_with_full_plan_names(self):
        reduced = self.item("reduced.xlsx", "Résultats", ("B1", "C1"))
        full = self.item(
            "full.xlsx", "Comparaison benchmark",
            ("B1", "C1", "B2", "C2"),
        )
        info = SimpleNamespace(
            inputs=(reduced, full),
            reference_filename="full.xlsx",
            product_names=("Bench 1", "Candidate 1", "Bench 2", "Candidate 2"),
        )

        reference = _cmr_product_reference(info)

        self.assertIs(reference, full)
        self.assertEqual(len(reference.product_keys), len(info.product_names))

    def test_reference_filename_wins_when_several_plans_have_the_same_size(self):
        first = self.item("first.xlsx", "Résultats", ("A", "B"))
        reference_item = self.item("reference.xlsx", "Résultats", ("C", "D"))
        info = SimpleNamespace(
            inputs=(first, reference_item),
            reference_filename="reference.xlsx",
            product_names=("Product C", "Product D"),
        )

        self.assertIs(_cmr_product_reference(info), reference_item)


    def test_benchmark_positions_use_the_full_reference_plan(self):
        reduced = self.item("reduced.xlsx", "Résultats", ("B1", "C1"))
        full = self.item(
            "full.xlsx", "Comparaison benchmark",
            ("B1", "C1", "B2", "C2"),
        )
        info = SimpleNamespace(
            inputs=(reduced, full),
            reference_filename="full.xlsx",
            product_names=("Bench 1", "Candidate 1", "Bench 2", "Candidate 2"),
        )
        matches = (
            SimpleNamespace(formula_type="benchmark", score=100),
            SimpleNamespace(formula_type="candidate", score=100),
            SimpleNamespace(formula_type="benchmark", score=100),
            SimpleNamespace(formula_type="candidate", score=100),
        )

        self.assertEqual(_cmr_benchmark_keys(info, matches), ("B1", "B2"))


if __name__ == "__main__":
    unittest.main()
