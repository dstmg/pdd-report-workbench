"""Exercise production pagination against local synthetic DOM; no merchant data."""
import asyncio
import json
import tempfile
from playwright.async_api import async_playwright
from collect_reports import scan_task
from collection_state import Journal

async def fixture(page, names, initial=0):
    await page.set_content('''<div>合成测试店铺</div><button>生成报表</button>
    <table><tbody></tbody></table>
    <button class="anq-pagination-item-link" id="prev">上一页</button>
    <button class="anq-pagination-item-link" id="next">下一页</button>''')
    await page.evaluate('''({names, initial}) => {
      let index = initial;
      function render() {
        document.querySelector('tbody').replaceChildren();
        for (const name of names[index]) {
          const row=document.createElement('tr'), cell=document.createElement('td');
          cell.textContent=name; row.append(cell); document.querySelector('tbody').append(row);
        }
        document.querySelector('#prev').disabled=index===0;
        document.querySelector('#next').disabled=index===names.length-1;
      }
      document.querySelector('#prev').onclick=()=>{index--;render();};
      document.querySelector('#next').onclick=()=>{index++;render();};render();
    }''', {'names': names, 'initial': initial})

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel='chrome',headless=True)
        try:
            page=await browser.new_page()
            await page.route('https://yingxiao.pinduoduo.com/**',lambda route:route.fulfill(body='<html></html>',content_type='text/html'))
            await page.goto('https://yingxiao.pinduoduo.com/tools/report/download')
            with tempfile.TemporaryDirectory() as directory:
                journal=Journal(directory,'合成测试店铺','2026-01-01','2026-01-07')
                await fixture(page,[['第一页'],['目标任务'],['末页']],2)
                row=await scan_task(page,journal,'目标任务')
                assert row is not None and await row.inner_text()=='目标任务'
                await fixture(page,[['第一页'],['第二页'],['末页']],1)
                assert await scan_task(page,journal,'缺失任务') is None
                await fixture(page,[['重复任务'],['中间页'],['重复任务']])
                try:
                    await scan_task(page,journal,'重复任务')
                except RuntimeError as exc:
                    assert '跨页发现同名任务' in str(exc)
                else:
                    raise AssertionError('Duplicate task must stop')
            print('Synthetic pagination passed: rewind, three-page matching, missing and duplicate protection.')
        finally:
            await browser.close()

if __name__=='__main__':asyncio.run(main())
