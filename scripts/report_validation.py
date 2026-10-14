"""Validate official exports locally; never infer shop identity from filenames."""
import hashlib
import re
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import openpyxl

METRICS = ('成交花费(元)', '总花费(元)', '交易额(元)', '净交易额(元)',
           '成交笔数', '曝光量', '点击量')


def number(value):
    if value is None or str(value).strip() in ('', '-', '--'):
        return None
    try:
        result=Decimal(str(value).replace(',', ''))
        if not result.is_finite():raise ValueError('基础指标包含非有限数值')
        return result
    except InvalidOperation as exc:
        raise ValueError('基础指标不是有效数字') from exc


def validate(path, start, end, category, mode):
    path = Path(path)
    start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    token = start_date.strftime('%Y%m%d') + '至' + end_date.strftime('%Y%m%d')
    expected = f'{category}_{mode}_{token}'
    if path.suffix.lower() != '.xlsx' or expected not in path.stem:
        raise ValueError('文件名与请求报表、维度或日期不符')
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip():raise ValueError('XLSX文件完整性检查失败')
    except zipfile.BadZipFile as exc:raise ValueError('文件不是完整XLSX，保留原件待核验') from exc
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    result = {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'start': start, 'end': end, 'category': category, 'mode': mode,
              'shop_verified': False, 'sheets': []}
    try:
        for sheet in workbook:
            if not sheet.title.endswith(f'_{mode}_{token}'):
                raise ValueError('工作表日期或维度与请求不符')
            sheet.reset_dimensions()
            rows = [list(row) for row in sheet.values if any(v is not None for v in row)]
            if not rows:
                raise ValueError('工作表缺少表头')
            header = rows[0]
            if category == '商品推广' and sheet.title.startswith('商品_'):
                if not {'商品ID', '推广场景', *METRICS}.issubset(header):
                    raise ValueError('商品推广字段不完整')
            detail, totals, notes = [], [], []
            seen_dates = set()
            for row in rows[1:]:
                first = str(row[0] or '')
                if first.startswith('注：') or first.startswith('注:'):
                    notes.append(first)
                elif first == '总计':
                    totals.append(row)
                elif first:
                    if mode == '分天数据':
                        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', first):
                            raise ValueError('分天明细日期格式未知')
                        parsed = date.fromisoformat(first)
                        if not start_date <= parsed <= end_date:
                            raise ValueError('明细日期超出请求区间')
                        seen_dates.add(first)
                    detail.append(row)
            if len(totals) > 1:
                raise ValueError('工作表有重复总计')
            sums, official, unavailable = {}, {}, []
            for metric in METRICS:
                if metric not in header:
                    continue
                index = header.index(metric)
                values = [number(row[index]) for row in detail]
                if any(v is None for v in values):
                    unavailable.append(metric)
                    continue
                sums[metric] = str(sum(values, Decimal(0)))
                if totals:
                    total = number(totals[0][index])
                    if total is None:
                        unavailable.append(metric)
                    else:
                        official[metric] = str(total)
                        if abs(Decimal(sums[metric]) - total) > Decimal('0.01'):
                            raise ValueError(f'{sheet.title}: {metric}明细与总计不一致')
            if mode == '分天数据' and sheet.title.startswith('汇总数据_'):
                if len(seen_dates) != (end_date - start_date).days + 1:
                    raise ValueError('每日汇总缺少完整自然日')
            result['sheets'].append({'name': sheet.title, 'fields': header,
                'data_rows': len(detail), 'dates': sorted(seen_dates), 'notes': notes,
                'sums': sums, 'official_totals': official, 'unavailable': unavailable,
                'empty': not detail})
    finally:
        workbook.close()
    required = {'商品推广': {'商品'}, '直播推广': {'直播间'}, '明星店铺': {'品牌词', '创意'}}[category]
    if mode == '分天数据':
        required = required | {'汇总数据'}
    elif category == '直播推广':
        required = required | {'直播场次'}
    if not required.issubset({s['name'].split('_')[0] for s in result['sheets']}):
        raise ValueError('缺少所选数据范围工作表')
    result['state'] = 'validated_local'
    return result


def reconcile(daily, summary):
    if (daily['start'], daily['end'], daily['category']) != (summary['start'], summary['end'], summary['category']):
        raise ValueError('对账报表范围不一致')
    if daily['mode'] != '分天数据' or summary['mode'] != '汇总数据':
        raise ValueError('对账需要分天和汇总报表')
    checks = []
    if daily['category']=='商品推广':
        overview=next(s for s in daily['sheets'] if s['name'].startswith('汇总数据_'))
        product=next(s for s in daily['sheets'] if s['name'].startswith('商品_'))
        for metric in METRICS:
            if metric in overview['unavailable'] or metric in product['unavailable']:continue
            if metric in overview['sums'] and metric in product['sums']:
                if abs(Decimal(overview['sums'][metric])-Decimal(product['sums'][metric]))>Decimal('0.01'):
                    raise ValueError(f'{metric}：每日汇总与商品日明细不一致')
    for sheet in summary['sheets']:
        dimension = sheet['name'].split('_')[0]
        match = next((s for s in daily['sheets'] if s['name'].split('_')[0] == dimension), None)
        if match is None:
            continue  # Summary-only live session dimension has no daily counterpart.
        for metric in METRICS:
            if metric in sheet['unavailable'] or metric in match['unavailable']:
                continue
            if metric in sheet['sums'] and metric in match['sums']:
                if abs(Decimal(sheet['sums'][metric]) - Decimal(match['sums'][metric])) > Decimal('0.01'):
                    raise ValueError(f'{dimension}: {metric}分天与汇总不一致')
                checks.append({'dimension': dimension, 'metric': metric, 'value': sheet['sums'][metric]})
    return {'state': 'matched' if checks else 'no_comparable_metrics', 'checks': checks}
