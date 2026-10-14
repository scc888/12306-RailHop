const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const catalog=require('../../backend/data/transfer_stations.json');
const url=process.env.BROWSER_URL || 'http://127.0.0.1:5173';
const key='railhop.journey.settings.v1';
const stationResponse={code:200,data:[{name:'上海',telecode:'SHH',city_name:'上海',city_code:'sh'},{name:'北京',telecode:'BJP',city_name:'北京',city_code:'bj'}]};
async function mocks(page){
  const requests=[];
  await page.route('**/api/transfers/stations?**',r=>r.fulfill({json:{code:200,data:catalog}}));
  await page.route('**/api/stations/search?**',r=>r.fulfill({json:stationResponse}));
  await page.route('**/api/stations/scope?**',r=>{const code=new URL(r.request().url()).searchParams.get('station_code'),station=stationResponse.data.find(s=>s.telecode===code);return r.fulfill({json:{code:200,data:{stations:[station],default_station_codes:[code]}}})});
  await page.route('**/api/journeys/query',r=>{
    const body=r.request().postDataJSON(),day=body.train_date;
    requests.push(body);
    const trains=Array.from({length:16},(_,i)=>({id:`row-${i}`,train_no:`physical-${i}`,train_code:`G${i+1}`,
      start_time:'08:00',arrive_time:'12:00',duration:'04:00',can_buy:true,
      from_station_name:'上海',to_station_name:'北京',from_station_telecode:'SHH',to_station_telecode:'BJP',
      start_station_name:'上海',end_station_name:'北京',departure_at:`${day}T08:00:00+08:00`,arrival_at:`${day}T12:00:00+08:00`,
      seats:{ze:'有',zy:'无',swz:'1'},prices:{ze:'¥550',zy:'¥850',swz:'¥1600'},selection:null}));
    const group=status=>({plans:[],meta:{status,notices:[]}});
    return r.fulfill({json:{code:200,data:{trains,direct:group('complete'),same_train:group('skipped'),transfer:group('skipped'),short_fallback:{options:[],meta:{status:'skipped',notices:[]}},queried_at:`${day}T07:00:00+08:00`,scope:{from_label:'上海',to_label:'北京'}}}});
  });
  return requests;
}
async function openSettings(page){
  const open=page.getByRole('button',{name:'修改条件',exact:true});
  if(await open.isVisible())await open.click();
}
async function shot(page,name){
  if(process.env.SCREENSHOT_DIR){fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`${name}.png`)});}
}
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'});
  try{
    const page=await browser.newPage({viewport:{width:1365,height:900}});
    await mocks(page);await page.goto(url);
    assert.equal(await page.locator('aside#journey-settings').count(),1,'query conditions live in a sidebar');
    await page.getByRole('button',{name:'查询车次',exact:true}).click();
    await page.locator('[data-train="G16"]').waitFor();
    const resultsScroll=page.locator('.journey-results-scroll');
    assert.equal(await resultsScroll.count(),1,'train results have their own scroll area');
    const initialPanel=await page.locator('#journey-settings').boundingBox();
    await resultsScroll.hover();await page.mouse.wheel(0,1100);
    await page.waitForFunction(()=>document.querySelector('.journey-results-scroll').scrollTop>0);
    await page.locator('[data-train="G12"]').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(()=>window.scrollY),0,'browsing trains never scrolls the document');
    assert.ok(await resultsScroll.evaluate(el=>el.scrollTop>0),'only train results scroll');
    const panel=await page.locator('#journey-settings').boundingBox(),row=await page.locator('[data-train="G12"]').boundingBox();
    assert.equal(panel.y,initialPanel.y,'settings panel does not move when results scroll');
    const header=await page.getByRole('banner').boundingBox();
    assert.ok(Math.abs(header.y)<1,'top navigation remains pinned while browsing lower trains');
    assert.ok(panel.y>=header.y+header.height+12 && panel.y<header.height+40,'sidebar stays below top navigation');
    assert.ok(panel.x+panel.width<row.x,'train results remain beside settings');
    const query=await page.getByRole('button',{name:'查询车次',exact:true}).boundingBox();
    assert.ok(query.y>=0 && query.y+query.height<=900,'query button stays on screen');
    await page.getByText('席别与中转设置',{exact:true}).click();
    await page.getByRole('checkbox',{name:'按各站官方参考换乘时间'}).uncheck();
    await page.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).fill('10');
    assert.equal(await page.getByTestId('train-row').count(),16,'changing transfer conditions preserves train list');
    const trainScrollTop=await resultsScroll.evaluate(el=>el.scrollTop);
    await page.locator('.settings-scroll').hover();await page.mouse.wheel(0,700);
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    assert.ok(await page.locator('.settings-scroll').evaluate(el=>el.scrollTop>0),'overflowing settings scroll inside their panel');
    assert.equal(await resultsScroll.evaluate(el=>el.scrollTop),trainScrollTop,'scrolling settings leaves trains in place');
    assert.equal(await page.evaluate(()=>window.scrollY),0,'settings never scroll the document');
    await shot(page,'settings-desktop-scrolled');
    console.log('PASS desktop sticky settings and preserved train list');

    for(const width of [320,390,1024]){
      const mobile=await browser.newPage({viewport:{width,height:844}});
      const requests=await mocks(mobile);await mobile.goto(url);
      await mobile.getByRole('button',{name:'修改条件',exact:true}).click();
      const dialog=mobile.getByRole('dialog',{name:'查询设置',exact:true});await dialog.waitFor();
      await dialog.getByText('席别与中转设置',{exact:true}).click();
      await dialog.getByRole('checkbox',{name:'按各站官方参考换乘时间'}).uncheck();
      await dialog.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).fill('10');
      const button=await dialog.getByRole('button',{name:'查询车次',exact:true}).boundingBox();
      assert.ok(button.y>=0 && button.y+button.height<=844,'drawer query button always visible');
      const close=await dialog.getByRole('button',{name:'关闭查询设置',exact:true}).boundingBox();
      assert.ok(close.y>=0 && close.y+close.height<=844,'drawer close button remains visible after scrolling settings');
      assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal overflow');
      await mobile.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
      assert.equal(await mobile.getByRole('button',{name:'修改条件',exact:true}).evaluate(e=>e===document.activeElement),true,'closing returns focus to trigger');
      await openSettings(mobile);await dialog.getByRole('button',{name:'查询车次',exact:true}).click();
      await dialog.waitFor({state:'hidden'});await mobile.locator('[data-train="G16"]').waitFor();
      await mobile.locator('[data-train="G12"]').scrollIntoViewIfNeeded();
      assert.equal(await mobile.evaluate(()=>window.scrollY),0,'narrow screen results do not scroll the document');
      assert.ok(await mobile.locator('.journey-results-scroll').evaluate(el=>el.scrollTop>0),'narrow screen results scroll independently');
      const trigger=await mobile.getByRole('button',{name:'修改条件',exact:true}).boundingBox();
      const mobileHeader=await mobile.getByRole('banner').boundingBox();
      assert.ok(Math.abs(mobileHeader.y)<1,'top navigation remains pinned on narrow screens');
      assert.ok(trigger.y>=mobileHeader.y+mobileHeader.height,'modify conditions is not covered by top navigation');
      assert.ok(trigger.y>=0 && trigger.y+trigger.height<=844,'modify conditions remains reachable below trains');
      if(width===390)await shot(mobile,'settings-mobile-trains');
      await openSettings(mobile);
      await dialog.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).fill('0');
      await dialog.getByRole('button',{name:'关闭查询设置',exact:true}).click();
      const queryCount=requests.length;
      await mobile.getByRole('button',{name:'查询车次',exact:true}).click();
      await dialog.waitFor({state:'visible',timeout:2000});
      assert.equal(requests.length,queryCount,'toolbar respects form validation and sends no invalid request');
      assert.equal(await mobile.getByTestId('train-row').count(),16,'invalid input does not clear existing trains');
      assert.equal(await dialog.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).evaluate(e=>e===document.activeElement),true,'invalid field is focused in drawer');
      await dialog.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).fill('10');
      await mobile.keyboard.press('Escape');
      const nextQuery=mobile.waitForRequest('**/api/journeys/query');
      await mobile.getByRole('button',{name:'查询车次',exact:true}).click();
      assert.equal((await nextQuery).postDataJSON().min_transfer_minutes,10,'valid toolbar query uses personal time');
      await mobile.locator('[data-train="G16"]').waitFor();
      await openSettings(mobile);if(width===390)await shot(mobile,'settings-mobile-drawer');
      await mobile.close();console.log(`PASS ${width}px drawer and reachable settings`);
    }
    await page.close();
    for(const viewport of [{width:1200,height:600},{width:1365,height:500}]){
      const compact=await browser.newPage({viewport});await mocks(compact);await compact.goto(url);
      await compact.getByRole('button',{name:'查询车次',exact:true}).click();
      await compact.locator('[data-train="G16"]').waitFor();
      await compact.locator('[data-train="G12"]').scrollIntoViewIfNeeded();
      const scroll=compact.locator('.journey-results-scroll');
      assert.ok(await scroll.evaluate(el=>el.scrollTop>0 && el.scrollWidth<=el.clientWidth+1),'compact window has vertical results scroll without horizontal clipping');
      assert.equal(await compact.evaluate(()=>window.scrollY),0,'compact window has no document scroll');
      const query=await compact.getByRole('button',{name:'查询车次',exact:true}).boundingBox();
      assert.ok(query.y>=0 && query.y+query.height<=viewport.height,'query remains reachable in short windows');
      await compact.close();console.log(`PASS ${viewport.width}x${viewport.height} independent scrolling`);
    }
  }finally{await browser.close();}

  const profileParent=path.resolve(__dirname,'../../.superpowers/sdd');fs.mkdirSync(profileParent,{recursive:true});
  const profile=fs.mkdtempSync(path.join(profileParent,'settings-profile-'));
  const launch=()=>chromium.launchPersistentContext(profile,{headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome',viewport:{width:1365,height:900}});
  let context=await launch();
  try{
    let page=await context.newPage();await mocks(page);await page.goto(url);
    await page.locator('#journey-from').fill('北京');await page.locator('#journey-to').fill('上海');
    await page.getByRole('combobox',{name:'出发范围',exact:true}).selectOption('station');
    await page.getByText('席别与中转设置',{exact:true}).click();
    await page.getByRole('checkbox',{name:'按各站官方参考换乘时间'}).uncheck();
    await page.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).fill('10');
    await page.getByRole('combobox',{name:'最多换乘'}).selectOption('2');
    await page.getByRole('combobox',{name:'第1个指定中转站'}).fill('郑州东');
    await page.getByRole('combobox',{name:'方案排序'}).selectOption('price');
    await page.getByRole('checkbox',{name:'无座',exact:true}).check();
    await page.waitForFunction(k=>JSON.parse(localStorage.getItem(k))?.settings?.minMinutes===10,key);
    await context.close();context=await launch();
    page=await context.newPage();await mocks(page);await page.goto(url);
    assert.equal(await page.locator('#journey-from').inputValue(),'北京');assert.equal(await page.locator('#journey-to').inputValue(),'上海');
    assert.equal(await page.getByRole('combobox',{name:'出发范围',exact:true}).inputValue(),'station');
    assert.equal(await page.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).inputValue(),'10');
    assert.equal(await page.getByRole('combobox',{name:'最多换乘'}).inputValue(),'2');
    assert.equal(await page.getByRole('combobox',{name:'第1个指定中转站'}).inputValue(),'郑州东');
    assert.equal(await page.getByRole('combobox',{name:'方案排序'}).inputValue(),'price');
    assert.equal(await page.getByRole('checkbox',{name:'无座',exact:true}).isChecked(),true);
    const today=await page.locator('#journey-date').getAttribute('min');
    await page.evaluate(k=>{const data=JSON.parse(localStorage.getItem(k));data.settings.trainDate='2000-01-01';localStorage.setItem(k,JSON.stringify(data));},key);
    await page.reload();assert.equal(await page.locator('#journey-date').inputValue(),today);
    assert.equal(await page.getByRole('spinbutton',{name:'个人最少时间（分钟）'}).inputValue(),'10');
    await page.getByRole('button',{name:'恢复默认设置',exact:true}).click();
    assert.equal(await page.locator('#journey-from').inputValue(),'上海');
    await page.reload();assert.equal(await page.locator('#journey-from').inputValue(),'上海');
    console.log('PASS settings survive browser restart; expired date and reset');
  }finally{await context.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
