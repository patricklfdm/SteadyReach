"""Source-bound reference water levels used only to screen section coverage."""
import copy
import numpy as np
from .common import finite, intact


def prepare(model, geometry, request):
    if not isinstance(request, dict):
        raise ValueError('Reference coverage settings must be an object')
    if geometry.get('model_type') != 'river':
        raise ValueError('Reference coverage screening currently supports river reaches')
    datum = request.get('vertical_datum')
    if not isinstance(datum, str):
        raise ValueError('Enter the reference vertical datum')
    datum = datum.strip()
    if not datum or datum != geometry.get('vertical_datum'):
        raise ValueError('Reference water levels must use the model vertical datum / 参考水位须采用模型高程基准')
    sources = [entry for entry in model.get('attachments', [])
               if entry.get('path') == request.get('source_path')]
    if len(sources) != 1 or not intact(sources):
        raise ValueError('Choose an unchanged imported reference source / 请选择已导入且完整的参考资料')
    sections = geometry['cross_sections']
    by_rs = {float(row['rs']): index for index, row in enumerate(sections)}
    if len(by_rs) != len(sections):
        raise ValueError('Section identifiers must be unique')
    points = request.get('points')
    if not isinstance(points, list) or not 2 <= len(points) <= len(sections):
        raise ValueError('Enter at least two reference section / elevation pairs / 至少填写两组断面与参考水位')
    selected = {}
    for point in points:
        if not isinstance(point, dict) or not finite(point.get('rs')) or not finite(point.get('water_ft')):
            raise ValueError('Each reference needs a finite RS and water elevation in ft')
        rs = float(point['rs'])
        if rs not in by_rs or rs in selected:
            raise ValueError('Reference RS must be unique and belong to the current draft')
        selected[rs] = float(point['water_ft'])
    centers = np.asarray([row['center_xy'] for row in sections], dtype=float)
    distances = np.linalg.norm(np.diff(centers, axis=0), axis=1)
    if not np.isfinite(centers).all() or (distances <= 1e-8).any():
        raise ValueError('Distinct finite section centers required for reference interpolation')
    chain = np.r_[0., np.cumsum(distances)]
    ordered = sorted(selected, key=by_rs.get)
    controls = [chain[by_rs[rs]] for rs in ordered]
    levels = [selected[rs] for rs in ordered]
    interpolated = np.interp(chain, controls, levels)
    return dict(source=copy.deepcopy(sources[0]), vertical_datum=datum, units='international_ft',
        points=[dict(rs=rs, water_ft=selected[rs]) for rs in ordered],
        sections=[dict(rs=float(row['rs']), water_ft=float(level)) for row, level in zip(sections, interpolated)],
        basis='User-associated source water levels; linear interpolation along section-center distances; nearest control held beyond the end controls. Reference and current section correspondence requires review.',
        evidence_class='assumed', purpose='SECTION_EXTENT_SCREEN_ONLY', solver_run=False)
