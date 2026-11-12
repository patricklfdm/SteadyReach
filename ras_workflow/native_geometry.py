"""Checks against inspected native geometry fields, never inferred HDF paths."""
import numpy as np


def _redundant_road_points_only(wanted, actual):
    """Verify observed RAS compaction without editing or relaxing source inputs.

    RAS 7.0.1 can omit duplicate and collinear road vertices from the HDF
    while retaining every source vertex in the saved .g file. Retained HDF
    vertices must be an ordered subset. Every omitted vertex must lie on
    its retained segment to 1e-5 ft; real steps/crest changes cannot disappear.
    """
    if len(actual)>=len(wanted) or np.any(np.diff(wanted[:,0])<0):return False
    if not np.allclose(actual[0],wanted[0],rtol=0,atol=.002):return False
    previous=0
    for point in actual[1:]:
        rest=wanted[previous+1:]
        exact=np.flatnonzero(np.all(rest.astype(actual.dtype)==point,axis=1))
        candidates=exact if len(exact) else np.flatnonzero(np.all(np.isclose(rest,point,rtol=0,atol=.002),axis=1))
        if not len(candidates):return False
        current=previous+1+int(candidates[0])
        left,right=wanted[previous],wanted[current]
        skipped=wanted[previous+1:current]
        if len(skipped):
            width=right[0]-left[0]
            if width==0:
                # Never remove a distinct vertex along a vertical step.
                if not np.all(np.all(skipped==left,axis=1)|np.all(skipped==right,axis=1)):return False
            else:
                elevation=left[1]+(skipped[:,0]-left[0])*(right[1]-left[1])/width
                if np.any(np.abs(skipped[:,1]-elevation)>1e-5):return False
        previous=current
    # Trailing repetitions are harmless, but dropping the end of the road is not.
    return bool(np.all(wanted[previous:]==wanted[previous]))


def verify_road(structure, table, values, expected):
    if not np.isclose(structure['Weir Width'],expected['road_width_ft'],atol=.002,rtol=0):raise ValueError('Road width mismatch')
    if 'road_profiles' not in expected:
        if not np.isclose(structure['Weir Min Elevation'],expected['road_min_ft'],atol=.002,rtol=0):raise ValueError('Road crest mismatch')
        return 'LEGACY_EXPLICIT_MINIMUM_FIELD'
    elevations=[];compacted=False
    for side,prefix in [('upstream','US'),('downstream','DS')]:
        wanted=np.asarray(expected['road_profiles'][side],dtype=float)
        start=int(table[prefix+' BR Weir Profile (Index)']);count=int(table[prefix+' BR Weir Profile (Count)'])
        if start<0 or count<2 or start+count>len(values):raise ValueError('Invalid native road profile indices')
        actual=values[start:start+count]
        if (wanted.ndim!=2 or wanted.shape[1]!=2 or actual.ndim!=2 or actual.shape[1]!=2 or
            not np.isfinite(wanted).all() or not np.isfinite(actual).all()):
            raise ValueError('Road station/elevation profile mismatch: '+side)
        if actual.shape!=wanted.shape or not np.allclose(actual,wanted,rtol=0,atol=.002):
            if not _redundant_road_points_only(wanted,actual):
                raise ValueError('Road station/elevation profile mismatch: '+side)
            compacted=True
        elevations+=wanted[:,1].tolist()
    if not np.isclose(min(elevations),expected['road_min_ft'],atol=.002,rtol=0):raise ValueError('Road minimum differs from explicit profiles')
    # This optional native field is a user-entered override, not necessarily the
    # lowest elevation of the road profile. Empty source fields round-trip as NaN.
    override=expected['weir_minimum_override_ft'];actual=float(structure['Weir Min Elevation'])
    if override is None:
        if not np.isnan(actual):raise ValueError('Unexpected native weir minimum override')
    elif not np.isfinite(override) or not np.isclose(actual,override,atol=.002,rtol=0):raise ValueError('Native weir minimum override mismatch')
    return 'FULL_US_DS_PROFILE_AND_EXPLICIT_OVERRIDE'+('_REDUNDANT_VERTICES_VERIFIED' if compacted else '')
