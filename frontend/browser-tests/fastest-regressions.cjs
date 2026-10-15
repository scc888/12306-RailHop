// Offline contract and interaction proof; fixtures are not live railway availability.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || require('node:path').join(process.env.TEMP,'railhop-browser-tools/node_modules/playwright'));
const assert=require('node:assert/strict');
const seed=require('./fixtures/transfer.json').data.plans[0];
const stations=[{name:'上海',telecode:'SHH',city_name:'上海',city_code:'sh'},{name:'上海虹桥',telecode:'AOH',city_name:'上海',city_code:'sh'},{name:'安亭北',telecode:'ASH',city_name:'上海',city_code:'sh'},{name:'北京',telecode:'BJP',city_name:'北京',city_code:'bj'},{name:'北京南',telecode:'VNP',city_name:'北京',city_code:'bj'}];
const group=(plans=[],status='complete')=>({plans,meta:{status,notices:['固定样本：本次范围有限']}});
async function openStationSettings(page){const details=page.locator('details.station-settings');if(await details.count() && !await details.evaluate(el=>el.open))await details.locator('summary').click();}
function sample(body){
 const transfer={...structuredClone(seed),id:'fast',kind:'transfer'};
 transfer.legs.forEach(leg=>{for(const key of ['departure_at','arrival_at','queried_at'])leg[key]=body.train_date+leg[key].slice(10)});
 transfer.legs[0].from_station=body.from_station;transfer.legs[0].from_station_name=stations.find(s=>s.telecode===body.from_station)?.name||'上海';transfer.legs[1].to_station=body.to_station;transfer.legs[1].to_station_name=stations.find(s=>s.telecode===body.to_station)?.name||'北京';
 const slower={...structuredClone(transfer),id:'slow',total_minutes:300};slower.connections[0].wait_minutes=75;slower.legs[1].departure_at=body.train_date+'T10:15:00+08:00';slower.legs[1].arrival_at=body.train_date+'T13:00:00+08:00';
 const direct={...structuredClone(transfer),id:'direct',kind:'direct',connections:[],legs:[{...transfer.legs[0],to_station_name:transfer.legs[1].to_station_name,arrival_at:body.train_date+'T11:20:00+08:00'}],selected_seat_codes:['ze'],total_minutes:200};
 return {code:200,data:{trains:[],scope:{mode:body.mode,from_label:'上海',to_label:'北京'},queried_at:transfer.legs[0].queried_at,direct:group([direct]),same_train:group([],'skipped'),transfer:group([slower,transfer],'partial'),short_fallback:{options:[],meta:{status:'skipped',notices:[]}}}};
}
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE_PATH?{executablePath:process.env.BROWSER_EXECUTABLE_PATH}:{channel:'chrome'})});try{
 let emptyTransfers=false,holdScope=false,holdPost=false,many=false;const pendingScope=[],pendingPost=[];
 const page=await browser.newPage({viewport:{width:1365,height:900}}),bodies=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/stations/search?**',r=>r.fulfill({json:{code:200,data:stations}}));
 await page.route('**/api/stations/scope?**',r=>{const code=new URL(r.request().url()).searchParams.get('station_code'),city=stations.find(s=>s.telecode===code)?.city_code;if(holdScope){pendingScope.push({r,code,city});return;}return r.fulfill({json:{code:200,data:{city_name:city==='sh'?'上海':'北京',stations:stations.filter(s=>s.city_code===city),default_station_codes:[code]}}})});
 await page.route('**/api/transfers/stations?**',r=>r.fulfill({json:{code:200,data:[]}}));
 await page.route('**/api/journeys/query',r=>{const body=r.request().postDataJSON();bodies.push(body);if(holdPost){pendingPost.push({r,body});return;}const response=sample(body);if(emptyTransfers)response.data.transfer=group();if(many)response.data.transfer.plans.push(...Array.from({length:5},(_,i)=>{const plan={...structuredClone(response.data.transfer.plans[0]),id:`extra-${i}`,total_minutes:400+i};plan.legs.forEach(leg=>leg.seats[0].price_fen=1000);return plan}));return r.fulfill({json:response})});
 await page.goto(process.env.BROWSER_URL||'http://127.0.0.1:5181');
 const fastest=page.getByRole('button',{name:'查最快中转',exact:true});await fastest.waitFor({timeout:3000});
 await openStationSettings(page);
 await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).check();
 await page.getByRole('checkbox',{name:'出发 上海',exact:true}).uncheck();
 await fastest.click();await page.getByTestId('journey-plan').first().waitFor();
 if(process.env.SCREENSHOT_DIR){const fs=require('node:fs'),path=require('node:path');fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'fastest-desktop.png')});await page.setViewportSize({width:390,height:844});await page.getByTestId('journey-plan').first().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'fastest-mobile.png')});await page.setViewportSize({width:1365,height:900});}
 assert.equal(bodies[0].mode,'fastest');assert.equal(bodies[0].sort_by,'duration');assert.equal(bodies[0].selected_train,undefined);assert.equal(bodies[0].max_transfers,1);
 assert.deepEqual(bodies[0].from_station_codes,['AOH']);assert.equal(bodies[0].from_station,'AOH');
 assert.equal(await page.getByTestId('journey-plan').count(),2,'direct comparison is separate');
 assert.match(await page.getByTestId('direct-comparison').innerText(),/直达对照/);
 const first=page.getByTestId('journey-plan').first();assert.match(await first.innerText(),/本次已查范围内最快/);assert.match(await first.innerText(),/南京南.*等待 15/);
 assert.equal(await first.getByTestId('journey-leg').first().isVisible(),false);
 await first.getByRole('button',{name:'展开详情',exact:true}).click();
 await page.getByRole('combobox',{name:'方案排序',exact:true}).selectOption('price');
 assert.equal(await page.getByText('本次已查范围内最快',{exact:true}).count(),0);
 assert.equal(await first.getByRole('button',{name:'收起详情',exact:true}).count(),1);
 await page.getByRole('button',{name:'重新查询方案',exact:true}).click();assert.equal(bodies.at(-1).mode,'fastest');assert.equal(bodies.at(-1).sort_by,'duration');
 await page.getByRole('button',{name:'扩大到最多2次换乘',exact:true}).click();await page.getByTestId('journey-plan').first().waitFor();assert.equal(bodies.at(-1).max_transfers,2);assert.equal(bodies.at(-1).mode,'fastest');
 await page.reload();await openStationSettings(page);await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).waitFor();assert.equal(await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).isChecked(),true);assert.equal(await page.getByRole('checkbox',{name:'出发 上海',exact:true}).isChecked(),false);
 await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).uncheck();await fastest.click();await page.getByRole('alert').filter({hasText:'至少选择'}).waitFor();await page.reload();await openStationSettings(page);await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).waitFor({timeout:3000});assert.equal(await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).isChecked(),false);
 await page.getByRole('combobox',{name:'出发范围',exact:true}).selectOption('station');await fastest.click();await page.getByTestId('journey-plan').first().waitFor();assert.deepEqual(bodies.at(-1).from_station_codes,['SHH']);
 await page.getByRole('button',{name:'交换出发地与目的地',exact:true}).click();await fastest.click();await page.getByTestId('journey-plan').first().waitFor();assert.equal(bodies.at(-1).from_station,'BJP');assert.ok(!bodies.at(-1).from_station_codes.includes('AOH'));
 await page.locator('#journey-from').fill('上海虹桥');await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).waitFor();await fastest.click();await page.getByTestId('journey-plan').first().waitFor();assert.deepEqual(bodies.at(-1).from_station_codes,['AOH']);
 emptyTransfers=true;await page.getByRole('button',{name:'重新查询方案',exact:true}).click();await page.getByRole('button',{name:'允许较大绕行并重查',exact:true}).click();await page.getByRole('button',{name:'重新查询方案',exact:true}).waitFor();assert.equal(bodies.at(-1).mode,'fastest');assert.equal(bodies.at(-1).allow_large_detour,true);emptyTransfers=false;
 holdScope=true;const beforeCancel=bodies.length;await page.getByRole('button',{name:'重新查询方案',exact:true}).click();for(let i=0;i<30 && pendingScope.length<2;i++)await page.waitForTimeout(20);assert.equal(pendingScope.length,2);await page.getByRole('button',{name:'取消本次查询',exact:true}).click();holdScope=false;for(const {r,code,city} of pendingScope)await r.fulfill({json:{code:200,data:{stations:stations.filter(s=>s.city_code===city),default_station_codes:[code]}}}).catch(()=>{});assert.equal(bodies.length,beforeCancel,'cancelled scope preparation sends no POST');
 holdPost=true;await fastest.click();for(let i=0;i<30 && !pendingPost.length;i++)await page.waitForTimeout(20);assert.equal(pendingPost.length,1);await page.getByRole('button',{name:'取消本次查询',exact:true}).click();holdPost=false;many=true;await fastest.click();await page.getByTestId('journey-plan').first().waitFor();for(const {r,body} of pendingPost)await r.fulfill({json:sample(body)}).catch(()=>{});assert.equal(await page.getByTestId('journey-plan').count(),5);
 const boundary=page.getByTestId('journey-plan').first();await boundary.getByRole('button',{name:'展开详情',exact:true}).click();await boundary.getByRole('radio',{name:'第1段席别 一等座',exact:true}).check();
 await page.getByRole('combobox',{name:'方案排序',exact:true}).selectOption('price');
 const restored=page.getByTestId('journey-plan').filter({hasText:'G1 一等座'});assert.equal(await restored.count(),0,'expanded expensive plan crosses pagination boundary after price sort');
 await page.getByRole('button',{name:/再显示 2 条方案/}).click();assert.equal(await page.getByTestId('journey-plan').count(),7);
 assert.equal(await restored.getByRole('button',{name:'收起详情',exact:true}).count(),1,'expanded state survives unmount across sorting and pagination');assert.equal(await restored.getByRole('radio',{name:'第1段席别 一等座',exact:true}).isChecked(),true);
await page.setViewportSize({width:390,height:844});assert.equal(await page.getByRole('button',{name:'查最快中转',exact:true}).isVisible(),true);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);if(process.env.SCREENSHOT_DIR){require('node:fs').mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:require('node:path').join(process.env.SCREENSHOT_DIR,'fastest-pagination-mobile.png')});}
 await page.setViewportSize({width:1365,height:900});
 const reset=page.getByRole('button',{name:'恢复默认设置',exact:true});
 await reset.click();await openStationSettings(page);await page.getByRole('checkbox',{name:'出发 上海',exact:true}).waitFor();
 await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).check();await page.getByRole('checkbox',{name:'出发 上海',exact:true}).uncheck();
 await reset.click();await openStationSettings(page);await page.getByRole('checkbox',{name:'出发 上海',exact:true}).waitFor();
 assert.equal(await page.getByRole('checkbox',{name:'出发 上海',exact:true}).isChecked(),true,'reset immediately reloads default scope even when input and mode stay unchanged');
 assert.equal(await page.getByRole('checkbox',{name:'出发 上海虹桥',exact:true}).isChecked(),false,'reset clears the displayed custom scope before querying');
 await fastest.click();await page.getByTestId('journey-plan').first().waitFor();assert.deepEqual(bodies.at(-1).from_station_codes,['SHH'],'submitted scope matches reset checkboxes');
 pendingPost.length=0;holdPost=true;await fastest.click();for(let i=0;i<30 && !pendingPost.length;i++)await page.waitForTimeout(20);assert.equal(pendingPost.length,1);
 await reset.click();assert.equal(await page.getByRole('button',{name:'取消本次查询',exact:true}).count(),0,'reset cancels in-flight query');assert.equal(await page.getByTestId('journey-plan').count(),0);
 holdPost=false;for(const {r,body} of pendingPost)await r.fulfill({json:sample(body)}).catch(()=>{});
 await page.getByText('已恢复默认查询设置。',{exact:true}).waitFor();assert.equal(await page.getByTestId('journey-plan').count(),0,'late reset query does not restore stale results');
 assert.deepEqual(errors,[]);console.log('PASS fastest scope / anchors / persistence / max / comparison / collapsed facts / sort / retry / swap');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
