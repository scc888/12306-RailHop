// Fixed responses verify browser interactions, not live railway availability.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const stations=require('../../backend/data/transfer_stations.json');
const fixture=require('./fixtures/transfer.json');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'});
  try {
    for(const width of [1365,390]) {
      const page=await browser.newPage({viewport:{width,height:900}});
      const errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      const stationResponse={code:200,data:[
        {name:'上海',telecode:'SHH',pinyin:'shanghai',pinyin_abbr:'sh'},
        {name:'北京',telecode:'BJP',pinyin:'beijing',pinyin_abbr:'bj'}]};
      await page.route('**/api/stations/search?**',r=>r.fulfill({json:stationResponse}));
      await page.route('**/api/transfers/stations?**',r=>r.fulfill({json:{code:200,data:stations}}));
      const seats=Object.fromEntries(['ze','zy','swz','srrb','rw','yw','yz','wz','gr','rz'].map(code=>[code,'--']));
      const trains=['G1','K1'].map(train=>({train_no:train,train_code:train,start_time:'08:00',arrive_time:'12:00',duration:'04:00',
        from_station_name:'上海',to_station_name:'北京',start_station_name:'上海',end_station_name:'北京',can_buy:true,
        seats:{...seats,has_any_ticket:true,...(train==='K1'?{yw:'有',yz:'有'}:{ze:'有'})},prices:{yw:'150',yz:'100',ze:'250'}}));
      await page.route('**/api/tickets/query?**',r=>r.fulfill({json:{code:200,data:trains}}));
      const requests=[];
      await page.route('**/api/transfers/query',r=>{
        const body=r.request().postDataJSON();
        requests.push(body);
        const snapshot=structuredClone(fixture);
        const plan=snapshot.data.plans[0];
        plan.legs[0].train_code='K1';
        plan.legs[0].seats=[{code:'yw',name:'硬卧',availability:'有',price_fen:15000},{code:'yz',name:'硬座',availability:'有',price_fen:10000}];
        plan.selected_seat_codes[0]='yw';
        plan.legs[1].train_code=body.train_type==='regular'?'T2':'G2';
        if(body.train_type==='regular') {
          plan.legs[1].seats=[{code:'yw',name:'硬卧',availability:'有',price_fen:15000}];
          plan.selected_seat_codes[1]='yw';
        }
        plan.connections[0].station=stations.find(s=>s.station_code==='NKH');
        return r.fulfill({json:snapshot});
      });
      await page.goto(process.env.BROWSER_URL || 'http://127.0.0.1:5173');
      const type=page.getByRole('combobox',{name:'直达列车类型'});
      assert.equal(await type.inputValue(),'all');
      await page.getByRole('button',{name:'查询车票',exact:true}).click();
      await page.getByText('K1',{exact:true}).waitFor();
      assert.equal(await page.getByText('G1',{exact:true}).count(),1);
      await type.selectOption('regular');
      assert.equal(await page.getByText('G1',{exact:true}).count(),0);
      assert.equal(await page.getByText('K1',{exact:true}).count(),1);
      await type.selectOption('high_speed');
      assert.equal(await page.getByText('K1',{exact:true}).count(),0);
      assert.equal(await page.getByText('G1',{exact:true}).count(),1);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'direct page overflow');
      await type.selectOption('regular');
      await page.getByRole('button',{name:'中转查询',exact:true}).click();
      await page.getByText('已收录 12 个').waitFor();
      const transferType=page.getByRole('combobox',{name:'中转列车类型'});
      assert.equal(await transferType.inputValue(),'regular');
      for(const name of ['硬座','硬卧','软卧']) assert.equal(await page.getByRole('checkbox',{name,exact:true}).isChecked(),true);
      await page.getByRole('button',{name:'查询中转方案',exact:true}).click();
      await page.getByTestId('transfer-plan').waitFor();
      assert.equal(requests[0].train_type,'regular');
      assert.ok(requests[0].allowed_seats.includes('yw'));
      assert.equal(await page.getByTestId('total-price').textContent(),'¥300');
      await page.getByRole('combobox',{name:'第1段席别'}).selectOption('yz');
      assert.equal(await page.getByTestId('total-price').textContent(),'¥250');
      await transferType.selectOption('all');
      assert.equal(await page.getByTestId('transfer-plan').count(),0);
      await page.getByRole('button',{name:'查询中转方案',exact:true}).click();
      await page.getByTestId('transfer-plan').waitFor();
      assert.equal(requests[1].train_type,'all');
      assert.equal(await page.getByTestId('transfer-plan').getByText('K1',{exact:true}).count(),1);
      assert.equal(await page.getByTestId('transfer-plan').getByText('G2',{exact:true}).count(),1);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'transfer page overflow');
      assert.deepEqual(errors,[]);
      console.log(`PASS ordinary trains: ${width}px direct filters, inherited preferences, regular/mixed transfers, seat pricing`);
      await page.close();
    }
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
