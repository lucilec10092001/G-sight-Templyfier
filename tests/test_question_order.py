import unittest

from question_order import ORDER_JS


class QuestionOrderComponentTests(unittest.TestCase):
    def test_moves_stay_local_until_save_order(self):
        move_body = ORDER_JS.split('function move(ids, target, after=false)', 1)[1].split('function nudge', 1)[0]
        self.assertNotIn('emit();', move_body)
        self.assertIn("button('Save order',()=>emit())", ORDER_JS)
        self.assertIn('dirty=true;draw();', move_body)

    def test_multi_selection_and_local_reset_remain_available(self):
        self.assertIn("button('Select all'", ORDER_JS)
        self.assertIn('if(e.shiftKey && anchor!==null)', ORDER_JS)
        self.assertIn("button('Discard moves'", ORDER_JS)
        self.assertIn('dragIds=rows.filter(r=>selected.has(r.id))', ORDER_JS)
