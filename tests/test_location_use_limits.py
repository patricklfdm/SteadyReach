import unittest
from unittest.mock import patch

from ras_workflow.purpose_acceptance import evaluate
from ras_workflow.use_limits import comparison_coverage


class LocationUseLimits(unittest.TestCase):
    def comparison(self, changed, added=(), removed=()):
        rows = [dict(profile='Q100', station=str(i), location_status='MOVED' if i in changed else 'SAME_CENTER') for i in range(1,33)]
        return dict(status='COMPARISON_NOT_ACCEPTANCE', cross_sections=rows, profiles=[
            dict(profile='Q100', matched_sections=32, verified_center_count=32-len(changed),
                 added_stations=added, removed_stations=removed)])

    def test_one_verified_center_only_allows_local_comparison(self):
        result = comparison_coverage(self.comparison(range(2,33)), 'Q100')
        self.assertEqual((result['state'], result['verified'], len(result['excluded'])), ('missing', ['1'], 31))
        self.assertIn('1/32', result['zh'])
        self.assertEqual(comparison_coverage(self.comparison([]), 'Q100')['state'], 'met')
        self.assertEqual(comparison_coverage(self.comparison([], ['34'], ['33']), 'Q100')['excluded'], ['34','33'])

    def test_whole_reach_claim_includes_unpaired_profiles_and_controls(self):
        c = self.comparison([])
        c.update(unmatched_previous_profiles=['Q500'], rows=[dict(profile='Q100',metric='headwater_wse_ft',
            location_status='MOVED',previous=109,current=112,previous_station='200',current_station='300')])
        s = dict(configuration=dict(production_scope=dict(purpose='comparison',criteria={})),
                 hydraulics=dict(run_id='test',profiles=[dict(profile_id='Q100',flow_cfs=10)]))
        decision = evaluate(s,comparison=c)
        self.assertEqual(decision['state'],'NEED_EVIDENCE')
        self.assertTrue(any(r.get('control_stations')==['200','300'] for r in decision['use_limits']))
        self.assertTrue(any('Q500' in r['en'] for r in decision['use_limits']))
        s['configuration']['production_scope']['criteria']['profile']='Q100'
        self.assertFalse(any('Q500' in r['en'] for r in evaluate(s,comparison=c)['rows']))

    def study(self, side, diff=.25, profile='Q100', before=1, after=2, other=False):
        changes=[dict(path='boundary_slopes.'+side, before=before, after=after)]
        if other: changes.append(dict(path='channel_n', before=.04, after=.05))
        return dict(analysis={'sha256':'test'}, cases=[dict(id='trial',changes=changes)], comparisons=[dict(case='trial',
            cross_section_differences=[dict(station='100',profile=profile,delta_wse_ft=diff)])])

    def assess(self, regime, studies):
        cfg=dict(production_scope=dict(criteria={}, purpose='review', delivery_template='between_bridges_v1',flow_paths='single'))
        with patch('ras_workflow.qa.verified_profiles', return_value={'Q100':{'100':1.0}}):
            d=evaluate(dict(configuration=cfg,hydraulics=dict(flow_regime=regime,model_type='river',run_id='fixture',
                profiles=[dict(profile_id='Q100',flow_cfs=10)])),studies=studies)
        return d,[r['en'] for r in d['rows'] if r['state']=='missing' and r.get('action',{}).get('tool')=='sensitivity']

    def test_end_profile_factor_and_station_restrictions(self):
        for regime,ends in [('mixed',2),('subcritical',1),('supercritical',1),(None,1)]:
            self.assertEqual(len(self.assess(regime,[])[1]),ends)
        d,missing=self.assess('mixed',[self.study('downstream'),self.study('upstream',profile='Q500'),
            self.study('upstream',before=2,after=2),self.study('upstream',other=True)])
        self.assertEqual(len(missing),1)
        self.assertIn('upstream',missing[0])
        self.assertTrue(any(r.get('stations')==['100'] and r['profile']=='Q100' for r in d['use_limits']))
        self.assertFalse(self.assess('mixed',[self.study('downstream'),self.study('upstream',diff=0)])[1])
