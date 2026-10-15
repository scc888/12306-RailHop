// Offline browser interaction proof. Fixtures do not verify live railway availability.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const url=process.env.BROWSER_URL || 'http://127.0.0.1:5173';
const stations=[
  {name:'上海',telecode:'SHH',city_name:'上海',city_code:'sh'},
  {name:'上海虹桥',telecode:'AOH',city_name:'上海',city_code:'sh'},
  {name:'北京',telecode:'BJP',city_name:'北京',city_code:'bj'},
  {name:'北京南',telecode:'VNP',city_name:'北京',city_code:'bj'},
];

async function createPage(browser,viewport={width:1365,height:900},deviceScaleFactor=1,{manyStations=false}={}){
  const page=await browser.newPage({viewport,deviceScaleFactor}),requests=[],errors=[];
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const fixtureStations=manyStations ? [...stations,...['sh','bj'].flatMap(city=>Array.from({length:28},(_,index)=>({name:`${city==='sh'?'上海':'北京'}城市范围内用于窄屏文字换行检查的较长车站名称第${index+1}站`,telecode:`${city==='sh'?'X':'Y'}${alphabet[Math.floor(index/26)]}${alphabet[index%26]}`,city_name:city==='sh'?'上海':'北京',city_code:city})))] : stations;
  page.setDefaultTimeout(5000);
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/stations/search?**',route=>route.fulfill({json:{code:200,data:fixtureStations}}));
  await page.route('**/api/stations/scope?**',route=>{
    const anchor=new URL(route.request().url()).searchParams.get('station_code');
    const city=fixtureStations.find(station=>station.telecode===anchor)?.city_code,cityStations=fixtureStations.filter(station=>station.city_code===city);
    return route.fulfill({json:{code:200,data:{city_name:city==='sh'?'上海':'北京',stations:cityStations,default_station_codes:manyStations?cityStations.map(station=>station.telecode):[anchor]}}});
  });
  await page.route('**/api/transfers/stations?**',route=>route.fulfill({json:{code:200,data:[]}}));
  await page.route('**/api/journeys/query',route=>{
    const body=route.request().postDataJSON();requests.push(body);
    const group=status=>({plans:[],meta:{status,notices:[]}});
    const from=fixtureStations.find(station=>station.telecode===body.from_station),to=fixtureStations.find(station=>station.telecode===body.to_station);
    const trains=Array.from({length:16},(_,index)=>({id:`row-${index}`,train_no:`physical-${index}`,train_code:`G${index+1}`,start_time:'08:00',arrive_time:'12:00',duration:'04:00',can_buy:true,from_station_name:from.name,to_station_name:to.name,from_station_telecode:from.telecode,to_station_telecode:to.telecode,start_station_name:from.name,end_station_name:to.name,departure_at:`${body.train_date}T08:00:00+08:00`,arrival_at:`${body.train_date}T12:00:00+08:00`,seats:{ze:'有',zy:'无',swz:'1'},prices:{ze:'¥550',zy:'¥850',swz:'¥1600'},selection:null}));
    return route.fulfill({json:{code:200,data:{trains,direct:group('complete'),same_train:group('skipped'),transfer:group('complete'),short_fallback:{options:[],meta:{status:'skipped',notices:[]}},queried_at:`${body.train_date}T07:00:00+08:00`,scope:{from_label:from.name,to_label:to.name}}}});
  });
  await page.goto(url);
  await page.getByRole('checkbox',{name:'出发 上海',exact:true,includeHidden:true}).waitFor({state:'attached'});
  await page.getByRole('checkbox',{name:'到达 北京',exact:true,includeHidden:true}).waitFor({state:'attached'});
  return {page,requests,errors};
}

async function openSettings(page){
  const trigger=page.getByRole('button',{name:'修改条件',exact:true});
  if(await trigger.isVisible())await trigger.click();
}
async function openStations(page){
  await openSettings(page);
  const details=page.locator('details.station-settings');
  // The red-phase swap proof also runs before this disclosure is introduced.
  if(await details.count() && !await details.evaluate(element=>element.open))await details.locator('summary').click();
}
async function setDisclosure(page,selector,open){
  const details=page.locator(selector);
  if(await details.evaluate(element=>element.open)!==open)await details.locator('summary').click();
}
async function screenshot(page,name){
  if(!process.env.SCREENSHOT_DIR)return;
  fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});
  await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`${name}.png`)});
}
async function submit(page,name='查询车次'){
  const response=page.waitForResponse(response=>response.url().endsWith('/api/journeys/query'));
  await page.getByRole('button',{name,exact:true}).click();
  await response;
  await page.getByRole('heading',{level:2}).waitFor();
}
const checkbox=(page,name)=>page.getByRole('checkbox',{name,exact:true,includeHidden:true});

async function swapScenario(browser){
  const {page,requests,errors}=await createPage(browser);
  try{
    await openStations(page);
    await checkbox(page,'出发 上海虹桥').check();await checkbox(page,'出发 上海').uncheck();
    await checkbox(page,'到达 北京南').check();await checkbox(page,'到达 北京').uncheck();
    await submit(page);
    assert.deepEqual(requests.at(-1).from_station_codes,['AOH']);
    assert.deepEqual(requests.at(-1).to_station_codes,['VNP']);
    await page.getByRole('button',{name:'交换出发地与目的地',exact:true}).click();
    await submit(page);
    assert.deepEqual(requests.at(-1).from_station_codes,['VNP'],'swap keeps the destination city custom station selection');
    assert.deepEqual(requests.at(-1).to_station_codes,['AOH'],'swap keeps the origin city custom station selection');
    assert.equal(requests.at(-1).from_station,'VNP');assert.equal(requests.at(-1).to_station,'AOH');
    await openStations(page);
    assert.equal(await checkbox(page,'出发 北京南').isChecked(),true);
    assert.equal(await checkbox(page,'出发 北京').isChecked(),false);
    assert.equal(await checkbox(page,'到达 上海虹桥').isChecked(),true);
    assert.equal(await checkbox(page,'到达 上海').isChecked(),false);
    await page.getByRole('button',{name:'交换出发地与目的地',exact:true}).click();
    await submit(page);
    assert.deepEqual(requests.at(-1).from_station_codes,['AOH'],'swapping back restores both custom station sets');
    assert.deepEqual(requests.at(-1).to_station_codes,['VNP']);
    assert.deepEqual(errors,[]);
    console.log('PASS swap preserves both city station selections and request anchors');
  }finally{await page.close()}
}

async function validationScenario(browser){
  for(const viewport of [{width:1365,height:900},{width:390,height:844}]){
    for(const invalid of ['', '0'])for(const method of viewport.width<1200?['button','enter','input-enter']:['button','enter']){
      const {page,requests,errors}=await createPage(browser,viewport);
      try{
        await openSettings(page);
        await setDisclosure(page,'details.advanced-settings',true);
        await page.getByRole('checkbox',{name:'按各站官方参考换乘时间',exact:true}).uncheck();
        const minutes=page.getByRole('spinbutton',{name:'个人最少时间（分钟）',exact:true,includeHidden:true});
        await minutes.fill(invalid);
        await setDisclosure(page,'details.advanced-settings',false);
        if(method==='button'){
          if(viewport.width<1200)await page.getByRole('button',{name:'关闭查询设置',exact:true}).click();
          await page.getByRole('button',{name:'查询车次',exact:true}).click();
        }else if(method==='input-enter'){
          await page.locator('#journey-from').press('Enter');
        }else if(viewport.width<1200){
          // Keyboard activation remains deterministic with the native datalist.
          await page.locator('#journey-settings').getByRole('button',{name:'查询车次',exact:true}).press('Enter');
        }else{
          await page.locator('#journey-from').focus();
          // A native datalist may consume Enter to accept its highlighted station.
          await page.keyboard.press('Escape');
          await page.keyboard.press('Enter');
        }
        await minutes.waitFor({state:'visible'});
        assert.equal(await page.locator('details.advanced-settings').evaluate(element=>element.open),true,'invalid hidden custom time opens its settings');
        assert.equal(await minutes.evaluate(element=>element===document.activeElement),true,'validation focuses the invalid custom time field');
        assert.equal(await minutes.inputValue(),invalid,'validation does not replace the personal value');
        assert.equal(requests.length,0,'invalid settings never send a query POST');
        if(viewport.width<1200)assert.equal(await page.getByRole('dialog',{name:'查询设置',exact:true}).isVisible(),true,'mobile validation keeps the drawer open');
        await minutes.fill('10');
        await submit(page);
        assert.equal(requests.at(-1).mode,'direct');
        assert.equal(requests.at(-1).min_transfer_minutes,10,'corrected personal time is authoritative');
        await page.reload();await openSettings(page);
        await setDisclosure(page,'details.advanced-settings',true);
        assert.equal(await page.getByRole('spinbutton',{name:'个人最少时间（分钟）',exact:true}).inputValue(),'10','corrected time persists after reload');
        assert.deepEqual(errors,[]);
        console.log(`PASS custom time ${JSON.stringify(invalid)} / ${method} / width ${viewport.width}`);
      }finally{await page.close()}
    }
  }
}

async function seatsScenario(browser){
  for(const viewport of [{width:1365,height:900},{width:320,height:844},{width:390,height:844}]){
    const {page,requests,errors}=await createPage(browser,viewport);
    try{
      await openSettings(page);await setDisclosure(page,'details.advanced-settings',true);
      const seats=page.getByRole('group',{name:'可接受席别',exact:true});
      for(const input of await seats.getByRole('checkbox').all())await input.uncheck();
      await setDisclosure(page,'details.advanced-settings',false);
      await page.getByRole('button',{name:'查询车次',exact:true}).click();
      await seats.waitFor({state:'visible'});
      assert.equal(await page.locator('details.advanced-settings').evaluate(element=>element.open),true,'empty seats opens the seat settings');
      await page.getByRole('alert',{includeHidden:true}).filter({hasText:'请至少选择一种可接受席别'}).first().waitFor({state:'visible'});
      assert.equal(await seats.evaluate(element=>element===document.activeElement || element.contains(document.activeElement)),true,'empty seats focuses the seat selection area');
      assert.equal(requests.length,0,'empty seats never send a query POST');
      if(viewport.width<1200)assert.equal(await page.getByRole('dialog',{name:'查询设置',exact:true}).isVisible(),true,'seat validation keeps mobile settings open');
      await seats.getByRole('checkbox',{name:'二等座',exact:true}).check();
      await submit(page);assert.deepEqual(requests.at(-1).allowed_seats,['ze']);
      assert.deepEqual(errors,[]);
      console.log(`PASS empty seat error opens and focuses seat choices / width ${viewport.width}`);
    }finally{await page.close()}
  }
}

async function collapseScenario(browser){
  const {page,requests,errors}=await createPage(browser);
  try{
    const stationSettings=page.locator('details.station-settings'),summary=stationSettings.locator('summary');
    assert.equal(await stationSettings.evaluate(element=>element.open),false,'specific station settings start collapsed');
    assert.match(await summary.innerText(),/选择具体车站/);
    assert.match(await summary.innerText(),/上海/);assert.match(await summary.innerText(),/北京/);
    assert.equal(await checkbox(page,'出发 上海').isVisible(),false,'station checkboxes stay hidden until requested');
    await submit(page);const initial=structuredClone(requests.at(-1));
    await openStations(page);
    await checkbox(page,'出发 上海虹桥').check();await checkbox(page,'出发 上海').uncheck();
    await checkbox(page,'到达 北京南').check();await checkbox(page,'到达 北京').uncheck();
    await setDisclosure(page,'details.station-settings',false);
    assert.match(await summary.innerText(),/上海虹桥/);assert.match(await summary.innerText(),/北京南/);
    await submit(page);const customized=structuredClone(requests.at(-1));
    assert.deepEqual(customized.from_station_codes,['AOH']);assert.deepEqual(customized.to_station_codes,['VNP']);
    await setDisclosure(page,'details.station-settings',true);
    assert.equal(await checkbox(page,'出发 上海虹桥').isChecked(),true);assert.equal(await checkbox(page,'到达 北京南').isChecked(),true);
    await setDisclosure(page,'details.station-settings',false);await submit(page);
    assert.deepEqual(requests.at(-1),customized,'opening and closing configuration preserves the query request');
    assert.equal(await page.locator('details.advanced-settings').evaluate(element=>element.open),false,'advanced configuration also starts collapsed');
    assert.notDeepEqual(initial.from_station_codes,customized.from_station_codes);
    await screenshot(page,'ui-station-summary-desktop');
    assert.deepEqual(errors,[]);
    console.log('PASS station disclosure defaults, selected summary, and request preservation');
  }finally{await page.close()}
}

async function withinViewport(page,locator,label){
  const box=await locator.boundingBox(),viewport=page.viewportSize();
  assert.ok(box && box.x>=-1 && box.y>=-1 && box.x+box.width<=viewport.width+1 && box.y+box.height<=viewport.height+1,`${label} stays fully on screen: ${JSON.stringify(box)}`);
}
async function layoutScenario(browser){
  for(const viewport of [{width:1365,height:900},{width:320,height:844},{width:390,height:844},{width:1024,height:768},{width:1365,height:480},{width:390,height:500},{width:683,height:450,zoom:2}]){
    // 200% browser zoom halves the CSS viewport; doubled density preserves a
    // 1366x900 physical surface. This checks equivalent reflow, not pinch zoom.
    const {zoom,...size}=viewport,{page,requests,errors}=await createPage(browser,size,zoom || 1);
    try{
      if(size.width===1365 && size.height===900){
        await withinViewport(page,page.locator('details.station-settings summary'),'desktop station disclosure');
        await withinViewport(page,page.locator('details.advanced-settings summary'),'desktop advanced disclosure');
      }
      await openSettings(page);await setDisclosure(page,'details.station-settings',true);await setDisclosure(page,'details.advanced-settings',true);
      const panel=page.locator('#journey-settings');
      const direct=panel.getByRole('button',{name:'查询车次',exact:true}),fastest=panel.getByRole('button',{name:'查最快中转',exact:true});
      assert.equal(await direct.evaluate(element=>element.classList.contains('journey-primary')),true,'train query has primary emphasis');
      assert.equal(await fastest.evaluate(element=>element.classList.contains('journey-secondary')),true,'fastest transfer has secondary emphasis');
      await withinViewport(page,direct,'drawer or sidebar query button');await withinViewport(page,fastest,'drawer or sidebar transfer button');
      await page.locator('.settings-scroll').hover();await page.mouse.wheel(0,1000);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      await withinViewport(page,direct,'query button after settings scroll');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'expanded settings have no horizontal overflow');
      assert.equal(await page.evaluate(()=>window.scrollY),0,'settings use their own scroll container');
      await submit(page);assert.equal(requests.length,1);
      await page.locator('[data-train="G16"]').waitFor();
      await page.locator('[data-train="G12"]').scrollIntoViewIfNeeded();
      assert.equal(await page.evaluate(()=>window.scrollY),0,'results use their own scroll container');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'results have no horizontal overflow');
      if(size.width<1200){
        const mobile=page.locator('.mobile-query-bar');
        await withinViewport(page,mobile.getByRole('button',{name:'修改条件',exact:true}),'modify conditions');
        await withinViewport(page,mobile.getByRole('button',{name:'查询车次',exact:true}),'mobile query button');
        await withinViewport(page,mobile.getByRole('button',{name:'查最快中转',exact:true}),'mobile transfer button');
      }else await withinViewport(page,direct,'sidebar query after results scroll');
      await screenshot(page,`ui-layout-${size.width}x${size.height}${zoom?'-zoom200':''}`);
      assert.deepEqual(errors,[]);
      console.log(`PASS reachable actions and internal scrolling / ${size.width}x${size.height}${zoom?' / 200% equivalent reflow':''}`);
    }finally{await page.close()}
  }
}

async function manyStationsScenario(browser){
  const {page,requests,errors}=await createPage(browser,{width:320,height:640},1,{manyStations:true});
  try{
    const mobile=page.locator('.mobile-query-bar');
    assert.match(await mobile.innerText(),/出发\s*30\s*站/);assert.match(await mobile.innerText(),/到达\s*30\s*站/);
    await openSettings(page);
    const summary=page.locator('details.station-settings summary');
    assert.match(await summary.innerText(),/等\s*30\s*站/,'large station ranges show a bounded summary');
    await setDisclosure(page,'details.station-settings',true);await setDisclosure(page,'details.advanced-settings',true);
    assert.equal(await page.locator('.station-details-content input[type=checkbox]').count(),60);
    assert.equal(await page.locator('.station-details-content input[type=checkbox]:checked').count(),60,'all 30 stations per endpoint start selected');
    const longLabel=page.locator('.station-details-content label').filter({hasText:'第1站'}).first();
    assert.ok(await longLabel.evaluate(element=>element.getBoundingClientRect().height>parseFloat(getComputedStyle(element).lineHeight)*1.5),'long station names wrap across lines');
    await withinViewport(page,page.locator('#journey-settings').getByRole('button',{name:'查询车次',exact:true}),'query with a large station range');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'expanded long station names and advanced settings fit 320px');
    await submit(page);
    assert.equal(requests.at(-1).from_station_codes.length,30);assert.equal(requests.at(-1).to_station_codes.length,30,'the compact summary preserves the full request scope');
    const results=page.locator('.journey-results-scroll');
    assert.ok((await results.boundingBox()).height>=160,'a large station scope leaves at least 160px for results at 320x640');
    await page.locator('[data-train="G12"]').scrollIntoViewIfNeeded();
    await withinViewport(page,mobile.getByRole('button',{name:'查询车次',exact:true}),'mobile query after large-scope results');
    await withinViewport(page,mobile.getByRole('button',{name:'修改条件',exact:true}),'modify large-scope conditions');
    assert.equal(await page.evaluate(()=>window.scrollY),0);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
    await screenshot(page,'ui-many-stations-320x640');
    assert.deepEqual(errors,[]);
    console.log('PASS 30 stations per city / bounded summary / wrapped names / 320x640 result height');
  }finally{await page.close()}
}

async function routeValidationScenario(browser){
  for(const viewport of [{width:1365,height:900},{width:390,height:844}]){
    const {page,requests,errors}=await createPage(browser,viewport);
    try{
      await submit(page);await page.locator('[data-train="G16"]').waitFor();
      await openSettings(page);await setDisclosure(page,'details.advanced-settings',true);
      await page.getByRole('checkbox',{name:'按各站官方参考换乘时间',exact:true}).uncheck();
      const minutes=page.getByRole('spinbutton',{name:'个人最少时间（分钟）',exact:true,includeHidden:true});
      await minutes.fill('0');await setDisclosure(page,'details.advanced-settings',false);
      if(viewport.width<1200)await page.getByRole('button',{name:'关闭查询设置',exact:true}).click();
      await page.getByRole('button',{name:'不限定车次，查全部路线',exact:true}).click();
      await minutes.waitFor({state:'visible'});
      assert.equal(await minutes.evaluate(element=>element===document.activeElement),true,'the route action focuses its invalid hidden field');
      assert.equal(requests.length,1,'route actions cannot bypass shared input validation');
      assert.equal(await page.getByTestId('train-row').count(),16,'failed route validation preserves the existing train list');
      if(viewport.width<1200)assert.equal(await page.getByRole('dialog',{name:'查询设置',exact:true}).isVisible(),true);
      await minutes.fill('10');
      if(viewport.width<1200)await page.getByRole('button',{name:'关闭查询设置',exact:true}).click();
      const response=page.waitForResponse(response=>response.url().endsWith('/api/journeys/query'));
      await page.getByRole('button',{name:'不限定车次，查全部路线',exact:true}).click();await response;
      assert.equal(requests.at(-1).mode,'all');assert.equal(requests.at(-1).min_transfer_minutes,10);
      assert.deepEqual(errors,[]);
      console.log(`PASS route actions validate hidden conditions and preserve trains / width ${viewport.width}`);
    }finally{await page.close()}
  }
}

(async()=>{
  const executablePath=process.env.BROWSER_EXECUTABLE_PATH;
  const browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{channel:process.env.BROWSER_CHANNEL || 'chrome'})});
  try{
    const scenarios={swap:swapScenario,validation:validationScenario,seats:seatsScenario,collapse:collapseScenario,layout:layoutScenario,'many-stations':manyStationsScenario,'route-validation':routeValidationScenario};
    const requested=(process.env.UI_SCENARIOS || Object.keys(scenarios).join(',')).split(',');
    for(const name of requested){assert.ok(scenarios[name],`unknown UI scenario: ${name}`);await scenarios[name](browser)}
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
