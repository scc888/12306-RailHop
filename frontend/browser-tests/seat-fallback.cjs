// Fixed railway responses: exercise actual UI requests, without live availability claims.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const seed=require('./fixtures/transfer.json').data.plans[0];
const defaults=['ze','zy','yz','yw','rw'];
const group=(plans=[])=>({plans,meta:{status:'complete',notices:[]}});
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'});
  try{
    for(const mobile of [false,true]){
      const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1365,height:900}});
      await context.addInitScript(()=>localStorage.setItem('railhop.journey.settings.v1',JSON.stringify({version:1,settings:{allowedSeats:['yw']}})));
      const page=await context.newPage(),requests=[],errors=[];
      page.setDefaultTimeout(5000);
      page.on('pageerror',e=>errors.push(e.message));
      await page.route('**/api/transfers/stations?**',r=>r.fulfill({json:{code:200,data:[]}}));
      await page.route('**/api/stations/search?**',r=>r.fulfill({json:{code:200,data:[
        {name:'上海',telecode:'SHH',city_code:'sh',city_name:'上海'},
        {name:'北京',telecode:'BJP',city_code:'bj',city_name:'北京'}]}}));
      await page.route('**/api/journeys/query',r=>{
        const body=r.request().postDataJSON();requests.push(body);
        const at=time=>`${body.train_date}T${time}:00+08:00`;
        const trains=['G1','K1'].map(code=>({id:`row-${code}`,train_no:code,train_code:code,
          start_time:'08:00',arrive_time:'12:00',duration:'04:00',can_buy:true,
          from_station_name:'上海',to_station_name:'北京',from_station_telecode:'SHH',to_station_telecode:'BJP',
          departure_at:at('08:00'),arrival_at:at('12:00'),
          seats:code==='G1'?{ze:'有',zy:'无',yw:'--'}:{yw:'无',yz:'有'},
          prices:code==='G1'?{ze:'¥550',zy:'¥850'}:{yw:'¥300',yz:'¥150'},
          selection:{train_no:code,run_date:body.train_date,from_station:'SHH',to_station:'BJP',departure_at:at('08:00')}}));
        const plan=structuredClone(seed);plan.id='default-seats-plan';plan.kind='same_train';plan.connections=[];
        plan.selected_seat_codes=['ze','ze'];
        plan.legs.forEach((leg,i)=>Object.assign(leg,{train_no:'G1',train_code:'G1',
          departure_at:at(i?'09:02':'08:00'),arrival_at:at(i?'12:00':'09:00'),
          seats:[{code:'ze',name:'二等座',availability:'有',price_fen:12350}]}));
        const plans=body.selected_train?.train_no==='G1' && body.allowed_seats.includes('ze')?[plan]:[];
        return r.fulfill({json:{code:200,data:{trains,selected_train:body.selected_train||null,
          direct:group(),same_train:group(plans),transfer:group(),queried_at:at('07:00'),
          short_fallback:{options:[],meta:{status:'skipped',notices:[]}},scope:{from_label:'上海',to_label:'北京'}}}});
      });
      await page.goto(process.env.BROWSER_URL || 'http://127.0.0.1:5173');
      await page.getByRole('button',{name:'查询车次',exact:true}).first().click();
      const high=page.locator('[data-train="G1"]');
      await high.waitFor();
      assert.deepEqual(requests[0].allowed_seats,['yw']);
      await high.getByRole('button',{name:'查看 G1 的接续中转方案'}).click();
      await high.getByRole('button',{name:'重新查询方案',exact:true}).waitFor();
      assert.deepEqual(requests.at(-1).allowed_seats,defaults);
      await high.getByTestId('journey-plan').first().waitFor();
      assert.match(await high.innerText(),/默认席别/);
      assert.match(await high.innerText(),/二等座/);
      const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('railhop.journey.settings.v1')));
      assert.deepEqual(stored.settings.allowedSeats,['yw'],'fallback must not replace saved preferences');
      const regular=page.locator('[data-train="K1"]');
      await regular.getByRole('button',{name:'查看 K1 的接续中转方案'}).click();
      await regular.getByRole('button',{name:'重新查询方案',exact:true}).waitFor();
      assert.deepEqual(requests.at(-1).allowed_seats,['yw'],'a sold-out offered sleeper must keep the preference');
      assert.doesNotMatch(await regular.innerText(),/默认席别/);
      await page.getByRole('button',{name:'不限定车次，查全部路线',exact:true}).click();
      await page.getByRole('button',{name:'返回车次列表',exact:true}).waitFor();
      assert.deepEqual(requests.at(-1).allowed_seats,['yw'],'unrestricted search keeps saved preferences');
      assert.deepEqual(errors,[]);
      console.log(`PASS incompatible seat fallback and sold-out preference ${mobile?'mobile':'desktop'}`);
      await context.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
