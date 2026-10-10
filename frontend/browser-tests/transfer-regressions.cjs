// Optional browser tooling; see docs/superpowers/transfer-query-validation.md.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('fs');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'});
  const failures=[];
  try {
    for(const scenario of ['unmount','sort']) {
      const page=await browser.newPage();
      try {
        const snapshot=JSON.parse(fs.readFileSync(`${__dirname}/fixtures/transfer.json`,'utf8'));
        snapshot.data.plans=Array.from({length:50},(_,i)=>({...structuredClone(snapshot.data.plans[0]),id:`sample-${i}`}));
        snapshot.data.meta.truncated=true;
        snapshot.data.meta.truncation_reasons=['result_limit'];
        snapshot.data.meta.status='partial';
        const stations=require('../../backend/data/transfer_stations.json');
        let posts=0;
        let pending=[];
        await page.route('**/api/transfers/stations?**',route=>route.fulfill({json:{code:200,data:stations}}));
        const stationResponse={code:200,data:[
          {name:'上海',telecode:'SHH',pinyin:'shanghai',pinyin_abbr:'sh'},
          {name:'北京',telecode:'BJP',pinyin:'beijing',pinyin_abbr:'bj'}]};
        await page.route('**/api/stations/search?**',route=>route.fulfill({json:stationResponse}));
        await page.route('**/api/transfers/query',route=>{
          posts++;
          if(scenario==='sort' && posts===2) {
            assert.equal(route.request().postDataJSON().sort_by,'price');
            snapshot.data.plans[0].legs[0].seats.forEach(s=>s.price_fen=100);
          }
          return route.fulfill({json:snapshot});
        });
        await page.goto(process.env.BROWSER_URL || 'http://127.0.0.1:5173');
        await page.getByRole('button',{name:'中转查询',exact:true}).click();
        await page.getByText('已收录 12 个').waitFor();
        if(scenario==='unmount') {
          await page.route('**/api/stations/search?**',route=>pending.push(route));
          await page.getByRole('button',{name:'查询中转方案',exact:true}).click();
          await page.waitForFunction(()=>document.querySelector('[role=status]')!==null);
          await page.getByRole('button',{name:'直达查询',exact:true}).click();
          assert.equal(pending.length,2,'both station lookups must be pending before unmount');
          for(const route of pending) await route.fulfill({json:stationResponse}).catch(()=>{});
          await page.waitForTimeout(150);
          assert.equal(posts,0,'unmount during station lookup must not start POST');
        } else {
          await page.getByRole('button',{name:'查询中转方案',exact:true}).click();
          await page.getByTestId('transfer-plan').first().waitFor();
          assert.equal(await page.getByTestId('transfer-plan').count(),50);
          await page.getByRole('combobox',{name:'结果排序'}).selectOption('price');
          assert.equal(await page.getByTestId('transfer-plan').count(),0,'old top50 must be invalidated after sort changes');
          await page.getByText('排序条件已变更，请重新查询以获取该排序下的前列方案。',{exact:true}).waitFor();
          await page.getByRole('button',{name:'查询中转方案',exact:true}).click();
          await page.getByTestId('transfer-plan').first().waitFor();
          assert.equal(posts,2);
        }
        console.log(`PASS ${scenario}`);
      } catch(e) {failures.push(`${scenario}: ${e.message}`)}
      finally {await page.close()}
    }
  } finally {await browser.close()}
  if(failures.length) throw new Error(failures.join('\n'));
})().catch(e=>{console.error(e);process.exit(1)});
