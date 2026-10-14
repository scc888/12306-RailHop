// Offline UI proof: an unlisted station resolves and unknown provenance stays unknown.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const seed=require('./fixtures/transfer.json').data.plans[0];
const url=process.env.BROWSER_URL || 'http://127.0.0.1:5173';
const dictionary=[{name:'上海',telecode:'SHH',city_name:'上海',city_code:'sh'},
  {name:'北京',telecode:'BJP',city_name:'北京',city_code:'bj'},
  {name:'合肥南',telecode:'ENH',pinyin:'hefeinan',pinyin_abbr:'hfn',city_name:'合肥',city_code:'hf'}];
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'});
  try{
    for(const mobile of [false,true]){
      const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1365,height:900}});
      page.setDefaultTimeout(5000);
      const errors=[],requests=[];
      page.on('pageerror',error=>errors.push(error.message));
      // A failed convenience catalogue must not disable all-dictionary via lookup.
      await page.route('**/api/transfers/stations?**',route=>route.fulfill({status:503,json:{detail:'unavailable'}}));
      await page.route('**/api/stations/search?**',route=>route.fulfill({json:{code:200,data:dictionary}}));
      await page.route('**/api/stations/scope?**',r=>{const code=new URL(r.request().url()).searchParams.get('station_code'),station=dictionary.find(s=>s.telecode===code);return r.fulfill({json:{code:200,data:{stations:[station],default_station_codes:[code]}}})});
  await page.route('**/api/journeys/query',route=>{
        const body=route.request().postDataJSON();requests.push(body);
        const at=time=>`${body.train_date}T${time}:00+08:00`;
        const plan=structuredClone(seed);plan.id='unknown-via';plan.kind='transfer';
        plan.legs[0].to_station='ENH';plan.legs[0].to_station_name='合肥南';
        plan.legs[1].from_station='ENH';plan.legs[1].from_station_name='合肥南';
        plan.legs.forEach((leg,i)=>{leg.departure_at=at(i?'10:00':'08:00');leg.arrival_at=at(i?'12:00':'09:00');leg.queried_at=at('07:00');});
        plan.connections[0]={station:{station_name:'合肥南',station_code:'ENH',convenient_transfer_confirmed:false,
          source_url:null,source_published_at:null,verified_at:null,applicable_conditions:'可能需要出站重新安检进站'},
          wait_minutes:60,required_minutes:60,official_min_minutes:null,source_url:null};
        const group=(plans=[],status='complete')=>({plans,meta:{status,notices:[]}});
        return route.fulfill({json:{code:200,data:{trains:[],direct:group(),same_train:group(),
          transfer:group([plan],'partial'),short_fallback:{options:[],meta:{status:'skipped'}},
          queried_at:at('07:00'),scope:{from_label:'上海',to_label:'北京'}}}});
      });
      await page.goto(url);
      if(mobile)await page.getByRole('button',{name:'修改条件',exact:true}).click();
      await page.getByText('席别与中转设置',{exact:true}).click();
      const via=page.locator('#via-0');await via.fill('合肥南');
      await page.getByRole('button',{name:'查询车次',exact:true}).click();
      await page.getByRole('button',{name:'不限定车次，查全部路线',exact:true}).click();
      await page.getByRole('button',{name:'展开详情',exact:true}).click();
      await page.getByText('便捷换乘状态未核实，可能需要出站重新安检进站；请核对通道开放时段和检票截止时间。',{exact:true}).waitFor();
      assert.deepEqual(requests.at(-1).ordered_via_stations,['ENH']);
      assert.match(await page.locator('[data-testid="journey-connection"]').innerText(),/至少 60 分钟/);
      await page.getByText('换乘资料及适用条件',{exact:true}).click();
      assert.equal(await page.getByRole('link',{name:'便捷换乘资料来源',exact:true}).count(),0);
      assert.doesNotMatch(await page.locator('[data-testid="journey-connection"]').innerText(),/null|undefined|资料发布/);
      assert.deepEqual(errors,[]);
      await page.close();console.log(`PASS unlisted manual station and unknown metadata ${mobile?'mobile':'desktop'}`);
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
