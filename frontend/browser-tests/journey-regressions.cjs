// Fixed-response browser tests; these samples are NOT live ticket availability.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const catalog=require('../../backend/data/transfer_stations.json');
const seed=require('./fixtures/transfer.json').data.plans[0];
const stationResponse={code:200,data:[{name:'上海',telecode:'SHH',pinyin:'shanghai',pinyin_abbr:'sh',city_name:'上海',city_code:'sh'},{name:'北京',telecode:'BJP',pinyin:'beijing',pinyin_abbr:'bj',city_name:'北京',city_code:'bj'}]};
const group=(plans=[],status='complete',notices=[])=>({plans,meta:{status,notices}});
function sample(body,scenario){
  const transfer={...structuredClone(seed),id:'sample-transfer',kind:'transfer'};
  transfer.connections[0].station=catalog.find(s=>s.station_code==='NKH');
  transfer.connections[0].official_min_minutes=15;
  const same={...structuredClone(seed),id:'sample-same',kind:'same_train',connections:[],selected_seat_codes:['yw','yw'],total_price_fen:30000,known_price_fen:30000};
  same.legs.forEach((leg,i)=>{leg.train_no='physical-K1';leg.train_code='K1';leg.run_date='2026-10-11';leg.seats=[{code:'yw',name:'硬卧',availability:'有',price_fen:15000},...(i===0?[{code:'yz',name:'硬座',availability:'2',price_fen:10000}]:[])];});
  if(body.train_type==='regular')transfer.legs.forEach((l,i)=>{l.train_code=`K${i+2}`;});
  if(body.allow_large_detour)transfer.route_assessment={mode:'expanded',warnings:['此路线可能明显绕行或等待较长，请核对经由站和全程耗时。']};
  const data={direct:group(),same_train:group([same]),transfer:group([transfer],'partial',['固定样本：候选范围有限。']),short_fallback:{options:[],meta:{status:'skipped',notices:[]}},queried_at:'2026-10-12T10:00:00+08:00',scope:{from_label:'上海（同城车站）',to_label:'北京（同城车站）'}};
  if(['fallback','mobile_fallback','partial'].includes(scenario)){
    data.same_train=group();data.transfer=group([],scenario==='partial'?'partial':'complete');
    if(body.include_short_fallback)data.short_fallback={options:[{id:'sample-short',ticketed_leg:same.legs[0],selected_seat_code:'yw',destination_station:'BJP',destination_station_name:'北京',scheduled_arrival_at:same.legs[1].arrival_at,known_price_fen:15000,extension_price_fen:null,total_price_fen:null,conditions:'必须在原票到站前向列车工作人员申请补票；有运输能力时才可办理，被拒绝时须在原票到站下车。不承诺后续有座、同席别或继续使用原席位。',source_url:'https://mobile.12306.cn/otsmobile/h5/otsbussiness/info/transportationRules.html'}],meta:{status:'partial',notices:['只确认前段有票；后续尚未确认。']}};
  }
  return {code:200,data};
}
async function shot(page,name){const dir=process.env.SCREENSHOT_DIR;if(dir){fs.mkdirSync(dir,{recursive:true});await page.screenshot({path:path.join(dir,`${name}.png`),fullPage:true});}}
async function noOverflow(page){assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow');}
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'}),failures=[];
  const scenarios=process.env.BROWSER_SCENARIOS?.split(',') || ['desktop','mobile','seats_sort_official','regular','fallback','mobile_fallback','partial','expanded','cancel','error'];
  try{for(const scenario of scenarios){
    const context=await browser.newContext({viewport:scenario.startsWith('mobile')?{width:390,height:844}:{width:1365,height:900},permissions:['clipboard-read','clipboard-write']});
    const page=await context.newPage(),bodies=[],errors=[];let pending=[];
    page.on('pageerror',e=>errors.push(e.message));
    try{
      await page.route('**/api/transfers/stations?**',r=>r.fulfill({json:{code:200,data:catalog}}));
      await page.route('**/api/stations/search?**',r=>r.fulfill({json:stationResponse}));
      await page.route('**/api/journeys/query',r=>{const body=r.request().postDataJSON();bodies.push(body);return scenario==='error'?r.fulfill({status:429,json:{detail:'当前有路线查询正在进行，请稍后重试'}}):r.fulfill({json:sample(body,scenario)});});
      await page.goto(process.env.BROWSER_URL || 'http://127.0.0.1:5173');
      await page.getByText('目前 12 个有便捷换乘资料的候选站',{exact:false}).waitFor({state:'attached'});
      assert.equal(await page.getByRole('combobox',{name:'列车类型'}).inputValue(),'all');
      assert.equal(await page.getByRole('checkbox',{name:'无座',exact:true}).isChecked(),false);
      assert.equal(await page.getByRole('checkbox',{name:'硬座',exact:true}).isChecked(),true);
      await noOverflow(page);
      const query=page.getByRole('button',{name:'查询出行路线',exact:true});
      if(['desktop','mobile'].includes(scenario)){
        const box=await query.boundingBox();assert.ok(box.y+box.height<844,'query visible without scrolling');
        await shot(page,`journey-after-${scenario}`);await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>document.activeElement!==document.body));
      }
      if(scenario==='cancel'){
        await page.route('**/api/stations/search?**',r=>pending.push(r));await query.click();
        await page.getByRole('button',{name:'取消本次查询',exact:true}).click();assert.equal(pending.length,2);
        for(const r of pending)await r.fulfill({json:stationResponse}).catch(()=>{});
        await page.waitForTimeout(100);assert.equal(bodies.length,0);await page.getByText('已取消本次查询。',{exact:true}).waitFor();
      }else{
        if(scenario==='regular')await page.getByRole('combobox',{name:'列车类型'}).selectOption('regular');
        if(scenario==='expanded'){await page.getByText('更多路线条件',{exact:true}).click();await page.getByRole('checkbox',{name:'允许较大绕行（默认关闭）'}).check();}
        await query.click();
        if(scenario==='error')await page.getByRole('alert').filter({hasText:'当前有路线查询正在进行'}).waitFor();
        else if(['fallback','mobile_fallback','partial'].includes(scenario)){
          await page.getByRole('heading',{name:'本次范围内未找到全程有票路线'}).waitFor();assert.equal(await page.getByTestId('journey-plan').count(),0);
          if(scenario==='partial')await page.getByText('本次查询未完整完成，以下仅为已查到的结果。',{exact:true}).waitFor();
          else{
            await page.getByRole('button',{name:'查看短途有票／补票备选',exact:true}).click();
            const card=page.getByTestId('short-ticket-option');await card.waitFor();assert.equal(bodies.at(-1).include_short_fallback,true);assert.equal(bodies.at(-1).mode,'all');
            await card.getByRole('combobox',{name:'前段席别'}).selectOption('yz');await card.getByText('前段 ¥100',{exact:true}).waitFor();
            await card.getByRole('button',{name:'复制备选及条件'}).click();const copied=await page.evaluate(()=>navigator.clipboard.readText());
            assert.match(copied,/原票到站：南京南/);assert.match(copied,/全程总价待确认/);assert.match(copied,/下车/);
            assert.equal(await page.getByTestId('journey-plan').count(),0);await shot(page,scenario==='mobile_fallback'?'journey-after-mobile-fallback':'journey-after-fallback');
          }
        }else{
          await page.getByTestId('journey-plan').first().waitFor();assert.equal(bodies[0].allow_large_detour,scenario==='expanded');assert.equal(bodies[0].min_transfer_minutes,null);assert.equal(bodies[0].from_scope,'city');
          if(scenario==='regular')assert.equal(bodies[0].train_type,'regular');
          if(scenario==='expanded')await page.getByText('此路线可能明显绕行或等待较长，请核对经由站和全程耗时。',{exact:true}).waitFor();
          if(scenario==='seats_sort_official'){
            const card=page.locator('[data-kind="same_train"]');await card.getByRole('combobox',{name:'第1段席别'}).selectOption('yz');assert.equal(await card.getByTestId('total-price').innerText(),'¥250');
            await card.getByRole('button',{name:'复制完整路线'}).click();assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/¥250/);
            await page.getByRole('combobox',{name:'结果排序'}).selectOption('price');assert.equal(await page.getByTestId('journey-plan').count(),0);await query.click();await page.getByTestId('journey-plan').first().waitFor();assert.equal(bodies[1].sort_by,'price');
            await page.getByText('更多路线条件',{exact:true}).click();await page.getByRole('checkbox',{name:'按各站官方参考换乘时间'}).uncheck();await page.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).fill('60');assert.equal(await page.getByTestId('journey-plan').count(),0);
            await query.click();await page.getByTestId('journey-plan').first().waitFor();assert.equal(bodies[2].min_transfer_minutes,60);
          }
          if(['desktop','mobile'].includes(scenario))await shot(page,`journey-after-${scenario}-results`);
        }
      }
      await noOverflow(page);if(scenario==='mobile'){await page.setViewportSize({width:320,height:740});await noOverflow(page);}assert.deepEqual(errors,[]);console.log(`PASS ${scenario}`);
    }catch(e){failures.push(`${scenario}: ${e.stack}`);}finally{await context.close();}
  }}finally{await browser.close();}
  if(failures.length)throw Error(failures.join('\n'));
})().catch(e=>{console.error(e);process.exit(1)});
