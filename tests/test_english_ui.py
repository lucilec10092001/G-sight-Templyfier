import unittest
from pathlib import Path
import pandas as pd
from english_ui import _table, choice


class EnglishUiTests(unittest.TestCase):
    def test_table_display_translation_preserves_all_unedited_internal_fields(self):
        source=pd.DataFrame([{'Type':'Autres','Grouping choice':'Propos�','Display label':'Autres',
            'Metric':'Aucune','Question ID':'Q-1-Couleur','Why':'Aucune'}])
        captured=[]
        def editor(frame,**kwargs):captured.append(frame.copy());return frame.copy()
        restored=_table(editor,[source],{})
        pd.testing.assert_frame_equal(restored,source)
        self.assertEqual(captured[0]['Type'][0],'Project-specific')
        self.assertEqual(captured[0]['Display label'][0],'Autres')
        self.assertEqual(captured[0]['Metric'][0],'Aucune')
        self.assertEqual(captured[0]['Question ID'][0],'Q-1-Couleur')

    def test_english_type_edit_returns_compatible_legacy_enum(self):
        source=pd.DataFrame([{'Type':'Autres','Display label':'Original'}])
        def editor(frame,**kwargs):
            frame=frame.copy();frame.loc[0,'Type']='Bipolar';frame.loc[0,'Display label']='Custom colour';return frame
        result=_table(editor,[source],{})
        self.assertEqual(result['Type'][0],'Bipolaire')
        self.assertEqual(result['Display label'][0],'Custom colour')

    def test_question_type_display_names_are_english(self):
        from english_ui import text
        self.assertEqual(text('Candidate scores � own significance � optional gaps'),'Candidate scores � own significance � optional gaps')
        self.assertEqual(choice('Autres'),'Project-specific')
        self.assertEqual(choice('Bipolaire'),'Bipolar')
        self.assertEqual(choice('Listing'),'Listing')
        self.assertEqual(choice('Preference'),'Preference')

    def test_main_journey_does_not_reintroduce_the_rejected_preview(self):
        source = (Path(__file__).resolve().parents[1] / 'smart_ui.py').read_text(encoding='utf-8')
        self.assertNotIn('Preview the final Excel', source)
        self.assertNotIn('Worksheet to preview', source)

    def test_advanced_product_and_file_checks_are_in_english(self):
        source = (Path(__file__).resolve().parents[1] / 'smart_ui.py').read_text(encoding='utf-8')
        for legacy_label in (
            'Contr�le des fichiers et des comparaisons',
            'Quel nom veux-tu afficher dans les toplines ?',
            'T�l�charger mes toplines',
        ):
            self.assertNotIn(legacy_label, source)

