"""Isolated calculator UI and shortcut file tests, without merchant data."""
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright,expect
from test_clean_start import RUNTIME

ROOT=Path(__file__).resolve().parents[1]

async def main():
    with tempfile.TemporaryDirectory() as directory:
        target=Path(directory);(target/'scripts').mkdir();desktop=target/'Desktop';desktop.mkdir()
        for name in RUNTIME:shutil.copy2(ROOT/'scripts'/name,target/'scripts'/name)
        for folder in ('web','examples'):shutil.copytree(ROOT/folder,target/folder)
        for name in ('create-desktop-shortcut.ps1','start-workbench.ps1'):shutil.copy2(ROOT/name,target/name)
        command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(target/'create-desktop-shortcut.ps1'),'-DesktopDirectory',str(desktop)]
        for _ in range(2):subprocess.run(command,check=True,capture_output=True)
        assert (desktop/'PDD Workbench.lnk').is_file()
        env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1');env.pop('PDD_REVIEW_DIR',None)
        process=subprocess.Popen([sys.executable,str(target/'scripts/serve_workbench.py'),'--port','0'],cwd=target,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        try:
            port=re.search(r'127\.0\.0\.1:(\d+)',process.stdout.readline()).group(1)
            async with async_playwright() as p:
                browser=await p.chromium.launch(channel='chrome',headless=True)
                try:
                    page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    await page.goto('http://127.0.0.1:'+port)
                    await page.locator('[data-view="calculator"]').click()
                    await expect(page.locator('#calculator')).to_be_visible()
                    await expect(page.locator('.toolbar')).to_be_hidden()
                    await expect(page.locator('#sku-demo-label')).to_be_visible()
                    assert await page.locator('#sku-table tbody tr').count()==8
                    await expect(page.locator('#sku-current-daily')).to_contain_text('63.00')
                    await page.locator('#sku-table tbody tr').first.get_by_role('button',name='删除',exact=True).click()
                    assert await page.locator('#sku-table tbody tr').count()==7
                    await page.locator('#sku-undo').click()
                    assert await page.locator('#sku-table tbody tr').count()==8
                    assert await page.locator('#sku-table th').nth(1).evaluate('(e)=>getComputedStyle(e).textAlign')=='center'
                    assert await page.locator('#sku-table input[aria-label="售价"]').first.evaluate('(e)=>getComputedStyle(e).textAlign')=='center'
                    page.on('dialog',lambda dialog:dialog.accept())
                    await page.locator('#sku-clear').click()
                    await page.locator('#sku-add').click()
                    row=page.locator('#sku-table tbody tr')
                    for name,value in [('SKU名称','合成SKU'),('售价','100'),('原料成本','40'),('快递成本','10'),('其他成本','0'),('周期销量','10')]:await row.get_by_role('textbox',name=name).fill(value) if name=='SKU名称' else await row.get_by_role('spinbutton',name=name,exact=True).fill(value)
                    await expect(row.locator('[data-result="breakeven"]')).to_have_text('2.00')
                    await expect(row.locator('[data-result="unit"]')).to_have_text('10.00')
                    await expect(row.locator('[data-result="profit"]')).to_have_text('100.00')
                    await row.get_by_role('spinbutton',name='售价',exact=True).fill('')
                    await expect(page.locator('#sku-input-error')).to_be_visible()
                    await expect(page.locator('#sku-totals')).to_be_hidden()
                    await row.get_by_role('spinbutton',name='售价',exact=True).fill('100')
                    await expect(page.locator('#sku-input-error')).to_be_hidden()
                    await row.get_by_role('spinbutton',name='原料成本',exact=True).fill('100')
                    await expect(row.locator('[data-result="breakeven"]')).to_have_text('不可保本')
                    await page.locator('#sku-add').click();await page.locator('#sku-daily').fill('3');await page.locator('#sku-distribute').click()
                    assert await page.locator('#sku-table tbody input[aria-label="周期销量"]').evaluate_all('(els)=>els.reduce((sum,e)=>sum+Number(e.value),0)')==90
                    await page.reload();await page.locator('[data-view="calculator"]').click();assert await page.locator('#sku-table tbody tr').count()==2
                    await page.locator('[data-view="management"]').click();await expect(page.locator('#create-desktop-shortcut')).to_be_visible()
                    await page.locator('[data-view="charts"]').click()
                    await expect(page.locator('[data-readable-trend] svg')).to_have_count(2)
                    await expect(page.locator('[data-reference="spend"]')).to_have_count(1)
                    await expect(page.locator('[data-reference="roi"]')).to_have_count(1)
                    assert await page.locator('[data-readable-trend="roi"] polyline').count()>0
                    await page.locator('#chart-grouping').select_option('week')
                    await expect(page.locator('.chart-summary')).to_contain_text('周期加权ROI')
                    await expect(page.locator('[data-readable-trend="spend"]')).to_contain_text('所选周平均花费')
                    await page.locator('[data-view="calculator"]').click()
                    await page.locator('#sku-new').click()
                    await expect(page.locator('#sku-demo-label')).to_be_hidden()
                    await expect(page.locator('#sku-shop')).to_have_value('我的测算')
                    assert await page.locator('#sku-table tbody tr').count()==0
                    assert not errors,errors
                finally:await browser.close()
            print('Desktop shortcut creation/reuse and isolated SKU calculation, allocation and persistence passed.')
        finally:process.terminate();process.wait(timeout=10)

if __name__=='__main__':asyncio.run(main())
