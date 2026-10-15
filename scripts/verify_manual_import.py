"""Isolated browser import acceptance; synthetic data and disposable server only."""
import asyncio,base64,os,subprocess,sys,tempfile
from pathlib import Path
from playwright.async_api import async_playwright,expect
from test_manual_import import request
ROOT=Path(__file__).resolve().parents[1]
async def main():
    # The public staging tree has no user data before this acceptance run.
    from build_update import TARGET,build
    build()
    with tempfile.TemporaryDirectory() as temp:
        import shutil
        target=Path(temp)/'project';shutil.copytree(TARGET,target)
        import site
        environment={k:v for k,v in os.environ.items() if k!='PDD_REVIEW_DIR'}
        environment['PYTHONPATH']=os.pathsep.join(site.getsitepackages())
        process=subprocess.Popen([sys._base_executable,'-X','utf8',str(target/'scripts/serve_workbench.py'),'--port','0'],cwd=target,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=environment)
        try:
            import re
            line=process.stdout.readline();match=re.search(r'127\.0\.0\.1:(\d+)',line)
            if not match:raise RuntimeError(line+process.stderr.read())
            url='http://127.0.0.1:'+match.group(1)
            async with async_playwright() as p:
                browser=await p.chromium.launch(channel='chrome',headless=True)
                try:
                    page=await browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    await page.goto(url);await expect(page.locator('#verified')).to_contain_text('模拟数据')
                    await page.locator('[data-view="management"]').click()
                    async def upload(mode):
                        r=request(mode)
                        for field in ('shop','start','end'):await page.locator('#import-'+field).fill(r[field])
                        f=r['files'][0];await page.locator('#import-files').set_input_files({'name':f['name'],'mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':base64.b64decode(f['content'])})
                        await page.locator('#import-preview').click();await expect(page.locator('#import-message')).to_contain_text('结构及日期校验通过')
                        await page.locator('#import-confirmed').check();await page.locator('#import-submit').click();await expect(page.locator('#import-message')).to_contain_text('导入完成')
                    await upload('汇总数据')
                    await expect(page.locator('#verified')).to_contain_text('仅汇总报表')
                    await expect(page.locator('#raw-sheet')).to_be_visible()
                    await page.locator('[data-view="overview"]').click();await expect(page.locator('#management')).to_be_visible()
                    await upload('分天数据');await expect(page.locator('#import-message')).to_contain_text('对账通过')
                    await page.locator('[data-view="overview"]').click();await expect(page.locator('#verified')).to_contain_text('基础指标对账通过')
                    await expect(page.locator('#analysis')).to_be_visible()
                    await page.locator('[data-view="management"]').click()
                    await expect(page.locator('#import-files')).to_be_visible()
                    await page.screenshot(path=str(ROOT/'data/manual-import-acceptance.png'),full_page=True)
                    assert not errors,errors
                    print('UI passed: summary-only source table, no fabricated analysis, second file reconciliation, full analysis restored; no JS errors')
                finally:await browser.close()
        finally:
            process.terminate();process.wait(timeout=10)
            process.stdout.close();process.stderr.close()
if __name__=='__main__':asyncio.run(main())
