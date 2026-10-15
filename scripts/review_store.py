"""Local versioned reviews; evidence is generated from verified data and immutable."""
import json
import shutil
import threading
import uuid
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
from dashboard_data import dataset


def aggregate(rows,fields,official=None):
    official=official or {}; result={}
    for f in fields:
        values=[r.get(f['key']) for r in rows]
        if f['kind']=='sum':result[f['key']]=None if not values or any(v is None for v in values) else sum(round(v*100) for v in values)/100
        elif f['kind']=='source':result[f['key']]=official.get(f['key'],values[0] if len(values)==1 else None)
    for f in fields:
        if f['kind']=='ratio':
            a,b,factor=f['ratio'];result[f['key']]=result[a]/result[b]*factor if result.get(a) is not None and result.get(b) and result[b]>0 else None
    return result


def snapshot(request):
    data=dataset(request['batch'])
    if data['demo']:raise ValueError('模拟数据不能写入真实店铺复盘')
    if data.get('partial') or data.get('reconciled') is False:raise ValueError('缺少完整分天与汇总对账，不写入正式复盘')
    start,end=request['start'],request['end']
    date.fromisoformat(start);date.fromisoformat(end)
    if not data['start']<=start<=end<=data['end']:raise ValueError('证据日期超出报表范围')
    fields=data['metricFields'];subject=request.get('subject')
    daily=[r for r in data['daily'] if start<=r['date']<=end]
    products=[r for r in data['products'] if start<=r['date']<=end]
    complete=start==data['start'] and end==data['end']
    if subject:
        identity=['id','scene','promotion','bid','group']
        if set(subject)!=set(identity):raise ValueError('证据主体字段无效')
        products=[r for r in products if all(r[k]==subject[k] for k in identity)]
        if not products:raise ValueError('所选主体在当前日期没有有效记录')
        official=next((r for r in data['officialProducts'] if all(r[k]==subject[k] for k in identity)),{}) if complete else {}
        metrics=aggregate(products,fields,official)
        title=products[0]['name']
    else:
        metrics=aggregate(daily,fields,data['officialOverview'] if complete else {})
        headers=data['rawReports'][0]['sheets'][0]['fields'];detail=aggregate(products,fields)
        for f in fields:
            if f['name'] not in headers:metrics[f['key']]=detail.get(f['key'])
        title='整体概览'
    return {'shop':data['shop'],'batch':data['id'],'start':start,'end':end,'subject':subject,
            'title':title,'metrics':metrics,'sources':data['sources'],'captured_at':datetime.now(timezone(timedelta(hours=8))).isoformat()}


class ReviewStore:
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/'reviews.json';self.lock=threading.RLock()

    def read(self):
        with self.lock:
            if not self.path.exists():return {'version':0,'items':[]}
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data.get('version'),int) or not isinstance(data.get('items'),list):raise ValueError('复盘文件损坏或版本未知，不重置数据')
            return data

    def save(self,payload):
        with self.lock:
            data=self.read()
            if payload.get('version')!=data['version']:raise ValueError('复盘已被其他窗口修改，请保留草稿并重新读取')
            fields=('title','discovery','action','status','executed_on','review_on','result','archived')
            item_id=payload.get('id')
            item=next((r for r in data['items'] if r['id']==item_id),None) if item_id else None
            if item_id and item is None:raise ValueError('复盘记录不存在')
            if not str(payload.get('title','')).strip():raise ValueError('请填写复盘标题')
            if payload.get('status') not in ('pending','observing','reviewed'):raise ValueError('复盘状态无效')
            for field in ('executed_on','review_on'):
                if payload.get(field):date.fromisoformat(payload[field])
            if item is None:
                evidence=snapshot(payload['snapshot']) if payload.get('snapshot') else None
                shop=evidence['shop'] if evidence else str(payload.get('shop','')).strip()
                if not shop or '模拟' in shop or '示例' in shop:raise ValueError('请指定真实店铺，模拟记录不进入正式复盘')
                item={'id':uuid.uuid4().hex,'shop':shop,'evidence':evidence,'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat()}
                data['items'].append(item)
            elif payload.get('snapshot'):raise ValueError('已有复盘的指标证据不可改写；请新建复盘')
            for field in fields:
                value=payload.get(field,False if field=='archived' else '')
                if field=='archived' and not isinstance(value,bool):raise ValueError('归档状态无效')
                if field!='archived' and (not isinstance(value,str) or len(value)>10000):raise ValueError('复盘字段长度或类型无效')
                item[field]=value
            item['updated_at']=datetime.now(timezone(timedelta(hours=8))).isoformat()
            data['version']+=1
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            if self.path.exists():shutil.copy2(self.path,self.directory/'reviews.previous.json')
            temp.replace(self.path)
            return data
