"""The absent side of a normal ineffective area must stay blank in native geometry."""
import unittest

from ras_workflow.native import fixed
from ras_workflow.section_hydraulics import cards


class IneffectiveCards(unittest.TestCase):
    def test_one_sided_and_two_sided_limits(self):
        left = {'ineffective_left': [10., 37.]}
        right = {'ineffective_right': [50., 38.]}
        for section, expected in [
            (left, [0., 10., 37., None, 0., None]),
            (right, [0., None, None, 50., 0., 38.]),
            ({**left, **right}, [0., 10., 37., 50., 0., 38.]),
        ]:
            with self.subTest(section=section):
                line = cards(section, fixed).splitlines()[1]
                self.assertEqual(len(line), 48)
                fields = [line[i:i+8].strip() for i in range(0, 48, 8)]
                self.assertEqual([float(v) if v else None for v in fields], expected)
        self.assertEqual(cards({}, fixed), '')
