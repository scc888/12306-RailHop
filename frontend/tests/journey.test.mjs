import test from 'node:test'
import assert from 'node:assert/strict'
import { buildJourneyText, buildShortTicketText, createJourneyQueryController, findExactStation, shanghaiDate, addDays, journeySummary, groupNotices,hasTicket,trainHasSeats,trainArrivalDay,journeyDayLabel } from '../src/lib/journey.js'

const leg = (overrides = {}) => ({train_code:'K1',from_station_name:'上海',to_station_name:'南京',departure_at:'2026-10-11T23:00:00+08:00',arrival_at:'2026-10-12T01:00:00+08:00',seats:[{code:'yw',name:'硬卧',price_fen:12005},{code:'yz',name:'硬座',price_fen:null}],...overrides})
const result = () => Object.fromEntries(['direct','same_train','transfer'].map(key=>[key,{plans:[],meta:{status:'complete',notices:[]}}]))
const response = data => ({ok:true,json:async()=>({code:200,data})})

test('分段跨日标记始终相对全程出发日，按铁路日期计算',()=>{
  const start='2026-12-31T20:04:00+08:00'
  assert.equal(journeyDayLabel('2026-12-31T21:29:00+08:00',start),'')
  assert.equal(journeyDayLabel('2027-01-01T07:43:00+08:00',start),'次日')
  assert.equal(journeyDayLabel('2027-01-01T07:49:00+08:00',start),'次日')
  assert.equal(journeyDayLabel('2027-01-02T01:00:00+08:00',start),'第3天')
  assert.equal(journeyDayLabel(null,start),'')
})

test('车次余票不把候补零票或不可售计为现票，跨日以铁路日期计算',()=>{
  for(const value of ['候补','0','--','无','未开售','１２',' 2','-1'])assert.equal(hasTicket(value),false)
  assert.equal(hasTicket('有'),true);assert.equal(hasTicket('2'),true)
  assert.equal(trainHasSeats({can_buy:false,seats:{ze:'有'}},['ze']),false)
  assert.equal(trainHasSeats({can_buy:true,seats:{ze:'无',yw:'1'}},['ze','yw']),true)
  assert.equal(trainArrivalDay({departure_at:'2026-10-10T23:00:00+08:00',arrival_at:'2026-10-12T01:00:00+08:00'}),'+2天')
})

test('指定车次请求保留运行日和实际上车区间，不能只传显示车次',async()=>{
  const selected_train={train_no:'physical-K1',run_date:'2026-10-09',from_station:'SHH',to_station:'BJP',departure_at:'2026-10-10T23:00:00+08:00'}
  let sent
  const controller=createJourneyQueryController(async(url,options)=>{sent=JSON.parse(options.body);return response({...result(),selected_train})})
  await controller.search({mode:'all',selected_train})
  assert.deepEqual(sent.selected_train,selected_train)
})

test('同车复制保留跨日、逐段席别和精确金额，不保证不下车',()=>{
  const plan={kind:'same_train',legs:[leg(),leg({from_station_name:'南京',to_station_name:'北京',departure_at:'2026-10-12T01:06:00+08:00',arrival_at:'2026-10-12T12:00:00+08:00'})],connections:[],selected_seat_codes:['yw','yw'],total_minutes:780}
  const text=buildJourneyText(plan)
  assert.match(text,/同一列车分段接续/)
  assert.match(text,/2026-10-12 01:06/)
  assert.match(text,/硬卧/)
  assert.match(text,/¥240.10/)
  assert.match(text,/站台换厢/)
  assert.doesNotMatch(text,/全程有座|无需下车/)
  plan.selected_seat_codes[1]='yz'
  assert.match(buildJourneyText(plan),/票价待确认（已知 ¥120.05）/)
})

test('精确站名优先于城市和拼音，歧义简拼不能选第一个站',()=>{
  const stations=[{name:'上海虹桥',telecode:'AOH',pinyin:'shanghaihongqiao',pinyin_abbr:'shhq',city_name:'上海',city_code:'SHH'}, {name:'上海',telecode:'SHH',pinyin:'shanghai',pinyin_abbr:'sh',city_name:'上海',city_code:'SHH'}]
  assert.equal(findExactStation(stations,'上海').telecode,'SHH')
  assert.equal(findExactStation(stations,'aoh').telecode,'AOH')
  assert.equal(findExactStation(stations,'Shanghai').telecode,'SHH')
  assert.throws(()=>findExactStation(stations,'上'),/无法识别/)
  assert.throws(()=>findExactStation([{name:'甲',telecode:'AAA',pinyin_abbr:'aa'},{name:'乙',telecode:'BBB',pinyin_abbr:'aa'}],'aa'),/多个车站/)
})

test('城市范围支持没有同名车站的城市，单站范围仍须精确站名',()=>{
  const stations=[{name:'白马井',telecode:'BIM',city_name:'儋州',city_code:'180'}, {name:'银滩',telecode:'CTQ',city_name:'儋州',city_code:'180'}]
  assert.equal(findExactStation(stations,'儋州','city').city_name,'儋州')
  assert.throws(()=>findExactStation(stations,'儋州','station'),/无法识别/)
})

test('上海日期和预售最后一天不受执行机器时区影响',()=>{
  assert.equal(shanghaiDate(new Date('2026-10-10T17:00:00Z')),'2026-10-11')
  assert.equal(addDays('2026-12-25',14),'2027-01-08')
})

test('分组空结果区分查询失败、部分结果和跳过',()=>{
  assert.match(journeySummary({plans:[],meta:{status:'upstream_error'}}),/不能判断/)
  assert.match(journeySummary({plans:[],meta:{status:'partial'}}),/未完整/)
  assert.match(journeySummary({plans:[],meta:{status:'skipped'}}),/未查询/)
  assert.match(journeySummary({plans:[],meta:{status:'complete'}}),/本次查询范围/)
  assert.deepEqual(groupNotices({meta:{notices:['范围有限',{message:'接口繁忙'}]}}),['范围有限','接口繁忙'])
})

test('补票备选复制只确认前段，保留未知总价和到站前申请条件',()=>{
  const option={ticketed_leg:leg(),selected_seat_code:'yw',destination_station_name:'北京',scheduled_arrival_at:'2026-10-12T12:00:00+08:00',conditions:'原票到站前申请，有运输能力才可办理；被拒绝须下车，不承诺后续有座。',source_url:'https://www.12306.cn/'}
  const copied=buildShortTicketText(option)
  assert.match(copied,/已查到有票：上海 → 南京/)
  assert.match(copied,/后续需申请补票：南京 → 北京/)
  assert.match(copied,/全程总价待确认/)
  assert.match(copied,/被拒绝须下车/)
  assert.match(copied,/¥120.05/)
})

test('较旧请求晚返回不能覆盖新结果，取消后预检不再发 POST',async()=>{
  const pending=[]
  const controller=createJourneyQueryController(()=>new Promise(resolve=>pending.push(resolve)))
  const first=controller.search({mode:'all'})
  const second=controller.search({mode:'direct'})
  const data={...result(),queried_at:'new'}
  pending[1](response(data))
  assert.deepEqual(await second,data)
  pending[0](response({...result(),queried_at:'old'}))
  assert.equal(await first,null)
  let finishLookup,posts=0
  const lookup=new Promise(resolve=>{finishLookup=resolve})
  const beforePost=createJourneyQueryController(async()=>{posts++;return response(result())})
  const canceled=beforePost.search({},async()=>{await lookup;return {}})
  beforePost.cancel();finishLookup()
  assert.equal(await canceled,null)
  assert.equal(posts,0)
})

test('车站解析及响应体读取受总超时保护',async()=>{
  const controller=createJourneyQueryController(async()=>response(result()),5)
  await assert.rejects(controller.search({},()=>new Promise(()=>{})),/查询超时/)
  const body=createJourneyQueryController(async()=>({ok:true,json:()=>new Promise(()=>{})}),5)
  await assert.rejects(body.search({}),/查询超时/)
})

test('错误或缺组响应拒绝展示，预售错误明示用户',async()=>{
  const missing=createJourneyQueryController(async()=>response({direct:{plans:[],meta:{}}}))
  await assert.rejects(missing.search({}),/响应格式异常/)
  const invalid=createJourneyQueryController(async()=>({ok:false,status:422,json:async()=>({detail:[{loc:['body','train_date'],msg:'Value error, 出发日期超出 15 天预售范围'}]})}))
  await assert.rejects(invalid.search({}),/15 天预售/)
  const unavailable=createJourneyQueryController(async()=>({ok:false,json:async()=>{throw new SyntaxError()}}))
  await assert.rejects(unavailable.search({}),/暂不可用/)
})
