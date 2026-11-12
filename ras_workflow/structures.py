"""Culvert records observed in official Examples 3/4 and 7.0.1 GUI saves.

This adapter is geometry serialization only. Scenario values require provenance
and authorization at the project gate, independently of their file syntax.
"""
import numpy as np


def group_parameters(group,scenario,index):
    top=group.get('mann_top',scenario['culvert_n'])
    return dict(group_id=index,name=group.get('name',f'Group {index+1}'),
        **{k:group[k] for k in ['count','shape','span_ft','rise_ft','length_ft','us_invert_ft','ds_invert_ft',
                               'entrance_loss','exit_loss','distance_us_ft','centers_ft','depth_blocked_ft']},
        chart=group['chart_scale'][0],scale=group['chart_scale'][1],culvert_n=top,
        bottom_n=group.get('mann_bottom',top),bottom_n_depth_ft=group.get('bottom_n_depth_ft',0.))


def native_groups(groups,scenario,fixed):
    text='';expected=[]
    for index,group in enumerate(groups):
        b=group_parameters(group,scenario,index);name=b['name']
        if not isinstance(name,str) or not name.isascii() or not 1<=len(name)<=12 or any(c in name for c in ',\r\n'):
            raise ValueError('Culvert group name must be ASCII 1..12 characters without commas/newlines')
        shape={'box':2,'circular':1}[b['shape']];span=b['span_ft'] if shape==2 else ''
        text+=f"Multiple Barrel Culv={shape},{b['rise_ft']},{span},{b['length_ft']},{b['culvert_n']},{b['entrance_loss']},{b['exit_loss']},{b['chart']},{b['scale']},{b['us_invert_ft']},{b['ds_invert_ft']}, {b['count']},{name:<12}, 0 ,{b['distance_us_ft']:.3f}\n"
        text+=fixed(np.array(b['centers_ft']).ravel())
        text+=f"Culvert Bottom n={b['bottom_n']}\n"
        if b['bottom_n_depth_ft']>0:text+=f"Culvert Bottom Depth={b['bottom_n_depth_ft']}\n"
        if b['depth_blocked_ft']>0:text+=f"Culvert Depth Blocked={b['depth_blocked_ft']}\n"
        expected.append(b)
    return text,expected


def total_culvert_flow(groups,metrics):
    """The 7.0.1 COM Q Culv field includes roadway flow in Example 3.

    Do not use its documented label as proof of its actual aggregation.
    A single group is directly observed; a multi-group total requires an
    explicitly available roadway discharge and is a conservation derivation.
    """
    if len(groups)==1:return metrics.get('Q Culv Group'),'SINGLE_GROUP_COM_Q_CULV_GROUP'
    total,weir=metrics.get('Q Total'),metrics.get('Q Weir')
    if total is None or weir is None:return None,'NOT_EXTRACTED'
    if total<weir:raise ValueError('Roadway flow exceeds total structure flow')
    return total-weir,'DERIVED_Q_TOTAL_MINUS_OBSERVED_Q_WEIR'


def group_outputs(groups,metrics,headwater):
    """COM exposes its first group only. Never label it as all groups.

    For exactly two groups and an observed Q Weir, derive the second discharge
    from total flow minus roadway flow minus first-group flow. Missing roadway
    flow stays unknown; Q Culv cannot substitute for the unknown group total.
    """
    output=[];first_flow=metrics.get('Q Culv Group');total,total_basis=total_culvert_flow(groups,metrics)
    for i,b in enumerate(groups):
        direct=i==0;flow=first_flow if direct else None;barrel=metrics.get('Q Barrel') if direct else None
        basis='COM_FIRST_GROUP' if direct else 'NOT_EXTRACTED'
        if i==1 and len(groups)==2 and total is not None and first_flow is not None:
            flow=total-first_flow
            if flow<0:raise ValueError('Culvert first-group flow exceeds all-group flow')
            barrel=flow/b['count'];basis='DERIVED_TWO_GROUP_REMAINDER_AND_EQUAL_BARREL_SHARE'
        output.append(dict(group_id=i,name=b.get('name',f'Group {i+1}'),shape=b['shape'],barrel_count=b['count'],
            flow_cfs=flow,representative_barrel_flow_cfs=barrel,flow_basis=basis,
            inlet_velocity_fts=metrics.get('Culv Vel US') if direct else None,
            outlet_velocity_fts=metrics.get('Culv Vel DS') if direct else None,
            inlet_control_egl_ft=metrics.get('E.G. IC') if direct else None,
            outlet_control_egl_ft=metrics.get('E.G. OC') if direct else None,
            full_flow_length_ft=metrics.get('Culv Full Len') if direct else None,
            hw_over_d=(headwater-b['us_invert_ft'])/b['rise_ft'],
            hw_over_d_basis='External headwater minus original invert / full geometric rise; blockage not subtracted',
            detail_coverage='FIRST_GROUP_COM_FIELDS' if direct else 'FLOW_ONLY_DERIVED' if flow is not None else 'NOT_EXTRACTED'))
    return output
