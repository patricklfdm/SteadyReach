import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import sensitivity_ranges as ranges
from ras_workflow.common import ROOT, item, read, rel, save


def fixture():
    c = dict(project_id='range_test', authorization='authorization.json', geometry='geometry.json',
             scenarios=[dict(id='q100', channel_n=.04, overbank_n=.1, profiles=[dict(id='Q100')])])
    g = dict(model_type='river', flow_regime='mixed', structure=dict(groups=[]),
             cross_sections=[dict(rs=100)], boundary_slopes=dict(upstream=.001, downstream=.003),
             boundaries=dict(upstream=dict(type='normal_depth'), downstream=dict(type='normal_depth')))
    return c, g


def candidate(value=.003, low=.002, high=.004, **extra):
    return dict(value=value, range=[low, high], basis='Conditional source range', evidence_class='assumed', **extra)


class RangeTests(unittest.TestCase):
    def test_adopted_range_selected_and_document_matches_require_choice(self):
        c, g = fixture()
        a = {'g.boundary_slopes.downstream':dict(value=.003, candidate_record=candidate())}
        field = dict(key='c.scenarios.0.channel_n', value=.04,
                     parameter_candidates=[candidate(.04,.035,.05,source={'path':'source.pdf'})])
        with patch.object(ranges, 'intact', return_value=True):
            rows = {r['path']:r for r in ranges.parameter_rows(c,g,'q100',a,[field])}
        self.assertIsNotNone(rows['boundary_slopes.downstream']['recommended_id'])
        n = rows['scenario.channel_n']
        self.assertEqual(n['status'], 'SOURCE_CHOICE_REQUIRED')
        self.assertIsNone(n['recommended_id'])
        self.assertFalse(n['options'][0]['applicability_confirmed'])
        self.assertEqual(rows['scenario.overbank_n']['options'], [])

    def test_changed_manual_value_does_not_inherit_old_range(self):
        c, g = fixture()
        for answer in (dict(value=.005,candidate_record=candidate()), dict(value=.003,candidate_record=candidate(.005))):
            rows = ranges.parameter_rows(c,g,'q100',{'g.boundary_slopes.downstream':answer},[])
            self.assertEqual(next(r for r in rows if r['path']=='boundary_slopes.downstream')['options'], [])

    def test_no_percentages_invalid_or_nonbracketing_range(self):
        for low,high in [(None,.004),(.004,.002),(.003,.003),(True,.004),(.005,.006)]:
            self.assertIsNone(ranges.range_option(candidate(low=low,high=high),'ADOPTED_RANGE',.003))
        self.assertIsNone(ranges.range_option(dict(value=.003,basis='No bounds'),'ADOPTED_RANGE',.003))

    def test_inactive_boundaries_and_overridden_roughness_not_proposed(self):
        c, g = fixture();g['flow_regime']='subcritical'
        g['boundaries']['downstream']=dict(type='known_stage',stages_ft=[100.])
        g['cross_sections'][0]['manning_segments']=[dict(station_ft=0,n=.04)]
        rows = ranges.parameter_rows(c,g,'q100',{},[])
        paths={r['path'] for r in rows}
        self.assertNotIn('boundary_slopes.upstream',paths)
        self.assertNotIn('boundary_slopes.downstream',paths)
        self.assertIn('boundaries.downstream.stages_ft.0',paths)
        self.assertTrue(next(r for r in rows if r['path']=='scenario.channel_n')['inactive'])

    def test_same_numbers_from_different_streams_are_not_collapsed(self):
        c,g=fixture();a=candidate(.04,.03,.05,source={'path':'a.pdf'})
        b=copy.deepcopy(a);b['basis']='Different river applicability'
        field=dict(key='c.scenarios.0.channel_n',value=.04,parameter_candidates=[a,b])
        with patch.object(ranges,'intact',return_value=True):
            row=ranges.parameter_rows(c,g,'q100',{},[field])[0]
        self.assertEqual(len(row['options']),2)
        self.assertIsNone(row['recommended_id'])

    def test_changed_source_does_not_survive_as_an_adopted_range(self):
        c,g=fixture();a={'g.boundary_slopes.downstream':dict(value=.003,candidate_record=candidate(source={'path':'missing'}))}
        with patch.object(ranges,'intact',return_value=False):
            rows=ranges.parameter_rows(c,g,'q100',a,[])
        row=next(r for r in rows if r['path']=='boundary_slopes.downstream')
        self.assertFalse(row['options']);self.assertTrue(row['notes'])

    def test_snapshot_decision_is_used_instead_of_mutable_draft(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            folder=Path(temp);c,g=fixture()
            save(folder/'project.json',c);save(folder/'geometry.json',g)
            save(folder/'decision.json',dict(project_id=c['project_id'],scenario='q100',answers={'sealed':True},uploads=[]))
            save(folder/'authorization.snapshot.json',dict(decision=item(folder/'decision.json')))
            # Manifest basenames follow the configured authorization name.
            save(folder/'sealed/authorization.json',read(folder/'authorization.snapshot.json'))
            save(folder/'manifest.json',dict(input_snapshots=[item(folder/'sealed/authorization.json')]))
            save(folder/'summary.json',dict(configuration=c))
            m=dict(active_project=rel(folder/'project.json'),summary=item(folder/'summary.json'),scenario='q100')
            with patch.object(ranges,'bound_inputs',return_value=(c,g,[item(folder/'manifest.json')])):
                _,_,answers,fields,sources,notes=ranges.load_context(m)
                self.assertEqual(answers,{'sealed':True})
                self.assertFalse(fields);self.assertTrue(notes)
                self.assertIn(item(folder/'decision.json'),sources)
                save(folder/'decision.json',{'tampered':True})
                self.assertEqual(ranges.load_context(m)[2],{})
                save(folder/'geometry.json',dict(g,flow_regime='subcritical'))
                with self.assertRaisesRegex(ValueError,'geometry changed'):ranges.load_context(m)

    def stored_packet(self,folder):
        c,g=fixture();a={'g.boundary_slopes.downstream':dict(value=.003,candidate_record=candidate())}
        save(folder/'source.json',dict(source=True));save(folder/'summary.json',{})
        model=dict(summary=item(folder/'summary.json'),active_project='test/project.json')
        packet=dict(baseline=model['summary'],active_project=model['active_project'],sources=[item(folder/'source.json')],
                    parameters=ranges.parameter_rows(c,g,'q100',a,[]),maximum_parameters=4)
        save(folder/'ranges.json',packet);model['sensitivity_suggestions']=item(folder/'ranges.json')
        return model,packet

    def test_inherited_review_uploads_do_not_hide_current_candidate_sources(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            folder=Path(temp);c,g=fixture();uploads=[]
            for name in ['parent_project',c['project_id']]:
                save(folder/name/'parameters.json',dict(project_id=name,ready=True,fingerprint=name,fields=[dict(key=name)]))
                review=item(folder/name/'parameters.json')
                save(folder/name/'confirmation.json',dict(action='CONFIRM_DISPLAYED_PARAMETERS_AND_RUN',review=review,reviewed_fingerprint=name))
                uploads += [review,item(folder/name/'confirmation.json')]
            save(folder/'decision.json',dict(project_id=c['project_id'],scenario='q100',answers={},uploads=uploads))
            save(folder/'sealed/authorization.json',dict(decision=item(folder/'decision.json')))
            save(folder/'manifest.json',dict(input_snapshots=[item(folder/'sealed/authorization.json')]))
            save(folder/'project.json',c);save(folder/'geometry.json',g);save(folder/'summary.json',dict(configuration=c))
            m=dict(summary=item(folder/'summary.json'),active_project=rel(folder/'project.json'),scenario='q100')
            with patch.object(ranges,'bound_inputs',return_value=(c,g,[item(folder/'manifest.json')])):
                self.assertEqual(ranges.load_context(m)[3],[dict(key=c['project_id'])])

    def test_edit_keeps_source_and_is_labelled_separate_assumption(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            model,packet=self.stored_packet(Path(temp))
            option=next(r for r in packet['parameters'] if r['path']=='boundary_slopes.downstream')['options'][0]
            body=dict(range_token=model['sensitivity_suggestions']['sha256'],parameters=[dict(path='boundary_slopes.downstream',option_id=option['id'],low=.0015,high=.004)])
            choices,sources=ranges.resolve(model,body)
            self.assertTrue(choices[0]['range_record']['edited'])
            self.assertEqual(choices[0]['range_record']['option']['low'],.002)
            self.assertEqual(choices[0]['low'],.0015)
            self.assertIn(model['sensitivity_suggestions'],sources)
            self.assertIn('User-edited',choices[0]['basis'])

    def test_stale_preview_baseline_and_source_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            folder=Path(temp);model,_=self.stored_packet(folder)
            with self.assertRaisesRegex(ValueError,'stale'):ranges.resolve(model,dict(range_token='wrong'))
            changed=copy.deepcopy(model);changed['summary']={'path':'other'}
            self.assertIsNone(ranges.current(changed))
            save(folder/'source.json',{'changed':True})
            with self.assertRaisesRegex(ValueError,'inputs changed'):ranges.current(model,strict=True)

    def test_four_inputs_supported_duplicate_or_boolean_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            model,packet=self.stored_packet(Path(temp))
            parameters=[dict(path=r['path'],low=r['value']*.8,high=r['value']*1.2) for r in packet['parameters']]
            # These are explicit test-operator entries, not suggested percentages.
            body=dict(range_token=model['sensitivity_suggestions']['sha256'],parameters=parameters)
            self.assertEqual(len(ranges.resolve(model,body)[0]),4)
            body['parameters']=[parameters[0],parameters[0]]
            with self.assertRaisesRegex(ValueError,'repeated'):ranges.resolve(model,body)
            body['parameters']=[dict(parameters[0],low=True)]
            with self.assertRaisesRegex(ValueError,'finite'):ranges.resolve(model,body)


if __name__=='__main__':unittest.main()
