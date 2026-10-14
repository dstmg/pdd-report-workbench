"""Independent visible PDD browser; capture original exports, never credentials."""
import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def dates(start=None, end=None):
    finish = date.fromisoformat(end) if end else date.today() - timedelta(days=1)
    begin = date.fromisoformat(start) if start else finish - timedelta(days=6)
    if begin > finish or finish >= date.today():
        raise ValueError('起始日期不能晚于结束日期；首轮仅支持完整自然日')
    return begin.isoformat(), finish.isoformat()

def inspect_file(path):
    """Structural inspection only. Shop/date/fields require a verified report schema."""
    suffix = path.suffix.lower()
    if suffix == '.xlsx':
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            # Official PDD exports may incorrectly declare their dimension as A1.
            # Ignore that metadata and inspect the actual streamed worksheet cells.
            sheets = []
            for sheet in book.worksheets:
                sheet.reset_dimensions()
                rows = 0
                columns = 0
                for row in sheet.iter_rows(values_only=True):
                    if any(value is not None for value in row):
                        rows += 1
                        columns = max(columns, len(row))
                sheets.append({'name': sheet.title, 'rows': rows, 'columns': columns})
        finally:
            book.close()
        if not any((s['rows'] or 0) > 1 for s in sheets):
            raise ValueError('没有可检查的数据行')
        return {'format': 'xlsx', 'sheets': sheets}
    if suffix == '.xls':
        import xlrd
        book = xlrd.open_workbook(path)
        sheets = [{'name': s.name, 'rows': s.nrows, 'columns': s.ncols} for s in book.sheets()]
        if not any(s['rows'] > 1 for s in sheets):
            raise ValueError('没有可检查的数据行')
        return {'format': 'xls', 'sheets': sheets}
    if suffix == '.csv':
        import csv
        raw = path.read_bytes()
        try:
            content = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            content = raw.decode('gb18030')
        if content.lstrip().lower().startswith(('<!doctype', '<html')):
            raise ValueError('下载内容是网页而非报表')
        rows = list(csv.reader(content.splitlines()))
        if len(rows) < 2 or len(rows[0]) < 2:
            raise ValueError('CSV缺少表头或数据行')
        return {'format': 'csv', 'rows': len(rows), 'columns': len(rows[0])}
    raise ValueError('尚未适配的文件格式，保留原文件待核验')

async def run(args):
    from playwright.async_api import async_playwright
    start, end = dates(args.start, args.end)
    batch = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    directory = ROOT / 'data' / 'reports' / f'{start}_{end}' / batch
    directory.mkdir(parents=True)
    journal = {'batch': batch, 'requested_start': start, 'requested_end': end,
               'report': args.report, 'state': 'needs_login', 'downloads': [],
               'note': '日期是请求参数，尚未证明已在后台选择；未通过店铺/日期/字段校验'}
    manifest = directory / 'manifest.json'
    atomic_json(manifest, journal)
    pending = set()

    async def save(download):
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', download.suggested_filename).rstrip('. ')
        target = directory / (datetime.now().strftime('%H%M%S_%f_') + (name or 'export'))
        entry = {'file': target.name, 'state': 'saving'}
        journal['downloads'].append(entry)
        atomic_json(manifest, journal)
        try:
            await download.save_as(target)
            if not target.exists() or not target.stat().st_size:
                raise ValueError('下载为空')
            entry.update(bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            duplicate = any(x is not entry and x.get('sha256') == entry['sha256'] for x in journal['downloads'])
            entry.update(structure=inspect_file(target), duplicate=duplicate, state='needs_validation')
            print('原文件已保存，店铺/日期/字段待核验：' + str(target), flush=True)
        except Exception as exc:
            entry.update(state='error', error=str(exc))
            print('文件保留，校验未通过：' + str(exc), flush=True)
        finally:
            journal['state'] = 'needs_validation'
            atomic_json(manifest, journal)

    def capture(download):
        task = asyncio.create_task(save(download))
        pending.add(task)
        task.add_done_callback(pending.discard)

    profile = Path(os.environ['LOCALAPPDATA']) / 'PddReportDownloader' / 'browser-profile-chrome'
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(profile), channel='chrome',
                    headless=False, accept_downloads=True, viewport={'width': 1440, 'height': 950})
        for page in context.pages:
            page.on('download', capture)
        context.on('page', lambda page: page.on('download', capture))
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto('https://yingxiao.pinduoduo.com/', wait_until='domcontentloaded')
        print(f'独立采集浏览器已打开。请求日期：{start} 至 {end}。请人工登录并进入报表页。', flush=True)
        print('命令：observe 查看页面，quit 退出。当前仅监听官方手动导出，自动导出待页面适配。', flush=True)
        try:
            while True:
                command = (await asyncio.to_thread(input)).strip()
                if command == 'quit':
                    break
                if command == 'observe':
                    for page in context.pages:
                        if not page.is_closed() and 'pinduoduo.com' in page.url:
                            print(json.dumps({'title': await page.title(), 'text': (await page.locator('body').inner_text())[:14000]}, ensure_ascii=False), flush=True)
        finally:
            if pending:
                await asyncio.gather(*list(pending))
            await context.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', help='YYYY-MM-DD')
    parser.add_argument('--end', help='YYYY-MM-DD')
    parser.add_argument('--report', default='推广概况（待核对官方名称）')
    asyncio.run(run(parser.parse_args()))
