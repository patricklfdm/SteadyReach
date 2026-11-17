import unittest
from ras_workflow.spacing_coverage import classify, assess_coverage


class SpacingCoverageTests(unittest.TestCase):
    def test_profiles_count_once_per_section_and_keep_both_observations(self):
        rows = [dict(rs='300.00',profile='Q100',left_excess_ft=1.,right_excess_ft=0.),
                dict(rs='300',profile='Q200',left_excess_ft=2.,right_excess_ft=1.),
                dict(rs='250',profile='Q200',left_excess_ft=0.,right_excess_ft=.4),
                dict(rs='100',profile='Q100',left_excess_ft=0.,right_excess_ft=0.)]
        actual = classify(rows, [400,300,200,100])
        self.assertEqual(actual['wet_sections'], ['300.0','250.0'])
        self.assertEqual(actual['retained_wet_sections'], ['300.0'])
        self.assertEqual(actual['added_wet_sections'], ['250.0'])
        self.assertEqual(len(actual['wet_section_profiles']), 3)
        self.assertEqual(actual['wet_section_profiles'][1]['profile'], 'Q200')

    def test_wet_results_stay_provisional_independent_of_numeric_threshold(self):
        dry = dict(id='baseline',status='COMPUTED',**classify([], [400,100]))
        wet = dict(id='refinement',status='COMPUTED',**classify(
            [dict(rs=250,profile='Q100',left_excess_ft=.01,right_excess_ft=0)], [400,100]))
        actual = assess_coverage([dry,wet])
        self.assertEqual(actual['status'], 'PROVISIONAL_WET_SECTION_ENDS')
        self.assertEqual(actual['next_action'], 'REVISE_COVERAGE_THEN_REPEAT_SPACING')
        self.assertEqual(actual['affected_cases'][0]['added_wet_sections'], ['250.0'])

    def test_dry_or_incomplete_does_not_clear_engineering_review(self):
        dry = dict(id='baseline',status='COMPUTED',**classify([], []))
        actual = assess_coverage([dry])
        self.assertEqual(actual['status'], 'ENDS_ABOVE_COMPUTED_WATER')
        self.assertEqual(actual['engineering_acceptance'], 'NOT_ASSESSED')
        incomplete = assess_coverage([dry,dict(id='refinement',status='FAILED')])
        self.assertEqual(incomplete['status'], 'INCOMPLETE')
        self.assertEqual(incomplete['next_action'], 'COMPLETE_BATCH')


if __name__ == '__main__': unittest.main()
