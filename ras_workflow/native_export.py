"""HEC-RAS 7.0.1 native table export in an exclusively owned solver process.

Uses inspected Win32 menus and controls, not screen coordinates or an AI service.
Only a current computed plan is read. Every table is bound to the input/output
hashes and checked again against HDF and COM before it can enter a report.
"""
import ctypes
import time
from pathlib import Path

from .common import ROOT, item, intact, rel, save, sha, utc


def capture(controller, project, pid, output, profiles):
    import win32con as wc
    import win32gui as wg
    import win32process as wp
    import win32clipboard as clip
    import pywintypes
    from ctypes import wintypes as wt
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.SendMessageW.argtypes=[wt.HWND,wt.UINT,wt.WPARAM,wt.LPARAM];user.SendMessageW.restype=wt.LPARAM
    user.GetMenuStringW.argtypes=[wt.HMENU,wt.UINT,wt.LPWSTR,ctypes.c_int,wt.UINT];user.GetMenuStringW.restype=ctypes.c_int

    project=Path(project).resolve();output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    trace=[];started=utc();files=[]
    sources=[item(project.with_suffix(ext),'native_export_source') for ext in ('.prj','.p01','.g01','.f01','.O01','.p01.hdf')]
    deadline=time.monotonic()+60

    def guard(hwnd=None):
        if time.monotonic()>deadline:raise TimeoutError('Native table export exceeded its time limit')
        if Path(controller.CurrentProjectFile()).resolve()!=project:raise ValueError('Export project identity changed')
        if hwnd and (not wg.IsWindow(hwnd) or wp.GetWindowThreadProcessId(hwnd)[1]!=pid):raise ValueError('Export control is not owned by this solver process')

    def send(hwnd,msg,wp_=0,lp=0):
        guard(hwnd)
        return wg.SendMessageTimeout(hwnd,msg,wp_,lp,wc.SMTO_ABORTIFHUNG,2000)[1]

    def post(hwnd,msg,wp_=0,lp=0):
        guard(hwnd);wg.PostMessage(hwnd,msg,wp_,lp)

    def wait(fn,label):
        until=min(deadline,time.monotonic()+10)
        while time.monotonic()<until:
            guard();v=fn()
            if v:return v
            time.sleep(.1)
        raise TimeoutError('Native export: '+label)

    def window(title):
        found=[]
        wg.EnumWindows(lambda h,_:found.append(h) if wp.GetWindowThreadProcessId(h)[1]==pid and wg.IsWindowVisible(h) and wg.GetWindowText(h)==title else None,None)
        if len(found)>1:raise ValueError('Ambiguous export window: '+title)
        return found[0] if found else None

    def control(parent,number,cls):
        found=[]
        wg.EnumChildWindows(parent,lambda h,_:found.append(h) if wg.GetDlgCtrlID(h)==number and wg.GetClassName(h)==cls and wg.IsWindowVisible(h) else None,None)
        if len(found)!=1:raise ValueError('Native control layout changed: '+str((number,cls)))
        guard(found[0]);return found[0]

    def items(hwnd):
        count=send(hwnd,wc.CB_GETCOUNT)
        if not 0<=count<=1000:raise ValueError('Invalid native selector length')
        result=[]
        for i in range(count):
            buf=ctypes.create_unicode_buffer(2048)
            # CB_GETLBTEXT is marshalled by Windows; this is not remote memory access.
            guard(hwnd);user.SendMessageW(hwnd,wc.CB_GETLBTEXT,i,ctypes.addressof(buf))
            result.append(buf.value.strip())
        return result

    def select(parent,number,value,expected_items=None):
        h=control(parent,number,'ThunderRT6ComboBox');labels=items(h)
        if expected_items is not None and labels!=expected_items:raise ValueError('Native selector differs from computed model: '+str(labels))
        if labels.count(value)!=1:raise ValueError('Missing/ambiguous native selector: '+value)
        index=labels.index(value);send(h,wc.CB_SETCURSEL,index)
        send(parent,wc.WM_COMMAND,number+(wc.CBN_SELCHANGE<<16),h)
        if send(h,wc.CB_GETCURSEL)!=index:raise ValueError('Native selection did not persist')
        trace.append(dict(action='select',window=wg.GetWindowText(parent),control=number,value=value,items=labels))

    def menu(parent,label):
        found=[]
        def walk(h):
            for i in range(wg.GetMenuItemCount(h)):
                buf=ctypes.create_unicode_buffer(1024)
                user.GetMenuStringW(h,i,buf,1024,wc.MF_BYPOSITION)
                text=buf.value.replace('&','').split('\t')[0].strip()
                sub=wg.GetSubMenu(h,i)
                if sub:walk(sub)
                elif text==label:found.append(wg.GetMenuItemID(h,i))
        guard(parent);h=wg.GetMenu(parent)
        if not h:raise ValueError('Native menu unavailable')
        walk(h)
        if len(found)!=1:raise ValueError('Native export menu changed: '+label)
        post(parent,wc.WM_COMMAND,found[0]);trace.append(dict(action='menu',label=label,id=found[0]))

    def clipboard_table(parent,header):
        sequence=clip.GetClipboardSequenceNumber()
        menu(parent,'Copy to Clipboard (Data and Headings)')
        wait(lambda:clip.GetClipboardSequenceNumber()!=sequence,'clipboard was not updated by HEC-RAS')
        def read_clipboard():
            try:clip.OpenClipboard()
            except (OSError,pywintypes.error) as e:
                if getattr(e,'winerror',None) not in (5,170):raise
                return None # HEC-RAS or the desktop clipboard service is still busy.
            try:
                owner=clip.GetClipboardOwner()
                if not owner:return None
                if wp.GetWindowThreadProcessId(owner)[1]!=pid:raise ValueError('Clipboard changed outside the owned HEC-RAS process')
                if not clip.IsClipboardFormatAvailable(wc.CF_UNICODETEXT):return None
                return clip.GetClipboardData(wc.CF_UNICODETEXT)
            finally:clip.CloseClipboard()
        text=wait(read_clipboard,'native clipboard remains busy')
        if not text.startswith(header+'\r\n') and not text.startswith(header+'\n'):raise ValueError('Copied table is stale or belongs to another group/profile')
        return text

    result=dict(schema='automatic_native_export_1',status='IN_PROGRESS',started_utc=started,project=rel(project),pid=pid,sources=sources,files=files,trace=trace,
        profiles=[p['id'] for p in profiles],scope='ONE_RIVER_ONE_REACH_ONE_CULVERT_CROSSING',solver_rerun=False)
    try:
        import h5py
        guard();controller.ShowRas();main=wait(lambda:window('HEC-RAS 7.0.1'),'main window')
        with h5py.File(project.with_suffix('.p01.hdf')) as f:
            if not f.attrs['File Version'].decode().startswith('HEC-RAS 7.0.1 ') or f.attrs['Units System']!=b'US Customary':raise ValueError('Uninspected native export version/units')
            structs=f['Geometry/Structures/Attributes'][:] if 'Geometry/Structures/Attributes' in f else []
            if len(structs)==0:
                attrs=f['Geometry/Cross Sections/Attributes'][:]
                identities={(a['River'].decode().strip(),a['Reach'].decode().strip()) for a in attrs}
                if len(identities)!=1:raise ValueError('River export requires one reach')
                river,reach=next(iter(identities));rs=None;groups=[]
                result['scope']='ONE_RIVER_ONE_REACH_NO_STRUCTURES'
            elif len(structs)==1:
                river,reach,rs=[structs[0][k].decode().strip() for k in ('River','Reach','RS')]
                groups=[g['Name'].decode().strip() for g in f['Geometry/Structures/Culvert Groups/Attributes'][:]]
                if not groups:raise ValueError('Unsupported non-culvert structure')
            else:raise ValueError('Automatic export supports one reach with zero or one crossing')
        if len(groups)!=len(set(groups)) or len(groups)>10:raise ValueError('Ambiguous or unsupported group list')
        ptext=project.with_suffix('.p01').read_text(encoding='ascii')
        short=next(l.split('=',1)[1].strip() for l in ptext.splitlines() if l.startswith('Short Identifier='))
        title=next(l.split('=',1)[1].strip() for l in ptext.splitlines() if l.startswith('Plan Title='))
        rivers=controller.Output_GetRivers(0,None);reaches=controller.Output_GetReaches(1,0,None)
        if [s.strip() for s in rivers[1]]!=[river] or [s.strip() for s in reaches[2]]!=[reach]:raise ValueError('Native warning scope is not one verified river/reach')
        if groups:
            controller.TableXS(river,reach,rs)
            table=wait(lambda:window('Culvert Output'),'Culvert Output')
            for pi,profile in enumerate(profiles):
                select(table,3,short,[short]);select(table,6,river,[river]);select(table,4,reach,[reach]);select(table,5,rs)
                select(table,8,profile['id'],[p['id'] for p in profiles])
                for gi,group in enumerate(groups):
                    select(table,7,'Culv Group:  '+group,['Culv Group:  '+g for g in groups])
                    header=f"Plan: {short}    {river}    {reach}  RS: {rs}   Culv Group:  {group}   Profile: {profile['id']}"
                    text=clipboard_table(table,header)
                    from .culvert_details import parse
                    path=output/f'profile_{pi+1:02d}_group_{gi+1:02d}.txt'
                    path.write_text(text,encoding='utf-8',newline='')
                    files.append(item(path,'automatic_native_group_export'))
                    parsed=parse(text)
                    trace.append(dict(action='group_export',profile=profile['id'],group=group,header=parsed['header'],file=files[-1]))
            post(table,wc.WM_CLOSE);wait(lambda:not wg.IsWindow(table) or not wg.IsWindowVisible(table),'close table')
        menu(main,'Summary Err,Warn, Notes ...')
        warning=wait(lambda:window('Errors Warnings and Notes for Plan : '+short),'warning window')
        select(warning,2,title,[title]);select(warning,8,river,['(All Rivers)',river]);select(warning,9,reach,['(All Reaches)',reach])
        select(warning,3,'(All Profiles)',['(All Profiles)']+[p['id'] for p in profiles])
        button=control(warning,7,'ThunderRT6CommandButton')
        if wg.GetWindowText(button)!='File ...':raise ValueError('Native File export control changed')
        post(button,wc.BM_CLICK)
        dialog=wait(lambda:window('Enter/Select Output File'),'native File save dialog')
        edit=control(dialog,1001,'Edit');path=output/'warnings.txt'
        if path.exists():raise ValueError('Refusing to overwrite a prior native export')
        send(edit,wc.WM_SETTEXT,0,str(path.resolve()));post(dialog,wc.WM_COMMAND,1)
        wait(lambda:path.exists() and (not wg.IsWindow(dialog) or not wg.IsWindowVisible(dialog)),'native warning file')
        text=path.read_text(encoding='utf-8-sig')
        from .native_warnings import parse
        parsed=parse(text)
        if parsed['plan_label']!=short:raise ValueError('Warning export plan mismatch')
        files.append(item(path,'automatic_native_warning_export'))
        trace.append(dict(action='warning_export',river=river,reach=reach,all_profiles=True,plan=title,counts=parsed['counts'],file=files[-1]))
        post(warning,wc.WM_CLOSE)
        if not intact(sources):raise ValueError('Native input/output changed during export')
        result.update(status='EXPORTED_PENDING_CROSSCHECK',group_tables=len(groups)*len(profiles),warning_scope='ALL_COMPUTED_PROFILES_VERIFIED_SINGLE_REACH',warning_counts=parsed['counts'])
    except Exception as e:
        result.update(status='UNAVAILABLE',error=str(e))
    result['finished_utc']=utc();save(output/'receipt.json',result)
    return result
