import unittest

from templyfier.smart import _suggest_question_splits


class SplitSuggestionSafetyTests(unittest.TestCase):
    def test_business_kpi_word_does_not_become_a_split_filter(self):
        self.assertEqual(
            _suggest_question_splits(
                "Q-09-Yellow fit",
                "Yellow fit",
                ("TOTAL", "COMFORT", "LENOR", "18-40 YO", "41+ YO", "YELLOW"),
            ),
            (),
        )

    def test_usual_yellow_fabric_conditioner_wording_stays_in_all_splits(self):
        self.assertEqual(
            _suggest_question_splits(
                "Q-10",
                "It smells better than my usual yellow fabric conditioner",
                ("TOTAL", "COMFORT", "LENOR", "YELLOW"),
            ),
            (),
        )

    def test_explicit_comparison_wording_can_target_a_split(self):
        self.assertEqual(
            _suggest_question_splits(
                "Q-25-F-Comparison smell with Yumos Orkide",
                "Comparison smell with Yumos Orkide",
                ("TOTAL", "YUMOS ORKIDE MO", "YUMOS MO"),
            ),
            ("YUMOS ORKIDE MO",),
        )

    def test_french_audience_wording_can_target_a_split(self):
        self.assertEqual(
            _suggest_question_splits(
                "Q-12",
                "Preference parmi les utilisateurs de Lenor",
                ("TOTAL", "LENOR"),
            ),
            ("LENOR",),
        )


if __name__ == "__main__":
    unittest.main()
