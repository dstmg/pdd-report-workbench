'use strict';
const historyCache=new Map(),historyPending=new Set();
let reviewData={version:0,items:[]},reviewEditing=null,reviewSnapshot=null,reviewShop='',reviewDirty=false;
const rowSection=document.querySelector('.table-section'),fullMarker=document.createComment('table-location');
rowSection.before(fullMarker);
const tools=document.querySelector('.table-section .table-controls');
const pauseButton=el('button','暂停采集');pauseButton.id='collect-pause';pauseButton.disabled=true;$('collect-continue').before(pauseButton);
const topLabel=el('label','榜单 '),topSelect=el('select');topSelect.id='top-count';topSelect.setAttribute('aria-label','TOP数量');
for(const [value,name] of [['0','全部'],['10','TOP10'],['20','TOP20']]){const option=el('option',name);option.value=value;topSelect.append(option);}topLabel.append(topSelect);tools.append(topLabel);
const shareLabel=el('label'),shareInput=el('input');shareInput.type='checkbox';shareInput.id='show-shares';shareLabel.append(shareInput,document.createTextNode('花费 / 交易额占比'));tools.append(shareLabel);
const colorLabel=el('label'),colorInput=el('input');colorInput.type='checkbox';colorInput.id='show-baseline';colorLabel.append(colorInput,document.createTextNode('与同场景均值对照'));tools.append(colorLabel);
const fullButton=el('button','全屏查看');fullButton.id='full-table-button';tools.append(fullButton);
const resetButton=el('button','重置筛选');resetButton.addEventListener('click',()=>{$('search').value='';$('minimum').value='0';$('zero').checked=false;topSelect.value='0';state.sort='spend';state.descending=true;state.page=1;render();});tools.append(resetButton);
for(const control of [topSelect,shareInput,colorInput])control.addEventListener('change',()=>{state.page=1;render();});
fullButton.addEventListener('click',()=>{$('full-table-content').append(rowSection);$('full-table').showModal();});
$('close-full-table').addEventListener('click',()=>$('full-table').close());
$('full-table').addEventListener('close',()=>fullMarker.after(rowSection));

function onDatasetLoaded(){
  historyCache.set(state.data.id,state.data);
  const demo=state.data.demo;$('record-overview').disabled=demo||!!state.data.partial||state.data.reconciled===false;$('review-new').disabled=demo||!!state.data.partial||state.data.reconciled===false;
  $('review-backup').disabled=demo;$('review-restore').disabled=demo;$('collect-start-button').disabled=!$('collect-shop').value.trim();
  if(!demo){$('collect-shop').value=state.data.shop;$('collect-start').value=state.data.start;$('collect-end').value=state.data.end;}
  else if(!$('collect-start').value){$('collect-end').value=shiftDay(todayShanghai(),-1);$('collect-start').value=shiftDay(todayShanghai(),-7);}
  $('raw-title').textContent=demo?'全部字段与模拟值':'全部字段与原始值';
  $('raw-description').textContent=demo?'字段按空报表结构生成，所有数值为模拟；此表不随上方筛选改变。':'保留完整源文件表头、总计、注释；此表不随上方筛选改变。';
  $('footer-source').textContent=demo?'页面演示 · '+state.data.category+' · 模拟数据':'本地预览 · '+state.data.category+'官方报表';
  $('scope-note').textContent=demo?'当前为模拟数据，所有指标不进入真实报表对账或正式复盘。':'店铺在采集页面核对；当前报表不等于账户账单。豁免率等未知规则字段完整周期显示官方源值，不对多日原始比率直接平均。';
}
function shiftDay(value,days){const date=new Date(value+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+days);return iso(date);}
function rangeTotal(data,start,end){const daily=data.daily.filter(r=>r.date>=start&&r.date<=end),products=data.products.filter(r=>r.date>=start&&r.date<=end),full=start===data.start&&end===data.end;
  const total=sum(daily,full?data.officialOverview:{}),details=sum(products),headers=data.rawReports[0].sheets.find(s=>s.name.startsWith('汇总数据_'))?.fields||[];
  for(const f of definitions())if(!headers.includes(f.name))total[f.key]=details[f.key];return total;}
function priorPeriod(){
  const {a,b}=selected(),days=Math.round((Date.parse(b)-Date.parse(a))/86400000)+1,start=shiftDay(a,-days),end=shiftDay(a,-1);
  if(state.data.demo)return {start,end,reason:'模拟数据不参与真实周期比较'};
  const candidates=availableBatches.filter(x=>x.state==='complete'&&!x.demo&&x.shop===state.data.shop&&x.start<=start&&x.end>=end);
  if(!candidates.length)return {start,end,reason:'上周期超出已下载范围，缺少完整报表'};
  const chosen=candidates.find(x=>x.id===state.data.id)||candidates[0],data=historyCache.get(chosen.id);
  if(!data){if(!historyPending.has(chosen.id)){historyPending.add(chosen.id);json('/api/dataset?batch='+encodeURIComponent(chosen.id)).then(value=>historyCache.set(chosen.id,value)).catch(error=>historyCache.set(chosen.id,{error:error.message})).finally(()=>{historyPending.delete(chosen.id);render();});}return {start,end,reason:'正在核验上周期本地数据'};}
  if(data.error)return {start,end,reason:'上周期文件未通过校验'};
  const dates=new Set(data.daily.map(r=>r.date));for(let d=start;d<=end;d=shiftDay(d,1))if(!dates.has(d))return {start,end,reason:'上周期缺少日期，不补零比较'};
  return {start,end,total:rangeTotal(data,start,end),reason:''};
}
function renderComparison(total){const previous=priorPeriod();$('comparison-note').textContent=`上周期：${previous.start} — ${previous.end} · ${previous.reason||'紧邻的等长自然日；涨跌不代表好坏，两批数据归因成熟度可能不同'}`;
  for(const card of $('metrics').children){const key=card.dataset.metric,a=total[key],b=previous.total?.[key];let text='上期不可比',cls='metric-change';if(previous.total){if(a==null||b==null)text='缺失或未知口径，无法比较';else if(a===b)text='持平 0.00%';else if(b===0){text=a>0?'↑ 上期为0，新增':'↓ 上期为0';cls+=a>0?' change-up':' change-down';}else{const change=(a-b)/Math.abs(b)*100;text=`${change>0?'↑ 上升':'↓ 下降'} ${fmt(Math.abs(change))}%`;cls+=change>0?' change-up':' change-down';}}const line=el('p',text,cls);line.dataset.comparison=key;if(b!=null)line.title='上期 '+metricFmt(key,b);card.append(line);}}
function decorateTable(){
  const visible=state.rows.slice((state.page-1)*10,state.page*10),head=$('table-head');
  if(shareInput.checked){head.append(el('th','花费占比'),el('th','交易额占比'));}
  head.append(el('th','复盘'));
  const trs=[...$('rows').children];
  if(!visible.length){trs[0]?.firstChild?.setAttribute('colspan',head.children.length);return;}
  visible.forEach((row,index)=>{const tr=trs[index];if(shareInput.checked){for(const key of ['spend','revenue']){const value=state.reportTotal[key]>0&&row[key]!=null?row[key]/state.reportTotal[key]*100:null;const cell=el('td',value==null?'—':fmt(value)+'%');cell.title='分母为当前完整报表和日期总额，不随搜索或TOP改变';tr.append(cell);}}
    if(colorInput.checked){const peers=state.allRows.filter(r=>r.scene===row.scene);tableMetrics.forEach((key,column)=>{const valid=peers.map(r=>r[key]).filter(v=>v!=null),mean=valid.length?valid.reduce((a,b)=>a+b,0)/valid.length:null;const cell=tr.children[column+1];cell.title='同场景有效记录的算术均值：'+metricFmt(key,mean)+'；只表示高低，不表示盈利';if(row[key]!=null&&row[key]!==0&&mean!=null)cell.classList.add(row[key]>mean?'change-up':row[key]<mean?'change-down':'neutral');});}
    const cell=el('td'),button=el('button','记问题');button.disabled=state.data.demo;button.addEventListener('click',()=>newReview(row));cell.append(button);tr.append(cell);});}
function rankedChart(container,title,rows,key,total){const section=el('section',null,'insight-section');section.append(el('h3',title));const chosen=[...rows].filter(r=>r[key]!=null).sort((a,b)=>b[key]-a[key]).slice(0,10),max=Math.max(...chosen.map(r=>r[key]),1);
  if(!chosen.length)section.append(el('p','当前范围没有可展示记录','coverage'));
  for(const row of chosen){const item=el('div',null,'rank-line'),name=el('button',row.name);name.addEventListener('click',()=>openDetail(row));const track=el('div',null,'rank-track'),bar=el('div',null,'rank-fill');bar.style.width=Math.max(0,row[key])/max*100+'%';track.append(bar);item.append(name,track,el('span',fmt(row[key])));section.append(item);}
  section.append(el('p','TOP10 · 基于当前日期有效明细；数值与占比不代表利润。','coverage'));container.append(section);}
let chartGrouping='day';
function readableTrend(target,rows,key,reference,weekly=false){
  const valid=rows.filter(row=>Number.isFinite(row[key]));
  if(!rows.length||!valid.length){target.append(el('p','当前范围无有效数值','coverage'));return;}
  const width=Math.max(760,rows.length*(weekly?100:48)+100),height=310,left=72,right=24,top=40,bottom=60,plotWidth=width-left-right,plotHeight=height-top-bottom;
  const ceiling=Math.max(...valid.map(row=>row[key]),Number.isFinite(reference)?reference:0,0);
  const magnitude=10**Math.floor(Math.log10(ceiling||1)),step=Math.ceil((ceiling||1)/magnitude/4)*magnitude,max=step*4;
  const x=index=>left+(index+0.5)*plotWidth/rows.length,y=value=>top+plotHeight-(value/max)*plotHeight;
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.style.width=width+'px';svg.setAttribute('role','img');svg.setAttribute('aria-label',`${labels[key]}每日趋势，含日期、数值、刻度与${key==='roi'?'周期加权ROI':'日均花费'}参考线`);
  function node(tag,attributes,text){const element=document.createElementNS(svg.namespaceURI,tag);for(const [name,value]of Object.entries(attributes))element.setAttribute(name,value);if(text!=null)element.textContent=text;svg.append(element);return element;}
  for(let i=0;i<=4;i++){const value=step*i;node('line',{x1:left,x2:width-right,y1:y(value),y2:y(value),stroke:'#e4e4e7'});node('text',{x:left-10,y:y(value)+4,'text-anchor':'end',fill:'#71717a','font-size':11},fmt(value,key==='roi'?2:0));}
  node('text',{x:left,y:18,fill:'#52525b','font-size':11},key==='roi'?'ROI（倍）':'花费（元）');
  let segment=[];const flush=()=>{if(segment.length>1)node('polyline',{points:segment.join(' '),fill:'none',stroke:'#7c3aed','stroke-width':2});segment=[];};
  rows.forEach((row,index)=>{const value=row[key],cx=x(index);node('text',{x:cx,y:height-32,'text-anchor':'middle',fill:'#71717a','font-size':10},row.periodLabel||row.date.slice(5));
    if(!Number.isFinite(value)){flush();node('text',{x:cx,y:top+plotHeight-10,'text-anchor':'middle',fill:'#71717a','font-size':10},'缺失');return;}
    let mark;if(key==='spend')mark=node('rect',{x:cx-12,y:y(value),width:24,height:Math.max(0,top+plotHeight-y(value)),fill:'#8b5cf6',opacity:0.8});
    else{segment.push(`${cx},${y(value)}`);mark=node('circle',{cx,cy:y(value),r:4,fill:'#7c3aed'});}
    const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=`${row.date} · ${labels[key]} ${fmt(value)}${key==='roi'?'倍':'元'}`;mark.append(title);
    node('text',{x:cx,y:Math.max(top-4,y(value)-9),'text-anchor':'middle',fill:'#3f3f46','font-size':10},fmt(value));
  });flush();
  if(Number.isFinite(reference))node('line',{x1:left,x2:width-right,y1:y(reference),y2:y(reference),stroke:'#52525b','stroke-width':1.5,'stroke-dasharray':'6 4','data-reference':key});
  const scroll=el('div',null,'readable-trend-scroll');scroll.append(svg);target.append(scroll);
  target.append(el('p',`${rows[0].date} — ${rows.at(-1).endDate||rows.at(-1).date} · ${key==='roi'?'虚线：周期加权ROI（总交易额 ÷ 总成交花费）':weekly?'虚线：所选周平均花费（含首尾不完整周）':'虚线：日均花费（有效日花费合计 ÷ 有效天数）'} ${Number.isFinite(reference)?fmt(reference)+(key==='roi'?'倍':'元'):'—'} · ${valid.length}个有效${weekly?'周':'日'} · 较长周期可横向滚动`,'coverage'));
}
function renderCharts(total,daily){const container=$('extra-charts');container.replaceChildren();const dual=el('section',null,'insight-section');dual.append(el('h3','每日投入与实际投产比'),el('p','花费柱图、ROI折线分别使用独立刻度；数字为每日原值，灰色虚线为周期参考。','coverage'));
  const spendDays=daily.filter(row=>Number.isFinite(row.spend)),mean=spendDays.length?spendDays.reduce((a,row)=>a+row.spend,0)/spendDays.length:null,peak=spendDays.reduce((a,row)=>!a||row.spend>a.spend?row:a,null);
  dual.append(el('p',`周期花费 ${fmt(total.spend)}元 · 日均花费 ${fmt(mean)}元 · 周期加权ROI ${fmt(total.roi)}倍 · 最高花费日 ${peak?peak.date+'（'+fmt(peak.spend)+'元）':'—'}`,'chart-summary'));
  const grouping=el('select');grouping.id='chart-grouping';grouping.setAttribute('aria-label','趋势粒度');for(const [value,name]of [['day','按日'],['week','按周']]){const option=el('option',name);option.value=value;grouping.append(option);}grouping.value=chartGrouping;grouping.addEventListener('change',()=>{chartGrouping=grouping.value;renderCharts(total,daily);});dual.append(grouping);
  let plotted=daily;
  if(chartGrouping==='week'){const groups=new Map();for(const row of daily){const day=new Date(row.date+'T00:00:00Z'),monday=shiftDay(row.date,-(day.getUTCDay()+6)%7);if(!groups.has(monday))groups.set(monday,[]);groups.get(monday).push(row);}plotted=[...groups.values()].map(rows=>({...sum(rows),date:rows[0].date,endDate:rows.at(-1).date,periodLabel:rows[0].date.slice(5)+'—'+rows.at(-1).date.slice(5)}));dual.append(el('p','按周汇总花费；周ROI由该周交易额 ÷ 成交花费计算。首尾可能为不完整周，不与完整周直接比较。','coverage'));}
  for(const key of ['spend','roi']){dual.append(el('p',labels[key],'meta'));const graph=el('div');graph.dataset.readableTrend=key;const values=plotted.filter(row=>Number.isFinite(row.spend));const reference=key==='roi'?total.roi:values.length?values.reduce((sum,row)=>sum+row.spend,0)/values.length:null;readableTrend(graph,plotted,key,reference,chartGrouping==='week');dual.append(graph);}container.append(dual);
  rankedChart(container,'花费排行',state.filteredRows||state.allRows,'spend',total);rankedChart(container,'交易额排行',state.filteredRows||state.allRows,'revenue',total);
  const shares=el('section',null,'insight-section');shares.append(el('h3','花费份额与交易额份额对照'),el('p','分母为当前日期的完整报表总额，搜索和TOP不改变分母。','coverage'));
  for(const row of [...state.allRows].sort((a,b)=>(b.spend||0)-(a.spend||0)).slice(0,10)){const line=el('div',null,'share-line');line.append(el('strong',row.name));for(const key of ['spend','revenue']){const pct=total[key]>0&&row[key]!=null?row[key]/total[key]*100:null;const bar=el('div',null,'share-track'),fill=el('div',null,key==='spend'?'share-fill':'share-fill muted');fill.style.width=(pct||0)+'%';bar.append(fill);line.append(bar,el('span',labels[key]+' '+(pct==null?'—':fmt(pct)+'%')));}shares.append(line);}container.append(shares);
  if(definition('直接交易额(元)')){const section=el('section',null,'insight-section');section.append(el('h3','直接与间接成交来源'));for(const key of ['直接交易额(元)','间接交易额(元)'])section.append(el('p',labels[key]+'：'+metricFmt(key,total[key])+'元'));section.append(el('p','直接与间接属于成交来源拆分，不与总交易额重复相加。','coverage'));container.append(section);}
}
function renderSummary(total,productDays){const groups=new Map();for(const row of productDays){if(!groups.has(row.scene))groups.set(row.scene,[]);groups.get(row.scene).push(row);}const baseline=new Map([...groups].map(([key,rows])=>[key,sum(rows)]));const zero=state.allRows.filter(r=>r.spend>0&&r.orders===0),zeroSpend=zero.reduce((a,r)=>a+r.spend,0);
  $('summary-facts').replaceChildren(el('p',`当前${state.allRows.length}条推广记录，总花费 ${fmt(total.spend)}元；${zero.length}条有花费、零成交记录，花费合计 ${fmt(zeroSpend)}元。`),el('p',`实际投产比 ${fmt(total.roi)}倍，净交易额 ${fmt(total.netRevenue)}元。以上是报表事实，不作利润判断。`));
  const minimum=Math.max(0,Number($('attention-minimum').value||0)),rows=state.allRows.filter(r=>r.spend>0&&r.spend>=minimum&&r.roi!=null&&baseline.get(r.scene)?.roi!=null&&r.roi<baseline.get(r.scene).roi).sort((a,b)=>b.spend-a.spend).slice(0,20);
  $('attention-rows').replaceChildren();for(const row of rows){const base=baseline.get(row.scene),facts=[];if(row.orders===0)facts.push('有花费但成交笔数为0');if(row.clicks>0&&base.clicks>0&&row.spend/row.clicks>base.spend/base.clicks)facts.push('点击花费偏高');if(row.clicks>0&&base.clicks>0&&row.orders/row.clicks<base.orders/base.clicks)facts.push('成交笔数/点击量偏低');if(row.orders>0&&base.orders>0&&row.revenue/row.orders<base.revenue/base.orders)facts.push('每笔成交金额偏低');const tr=el('tr'),nameCell=el('td'),button=el('button',row.name);button.addEventListener('click',()=>openDetail(row));nameCell.append(button);tr.append(nameCell,el('td',fmt(row.spend)),el('td',fmt(row.roi)),el('td',fmt(base.roi)),el('td',facts.join('；')||'结合样本量与投放目标核查'));const cell=el('td'),record=el('button','记问题');record.disabled=state.data.demo;record.addEventListener('click',()=>newReview(row));cell.append(record);tr.append(cell);$('attention-rows').append(tr);}if(!rows.length){const td=el('td','当前条件下没有待核查记录；不代表全部盈利。');td.colSpan=6;const tr=el('tr');tr.append(td);$('attention-rows').append(tr);}}
function renderExtras(total,daily,products){renderComparison(total);if(state.view==='charts')renderCharts(total,daily);if(state.view==='summary')renderSummary(total,products);}
$('attention-minimum').addEventListener('input',render);

async function post(url,body){const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),data=await response.json();if(!response.ok)throw Error(data.error||'本地操作失败');return data;}
async function updateCollection(){try{const result=await json('/api/collection');const names={idle:'尚未采集',starting:'正在连接',running:'采集中',paused:'暂停，等待人工处理',complete:'采集完成',needs_attention:'需要核查',pending:'待处理',submitting:'提交中',waiting:'等待生成',downloading:'下载中',saving:'保存中',needs_validation:'待校验',validated:'校验完成'};$('collect-message').textContent=names[result.state]+(result.message?' · '+result.message:'');$('collect-log').textContent=(result.logs||[]).join('\n');$('collect-tasks').replaceChildren(...(result.tasks||[]).map(t=>el('p',`${t.mode} · ${names[t.state]||t.state}`,'meta')));$('collect-continue').disabled=result.state!=='paused';$('collect-quit').disabled=result.state!=='paused';pauseButton.disabled=!['starting','running'].includes(result.state);const active=['starting','running','paused','needs_login'].includes(result.state);$('collect-start-button').disabled=!$('collect-shop').value.trim()||active;for(const id of ['collect-shop','collect-start','collect-end'])$(id).disabled=active;return result;}catch(error){$('collect-message').textContent=error.message;}}
let collectionPolling=false;
async function pollCollection(){if(collectionPolling)return;collectionPolling=true;try{const result=await updateCollection();if(result&&!['complete','needs_attention','idle'].includes(result.state))setTimeout(pollCollection,2000);else if(result?.state==='complete')refresh();}finally{collectionPolling=false;}}
$('open-browser').addEventListener('click',async()=>{try{$('collect-message').textContent='正在核验并打开专用Chrome…';const result=await post('/api/browser/open',{});$('collect-message').textContent=result.message;}catch(error){$('collect-message').textContent=error.message;}});
$('collect-start-button').addEventListener('click',async()=>{try{$('collect-start-button').disabled=true;await post('/api/collection/start',{shop:$('collect-shop').value,start:$('collect-start').value,end:$('collect-end').value});pollCollection();}catch(error){$('collect-message').textContent=error.message;$('collect-start-button').disabled=!$('collect-shop').value.trim();}});
$('collect-shop').addEventListener('input',()=>{$('collect-start-button').disabled=!$('collect-shop').value.trim();});
pauseButton.addEventListener('click',async()=>{try{const result=await post('/api/collection/pause',{});$('collect-message').textContent=result.message;pauseButton.disabled=true;}catch(error){$('collect-message').textContent=error.message;}});
for(const [id,action] of [['collect-continue','continue'],['collect-quit','quit']])$(id).addEventListener('click',async()=>{try{await post('/api/collection/command',{action});pollCollection();}catch(error){$('collect-message').textContent=error.message;}});
$('open-report-folder').addEventListener('click',async()=>{try{const result=await post('/api/report-folder',{});$('collect-message').textContent=result.message;}catch(error){$('collect-message').textContent=error.message;}});
$('create-desktop-shortcut').addEventListener('click',async()=>{const button=$('create-desktop-shortcut');button.disabled=true;try{const result=await post('/api/desktop-shortcut',{});$('desktop-shortcut-message').textContent=result.message;}catch(error){$('desktop-shortcut-message').textContent=error.message;}finally{button.disabled=false;}});

const reviewFields={title:'review-name',discovery:'review-discovery',action:'review-action',status:'review-status',executed_on:'review-executed',review_on:'review-on',result:'review-result'};
function reviewDraftKey(){return 'pdd-review-draft-v1-'+reviewShop;}
function draftValues(){return Object.fromEntries(Object.entries(reviewFields).map(([key,id])=>[key,$(id).value]));}
function cacheReviewDraft(){if(!reviewShop)return;reviewDirty=true;try{localStorage.setItem(reviewDraftKey(),JSON.stringify({id:reviewEditing?.id||null,snapshot:reviewSnapshot,values:draftValues()}));}catch{}}
async function newReview(row=null){if(state.data?.partial){fail('缺少完整分天与汇总对账，暂不能新建正式复盘');return;}if(state.data?.demo){fail('模拟数据不能进入真实店铺复盘');return;}if(reviewDirty){$('review-dialog').showModal();$('review-save-message').textContent='先保存或继续处理已有草稿，再新建记录。';return;}await loadReviews();reviewEditing=null;reviewShop=state.data.shop;const {a,b}=selected();reviewSnapshot={batch:state.data.id,start:a,end:b};if(row)reviewSnapshot.subject=Object.fromEntries(['id','scene','promotion','bid','group'].map(k=>[k,row[k]]));fillReview({title:row?row.name+' · 待核查问题':`${a}—${b} 本期复盘`,status:'pending'});$('review-evidence').textContent=`保存时带入已校验报表快照 · ${row?.name||'整体概览'} · ${a} 至 ${b}`;$('review-archive').disabled=true;$('review-dialog').showModal();}
function fillReview(item){for(const [key,id] of Object.entries(reviewFields))$(id).value=item[key]|| (key==='status'?'pending':'');$('review-save-message').textContent='';}
function renderReviews(){const filter=$('review-filter').value,shop=state.data?.demo?null:state.data?.shop,today=todayShanghai();$('review-list').replaceChildren();if(!shop){$('review-list').append(el('p','模拟场景不显示或创建真实复盘。','coverage'));return;}const items=reviewData.items.filter(r=>r.shop===shop&&(filter==='archived'?r.archived:!r.archived)&&(filter==='all'||filter==='archived'||(filter==='due'?r.status==='observing'&&r.review_on&&r.review_on<=today:r.status===filter)));
  if(!items.length)$('review-list').append(el('p','当前状态没有复盘记录。','coverage'));for(const item of items){const article=el('article',null,'review-item'),open=el('button',item.title);open.addEventListener('click',()=>editReview(item));const labels={pending:'待处理',observing:'待观察',reviewed:'已复查'};article.append(open,el('p',`${labels[item.status]}${item.archived?' · 已归档':''}${item.review_on?' · 复查日期 '+item.review_on:''}`,'meta'),el('p',item.discovery||'尚未记录问题'));if(item.evidence)article.append(el('p',`${item.evidence.title} · 证据 ${item.evidence.start} 至 ${item.evidence.end}`,'meta'));$('review-list').append(article);}}
async function loadReviews(){try{reviewData=await json('/api/reviews');renderReviews();return reviewData;}catch(error){fail(error.message);throw error;}}
function editReview(item){if(reviewDirty&&reviewEditing?.id!==item.id){$('review-dialog').showModal();$('review-save-message').textContent='已有未保存草稿，请先处理，不覆盖草稿。';return;}reviewEditing=item;reviewShop=item.shop;reviewSnapshot=null;fillReview(item);$('review-archive').disabled=false;$('review-archive').textContent=item.archived?'恢复归档':'归档';$('review-evidence').textContent=item.evidence?`已保存证据快照 · ${item.evidence.title} · ${item.evidence.start} 至 ${item.evidence.end}；此证据不会被刷新改写`:'手动复盘';$('review-dialog').showModal();}
async function saveReview(archive=false){try{const payload={version:reviewData.version,id:reviewEditing?.id,...draftValues(),shop:reviewShop,archived:archive?(reviewEditing?!reviewEditing.archived:false):reviewEditing?.archived||false};if(!reviewEditing&&reviewSnapshot)payload.snapshot=reviewSnapshot;const result=await post('/api/reviews',payload);reviewData=result;reviewDirty=false;try{localStorage.removeItem(reviewDraftKey());}catch{}$('review-dialog').close();renderReviews();}catch(error){$('review-save-message').textContent=error.message;}}
$('record-overview').addEventListener('click',()=>newReview());$('review-new').addEventListener('click',()=>newReview());
$('review-close').addEventListener('click',()=>$('review-dialog').close());
$('review-form').addEventListener('input',cacheReviewDraft);$('review-form').addEventListener('change',cacheReviewDraft);
$('review-form').addEventListener('submit',event=>{event.preventDefault();saveReview();});$('review-archive').addEventListener('click',()=>saveReview(true));
$('review-filter').addEventListener('change',renderReviews);$('review-reload').addEventListener('click',loadReviews);
$('review-restore').addEventListener('click',async()=>{try{if(state.data?.demo)return;if(reviewDirty){$('review-dialog').showModal();return;}await loadReviews();reviewShop=state.data.shop;const draft=JSON.parse(localStorage.getItem(reviewDraftKey())||'null');if(!draft){fail('当前店铺没有本机草稿');return;}reviewEditing=draft.id?reviewData.items.find(r=>r.id===draft.id&&r.shop===reviewShop):null;if(draft.id&&!reviewEditing)throw Error('草稿对应记录不存在，保留草稿供核查');reviewSnapshot=draft.snapshot;fillReview(draft.values);reviewDirty=true;$('review-evidence').textContent='已恢复本机草稿，正式记录以保存为准';$('review-archive').disabled=!reviewEditing;$('review-dialog').showModal();}catch(error){fail(error.message);}});
$('review-backup').addEventListener('click',async()=>{try{const data=await json('/api/reviews'),blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=el('a');link.href=url;link.download='拼多多复盘备份_'+todayShanghai()+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){fail(error.message);}});
