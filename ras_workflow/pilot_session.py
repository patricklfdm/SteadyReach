"""Optional site-pilot time log. Untimed visits do not generate estimates."""
from . import app_core as core
from .common import lock, read, save, utc


def update(key,body):
    model=core.model(key)
    path=core.folder(key)/'pilot_session.json'
    with lock(path.with_suffix('.lock')):
        data=read(path) if path.exists() else dict(project_id=key,intervals=[],developer_interventions=[],open=None,revision=0)
        action=body.get('action','read')
        if action=='read':return data
        if data['revision']!=body.get('timer_revision'):raise ValueError('Reload the pilot clock before changing it')
        now=utc()
        if action in ('intervention','blocker'):
            topic=body.get('topic','unspecified')
            if topic not in ('unspecified','data','geometry','parameters','hydraulics','delivery','recovery'):
                raise ValueError('Select a pilot topic')
            page=body.get('page')
            if page not in (None,'model','overview','review','delivery'):raise ValueError('Unknown pilot page')
            data.setdefault('checkpoints',[]).append(dict(at=now,kind=action,topic=topic,
                page=page,phase=model.get('phase'),status=model.get('status'),model_revision=model.get('revision')))
            if action=='intervention':
                data['developer_interventions'].append(now)
        elif action in ('engineer','external_wait','pause','discard'):
            ongoing=data['open']
            if (not ongoing and action in ('pause','discard')) or (ongoing and ongoing['kind']==action):return data
            if ongoing and action!='discard':data['intervals'].append(dict(**ongoing,finished_utc=now))
            data['open']=dict(kind=action,started_utc=now) if action in ('engineer','external_wait') else None
        else:raise ValueError('Unknown clock action')
        data['revision']+=1
        save(path,data)
        return data
