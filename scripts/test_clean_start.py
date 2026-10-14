"""Start a clean source copy with synthetic examples only, no merchant files."""
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=['browser_session.py','collect_reports.py','collection_state.py','collection_controller.py',
         'dashboard_data.py','launch_browser.py','metrics_catalog.py','report_validation.py','review_store.py','serve_workbench.py']

async def main():
    with tempfile.TemporaryDirectory() as temporary:
        target=Path(temporary);(target/'scripts').mkdir()
        for name in RUNTIME:shutil.copy2(ROOT/'scripts'/name,target/'scripts'/name)
        shutil.copytree(ROOT/'web',target/'web');shutil.copytree(ROOT/'examples',target/'examples')
        assert not (target/'data').exists()
        environment=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
        environment.pop('PDD_REVIEW_DIR',None)
        process=subprocess.Popen([sys.executable,str(target/'scripts/serve_workbench.py'),'--port','0'],cwd=target,
            env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        try:
            line=process.stdout.readline();port=re.search(r'127\.0\.0\.1:(\d+)',line).group(1)
            async with async_playwright() as p:
                browser=await p.chromium.launch(channel='chrome',headless=True)
                page=await browser.new_page()
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto('http://127.0.0.1:'+port)
                await expect(page.locator('#demo-banner')).to_be_visible()
                await expect(page.locator('#verified')).to_have_text('模拟数据 · 未做官方对账')
                await page.locator('[data-view="management"]').click()
                await expect(page.locator('#collect-shop')).to_have_value('')
                await expect(page.locator('#collect-start-button')).to_be_disabled()
                await page.locator('#collect-shop').fill('用户自己的实际店铺')
                await expect(page.locator('#collect-start-button')).to_be_enabled()
                assert not errors,errors
                await browser.close()
            assert not (target/'data/reports').exists()
            print('干净源码副本、无真实报表、独立模拟展示及首次真实店铺采集入口检查通过')
        finally:
            process.terminate();process.wait(timeout=10)

if __name__=='__main__':asyncio.run(main())
