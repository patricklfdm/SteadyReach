from .common import runtime_scratch
"""Hash-bound source transcription review, separate from permission to model.

Recompute derived candidates from the original source before accepting a review.
This records an operator's decisions; it does not authenticate their identity or
establish field accuracy, site applicability, or engineering approval.
"""
from pathlib import Path
import tempfile

from .common import ROOT, intact, item, read, safe_path, save, utc
from .evidence import parameters
from .hydrology import import_report


def verified_candidates(path):
    path=safe_path(ROOT,path);data=read(path)
    if not intact(data.get('sources',[])):
        raise ValueError('Candidate source evidence changed or is missing')
    sources=data['sources']
    with tempfile.TemporaryDirectory(prefix='review_review_',dir=runtime_scratch()) as temp:
        out=Path(temp)/'recomputed.json'
        if data.get('status')=='CANDIDATES_NOT_MODEL_INPUTS':
            actual=parameters(ROOT/sources[0]['path'],ROOT/sources[2]['path'],out)
        elif data.get('status')=='CANDIDATE_HYDROLOGY_REQUIRES_REVIEW':
            actual=import_report(ROOT/sources[0]['path'],ROOT/sources[2]['path'],out)
        else:raise ValueError('Unsupported candidate kind for source transcription review')
    if {k:v for k,v in actual.items() if k!='created_utc'}!={k:v for k,v in data.items() if k!='created_utc'}:
        raise ValueError('Candidate values differ from re-extracted source evidence')
    return data


def rows(data):
    if 'fields' in data:
        return [dict(key=f['name'],candidates=f['candidates'],required=f['required']) for f in data['fields']]
    return [dict(key='AEP:'+format(p['aep'],'.12g'),candidates=[p],required=True) for p in data['profiles']]


def template(candidate_path,output):
    data=verified_candidates(candidate_path);out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Choose a new review specification output')
    spec=dict(schema_version='1.0',scope='source_transcription_only',candidate=item(safe_path(ROOT,candidate_path)),
        reviewer=None,review_basis=None,decisions=[dict(key=r['key'],decision='PENDING',candidate_index=None,note=None) for r in rows(data)])
    save(out,spec);return spec


def review(candidate_path,spec_path,output):
    data=verified_candidates(candidate_path);sp=safe_path(ROOT,spec_path);spec=read(sp);path=safe_path(ROOT,candidate_path)
    if spec.get('schema_version')!='1.0' or spec.get('scope')!='source_transcription_only':
        raise ValueError('Source review cannot grant model or engineering approval')
    if spec.get('candidate')!=item(path) or not intact([spec['candidate']]):
        raise ValueError('Review specification belongs to a different candidate snapshot')
    if not isinstance(spec.get('reviewer'),str) or not spec['reviewer'].strip() or not spec.get('review_basis'):
        raise ValueError('Explicit reviewer and review basis required')
    choices=spec.get('decisions',[]);available=rows(data);keys=[r['key'] for r in available]
    if len(choices)!=len(keys) or {r['key'] for r in choices}!=set(keys):
        raise ValueError('One explicit decision for every candidate field is required')
    decisions={r['key']:r for r in choices};reviewed=[]
    for row in available:
        decision=decisions[row['key']];status=decision.get('decision');index=decision.get('candidate_index')
        if status not in ['TRANSCRIPTION_CHECKED','REJECTED','DEFERRED'] or not decision.get('note'):
            raise ValueError('Every decision needs a supported status and explanatory note')
        selected=None
        if status=='TRANSCRIPTION_CHECKED':
            if type(index)!=int or not 0<=index<len(row['candidates']):
                raise ValueError('A checked field requires an existing source candidate; missing data cannot be supplied')
            selected=row['candidates'][index]
        elif index is not None:raise ValueError('Rejected or deferred fields must not select a value')
        reviewed.append(dict(key=row['key'],status=status,selected_source_candidate=selected,
            note=decision['note'],model_value=None,approved_for_model=False))
    result=dict(schema_version='1.0',created_utc=utc(),status='SOURCE_REVIEW_RECORDED',scope=spec['scope'],
        reviewer=spec['reviewer'],review_basis=spec['review_basis'],reviewer_identity='OPERATOR_ATTESTED',
        sources=[item(path),item(sp)]+data['sources'],fields=reviewed,
        unresolved_applicability=data.get('required_unresolved_checks'),
        source_applicability_items=data.get('applicability_review_items',[]),
        approved_for_model=False,engineering_acceptance='NOT_ASSESSED',
        limitations=['Transcription review does not verify a reported dimension as a survey or as-built measurement',
            'Site applicability, units/datum interpretation and conditional-use authorization remain separate input gates',
            'No project or geometry modified; missing/rejected/deferred model values remain null'])
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Preserve previous review; choose a new output')
    save(out,result);return result
