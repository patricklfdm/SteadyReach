"""Computed-case continuation preserves the chosen state and source identities."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import study_revision, geometry_auto_qa, app_revision, intake
from ras_workflow.common import item, save, read, rel


class StudyRevisionTests(unittest.TestCase):
    def test_identical_geometry_answers_preserve_reviewed_joint_bank_metadata(self):
        from ras_workflow.geometry_qa import section_fingerprint
        row=dict(rs=100,station_ft=[0,10,20],elevation_ft=[5,0,5],center_xy=[10,0],
                 cutline_xy=[[0,0],[20,0]],bank_stations_ft=[0,20],
                 bank_candidates={'selected_indices':[0,2],'basis':'joint reach inference'})
        row['terrain_review']={'fingerprint':section_fingerprint(row)}
        geometry=dict(model_type='culvert',structure={'groups':[]},cross_sections=[row],terrain_review_required=True)
        draft=dict(geometry=geometry,answers={
            'g.cross_sections.0.'+key:dict(value=copy.deepcopy(row[key]))
            for key in ('station_ft','elevation_ft','center_xy','cutline_xy')})
        packet={'original_project':{'path':'test.json'},'scenario':'q100'}
        with patch.object(intake,'read',return_value={}), \
             patch.object(intake,'normalize_geometry',side_effect=copy.deepcopy), \
             patch.object(intake,'fields',return_value=[{'key':key} for key in draft['answers']]), \
             patch('ras_workflow.banks.propose',return_value={'basis':'changed shape'}) as propose:
            _,current=intake._objects(packet,draft)
            propose.assert_not_called()
            self.assertEqual(section_fingerprint(current['cross_sections'][0]),row['terrain_review']['fingerprint'])
            draft['answers']['g.cross_sections.0.elevation_ft']['value']=[6,0,5]
            _,changed=intake._objects(packet,draft)
            propose.assert_called_once()
            self.assertNotEqual(section_fingerprint(changed['cross_sections'][0]),row['terrain_review']['fingerprint'])

    def test_revision_rebases_saved_terrain_answers_and_keeps_parent(self):
        with tempfile.TemporaryDirectory(dir=study_revision.ROOT) as tmp:
            root=Path(tmp);old=root/'old'/'nested';new=root/'new'
            old.mkdir(parents=True)
            (root/'dem.tif').write_bytes(b'test-only')
            save(root/'provenance.json',{'test_only':True})
            save(old/'summary.json',{})
            parent=dict(id='parent',title='Test',revision=1,scenario='q100',summary=item(old/'summary.json'))
            save(old/'app.json',parent)
            config=dict(terrain=dict(mode='local',raster='../../dem.tif',provenance='../../provenance.json'),
                        delivery=dict(enabled=True,additional_sources=['../../provenance.json'],imagery=dict(raster='../../dem.tif')))
            draft=dict(answers={f'c.terrain.{key}':dict(value=value,basis='source retained',confirmed=True)
                                for key,value in config['terrain'].items() if key!='mode'})
            original=copy.deepcopy(draft)
            case_config=copy.deepcopy(config)
            case_config['delivery']['enabled']=False
            case_config['terrain'].update(raster=str(root/'dem.tif'),provenance=str(root/'provenance.json'))
            source=dict(config_path=old/'cases'/'case'/'project.json',config=case_config,geometry={},
                        case_id='repair_2',summary=parent['summary'],sources=[],geometry_source={},
                        analysis={},terrain={},maximum_width_ft=2000)
            def prepare(path,scenario):
                session=new/'intake'/'session.json'
                save(session,{})
                save(session.parent/'draft.json',{})
                return {'session':rel(session)}
            with patch.object(app_revision.core,'model',return_value=parent), \
                 patch.object(app_revision.core,'require_idle'), \
                 patch('ras_workflow.app_parameters.objects',return_value=(None,{'project':rel(old/'project.json')},draft,config,{})), \
                 patch.object(study_revision,'resolve',return_value=source), \
                 patch.object(study_revision,'answers',return_value=copy.deepcopy(draft['answers'])), \
                 patch.object(app_revision.core,'folder',side_effect=lambda key: old if key=='parent' else new), \
                 patch.object(app_revision.intake,'prepare',side_effect=prepare), \
                 patch.object(app_revision.core,'persist') as persist, \
                 patch.object(app_revision.core,'launch',side_effect=ValueError('Another project is processing')), \
                 patch.object(app_revision.core,'view',return_value={}):
                app_revision.create('parent',dict(revision=1,confirmed=True,study_kind='coverage',prepare=True))
                self.assertEqual(persist.call_args.args[1],'AUTOMATIC_PREPARATION_DEFERRED')
                self.assertEqual(persist.call_args.args[0]['errors'],['Another project is processing'])
            saved=read(new/'intake'/'draft.json')
            initial=read(new/'initial.json')
            for key in ('raster','provenance'):
                answer=saved['answers']['c.terrain.'+key]
                self.assertEqual(answer['value'],initial['terrain'][key])
                self.assertEqual((new/answer['value']).resolve(),(old/config['terrain'][key]).resolve())
                self.assertEqual(answer['basis'],'source retained')
                self.assertFalse(answer['confirmed'])
            self.assertEqual(draft,original)
            self.assertTrue(initial['delivery']['enabled'])
            self.assertEqual((new/initial['delivery']['additional_sources'][0]).resolve(),root/'provenance.json')
            self.assertEqual((new/initial['delivery']['imagery']['raster']).resolve(),root/'dem.tif')

    def answer_fixture(self):
        old_config={'scenarios':[{'id':'q200','profiles':[{'id':'Q200'}]},
                                 {'id':'q100','profiles':[{'id':'A'},{'id':'B'}]}]}
        config={'scenarios':[{'id':'q100','profiles':[{'id':'B'},{'id':'A'}]}]}
        old_geometry={'cross_sections':[{'rs':200,'reach_id':'river'},{'rs':100,'reach_id':'river'}]}
        geometry={'cross_sections':[{'rs':200,'reach_id':'river'},{'rs':150,'reach_id':'river'},
                                    {'rs':100,'reach_id':'river'}]}
        previous={
            'g.cross_sections.0.bank_stations_ft':dict(value=[10,30],evidence_class='assumed',basis='old banks',automatic_preparation=True,confirmed=True),
            'g.cross_sections.1.bank_stations_ft':dict(value=[20,40],evidence_class='reported',basis='retained bank source',confirmed=True),
            'c.scenarios.1.profiles.1.flow_cfs':dict(value=200,evidence_class='reported',basis='flow B',confirmed=True),
            'g.boundary_slopes.downstream':dict(value=.01,evidence_class='assumed',basis='old boundary',confirmed=True),
        }
        rows=[dict(key='g.cross_sections.0.bank_stations_ft',value=[100,120]),
              dict(key='g.cross_sections.1.bank_stations_ft',value=[30,50]),
              dict(key='g.cross_sections.2.bank_stations_ft',value=[20,40]),
              dict(key='c.scenarios.0.profiles.0.flow_cfs',value=200),
              dict(key='g.boundary_slopes.downstream',value=.01),
              dict(key='g.boundary_slopes.upstream',value=None)]
        source={'case_id':'level_2','summary':{'path':'actual.json','sha256':'actual'}}
        with patch('ras_workflow.intake.fields',return_value=rows):
            return study_revision.answers(previous,old_config,old_geometry,config,geometry,'q100',source),previous

    def test_remaps_retained_sections_and_reordered_profiles(self):
        result,previous=self.answer_fixture()
        self.assertEqual(result['g.cross_sections.2.bank_stations_ft']['basis'],'retained bank source')
        self.assertEqual(result['c.scenarios.0.profiles.0.flow_cfs']['basis'],'flow B')
        self.assertEqual(result['g.cross_sections.1.bank_stations_ft']['evidence_class'],'assumed')
        self.assertEqual(result['g.cross_sections.0.bank_stations_ft']['value'],[100,120])
        self.assertEqual(result['g.cross_sections.0.bank_stations_ft']['prior_input'],previous['g.cross_sections.0.bank_stations_ft'])

    def test_new_draft_has_no_consent_or_auto_owner_and_retains_sources(self):
        result,previous=self.answer_fixture()
        self.assertNotIn('g.boundary_slopes.upstream',result)
        self.assertTrue(all(not row['confirmed'] and 'automatic_preparation' not in row for row in result.values()))
        self.assertTrue(all(row['source_case']['sha256']=='actual' for row in result.values()))
        self.assertTrue(previous['g.cross_sections.0.bank_stations_ft']['confirmed'])

    def test_rejects_wrong_kind_token_and_changed_analysis(self):
        for body in ({'study_kind':'other'}, {'study_kind':'coverage','study_token':'old'},
                     {'study_kind':'coverage','study_token':'current'}):
            with self.subTest(body=body), patch.object(study_revision,'intact',return_value=False):
                with self.assertRaises(ValueError):
                    study_revision.resolve({'latest_coverage':{'sha256':'current'}},body)

    def test_incomplete_case_is_rejected_before_native_loading(self):
        analysis={'study':{'path':'study.json'},'review':{'path':'review.json'},'execution':{'path':'execution.json'}}
        plan={'analysis_kind':'section_spacing','evidence':[{'path':'baseline.json'}], 'cases':[{'id':'level_2'}]}
        journal={'study':analysis['study'],'review':analysis['review'],'cases':[{'id':'level_2','status':'FAILED'}]}
        parent={'summary':{'path':'baseline.json'},'latest_spacing':{'path':'analysis.json','sha256':'current'}}
        with patch.object(study_revision,'intact',return_value=True), \
             patch.object(study_revision,'read',side_effect=[analysis,journal]), \
             patch.object(study_revision,'reviewed',return_value=(None,plan,None,None)), \
             patch.object(study_revision,'load_summary') as native:
            with self.assertRaisesRegex(ValueError,'successfully computed'):
                study_revision.resolve(parent,dict(study_kind='spacing',case_id='level_2',study_token='current'))
            native.assert_not_called()

    def test_prior_water_uses_selected_case_geometry(self):
        with tempfile.TemporaryDirectory(dir=study_revision.ROOT) as tmp:
            path=Path(tmp)
            geometry={'cross_sections':[{'rs':150,'station_ft':[0,10],'elevation_ft':[5,0]}]}
            save(path/'geometry.json',geometry)
            save(path/'diagnostics.json',{'issues':[]})
            summary={'hydraulics':{'raw_hdf':{'path':'raw.hdf'},'diagnostics':item(path/'diagnostics.json')}}
            save(path/'summary.json',summary)
            parent={'project_id':'original','summary':item(path/'summary.json'),'geometry':item(path/'geometry.json')}
            with patch('ras_workflow.app_core.model') as original, \
                 patch('ras_workflow.qa_locator.collect',return_value={'rows':[{'rs':'150','left_excess_ft':1,'right_excess_ft':0,'wse_ft':6}]}), \
                 patch.object(geometry_auto_qa,'boundary_study_water',return_value=({},[])):
                water,_,_,old=geometry_auto_qa.prior_results({'parent_revision':parent},geometry)
                self.assertEqual(water,{150.:6})
                self.assertEqual(old[150.],geometry['cross_sections'][0])
                original.assert_not_called()
            save(path/'geometry.json',{'tampered':True})
            with self.assertRaisesRegex(ValueError,'geometry changed'):
                geometry_auto_qa.prior_results({'parent_revision':parent},geometry)


if __name__=='__main__':
    unittest.main()
