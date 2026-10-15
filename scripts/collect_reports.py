"""Visible official UI only. Human login/verification; no advertising mutations."""
import argparse
import asyncio
import re
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path

from browser_session import dates
from collection_state import Journal, BrowserLock
from report_validation import validate, reconcile
from launch_browser import owned

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://yingxiao.pinduoduo.com/tools/report/download'


async def human(journal, message):
    journal.data.update(state='paused', message=message)
    journal.save()
    print(message + '\n完成后输入 continue；输入 quit 停止，进度保留。', flush=True)
    answer = await asyncio.to_thread(input)
    if answer.strip() != 'continue':
        raise RuntimeError('用户停止或未确认继续')
    journal.data.update(state='running', message='人工处理后重新核对')
    journal.save()


async def guard(page, journal):
    while True:
        control=journal.directory/'control.json'
        if control.exists():
            request=json.loads(control.read_text(encoding='utf-8'))
            control.unlink()
            if request.get('action')=='quit':raise RuntimeError('用户请求停止，已在安全检查点保留进度')
            if request.get('action')=='pause':await human(journal,'已在安全检查点暂停；当前操作已结束，进度保留')
        try:
            await page.get_by_text(journal.shop, exact=True).wait_for(state='visible', timeout=10000)
        except Exception:
            pass
        text = await page.locator('body').inner_text()
        if re.search(r'拖动.*滑块|安全验证|请完成验证|请输入验证码|短信验证码', text):
            await human(journal, '检测到验证；自动操作已暂停，请人工完成')
            continue
        if not await page.get_by_text(journal.shop, exact=True).count():
            await human(journal, '未确认目标店铺，请登录正确店铺并进入报表下载页')
            continue
        if '/tools/report/download' not in page.url or not await page.get_by_role('button', name='生成报表', exact=True).count():
            await human(journal, '请进入官方报表下载页')
            continue
        return


def task_name(journal, category, mode):
    token = journal.start.replace('-', '') + '至' + journal.end.replace('-', '')
    return f'{category}_{mode}_{token}'


async def find_row(page, name):
    rows = page.get_by_role('row').filter(has=page.get_by_role('cell', name=name, exact=True))
    count = await rows.count()
    if count > 1:
        raise RuntimeError('同名任务不唯一，请人工核对')
    return rows if count == 1 else None


async def turn_page(page, button):
    before = await page.get_by_role('row').all_inner_texts()
    await button.click(timeout=5000)
    for _ in range(40):
        await asyncio.sleep(0.25)
        if await page.get_by_role('row').all_inner_texts() != before:
            return
    raise RuntimeError('翻页后列表没有变化，停止而不推断任务缺失')


async def scan_task(page, journal, name):
    await guard(page, journal)
    buttons = page.locator('button.anq-pagination-item-link')
    if await buttons.count() != 2:
        raise RuntimeError('分页控件未知，无法安全判断任务缺失')
    for _ in range(100):
        if await buttons.first.is_disabled():
            break
        await guard(page, journal)
        await turn_page(page, buttons.first)
    else:
        raise RuntimeError('列表超过分页扫描上限')
    matched_page = None
    pages = 0
    for index in range(100):
        await guard(page, journal)
        if await find_row(page, name) is not None:
            if matched_page is not None:
                raise RuntimeError('跨页发现同名任务，停止供人工核对')
            matched_page = index
        pages += 1
        if await buttons.last.is_disabled():
            break
        await turn_page(page, buttons.last)
    else:
        raise RuntimeError('列表超过分页扫描上限')
    if matched_page is None:
        print(f'已扫描{pages}页，未找到目标任务：{name}', flush=True)
        return None
    for _ in range(pages - 1 - matched_page):
        await guard(page, journal)
        await turn_page(page, buttons.first)
    return await find_row(page, name)


async def prepare(page, journal, mode):
    from playwright.async_api import expect
    await guard(page, journal)
    radio = page.get_by_role('radio', name=mode, exact=True)
    if not await radio.is_checked():
        await page.locator('label').filter(has=radio).click()
    await expect(radio).to_be_checked(timeout=5000)
    begin = page.get_by_role('textbox', name='开始日期', exact=True)
    finish = page.get_by_role('textbox', name='结束日期', exact=True)
    await select_calendar_date(page, begin, journal.start)
    await select_calendar_date(page, finish, journal.end)
    await page.get_by_text('报表生成条件', exact=True).click()
    if await begin.input_value() != journal.start.replace('-', '/') or await finish.input_value() != journal.end.replace('-', '/'):
        raise RuntimeError('后台日期读回不一致，未提交')
    clear = page.get_by_role('button', name='清空', exact=True)
    if 'disabled' not in (await clear.get_attribute('class') or ''):
        await clear.click()
        await expect(page.get_by_role('checkbox', name='推广商品', exact=True)).not_to_be_checked(timeout=5000)
    checkbox = page.get_by_role('checkbox', name='商品推广', exact=True)
    await page.locator('label').filter(has=checkbox).click()
    await expect(page.get_by_role('checkbox', name='推广商品', exact=True)).to_be_checked(timeout=5000)
    if mode == '分天数据':
        selected = page.get_by_role('checkbox', name='数据汇总', exact=True)
        if await selected.count() != 3:
            raise RuntimeError('商品每日汇总范围未确认，未提交')
        await expect(selected.nth(0)).to_be_checked(timeout=5000)


async def select_calendar_date(page, field, value):
    await field.click(timeout=5000)
    target_month = datetime.strptime(value, '%Y-%m-%d')
    for _ in range(120):
        year = page.locator('button.anq-picker-year-btn').filter(visible=True).first
        month = page.locator('button.anq-picker-month-btn').filter(visible=True).first
        y = int(re.search(r'\d+', await year.inner_text()).group())
        m = int(re.search(r'\d+', await month.inner_text()).group())
        offset = (target_month.year - y) * 12 + target_month.month - m
        if offset == 0:
            cell = page.locator(f'td.anq-picker-cell-in-view[title="{value}"]').filter(visible=True)
            if await cell.count() != 1 or 'disabled' in (await cell.get_attribute('class') or ''):
                raise RuntimeError('目标日期不可选择，未提交')
            await cell.click(timeout=5000)
            return
        direction = 'prev' if offset < 0 else 'next'
        await page.locator(f'button.anq-picker-header-{direction}-btn').filter(visible=True).first.click(timeout=5000)
    raise RuntimeError('日期超出可导航范围，未提交')


async def collect(page, journal, mode, args):
    category = '商品推广'
    task = journal.task(category, mode)
    if task.get('state') == 'downloading' and not task.get('file'):
        raise RuntimeError('上次下载点击结果不确定；先核对浏览器实际文件，不自动重复下载')
    if journal.completed(task):
        print(mode + '：文件重新校验通过，跳过', flush=True)
        return validate(journal.directory / task['file'], journal.start, journal.end, category, mode)
    await guard(page, journal)
    name = task_name(journal, category, mode)
    row = await scan_task(page, journal, name)
    if row is None:
        if row is None:
            if task['state'] != 'pending':
                raise RuntimeError('曾提交任务未找到，停止以避免重复生成')
            if not args.generate:
                raise RuntimeError('任务未找到；默认仅下载已有任务，使用 --generate 才允许生成')
            await prepare(page, journal, mode)
            # Reconcile once more immediately before submission.
            if await scan_task(page, journal, name) is not None:
                raise RuntimeError('提交前发现目标任务已出现，停止以避免重复生成')
            task.update(state='submitting', official_name=name)
            journal.save()  # Commit uncertain state BEFORE click; never retry submission blindly.
            await guard(page, journal)
            await page.get_by_role('button', name='生成报表', exact=True).click()
            print(mode + '：已点击生成，等待官方任务，不重复提交', flush=True)
            await page.wait_for_timeout(1500)
    task.update(state='waiting', official_name=name)
    journal.save()
    deadline = asyncio.get_running_loop().time() + args.timeout
    interval = 3
    while True:
        await guard(page, journal)
        row = await find_row(page, name)
        if row is None:
            row = await scan_task(page, journal, name)
        if row is not None:
            if await row.get_by_role('cell', name='已生成', exact=True).count():
                break
            if '生成失败' in await row.inner_text():
                raise RuntimeError('官方任务生成失败，保留任务供诊断')
        if asyncio.get_running_loop().time() >= deadline:
            await human(journal, '报表等待超时，请核对官方任务；不重复提交')
            deadline = asyncio.get_running_loop().time() + args.timeout
        await asyncio.sleep(interval)
        interval = min(interval * 1.5, 30)
        # The official page may update in place. Never refresh while verification is active.
        await guard(page, journal)
        if interval >= 10:
            await page.reload(wait_until='domcontentloaded')
    await guard(page, journal)
    task['state'] = 'downloading'
    journal.save()
    async with page.expect_download(timeout=60000) as pending:
        await row.get_by_role('button', name='下载', exact=True).click()
    download = await pending.value
    filename = download.suggested_filename
    if Path(filename).name != filename or task_name(journal, category, mode) not in filename:
        raise RuntimeError('下载文件名不符合目标任务')
    destination = journal.directory / filename
    if destination.exists():
        destination = journal.directory / (datetime.now().strftime('%H%M%S_%f_') + filename)
    task.update(file=destination.name, state='saving')
    journal.save()
    await download.save_as(destination)
    task['state'] = 'needs_validation'
    journal.save()
    result = validate(destination, journal.start, journal.end, category, mode)
    task.update(state='validated', file=destination.name, sha256=result['sha256'], shop_checked_on_page=True)
    journal.save()
    print(mode + '：下载及本地校验通过', flush=True)
    await asyncio.sleep(args.interval)
    return result


async def run(args):
    from playwright.async_api import async_playwright
    start, end = dates(args.start, args.end)
    with BrowserLock(ROOT), Journal(ROOT, args.shop, start, end) as journal:
        if journal.data.get('source')=='manual':raise ValueError('人工导入周期请继续人工补齐，不混合自动任务')
        async with async_playwright() as playwright:
            profile = Path(os.environ['LOCALAPPDATA']) / 'PddReportDownloader' / 'browser-profile-chrome'
            if args.attach:
                record = json.loads((ROOT / 'data/browser-launch.json').read_text(encoding='utf-8'))
                port, pid = int(record['port']), int(record['pid'])
                if Path(record['profile']) != profile or not 1 <= port <= 65535:
                    raise RuntimeError('浏览器登录目录或端口不匹配')
                if not owned(record):
                    raise RuntimeError('专用Chrome已退出，请先运行启动器')
                # Verify the listener belongs to the exact process launched by us.
                check = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                    f'$l=Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction Stop; '
                    f'if (@($l).Count -ne 1 -or $l.LocalAddress -ne "127.0.0.1" -or $l.OwningProcess -ne {pid}) {{exit 1}}; '
                    f'$p=Get-Process -Id {pid} -ErrorAction Stop; if ($p.ProcessName -ne "chrome") {{exit 1}}'],
                    capture_output=True)
                if check.returncode:
                    raise RuntimeError('本机CDP端口归属未通过核验，不连接')
                artifacts = journal.directory / 'download-staging'
                artifacts.mkdir(exist_ok=True)
                browser = await playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}',
                    is_local=True, artifacts_dir=artifacts)
                cdp = await browser.new_browser_cdp_session()
                await cdp.send('Browser.setDownloadBehavior', {'behavior': 'allowAndName',
                    'downloadPath': str(artifacts.resolve()), 'eventsEnabled': True})
                if len(browser.contexts) != 1:
                    raise RuntimeError('浏览器上下文不唯一，不选择首个上下文继续')
                context = browser.contexts[0]
                matching = [p for p in context.pages if p.url.startswith('https://yingxiao.pinduoduo.com/')]
                if len(matching) != 1:
                    raise RuntimeError('目标后台标签页不唯一，请只保留一个推广后台页面')
                page = matching[0]
            else:
                context = await playwright.chromium.launch_persistent_context(str(profile), channel='chrome',
                    headless=False, accept_downloads=True, viewport={'width': 1440, 'height': 950})
                page = context.pages[0] if context.pages else await context.new_page()
            try:
                # Start at the official entry so unauthenticated deep-link redirects
                # are not imposed on the user's manual login flow.
                if args.attach:
                    await page.goto(URL, wait_until='domcontentloaded')
                else:
                    await page.goto('https://yingxiao.pinduoduo.com/', wait_until='domcontentloaded')
                await guard(page, journal)
                journal.data['state'] = 'running'
                journal.save()
                if journal.data.get('source')=='manual':raise ValueError('人工导入周期请继续人工补齐，不混合自动任务')
                daily = await collect(page, journal, '分天数据', args)
                summary = await collect(page, journal, '汇总数据', args)
                journal.data.update(state='complete', reconciliation=reconcile(daily, summary))
                journal.save()
                print('商品推广分天与汇总完成并对账：' + str(journal.path), flush=True)
            except Exception as exc:
                journal.data.update(state='needs_attention', message=str(exc))
                journal.save()
                raise
            finally:
                if not args.attach:
                    await context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--shop', required=True, help='后台完整店铺名称，执行前核对')
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--generate', action='store_true', help='允许生成缺失任务，默认仅下载已有任务')
    parser.add_argument('--attach', action='store_true', default=True, help='默认连接已核验的普通专用Chrome')
    parser.add_argument('--direct-launch', action='store_false', dest='attach', help='仅诊断：直接由Playwright启动，可能出现登录兼容问题')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--interval', type=float, default=5)
    asyncio.run(run(parser.parse_args()))
