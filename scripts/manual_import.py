"""Manual official product XLSX import with explicit shop confirmation."""
import base64,hashlib,json,re,tempfile,uuid,zipfile
from datetime import datetime
from pathlib import Path
from browser_session import dates
from collection_state import BrowserLock,Journal
from report_validation import validate,reconcile

ROOT=Path(__file__).resolve().parents[1]
MODES=('分天数据','汇总数据')

def prepare(request):
    shop=str(request.get('shop','')).strip()
    if not shop or len(shop)>100 or any(s in shop for s in ('模拟','示例')):raise ValueError('请填写真实店铺完整名称')
    start,end=dates(request['start'],request['end'])
    files=request.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=2:raise ValueError('请选择1至2份商品推广XLSX')
    parsed=[];seen=set();total=0
    for item in files:
        name=str(item.get('name',''))
        if len(name)>240 or '/' in name or '\\' in name or not name.lower().endswith('.xlsx'):raise ValueError('只支持官方原始XLSX，请保留文件名')
        try:raw=base64.b64decode(item['content'],validate=True)
        except (ValueError,TypeError,KeyError):raise ValueError('文件编码无效')
        total+=len(raw)
        if not 0<len(raw)<=12*1024*1024 or total>23*1024*1024:raise ValueError('单份最多12MB，批次最多23MB')
        mode=next((m for m in MODES if f'商品推广_{m}_' in name),None)
        if not mode or mode in seen:raise ValueError('只支持商品推广分天和汇总，每种最多一份')
        seen.add(mode)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/name;path.write_bytes(raw)
            try:
                with zipfile.ZipFile(path) as z:
                    if len(z.infolist())>2000 or sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('XLSX解压后过大')
                result=validate(path,start,end,'商品推广',mode)
            except zipfile.BadZipFile:raise ValueError('文件不是完整XLSX')
        parsed.append({'name':name,'mode':mode,'raw':raw,'result':result})
    if len(parsed)==2:reconcile(*(next(p['result'] for p in parsed if p['mode']==m) for m in MODES))
    return shop,start,end,parsed

def preview(request):
    shop,start,end,parsed=prepare(request)
    return {'shop':shop,'start':start,'end':end,'files':[{'name':p['name'],'mode':p['mode'],'sheets':[{'name':s['name'],'rows':s['data_rows'],'fields':len(s['fields'])} for s in p['result']['sheets']]} for p in parsed], 'message':'结构及日期校验通过；店铺归属需本人确认，文件不能证明店铺身份'}

def import_files(request,root=ROOT):
    if request.get('confirmed') is not True:raise ValueError('请先确认文件的店铺、日期及推广类型')
    shop,start,end,parsed=prepare(request);root=Path(root)
    with BrowserLock(root),Journal(root,shop,start,end) as journal:
        if journal.data.get('source')!='manual' and journal.data['tasks']:raise ValueError('该周期已有自动任务，请使用其他独立项目导入，避免混合来源')
        checked={}
        for mode in MODES:
            task=journal.data['tasks'].get('商品推广_'+mode)
            if task:
                if not journal.completed(task):raise ValueError('已有文件尚未校验')
                checked[mode]=validate(journal.directory/task['file'],start,end,'商品推广',mode)
        for p in parsed:
            if p['mode'] in checked and checked[p['mode']]['sha256']!=p['result']['sha256']:raise ValueError('同周期同类型已有不同快照，不覆盖原件')
            checked[p['mode']]=p['result']
        match=reconcile(checked[MODES[0]],checked[MODES[1]]) if len(checked)==2 else {'state':'missing_report','checks':[]}
        added=0;batch=root/'data/imports'/uuid.uuid4().hex
        for p in parsed:
            key='商品推广_'+p['mode']
            if key in journal.data['tasks']:continue
            audit=batch/p['mode'];audit.mkdir(parents=True)
            (audit/'original.xlsx').write_bytes(p['raw'])
            (audit/'import.json').write_text(json.dumps({'shop':shop,'confirmed_by_user':True,'original_name':p['name'],'sha256':p['result']['sha256'],'imported_at':datetime.now().isoformat()},ensure_ascii=False,indent=2),encoding='utf-8')
            target=journal.directory/p['name'];target.write_bytes(p['raw'])
            journal.data['tasks'][key]={'category':'商品推广','mode':p['mode'],'state':'validated','file':target.name,'sha256':p['result']['sha256'],'source':'manual'};added+=1
        journal.data.update(source='manual',state='complete' if len(checked)==2 else 'partial',reconciliation=match)
        journal.save()
        return {'message':f'导入完成：新增{added}份，本周期已有{len(checked)}/2份。'+('分天与汇总对账通过' if match['state']=='matched' else '缺少另一份，尚未交叉对账'), 'id':journal.directory.relative_to(root/'data/reports').as_posix()}
