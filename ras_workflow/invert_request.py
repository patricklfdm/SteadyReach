"""Issue and match a culvert survey worksheet to a frozen edition and opening group."""
import csv
from io import StringIO
from .common import digest
from .revision_inputs import bound_inputs

ENDS = {'us_invert_ft':'inlet','ds_invert_ft':'outlet'}


def identity(group):
    return digest({k:group.get(k) for k in ('name','shape','count','span_ft','rise_ft','centers_ft')})


def issue(key, body):
    from .result_guidance import load_evidence
    m,_,summary,_,_,_=load_evidence(key,body)
    _,g,_=bound_inputs(summary)
    groups=g.get('structure',{}).get('groups',[])
    if not groups or m.get('native_review'):
        raise ValueError('A surveyed return requires an editable culvert model / 需使用可编辑涵洞模型')
    rows=[]
    for i,group in enumerate(groups):
        for name,side in ENDS.items():
            rows.append(dict(field=f'g.structure.groups.{i}.{name}',value='',unit='ft',datum=g.get('vertical_datum') or '',
                             evidence_class='reported',source='',opening_group=i+1,end=side,prior_ft=group.get(name),
                             request_summary=m['summary']['sha256'],opening_signature=identity(group)))
    buffer=StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return dict(project=key,run=summary['hydraulics']['run_id'],rows=rows,csv=buffer.getvalue())


def match(row, model, geometry):
    # Ordinary parameter CSVs retain the existing import contract.
    if not {'request_summary','opening_signature','opening_group','end'}.intersection(row):
        return
    origin=(model.get('parent_revision') or {}).get('summary') or {}
    if not origin.get('sha256') or row.get('request_summary')!=origin['sha256']:
        raise ValueError('Use an independent revision of the worksheet edition / 请在本索资单所对应计算的独立修订版中导回')
    groups=geometry.get('structure',{}).get('groups',[])
    try:
        i=int(row['opening_group'])-1
        group=groups[i] if i>=0 else None
    except (KeyError,TypeError,ValueError,IndexError):
        group=None
    if group is None or row.get('opening_signature')!=identity(group):
        raise ValueError('Opening group has changed / 涵孔组尺寸或位置已变化，请重新索资')
    if not any(row.get('field')==f'g.structure.groups.{i}.{k}' and row.get('end')==side for k,side in ENDS.items()):
        raise ValueError('Opening or inlet/outlet mismatch / 涵孔组或进出口标识不一致')
    if row.get('unit','').strip()!='ft' or not row.get('datum') or row['datum']!=geometry.get('vertical_datum'):
        raise ValueError('Use feet and the model datum / 请使用英尺及模型高程基准')
    if row.get('evidence_class','').strip().lower() not in ('reported','assumed'):
        raise ValueError('Identify the return as reported or assumed / 请区分原件记载与假设')
    if not (row.get('source') or '').strip():
        raise ValueError('Supply the measurement or assumption source / 请填写测量记录或假设依据')
