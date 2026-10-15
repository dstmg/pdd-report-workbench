"""Read validated local exports into a dashboard without changing originals."""
import json
from decimal import Decimal
from pathlib import Path
import openpyxl
from report_validation import validate, reconcile, number
from metrics_catalog import catalog, mapped

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'spend': '总花费(元)', 'conversionSpend': '成交花费(元)', 'revenue': '交易额(元)',
          'netRevenue': '净交易额(元)', 'orders': '成交笔数', 'impressions': '曝光量', 'clicks': '点击量'}


def records(path):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    result = {}
    try:
        for sheet in workbook:
            sheet.reset_dimensions()
            rows = [list(row) for row in sheet.values if any(v is not None for v in row)]
            header = rows[0]
            result[sheet.title.split('_')[0]] = [dict(zip(header, row)) for row in rows[1:]
                if row[0] and str(row[0]) != '总计' and not str(row[0]).startswith('注')]
    finally:
        workbook.close()
    return result


def raw_report(path):
    book=openpyxl.load_workbook(path,read_only=True,data_only=True)
    result=[]
    try:
        for sheet in book:
            sheet.reset_dimensions()
            rows=[list(row) for row in sheet.values if any(v is not None for v in row)]
            result.append({'name':sheet.title,'fields':rows[0],'rows':rows[1:]})
    finally:
        book.close()
    return result


def metrics(row):
    return {key: float(value) if (value := number(row.get(field))) is not None else None
            for key, field in FIELDS.items()}


def batches():
    result = []
    for path in (ROOT / 'data/reports').glob('*/*/collection.json'):
        try:
            journal = json.loads(path.read_text(encoding='utf-8'))
            result.append({'id': str(path.parent.relative_to(ROOT / 'data/reports')).replace('\\', '/'),
                'shop': journal['shop'], 'start': journal['start'], 'end': journal['end'],
                'state': journal['state'], 'tasks': [{'mode': t['mode'], 'state': t['state']}
                    for t in journal['tasks'].values()], 'updated': path.stat().st_mtime})
        except (ValueError, KeyError):
            continue
    real=sorted(result, key=lambda x: (x['end'], x['start']), reverse=True)
    demo_paths={path.name:path for path in (ROOT/'examples/demo').glob('*.json')}
    demo_paths.update({path.name:path for path in (ROOT/'data/demo').glob('*.json')})
    for path in demo_paths.values():
        demo=json.loads(path.read_text(encoding='utf-8'))
        real.append({k:demo[k] for k in ('id','shop','start','end','category','demo')} | {'state':'demo'})
    return real


def dataset(batch_id):
    if batch_id in ('demo-live','demo-brand'):
        path=ROOT/'data/demo'/f'{batch_id}.json'
        if not path.exists():path=ROOT/'examples/demo'/f'{batch_id}.json'
        result=json.loads(path.read_text(encoding='utf-8'))
        if result.get('demo') is not True:raise ValueError('演示文件缺少模拟标记')
        return result
    base = (ROOT / 'data/reports').resolve()
    directory = (base / batch_id).resolve()
    if not directory.is_relative_to(base) or directory == base:
        raise ValueError('无效批次路径')
    journal = json.loads((directory / 'collection.json').read_text(encoding='utf-8'))
    if journal['state'] not in ('complete','partial'):
        raise ValueError('该批次尚未完成校验')
    sources, checked = [], {}
    for mode in ('分天数据', '汇总数据'):
        task = journal['tasks'].get(f'商品推广_{mode}')
        if not task:continue
        path = (directory / task['file']).resolve()
        if path.parent != directory or task['state'] != 'validated':
            raise ValueError('报表路径或任务状态无效')
        result = validate(path, journal['start'], journal['end'], '商品推广', mode)
        if result['sha256'] != task['sha256']:
            raise ValueError('源文件已变化，请重新核验')
        checked[mode] = result
        sources.append({'mode': mode, 'file': path.name, 'bytes': path.stat().st_size,
            'sha256': result['sha256'], 'sheets': [{'name': s['name'], 'rows': s['data_rows'], 'empty': s['empty']}
                for s in result['sheets']]})
    checks = reconcile(checked['分天数据'], checked['汇总数据']) if len(checked)==2 else {'state':'missing_report','checks':[]}
    if not checked:raise ValueError('没有已校验报表')
    partial=len(checked)<2
    if '分天数据' not in checked:
        task=journal['tasks']['商品推广_汇总数据'];raw=raw_report(directory/task['file'])
        return {'id':batch_id,'shop':journal['shop'],'start':journal['start'],'end':journal['end'],'category':'商品推广','demo':False,'partial':True,'hasDaily':False,'reconciled':False,'checks':0,'daily':[],'products':[],'sources':sources,'notes':['仅有汇总文件：可查看原始工作表；缺分天数据，不能展示日趋势或进行交叉对账'],'metricFields':catalog(next(s['fields'] for s in raw if s['name'].startswith('商品_'))),'officialProducts':[],'officialOverview':{},'rawReports':[{'mode':'汇总数据','sheets':raw}]}
    daily_file = directory / journal['tasks']['商品推广_分天数据']['file']
    tables = records(daily_file)
    raw_daily=raw_report(daily_file)
    raw_summary=raw_report(directory / journal['tasks']['商品推广_汇总数据']['file']) if not partial else []
    definitions=catalog(next(s['fields'] for s in raw_daily if s['name'].startswith('商品_')))
    daily = [{'date': row['日期'], **mapped(row,definitions)} for row in tables['汇总数据']]
    products = []
    for row in tables['商品']:
        products.append({'date': row['日期'], 'id': str(row['商品ID']), 'name': str(row['商品名称']),
            'scene': str(row.get('推广场景') or ''), 'promotion': str(row.get('推广名称') or ''),
            'bid': str(row.get('出价方式') or ''), 'group': str(row.get('分组') or ''),
            'deleted': str(row.get('是否已删除') or ''), **mapped(row,definitions)})
    product_totals=records(directory / journal['tasks']['商品推广_汇总数据']['file'])['商品'] if not partial else []
    official=[{'id':str(row['商品ID']), 'scene':str(row.get('推广场景') or ''),
        'promotion':str(row.get('推广名称') or ''),'bid':str(row.get('出价方式') or ''),
        'group':str(row.get('分组') or ''),**mapped(row,definitions)} for row in product_totals]
    overview_sheet=next(s for s in raw_daily if s['name'].startswith('汇总数据_'))
    total_row=next((dict(zip(overview_sheet['fields'],r)) for r in overview_sheet['rows'] if r[0]=='总计'),{})
    notes = list(dict.fromkeys(n for s in checked['分天数据']['sheets'] for n in s['notes']))
    return {'id': batch_id, 'shop': journal['shop'], 'start': journal['start'], 'end': journal['end'],
        'daily': daily, 'products': products, 'sources': sources, 'notes': notes,
        'metricFields':definitions,'officialProducts':official,'officialOverview':mapped(total_row,definitions),
        'rawReports':[{'mode':'分天数据','sheets':raw_daily},{'mode':'汇总数据','sheets':raw_summary}],
        'category':'商品推广','demo':False,'partial':partial,'hasDaily':True,
        'reconciled': checks['state'] == 'matched', 'checks': len(checks['checks'])}
