"""Shared spatial checks for drafts, approval and native model input gates."""
import numpy as np
from .common import digest


def intersects(a, b, c, d):
    a,b,c,d = (np.asarray(p, dtype=float) for p in (a,b,c,d))
    cross = lambda u,v: float(u[0]*v[1]-u[1]*v[0])
    u,v = b-a,d-c
    den = cross(u,v)
    if abs(den)<1e-9:
        return abs(cross(c-a,u))<1e-7 and all(
            max(min(a[i],b[i]),min(c[i],d[i]))<=min(max(a[i],b[i]),max(c[i],d[i]))+1e-7 for i in (0,1))
    t,s = cross(c-a,v)/den,cross(c-a,u)/den
    return -1e-9<=t<=1+1e-9 and -1e-9<=s<=1+1e-9


def spatial_issues(sections):
    issues=[]; cuts=[]
    for i,row in enumerate(sections):
        try:
            cut=np.asarray(row.get('cutline_xy'),dtype=float)
            if cut.ndim!=2 or cut.shape[1]!=2 or len(cut)<2 or not np.isfinite(cut).all():raise ValueError()
            if (np.linalg.norm(np.diff(cut,axis=0),axis=1)<=1e-8).any():
                issues.append(dict(code='ZERO_LENGTH_CUT_SEGMENT',sections=[i],severity='BLOCKER'))
            for j in range(len(cut)-1):
                for k in range(j+2,len(cut)-1):
                    if intersects(*cut[j:j+2],*cut[k:k+2]):
                        issues.append(dict(code='SELF_INTERSECTING_CUT',sections=[i],severity='BLOCKER'))
            cuts.append(cut)
        except (ValueError,TypeError,AttributeError):
            cuts.append(None);issues.append(dict(code='INVALID_CUTLINE',sections=[i],severity='BLOCKER'))
    for i,a in enumerate(cuts):
        if a is None:continue
        for j in range(i+1,len(cuts)):
            b=cuts[j]
            if b is not None and any(intersects(*a[k:k+2],*b[m:m+2]) for k in range(len(a)-1) for m in range(len(b)-1)):
                issues.append(dict(code='INTERSECTING_SECTIONS',sections=[i,j],severity='BLOCKER'))
    return issues


def section_fingerprint(row):
    # Any relevant edit invalidates the prior visual review, including bank edits.
    return digest({k:row.get(k) for k in ['rs','center_xy','cutline_xy','station_ft','elevation_ft',
        'bank_stations_ft','reach_lengths_ft','expansion_contraction','bank_candidates']+
        [k for k in ['manning_segments','ineffective_left','ineffective_right'] if row.get(k)]})


def review_errors(g):
    errors=[]
    for i,row in enumerate(g.get('cross_sections',[])):
        stamp=row.get('terrain_sampling')
        if stamp and stamp.get('spatial_fingerprint')!=digest({k:row.get(k) for k in ['cutline_xy','station_ft','elevation_ft','center_xy']}):
            errors.append(f'XS {i}: cutline/samples changed after DEM sampling; resample the section')
        if not g.get('terrain_review_required'):continue
        r=row.get('terrain_review') or {}
        if r.get('decision')!='ACCEPT' or (not r.get('reviewer') and r.get('policy')!='local_computation_v1') or not r.get('basis') or r.get('fingerprint')!=section_fingerprint(row):
            errors.append(f'XS {i}: terrain/bank review missing or stale')
    return errors
