'use strict';
// Independent assumptions. Never infer SKU orders from advertising reports.
const skuStorage='pdd-sku-calculator-v1';
let skuModel={version:1,shop:'',fee:0,roi:2.5,days:30,rows:[]};
let skuUndo=null;
function skuDemo(){return {version:1,demo:true,shop:'示例店铺 · 小包粉模拟方案',fee:0.6,roi:2.5,days:30,rows:[
  {name:'蛋糕粉 1kg × 1',price:18.9,material:6.2,shipping:3.5,other:0.6,quantity:210},
  {name:'蛋糕粉 1kg × 2',price:33.9,material:12.4,shipping:4,other:0.8,quantity:110},
  {name:'面包粉 1kg × 1',price:19.9,material:7.4,shipping:3.5,other:0.6,quantity:320},
  {name:'面包粉 1kg × 2',price:35.9,material:14.8,shipping:4,other:0.8,quantity:130},
  {name:'蛋糕粉 2.5kg × 1',price:39.9,material:15.5,shipping:4.6,other:0.9,quantity:350},
  {name:'面包粉 2.5kg × 1',price:39.9,material:18.5,shipping:4.6,other:0.9,quantity:620},
  {name:'组合装 1kg + 1kg',price:35.9,material:13.6,shipping:4,other:0.8,quantity:90},
  {name:'组合装 2.5kg + 2.5kg',price:69.9,material:34,shipping:6,other:1.2,quantity:60}]};}
function skuValidate(model){
  if(!model||model.version!==1||typeof model.shop!=='string'||!Array.isArray(model.rows)||model.rows.length>500)throw Error('测算文件格式无效');
  for(const [key,max] of [['fee',100],['roi',100000],['days',366]])if(typeof model[key]!=='number'||!Number.isFinite(model[key])||model[key]<0||model[key]>max)throw Error('测算参数无效');
  if(model.roi<=0||!Number.isInteger(model.days)||model.days<1)throw Error('ROI须大于0，测算天数须为1至366的整数');
  for(const row of model.rows){if(typeof row.name!=='string'||row.name.length>200)throw Error('SKU名称无效');for(const key of ['price','material','shipping','other','quantity'])if(typeof row[key]!=='number'||!Number.isFinite(row[key])||row[key]<0||row[key]>1e9)throw Error('SKU数值无效');if(!Number.isInteger(row.quantity))throw Error('销量须为整数');}
  return model;
}
function skuCalculate(row,fee,roi){
  const cost=row.material+row.shipping+row.other,margin=row.price*(1-fee/100)-cost;
  const advertising=row.price/roi,unit=margin-advertising;
  return {cost,breakeven:row.price>0&&margin>0?row.price/margin:null,unit,spend:advertising*row.quantity,profit:unit*row.quantity,revenue:row.price*row.quantity,quantity:row.quantity};
}
try{const stored=localStorage.getItem(skuStorage);if(stored)skuModel=skuValidate(JSON.parse(stored));}catch{ /* Keep invalid saved data untouched until explicit reset/import. */ }
try{if(!skuModel.rows.length&&!skuModel.shop&&!localStorage.getItem('pdd-sku-demo-dismissed'))skuModel=skuDemo();}catch{}
const skuSection=$('calculator');
skuSection.innerHTML=`<div class="section-head"><div><p class="eyebrow">SKU SCENARIOS</p><h2>SKU 盈亏测算</h2></div><span class="meta">手工假设 · 独立于推广报表</span></div>
<p class="coverage">自行填写SKU售价、完整单件成本与假设销量。推广报表不能提供SKU销量，本页不自动关联或证明真实利润。未计入的退款、税费、运费险等会影响结果，请按自身口径纳入成本。</p>
<p id="sku-demo-label" class="demo-banner" hidden>模拟数据 · 参考小包粉SKU结构，售价、成本和销量均为虚构，不代表原店铺经营。</p><button id="sku-load-demo">载入模拟示例</button>
<div class="table-controls"><label>测算名称<input id="sku-shop" placeholder="例如：店铺或产品方案"></label><label>平台扣点 %<input id="sku-fee" type="number" min="0" max="100" step="0.01"></label><label>目标 ROI<input id="sku-roi" type="number" min="0.01" step="any"></label><label>测算天数<input id="sku-days" type="number" min="1" max="366" step="1"></label></div>
<div class="table-controls"><button data-sku-roi="2">ROI 2.0</button><button data-sku-roi="2.5">ROI 2.5</button><button data-sku-roi="3">ROI 3.0</button><label>重新分配的日均销量<input id="sku-daily" type="number" min="0" step="1" placeholder="填写后点击分配"></label><button id="sku-distribute">按比例分配周期销量</button></div><p id="sku-current-daily" class="coverage"></p><p id="sku-input-error" role="alert" hidden>输入有误，结果暂未更新。请修正标记的数值。</p>
<div id="sku-totals" class="table-controls" aria-live="polite"></div>
<div class="table-scroll"><table id="sku-table"><thead><tr><th>SKU 名称</th><th>售价</th><th>原料成本</th><th>快递成本</th><th>其他成本</th><th>周期销量</th><th>单件总成本</th><th>保本 ROI</th><th>预计单件结余</th><th>预计推广费</th><th>预计周期结余</th><th>操作</th></tr></thead><tbody></tbody></table></div>
<div class="table-controls"><button id="sku-add" class="signal-button">添加 SKU</button><button id="sku-new">新建我的测算</button><button id="sku-undo" disabled>撤销删除</button><button id="sku-export">导出 JSON</button><button id="sku-import">导入 JSON</button><input id="sku-import-file" type="file" accept="application/json,.json" hidden><button id="sku-csv">导出 CSV</button><button id="sku-clear">清空测算</button></div>
<p id="sku-message" role="status"></p><p class="coverage">保本ROI = 售价 ÷（售价 ×（1 − 扣点）− 单件成本）；预计单件结余 = 售价 ×（1 − 扣点）− 单件成本 − 售价 ÷ 目标ROI。无正毛利时，保本ROI显示“不可保本”。周期推广费按假设销量 × 售价 ÷ 目标ROI测算，不是自动投放建议。数据仅保存在当前浏览器，导出后可在另一台电脑导入。</p>`;
function skuPersist(){try{localStorage.setItem(skuStorage,JSON.stringify(skuModel));$('sku-message').textContent='测算已保存在当前浏览器；建议导出备份。';}catch{$('sku-message').textContent='浏览器保存失败，请导出 JSON 备份。';}}
function skuOutputs(){
  const invalid=[...skuSection.querySelectorAll('#sku-table input,#sku-shop,#sku-fee,#sku-roi,#sku-days')].some(input=>!input.validity.valid);
  $('sku-input-error').hidden=!invalid;skuSection.classList.toggle('sku-invalid',invalid);
  for(const id of ['sku-export','sku-csv','sku-distribute'])$(id).disabled=invalid;
  $('sku-demo-label').hidden=!skuModel.demo;
  const total={revenue:0,spend:0,profit:0,quantity:0};
  skuModel.rows.forEach((row,index)=>{const result=skuCalculate(row,skuModel.fee,skuModel.roi),tr=$('sku-table').querySelectorAll('tbody tr')[index];
    for(const key of ['cost','breakeven','unit','spend','profit']){const cell=tr.querySelector(`[data-result="${key}"]`);cell.textContent=key==='breakeven'&&result[key]===null?'不可保本':fmt(result[key],2);cell.classList.toggle('change-up',['unit','profit'].includes(key)&&result[key]<0);}
    for(const key of Object.keys(total))total[key]+=result[key];
  });
  $('sku-totals').replaceChildren();for(const [key,name] of [['quantity','周期销量'],['revenue','预计交易额'],['spend','预计推广费'],['profit','预计周期结余']])$('sku-totals').append(el('p',`${name}：${fmt(total[key],key==='quantity'?0:2)}`));
  $('sku-current-daily').textContent=`当前 ${skuModel.days} 天 · 周期销量 ${fmt(total.quantity,0)} 单 · 折算日均 ${fmt(total.quantity/skuModel.days,2)} 单；重新分配不会自动修改销量。`;
  $('sku-undo').disabled=!skuUndo;
}
function skuRows(){
  const body=$('sku-table').querySelector('tbody');body.replaceChildren();
  skuModel.rows.forEach((row,index)=>{const tr=el('tr');
    for(const [key,name] of [['name','SKU名称'],['price','售价'],['material','原料成本'],['shipping','快递成本'],['other','其他成本'],['quantity','周期销量']]){const td=el('td'),input=el('input');input.setAttribute('aria-label',name);input.value=row[key];input.type=key==='name'?'text':'number';if(key!=='name'){input.min='0';input.step=key==='quantity'?'1':'0.01';}else input.maxLength=200;
      input.addEventListener('input',()=>{const value=key==='name'?input.value:input.valueAsNumber;if(key!=='name'&&(!Number.isFinite(value)||value<0||value>1e9||(key==='quantity'&&!Number.isInteger(value)))){input.setCustomValidity('请输入有效的非负数；销量须为整数');skuOutputs();return;}input.setCustomValidity('');row[key]=value;skuOutputs();skuPersist();});td.append(input);tr.append(td);}
    for(const key of ['cost','breakeven','unit','spend','profit']){const td=el('td');td.dataset.result=key;tr.append(td);}
    const td=el('td'),remove=el('button','删除');remove.addEventListener('click',()=>{skuUndo={index,row:skuModel.rows[index]};skuModel.rows.splice(index,1);skuRows();skuPersist();});td.append(remove);tr.append(td);body.append(tr);
  });skuOutputs();
}
function skuSettings(){skuUndo=null;for(const key of ['shop','fee','roi','days']){$('sku-'+key).value=skuModel[key];$('sku-'+key).setCustomValidity('');}skuRows();}
for(const key of ['shop','fee','roi','days'])$('sku-'+key).addEventListener('input',()=>{const input=$('sku-'+key),next={...skuModel,[key]:key==='shop'?input.value:input.valueAsNumber};try{skuValidate(next);skuModel=next;input.setCustomValidity('');skuOutputs();skuPersist();}catch(error){input.setCustomValidity(error.message);skuOutputs();}});
$('sku-undo').addEventListener('click',()=>{if(!skuUndo)return;skuModel.rows.splice(skuUndo.index,0,skuUndo.row);skuUndo=null;skuRows();skuPersist();});
$('sku-new').addEventListener('click',()=>{if(skuModel.rows.length&&!confirm('新建将清空当前方案，请先导出需要保留的测算。继续？'))return;try{localStorage.setItem('pdd-sku-demo-dismissed','true');}catch{}skuModel={version:1,demo:false,shop:'我的测算',fee:0,roi:2.5,days:30,rows:[]};skuSettings();skuPersist();});
for(const button of skuSection.querySelectorAll('[data-sku-roi]'))button.addEventListener('click',()=>{skuModel.roi=Number(button.dataset.skuRoi);$('sku-roi').value=skuModel.roi;$('sku-roi').setCustomValidity('');skuOutputs();skuPersist();});
$('sku-add').addEventListener('click',()=>{if(skuModel.rows.length>=500){$('sku-message').textContent='最多500个SKU';return;}skuModel.rows.push({name:'',price:0,material:0,shipping:0,other:0,quantity:0});skuRows();skuPersist();});
$('sku-distribute').addEventListener('click',()=>{const daily=$('sku-daily').valueAsNumber;if(!Number.isInteger(daily)||daily<0||daily*skuModel.days>1e9||!skuModel.rows.length){$('sku-message').textContent='先添加SKU，并输入有效的整数日均销量。';return;}const count=daily*skuModel.days,total=skuModel.rows.reduce((sum,row)=>sum+row.quantity,0),allocations=skuModel.rows.map((row,index)=>{const exact=count*(total?row.quantity/total:1/skuModel.rows.length);return {index,quantity:Math.floor(exact),fraction:exact-Math.floor(exact)};}),remaining=count-allocations.reduce((sum,row)=>sum+row.quantity,0);allocations.sort((a,b)=>b.fraction-a.fraction||a.index-b.index);for(let i=0;i<remaining;i++)allocations[i].quantity++;for(const row of allocations)skuModel.rows[row.index].quantity=row.quantity;skuRows();skuPersist();});
function skuDownload(filename,text,type){const url=URL.createObjectURL(new Blob([text],{type})),link=el('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('sku-export').addEventListener('click',()=>skuDownload('SKU测算.json',JSON.stringify(skuModel,null,2),'application/json'));
$('sku-import').addEventListener('click',()=>$('sku-import-file').click());
$('sku-import-file').addEventListener('change',async()=>{try{const file=$('sku-import-file').files[0];if(!file)return;if(file.size>1000000)throw Error('文件过大');const next=skuValidate(JSON.parse(await file.text()));if(!confirm('导入将替换当前测算，请先导出需要保留的内容。继续导入？'))return;skuModel=next;skuSettings();skuPersist();}catch(error){$('sku-message').textContent='导入失败：'+error.message;}finally{$('sku-import-file').value='';}});
$('sku-clear').addEventListener('click',()=>{if(!confirm('清空当前测算？建议先导出备份。'))return;try{localStorage.setItem('pdd-sku-demo-dismissed','true');}catch{}skuModel={version:1,shop:'',fee:0,roi:2.5,days:30,rows:[]};skuSettings();skuPersist();});
$('sku-load-demo').addEventListener('click',()=>{if(skuModel.rows.length&&!confirm('载入模拟示例将替换当前测算，请先导出备份。继续？'))return;skuModel=skuDemo();skuSettings();skuPersist();});
$('sku-csv').addEventListener('click',()=>{const escape=value=>'"'+String(typeof value==='string'&&/^[=+@\-]/.test(value)?'\''+value:value).replaceAll('"','""')+'"';const rows=[['SKU名称','售价','原料成本','快递成本','其他成本','周期销量','单件总成本','保本ROI','预计单件结余','预计推广费','预计周期结余'],...skuModel.rows.map(row=>{const result=skuCalculate(row,skuModel.fee,skuModel.roi);return [row.name,row.price,row.material,row.shipping,row.other,row.quantity,result.cost,result.breakeven??'不可保本',result.unit,result.spend,result.profit];})];skuDownload('SKU测算.csv','\uFEFF'+rows.map(row=>row.map(escape).join(',')).join('\r\n'),'text/csv;charset=utf-8');});
skuSettings();


