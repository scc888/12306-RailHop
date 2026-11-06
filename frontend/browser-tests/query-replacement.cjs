// Fixed responses verify replacement/cancellation; no live railway availability is asserted.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const stations=[{name:'上海',telecode:'SHH',city_name:'上海',city_code:'sh'}, {name:'北京',telecode:'BJP',city_name:'北京',city_code:'bj'}];
const group=()=>({plans:[],meta:{status:'complete',notices:[]}});
function response(body,code){
  return {code:200,data:{trains:[{id:code,train_no:code,train_code:code,start_time:'08:00',arrive_time:'12:00',duration:'04:00',can_buy:true,
    from_station_name:'上海',to_station_name:'北京',seats:{ze:'有'},prices:{ze:'¥100'},selection:null}],
    direct:group(),same_train:group(),transfer:group(),queried_at:`${body.train_date}T07:00:00+08:00`,scope:{from_label:'上海',to_label:'北京'}}};
}
async function waitForRequests(page,pending,count){
  for(let attempt=0;pending.length<count && attempt<100;attempt++)await page.waitForTimeout(20);
  assert.equal(pending.length,count,`expected ${count} requests`);
}
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE_PATH?{executablePath:process.env.BROWSER_EXECUTABLE_PATH}:{channel:'chrome'})});
  try{
    for(const width of [1365,390]){
      const page=await browser.newPage({viewport:{width,height:900}}),pending=[],errors=[];
      page.setDefaultTimeout(5000);
      page.on('pageerror',error=>errors.push(error.message));
      await page.route('**/api/stations/search?**',route=>route.fulfill({json:{code:200,data:stations}}));
      await page.route('**/api/stations/scope?**',route=>{
        const code=new URL(route.request().url()).searchParams.get('station_code');
        return route.fulfill({json:{code:200,data:{stations:stations.filter(s=>s.telecode===code),default_station_codes:[code]}}});
      });
      await page.route('**/api/transfers/stations?**',route=>route.fulfill({json:{code:200,data:[]}}));
      await page.route('**/api/journeys/query',route=>{pending.push({route,body:route.request().postDataJSON()})});
      await page.goto(process.env.BROWSER_URL || 'http://127.0.0.1:5181');
      const visibleButton=name=>page.getByRole('button',{name,exact:true}).filter({visible:true});
      await visibleButton('查最快中转').click();
      await page.waitForFunction(()=>document.querySelector('[role=status]'));
      await waitForRequests(page,pending,1);
      assert.equal(await visibleButton('重新查询车次').isEnabled(),true);
      await visibleButton('重新查询车次').click();
      await waitForRequests(page,pending,2);
      assert.equal(pending[0].body.mode,'fastest');
      assert.equal(pending[1].body.mode,'direct');
      await pending[1].route.fulfill({json:response(pending[1].body,'G222')});
      await page.getByText('G222',{exact:true}).waitFor();
      await pending[0].route.fulfill({json:response(pending[0].body,'G111')}).catch(()=>{});
      await page.waitForTimeout(100);
      assert.equal(await page.getByText('G111',{exact:true}).count(),0);
      assert.equal(await page.getByText('G222',{exact:true}).count(),1);
      // Repeated direct searches with identical conditions also replace an in-flight request.
      await visibleButton('查询车次').click();
      await waitForRequests(page,pending,3);
      await visibleButton('重新查询车次').click();
      await waitForRequests(page,pending,4);
      await pending[3].route.fulfill({json:response(pending[3].body,'G444')});
      await page.getByText('G444',{exact:true}).waitFor();
      await pending[2].route.fulfill({json:response(pending[2].body,'G333')}).catch(()=>{});
      await page.waitForTimeout(100);
      assert.equal(await page.getByText('G333',{exact:true}).count(),0);
      assert.deepEqual(errors,[]);
      console.log(`PASS in-flight fastest/direct replacement, repeat submission and stale results / width ${width}`);
      await page.close();
    }
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
