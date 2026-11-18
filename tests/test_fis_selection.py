"""FIS alternatives and conflicts in actual parameter rows."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from ras_workflow import app_acquisition, source_tables


class SelectionTests(TestCase):
    def setUp(self):
        rows = [
            dict(kind='discharge', stream='Main River', location='Upper', aep_percent=1,
                 column_label='1% Annual Chance', layout_line=4, flow_cfs=110),
            dict(kind='discharge', stream='Main River', location='Lower', aep_percent=1,
                 column_label='1% Annual Chance', layout_line=5, flow_cfs=140),
        ]
        roughness = [dict(kind='roughness', stream=name, channel_range=interval,
                          overbank_range=interval, layout_line=4)
                     for name, interval in [('Main River', [.04, .06]), ('Tributary', [.07, .09])]]
        self.choices = source_tables.candidates([
            dict(rows=rows, pdf_page=30, table_number=9, title='Summary of Discharges'),
            dict(rows=roughness, pdf_page=38, table_number=13, title='Roughness Coefficients')])
        for i, candidate in enumerate(self.choices):
            candidate.update(source=dict(sha256='verified-fis'), candidate=str(i), auto_eligible=False)

    def field(self, candidate):
        answer = {key:candidate[key] for key in ('value', 'basis', 'evidence_class')}
        return dict(key=candidate['field'], value=candidate['value'], missing=False,
                    answer=dict(answer, candidate_record=deepcopy(candidate)), parameter_candidates=[])

    def enrich(self, fields, choices=None):
        with patch.object(app_acquisition, 'snapshot', return_value=dict(candidates=self.choices if choices is None else choices)):
            return app_acquisition.enrich({}, fields)

    def test_adopted_flow_and_midpoint_keep_other_locations_searchable(self):
        fields = self.enrich([self.field(self.choices[i]) for i in (0, 2, 3)])
        for field in fields:
            self.assertFalse(field['source_conflict'])
            self.assertFalse(field['acquisition']['manual_decision_required'])
            self.assertEqual(field['acquisition']['status'], 'FIS_ROW_SELECTED')
            self.assertEqual(len(field['parameter_candidates']), 2)
        self.assertEqual(fields[1]['answer']['evidence_class'], 'assumed')

    def test_same_location_different_flow_or_independent_unlabelled_value_remains_open(self):
        prior = self.choices[0]
        for extra in [dict(prior, value=120), dict(self.choices[1], source=dict(sha256='another')),
                      dict(prior, value=125, source_locus={})]:
            field, = self.enrich([self.field(prior)], self.choices+[extra])
            self.assertEqual(field['acquisition']['status'], 'CONFLICT')
            self.assertTrue(field['source_conflict'])

    def test_spelling_case_and_spacing_do_not_hide_same_location_conflict(self):
        prior = self.choices[0]
        extra = deepcopy(prior)
        extra['value'] = 120
        for key in ('hydrologic_context', 'source_locus'):
            extra[key].update(stream='MAIN   RIVER', location='  UPPER ')
        field, = self.enrich([self.field(prior)], self.choices+[extra])
        self.assertEqual(field['acquisition']['status'], 'CONFLICT')

    def test_equal_midpoint_different_range_still_requires_review(self):
        prior = self.choices[2]
        field, = self.enrich([self.field(prior)], self.choices+[dict(prior, range=[.03, .07])])
        self.assertTrue(field['source_conflict'])

    def test_river_change_flags_retained_roughness_for_that_scenario(self):
        flow, wrong, matching = [self.field(self.choices[i]) for i in (0, 4, 3)]
        fields = self.enrich([flow, wrong, matching])
        self.assertEqual([f['acquisition']['status'] for f in fields],
                         ['FIS_ROW_SELECTED', 'FIS_STREAM_MISMATCH', 'FIS_ROW_SELECTED'])

    def test_stale_or_manually_modified_selection(self):
        field = self.field(self.choices[0])
        field['answer']['basis'] = 'modified'
        self.assertEqual(self.enrich([field])[0]['acquisition']['status'], 'FIS_SELECTION_CHANGED')
        field, = self.enrich([self.field(self.choices[0])], self.choices[1:])
        self.assertTrue(field['acquisition']['manual_decision_required'])

    def test_matching_number_without_explicit_selection_is_unresolved(self):
        for change in [dict(answer={}), dict(answer=dict(self.field(self.choices[0])['answer'], automatic_preparation=True))]:
            field = dict(self.field(self.choices[0]), **change)
            self.assertTrue(self.enrich([field])[0]['source_conflict'])

    def test_changed_file_is_not_a_current_choice(self):
        prior = self.choices[0]
        with patch.object(app_acquisition,'snapshot',return_value=dict(candidates=self.choices,sources=[dict(path='missing')])), patch.object(app_acquisition,'intact',return_value=False):
            field, = app_acquisition.enrich({}, [self.field(prior)])
        self.assertEqual(field['acquisition']['status'], 'SOURCE_CHANGED')
        self.assertEqual(field['parameter_candidates'], [])
        self.assertTrue(field['acquisition']['manual_decision_required'])
