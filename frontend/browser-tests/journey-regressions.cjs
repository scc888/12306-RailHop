// Fixed-response interaction tests. Samples do not represent live ticket availability.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const catalog=require('../../backend/data/transfer_stations.json');
const seed=require('./fixtures/transfer.json').data.plans[0];
const stationResponse={code:200,data:[{name:'上海',telecode:'SHH',city_name:'上海',city_code:'sh'},{name:'北京',telecode:'BJP',city_name:'北京',city_code:'bj'},...catalog.filter(s=>s.station_code!=='SHH').map(s=>({...s,name:s.station_name,telecode:s.station_code}))]};
const group=(plans=[],status='complete',notices=[])=>({plans,meta:{status,notices}});
const fareScenarios=['fare_visibility','mobile_fares','missing_fares'];
const segmentScenarios=['segment_desktop','mobile_segments','narrow_segments'];
function segmentSample(body){
  const day=body.train_date,nextDay=new Date(`${day}T12:00:00+08:00`);nextDay.setUTCDate(nextDay.getUTCDate()+1);
  const tomorrow=nextDay.toISOString().slice(0,10),at=(time,next=false)=>`${next?tomorrow:day}T${time}:00+08:00`;
  const selection={train_no:'physical-T109',run_date:day,from_station:'BJP',to_station:'SHH',departure_at:at('20:04')};
  const train={id:'row-T109',train_no:'physical-T109',train_code:'T109',start_time:'20:04',arrive_time:'11:02',duration:'14:58',can_buy:true,from_station_name:'北京',to_station_name:'上海',from_station_telecode:'BJP',to_station_telecode:'SHH',start_station_name:'北京',end_station_name:'上海',departure_at:at('20:04'),arrival_at:at('11:02',true),seats:{yz:'无',yw:'无',rw:'无'},prices:{yz:'¥177.50',yw:'¥304.50',rw:'¥476.50'},selection};
  const leg=(from,to,fromName,toName,dep,arr,seats)=>({train_no:'physical-T109',train_code:'T109',from_station:from,to_station:to,from_station_name:fromName,to_station_name:toName,departure_at:dep,arrival_at:arr,seats,queried_at:at('19:00'),run_date:day});
  const seat=(code,name,price_fen,availability='有')=>({code,name,price_fen,availability});
  const plan={id:'T109-three-segments',kind:'same_train',total_minutes:898,total_price_fen:29050,known_price_fen:29050,selected_seat_codes:['yw','yz','yw'],connections:[],legs:[
    leg('BJP','TXP','北京','天津西',at('20:04'),at('21:29'),[seat('yw','硬卧',6950,'8'),seat('rw','软卧',10450,'1')]),
    leg('TXP','NJH','天津西','南京',at('21:32'),at('07:43',true),[seat('yz','硬座',12850)]),
    leg('NJH','SHH','南京','上海',at('07:49',true),at('11:02',true),[seat('yw','硬卧',9250),seat('rw','软卧',14050,'2')])
  ]};
  return {code:200,data:{trains:[train],selected_train:body.selected_train||null,direct:group(),same_train:body.mode==='all'?group([plan]):group([],'skipped'),transfer:group([],body.mode==='all'?'complete':'skipped'),short_fallback:{options:[],meta:{status:'skipped',notices:[]}},queried_at:at('19:00'),scope:{from_label:'北京（同城车站）',to_label:'上海（同城车站）'}}};
}
function sample(body,scenario){
  if(segmentScenarios.includes(scenario))return segmentSample(body);
  const day=body.train_date, at=time=>`${day}T${time}:00+08:00`;
  const trains=['G1','G9','K1'].filter(code=>body.train_type==='regular'?code==='K1':body.train_type==='high_speed'?code!=='K1':true).map((code,i)=>({
    id:`row-${code}`,train_no:`physical-${code}`,train_code:code,start_time:'08:00',arrive_time:'12:00',duration:'04:00',can_buy:true,
    from_station_name:'上海',to_station_name:'北京',from_station_telecode:'SHH',to_station_telecode:'BJP',start_station_name:'上海',end_station_name:'北京',
    departure_at:at('08:00'),arrival_at:at('12:00'),
    seats:code==='K1'?{yz:'无',yw:'无',rw:'无',wz:'--'}:{ze:code==='G9'?'3':'无',zy:'无',swz:'有',wz:'--'},
    prices:code==='K1'?{yz:'¥150',yw:'¥300',rw:'¥480'}:{ze:scenario==='missing_fares'?null:'¥550',zy:'¥850',swz:'¥1600'},
    selection:{train_no:`physical-${code}`,run_date:day,from_station:'SHH',to_station:'BJP',departure_at:at('08:00')}
  }));
  if(scenario==='missing_fares')trains.forEach(train=>{train.prices.wz='¥550';});
  const chosen=trains.find(t=>t.train_no===body.selected_train?.train_no)||trains[0];
  const transfer={...structuredClone(seed),id:`${chosen?.train_code}-transfer`,kind:'transfer'};
  transfer.legs.forEach((leg,i)=>{leg.departure_at=at(i?'09:15':'08:00');leg.arrival_at=at(i?'12:00':'09:00');leg.run_date=day;leg.queried_at=at('07:00');});
  transfer.legs[0].train_no=chosen?.train_no;transfer.legs[0].train_code=chosen?.train_code;
  transfer.connections[0].station=catalog.find(s=>s.station_code==='NKH');transfer.connections[0].official_min_minutes=15;
  if(chosen?.train_code==='K1')transfer.legs[0].seats=[{code:'yw',name:'硬卧',availability:'有',price_fen:12350}];
  if(chosen?.train_code==='K1')transfer.selected_seat_codes[0]='yw';
  if(body.allow_large_detour)transfer.route_assessment={mode:'expanded',warnings:['此路线可能明显绕行或等待较长，请核对经由站和全程耗时。']};
  const same={...structuredClone(transfer),id:`${chosen?.train_code}-same`,kind:'same_train',connections:[],selected_seat_codes:['ze','ze'],total_price_fen:32355,known_price_fen:32355};
  same.legs[1].departure_at=at('09:02');
  same.legs.forEach(leg=>{leg.train_no=chosen?.train_no;leg.train_code=chosen?.train_code;leg.seats=[{code:'ze',name:'二等座',availability:'有',price_fen:12350},{code:'zy',name:'一等座',availability:'2',price_fen:20000}];});
  if(scenario==='missing_fares'){same.legs[0].seats[0].price_fen=null;same.total_price_fen=null;same.known_price_fen=12350;}
  if(chosen?.train_code==='K1'){same.selected_seat_codes=['yw','yw'];same.legs.forEach(l=>l.seats=[{code:'yw',name:'硬卧',availability:'有',price_fen:12350},{code:'yz',name:'硬座',availability:'2',price_fen:10000}]);}
  const data={trains,selected_train:body.selected_train||null,direct:group(),same_train:group([], 'skipped'),transfer:group([], 'skipped'),short_fallback:{options:[],meta:{status:'skipped',notices:[]}},queried_at:at('07:00'),scope:{from_label:'上海（同城车站）',to_label:'北京（同城车站）'}};
  if(body.mode==='all'){
    data.same_train=group([same]);data.transfer=group([transfer],'partial',['固定样本：候选范围有限。']);
    if(fareScenarios.includes(scenario))data.same_train.plans.push({...structuredClone(same),id:`${chosen?.train_code}-same-collapsed`,total_minutes:same.total_minutes+30});
    if(scenario==='sort_preserves'){
      same.total_minutes=200;same.total_price_fen=24700;same.known_price_fen=24700;
      const cheapest={...structuredClone(same),id:'sort-cheapest',total_minutes:300,total_price_fen:10000,known_price_fen:10000};cheapest.legs.forEach(l=>{l.seats[0].price_fen=5000;});cheapest.legs.at(-1).arrival_at=at('13:00');
      const earliest={...structuredClone(same),id:'sort-earliest',total_minutes:250,total_price_fen:60000,known_price_fen:60000};earliest.legs.forEach(l=>{l.seats[0].price_fen=30000;});earliest.legs.at(-1).arrival_at=at('11:00');
      data.same_train.plans.push(cheapest,earliest);
    }
    if(['fallback','mobile_fallback','partial','empty'].includes(scenario)){
      data.same_train=group();data.transfer=group([],scenario==='partial'?'partial':'complete');
      if(body.include_short_fallback)data.short_fallback={options:[{id:'sample-short',ticketed_leg:same.legs[0],selected_seat_code:same.selected_seat_codes[0],destination_station:'BJP',destination_station_name:'北京',scheduled_arrival_at:at('12:00'),known_price_fen:12350,extension_price_fen:null,total_price_fen:null,conditions:'必须在原票到站前申请补票；有运输能力时才可办理，被拒绝须在原票到站下车。不承诺后续有座。',source_url:'https://mobile.12306.cn/otsmobile/h5/otsbussiness/info/transportationRules.html'}],meta:{status:'partial',notices:['只确认前段有票；后续尚未确认。']}};
    }
  }
  if(scenario==='empty'&&body.mode==='direct')data.trains=[];
  return {code:200,data};
}
async function shot(page,name){const dir=process.env.SCREENSHOT_DIR;if(dir){fs.mkdirSync(dir,{recursive:true});await page.screenshot({path:path.join(dir,`${name}.png`),fullPage:true});}}
async function noOverflow(page){assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow');}
async function openPlan(card){
  const toggle=card.getByRole('button',{name:'展开详情',exact:true});
  assert.equal(await toggle.getAttribute('aria-expanded'),'false');
  assert.equal(await card.getByTestId('journey-leg').first().isVisible(),false,'segment details are initially collapsed');
  assert.equal(await card.getByTestId('fare-summary').isVisible(),false);
  assert.equal(await card.getByRole('button',{name:'复制完整路线',exact:true}).isVisible(),false);
  assert.equal(await card.getByTestId('total-price').isVisible(),true,'the summary fare remains visible');
  await toggle.click();
  assert.equal(await card.getByRole('button',{name:'收起详情',exact:true}).getAttribute('aria-expanded'),'true');
  await card.getByTestId('journey-leg').first().waitFor({state:'visible'});
}
async function trainFare(row,name,price){
  const tile=row.locator('.train-seat').filter({hasText:name});
  await tile.waitFor({state:'visible'});assert.match(await tile.innerText(),new RegExp(price.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
}
async function legFares(card,index,{missing=false}={}){
  const group=card.getByRole('group',{name:`第${index}段席别`,exact:true});
  await group.getByRole('radio',{name:`第${index}段席别 二等座`,exact:true}).waitFor({state:'visible'});
  await group.getByRole('radio',{name:`第${index}段席别 一等座`,exact:true}).waitFor({state:'visible'});
  await group.getByText(missing?'票价待确认':'¥123.50',{exact:true}).waitFor({state:'visible'});
  await group.getByText('¥200',{exact:true}).waitFor({state:'visible'});
  assert.equal(await card.getByRole('combobox',{name:`第${index}段席别`,exact:true}).count(),0,'all segment fares appear without a dropdown');
  return group;
}
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'}),failures=[];
  const scenarios=process.env.BROWSER_SCENARIOS?.split(',') || ['desktop','mobile','fare_visibility','mobile_fares','missing_fares',...segmentScenarios,'sort_preserves','selected_transfer','regular','seats_settings','adjust_selected','fallback','mobile_fallback','partial','expanded','cancel','switch_train','collapse','empty','error'];
  try{for(const scenario of scenarios){
    const context=await browser.newContext({viewport:scenario==='narrow_segments'?{width:320,height:740}:scenario.startsWith('mobile')?{width:390,height:844}:{width:1365,height:900},permissions:['clipboard-read','clipboard-write']});
    const page=await context.newPage(),bodies=[],errors=[];let pending=[];
    page.setDefaultTimeout(Number(process.env.BROWSER_TIMEOUT_MS)||5000);
    page.on('pageerror',e=>errors.push(e.message));
    try{
      await page.route('**/api/transfers/stations?**',r=>r.fulfill({json:{code:200,data:catalog}}));
      await page.route('**/api/stations/search?**',r=>r.fulfill({json:stationResponse}));
      await page.route('**/api/stations/scope?**',r=>{const code=new URL(r.request().url()).searchParams.get('station_code');const station=stationResponse.data.find(s=>s.telecode===code);return r.fulfill({json:{code:200,data:{city_name:station?.city_name || station?.name,stations:[station],default_station_codes:[code]}}})});
      await page.route('**/api/journeys/query',r=>{const body=r.request().postDataJSON();bodies.push(body);if(scenario==='error'&&body.selected_train)return r.fulfill({status:400,json:{detail:'所选车次已变化，请重新查询车次后选择'}});if(['switch_train','collapse'].includes(scenario)&&body.selected_train?.train_no==='physical-G1'){pending.push({route:r,body});return;}return r.fulfill({json:sample(body,scenario)});});
      await page.goto(process.env.BROWSER_URL || 'http://127.0.0.1:5173');
      if(await page.getByRole('button',{name:'修改条件',exact:true}).isVisible())await page.getByRole('button',{name:'修改条件',exact:true}).click();
      assert.equal(await page.getByRole('combobox',{name:'列车类型'}).inputValue(),'all');
      const query=page.getByRole('button',{name:'查询车次',exact:true});
      if(segmentScenarios.includes(scenario)){await page.getByRole('button',{name:'交换出发地与目的地',exact:true}).click();await page.getByText('席别与中转设置',{exact:true}).click();await page.getByRole('combobox',{name:'同车最多分段',exact:true}).selectOption('3');await page.getByText('席别与中转设置',{exact:true}).click();}
      if(['desktop','mobile'].includes(scenario)){const box=await query.boundingBox();assert.ok(box.y+box.height<844,'query visible without scrolling');await shot(page,`train-ui-after-${scenario}`);}
      if(scenario==='regular')await page.getByRole('combobox',{name:'列车类型'}).selectOption('regular');
      if(scenario==='seats_settings'){
        await page.getByText('席别与中转设置',{exact:true}).click();
        assert.equal(await page.getByRole('checkbox',{name:'无座',exact:true}).isChecked(),false);
        assert.equal(await page.getByRole('checkbox',{name:'硬座',exact:true}).isChecked(),true);
        await page.getByRole('checkbox',{name:'按各站官方参考换乘时间'}).uncheck();
        const personalTime=page.getByRole('spinbutton',{name:'个人最少时间（分钟）'});
        await personalTime.fill('10');
        assert.equal(await personalTime.evaluate(input=>input.checkValidity()),true,'personal time below 15 minutes can be submitted');
        await page.getByRole('combobox',{name:'最多换乘'}).selectOption('2');
        await page.getByRole('combobox',{name:'第1个指定中转站'}).fill('南京南');
        await page.getByRole('combobox',{name:'方案排序'}).selectOption('price');
        await page.getByText('席别与中转设置',{exact:true}).click();
      }
      if(scenario==='cancel'){
        await page.route('**/api/stations/search?**',r=>pending.push(r));await query.click();await page.getByRole('button',{name:'取消本次查询',exact:true}).click();
        for(const r of pending)await r.fulfill({json:stationResponse}).catch(()=>{});
        assert.equal(bodies.length,0);await page.getByText('已取消本次查询。',{exact:true}).waitFor();
      }else{
        await query.click();
        if(scenario==='empty'){
          await page.getByText('本次范围内未查到符合条件的直达车次',{exact:true}).waitFor();await page.getByRole('button',{name:'查询全局路线',exact:true}).click();
          await page.getByRole('button',{name:'返回车次列表',exact:true}).waitFor();assert.equal(bodies.at(-1).mode,'all');assert.equal(bodies.at(-1).selected_train,undefined);
        }else{
          const code=segmentScenarios.includes(scenario)?'T109':scenario==='regular'?'K1':'G1',row=page.locator(`[data-train="${code}"]`);
          await row.waitFor();assert.equal(bodies[0].mode,'direct');assert.equal(bodies[0].selected_train,undefined);
          assert.match(await row.innerText(),/所选席别无现票/);
          if(fareScenarios.includes(scenario)){
            await shot(page,`fare-${scenario}-list`);
            await trainFare(row,'商务座','¥1600');
            await trainFare(row,'一等座','¥850');
            const soldOutFirst=row.locator('.train-seat').filter({hasText:'一等座'});
            assert.match(await soldOutFirst.innerText(),/无票|无/,'sold-out first-class fare remains visible');
            await trainFare(row,'二等座',scenario==='missing_fares'?'票价待确认':'¥550');
            if(scenario==='missing_fares'){
              const missing=row.locator('.train-seat').filter({hasText:'二等座'});
              assert.doesNotMatch(await missing.innerText(),/—|¥0(?:\.00)?(?:\s|$)/,'a missing price is never zero or a dash');
              await trainFare(row,'无座','¥550');
              assert.match(await row.locator('.train-seat').filter({hasText:'无座'}).innerText(),/余票待确认/,'a known price does not imply sold-out availability');
            }
            const regular=page.locator('[data-train="K1"]');
            for(const [name,price] of [['硬座','¥150'],['硬卧','¥300'],['软卧','¥480']])await trainFare(regular,name,price);
          }
          if(scenario==='mobile')await shot(page,'train-ui-after-mobile-list');
          await row.getByRole('button',{name:`查看 ${code} 的接续中转方案`}).click();
          if(['switch_train','collapse'].includes(scenario)){
            await page.getByText('正在核对G1余票与换乘条件…',{exact:true}).waitFor();
            if(scenario==='switch_train'){await page.locator('[data-train="G9"]').getByRole('button',{name:'接续 / 中转',exact:true}).click();await page.getByTestId('journey-plan').first().waitFor();}
            else await row.getByRole('button',{name:'收起方案',exact:true}).click();
            for(const p of pending)await p.route.fulfill({json:sample(p.body,scenario)}).catch(()=>{});
            if(scenario==='switch_train'){assert.equal(await row.getByTestId('journey-alternatives').count(),0);assert.match(await page.locator('[data-train="G9"]').getByTestId('journey-plan').first().innerText(),/G9/);}
            else assert.equal(await page.getByTestId('journey-alternatives').count(),0);
          }else if(scenario==='error')await row.getByRole('alert').filter({hasText:'所选车次已变化'}).waitFor();
          else if(['fallback','mobile_fallback','partial'].includes(scenario)){
            await row.getByText('本次范围内未找到全程有票的接续或中转方案',{exact:true}).waitFor();
            if(scenario==='partial')await row.getByText('站内中转：0 条 · 范围有限或尚未查完',{exact:true}).waitFor();
            else{
              await row.getByRole('button',{name:'查看短途有票／补票备选',exact:true}).click();await row.getByTestId('short-ticket-option').waitFor();
              assert.equal(bodies.at(-1).selected_train.train_no,'physical-G1');assert.equal(bodies.at(-1).include_short_fallback,true);
              const short=row.getByTestId('short-ticket-option'),shortFares=short.getByRole('group',{name:'前段席别',exact:true});
              await shortFares.getByText('¥123.50',{exact:true}).waitFor({state:'visible'});await shortFares.getByText('¥200',{exact:true}).waitFor({state:'visible'});
              await short.getByRole('radio',{name:'前段席别 一等座',exact:true}).check();await row.getByText('前段 ¥200',{exact:true}).waitFor();
              await row.getByRole('button',{name:'复制备选及条件'}).click();assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/原票到站：南京南/);
              await shot(page,`train-ui-after-${scenario}`);
            }
          }else{
            await row.getByTestId('journey-plan').first().waitFor();
            assert.deepEqual(bodies[1].selected_train,sample(bodies[0],scenario).data.trains.find(t=>t.train_code===code).selection);
            if(segmentScenarios.includes(scenario)){
              const card=row.getByTestId('journey-plan').first();
              await card.scrollIntoViewIfNeeded();
              await shot(page,`plan-collapsed-${scenario}`);
              if(process.env.SCREENSHOT_DIR)await card.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`plan-collapsed-${scenario}-card.png`)});
              await openPlan(card);
              const phase=process.env.SEGMENT_BASELINE==='1'?'before':'after';
              await shot(page,`segment-${phase}-${scenario}`);
              if(process.env.SCREENSHOT_DIR)await card.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`segment-${phase}-${scenario}-plan.png`)});
              if(process.env.SEGMENT_BASELINE!=='1'){
                const legs=card.getByTestId('journey-leg');assert.equal(await legs.count(),3);
                for(const [index,title,times] of [[0,'北京 → 天津西',['20:04','21:29']],[1,'天津西 → 南京',['21:32','07:43']],[2,'南京 → 上海',['07:49','11:02']]]){
                  const leg=legs.nth(index),heading=leg.getByRole('heading',{name:title,exact:true,level:4});await heading.waitFor({state:'visible'});
                  assert.match(await leg.innerText(),new RegExp(`第\\s*${index+1}\\s*段`));
                  const headingBox=await heading.boundingBox(),stepBox=await leg.locator('.leg-step').boundingBox();assert.ok(Math.abs(headingBox.y-stepBox.y)<45 && Math.abs(headingBox.x-stepBox.x)<130,'segment number and station route stay together');
                  for(const time of times)await leg.getByText(time,{exact:true}).waitFor({state:'visible'});
                }
                assert.match(await legs.nth(1).innerText(),/次日/);assert.match(await legs.nth(2).innerText(),/次日/);
                assert.equal(await card.getByRole('button',{name:/查看分段详情|收起分段详情/}).count(),0);
                const connections=card.getByTestId('journey-connection');assert.equal(await connections.count(),2);
                assert.match(await connections.nth(0).innerText(),/天津西/);assert.match(await connections.nth(0).innerText(),/硬卧\s*→\s*硬座/);assert.match(await connections.nth(1).innerText(),/南京/);
                assert.equal(await card.getByTestId('total-price').innerText(),'¥290.50');
                await card.getByRole('radio',{name:'第1段席别 软卧',exact:true}).check();assert.equal(await card.getByTestId('total-price').innerText(),'¥325.50');assert.match(await connections.nth(0).innerText(),/软卧\s*→\s*硬座/);
                await card.getByRole('button',{name:'收起详情',exact:true}).click();
                assert.equal(await legs.first().isVisible(),false);
                assert.equal(await card.getByTestId('total-price').innerText(),'¥325.50','collapse keeps the selected fare in the summary');
                const toggle=card.getByRole('button',{name:'展开详情',exact:true});await toggle.focus();await toggle.press('Enter');
                assert.equal(await card.getByRole('radio',{name:'第1段席别 软卧',exact:true}).isChecked(),true,'reopening keeps the selected seat');
                assert.match(await card.getByTestId('fare-summary').innerText(),/¥104\.50\s*\+\s*¥128\.50\s*\+\s*¥92\.50/);assert.match(await card.getByTestId('fare-summary').innerText(),/¥325\.50/);
                const singleTile=legs.nth(1).locator('.fare-option');assert.equal(await singleTile.count(),1);const tileBox=await singleTile.boundingBox();assert.ok(tileBox.width<=340,`single seat option should not stretch across desktop (${tileBox.width}px)`);
                await card.getByRole('radio',{name:'第1段席别 硬卧',exact:true}).check();
                await shot(page,`segment-${phase}-${scenario}`);
                if(process.env.SCREENSHOT_DIR)await card.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`segment-${phase}-${scenario}-plan.png`)});
              }
            }
            if(fareScenarios.includes(scenario)){
              const cards=row.getByTestId('journey-plan');assert.equal(await cards.count(),2);
              const first=cards.nth(0),collapsed=cards.nth(1),missing=scenario==='missing_fares';
              await openPlan(first);
              assert.equal(await collapsed.getByTestId('journey-leg').first().isVisible(),false,'each plan expands independently');
              await openPlan(collapsed);
              for(const card of [first,collapsed]){await legFares(card,1,{missing});await legFares(card,2);}
              await collapsed.getByTestId('journey-leg').first().getByRole('heading',{level:4}).waitFor({state:'visible'});
              await legFares(first,1,{missing});await legFares(first,2);
              assert.equal(await first.getByTestId('total-price').innerText(),missing?'票价待确认':'¥247');
              if(missing){
                assert.match(await first.innerText(),/已知 ¥123\.50/);
                await first.getByRole('button',{name:'复制完整路线',exact:true}).click();
                assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/总价：票价待确认/);
              }
              await first.getByRole('radio',{name:'第1段席别 一等座',exact:true}).check();
              assert.equal(await first.getByTestId('total-price').innerText(),'¥323.50');
              assert.equal(await collapsed.getByRole('radio',{name:'第1段席别 二等座',exact:true}).isChecked(),true,'native radio groups are independent across plans');
              await collapsed.getByRole('radio',{name:'第1段席别 一等座',exact:true}).check();
              assert.equal(await collapsed.getByTestId('total-price').innerText(),'¥323.50','an expanded plan remains selectable');
              assert.equal(await first.getByRole('radio',{name:'第1段席别 一等座',exact:true}).isChecked(),true);
              await collapsed.getByRole('radio',{name:'第1段席别 二等座',exact:true}).check();
              await first.getByRole('button',{name:/复制完整路线|已复制路线/}).click();
              const copied=await page.evaluate(()=>navigator.clipboard.readText());assert.match(copied,/一等座/);assert.match(copied,/总价：¥323\.50/);
              await first.getByRole('radio',{name:'第1段席别 二等座',exact:true}).check();
              assert.equal(await first.getByTestId('total-price').innerText(),missing?'票价待确认':'¥247','switching back preserves the known or unknown total');
              await shot(page,`fare-${scenario}-plans`);
              if(process.env.SCREENSHOT_DIR)await first.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`fare-${scenario}-first-plan.png`)});
              if(scenario==='mobile_fares'){await page.setViewportSize({width:320,height:740});await noOverflow(page);await legFares(first,1);await legFares(collapsed,2);await shot(page,'fare-mobile-320');}
            }
            if(scenario==='selected_transfer'){
              await row.getByRole('button',{name:'站内中转 1'}).click();
              const card=row.getByTestId('journey-plan'),connection=card.getByTestId('journey-connection');await openPlan(card);await connection.waitFor({state:'visible'});
              const text=await connection.innerText();assert.match(text,/南京南/);assert.match(text,/同站换车/);assert.match(text,/等待\s*15\s*分钟/);assert.match(text,/G1\s*→\s*G2/);
              const details=connection.locator('details');assert.equal(await details.getAttribute('open'),null);assert.equal(await connection.getByRole('link',{name:'便捷换乘资料来源',exact:true}).isVisible(),false);
              await connection.getByText('换乘资料及适用条件',{exact:true}).click();await connection.getByRole('link',{name:'便捷换乘资料来源',exact:true}).waitFor({state:'visible'});
              await connection.getByText('换乘资料及适用条件',{exact:true}).click();await connection.waitFor({state:'visible'});
              await shot(page,'segment-after-station-transfer');
            }
            if(scenario==='sort_preserves'){
              const cards=row.getByTestId('journey-plan');assert.equal(await cards.count(),3);
              const original=cards.filter({hasText:'¥247'});assert.equal(await original.count(),1);await openPlan(original);
              await original.getByRole('radio',{name:'第1段席别 一等座',exact:true}).check();
              const selectedPlan=cards.filter({hasText:'¥323.50'});assert.equal(await selectedPlan.count(),1);
              const before=bodies.length;await page.getByRole('combobox',{name:'方案排序',exact:true}).selectOption('price');
              assert.equal(await page.getByTestId('train-row').count(),3);assert.equal(await cards.count(),3,'sort keeps expanded plans');assert.equal(await cards.first().getByTestId('total-price').innerText(),'¥100');
              assert.equal(await selectedPlan.getByRole('radio',{name:'第1段席别 一等座',exact:true}).isChecked(),true,'sort keeps selected seats');
              assert.equal(await selectedPlan.getByRole('button',{name:'收起详情',exact:true}).getAttribute('aria-expanded'),'true','sort keeps expansion state');
              assert.equal(await cards.first().getByTestId('journey-leg').first().isVisible(),false,'sort keeps other plans collapsed');
              await page.getByRole('combobox',{name:'方案排序',exact:true}).selectOption('arrival');assert.equal(await cards.first().getByTestId('total-price').innerText(),'¥600');
              await page.getByRole('combobox',{name:'方案排序',exact:true}).selectOption('duration');assert.equal(await cards.first().getByTestId('total-price').innerText(),'¥323.50');
              assert.equal(bodies.length,before,'sorting is local and never re-queries');
            }
            if(scenario==='adjust_selected'){
              await page.getByText('席别与中转设置',{exact:true}).click();
              await page.getByRole('checkbox',{name:'按各站官方参考换乘时间'}).uncheck();
              await page.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).fill('45');
              assert.equal(await page.getByTestId('train-row').count(),3);assert.equal(await row.getByTestId('journey-plan').count(),0);
              await row.getByRole('button',{name:'重新查询方案'}).click();await row.getByTestId('journey-plan').first().waitFor();
              assert.equal(bodies.at(-1).selected_train.train_no,'physical-G1');assert.equal(bodies.at(-1).min_transfer_minutes,45);
              assert.equal(bodies.filter(b=>b.mode==='direct').length,1);
            }
            if(scenario==='seats_settings'){
              assert.equal(bodies[0].min_transfer_minutes,10);assert.equal(bodies[1].min_transfer_minutes,10);assert.equal(bodies[1].transfer_count,2);assert.deepEqual(bodies[1].ordered_via_stations,['NKH']);assert.equal(bodies[1].sort_by,'price');
              const card=row.getByTestId('journey-plan');await openPlan(card);await card.getByRole('radio',{name:'第1段席别 一等座',exact:true}).check();assert.equal(await card.getByTestId('total-price').innerText(),'¥323.50');
              await card.getByRole('button',{name:'复制完整路线'}).click();assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/¥323.50/);
            }
            if(scenario==='expanded'){
              // Re-run with an empty result so the expansion action is available.
              await page.route('**/api/journeys/query',r=>{const body=r.request().postDataJSON();bodies.push(body);return r.fulfill({json:sample(body,body.allow_large_detour?'expanded':'fallback')});});
              await row.getByRole('button',{name:'重新查询方案'}).click();await row.getByRole('button',{name:'允许较大绕行并重查'}).click();
              await row.getByTestId('journey-plan').first().waitFor();assert.equal(bodies.at(-1).allow_large_detour,true);assert.equal(bodies.at(-1).selected_train.train_no,'physical-G1');
              await row.getByRole('button',{name:'站内中转 1'}).click();await openPlan(row.getByTestId('journey-plan'));await row.getByText('此路线可能明显绕行或等待较长，请核对经由站和全程耗时。',{exact:true}).waitFor();
            }
            if(['desktop','mobile'].includes(scenario)){
              await row.getByRole('button',{name:'站内中转 1'}).click();
              const card=row.getByTestId('journey-plan');await card.scrollIntoViewIfNeeded();
              await shot(page,`train-ui-after-${scenario}-selected`);
              if(process.env.SCREENSHOT_DIR)await card.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`plan-collapsed-transfer-${scenario}-card.png`)});
            }
          }
        }
      }
      await noOverflow(page);if(scenario==='mobile'){await page.setViewportSize({width:320,height:740});await noOverflow(page);}assert.deepEqual(errors,[]);console.log(`PASS ${scenario}`);
    }catch(e){failures.push(`${scenario}: ${e.stack}`);}finally{await context.close();}
  }}finally{await browser.close();}
  if(failures.length)throw Error(failures.join('\n'));
})().catch(e=>{console.error(e);process.exit(1)});
