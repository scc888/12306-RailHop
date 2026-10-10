import test from 'node:test'
import assert from 'node:assert/strict'
import { calculateFare, sortPlans, formatMoney, buildTransferText, createTransferQueryController } from '../src/lib/transfer.js'

const legs = [{train_code:'G1', from_station_name:'上海', to_station_name:'南京南', departure_at:'2026-10-10T23:00:00+08:00', arrival_at:'2026-10-11T00:00:00+08:00', seats:[{code:'ze', price_fen:12350}, {code:'zy', price_fen:20000}]},
              {train_code:'G2', from_station_name:'南京南', to_station_name:'北京', departure_at:'2026-10-11T00:15:00+08:00', arrival_at:'2026-10-11T04:00:00+08:00', seats:[{code:'ze',price_fen:20005}, {code:'zy',price_fen:null}]}]

test('分段席别改变后以整数分合计，缺价保持未知', () => {
  assert.deepEqual(calculateFare(legs,['ze','ze']), {totalPriceFen:32355,knownPriceFen:32355})
  assert.deepEqual(calculateFare(legs,['zy','ze']), {totalPriceFen:40005,knownPriceFen:40005})
  assert.deepEqual(calculateFare(legs,['ze','zy']), {totalPriceFen:null,knownPriceFen:12350})
  assert.deepEqual(calculateFare(legs,['ze','bad']), {totalPriceFen:null,knownPriceFen:12350})
  assert.equal(formatMoney(32355),'¥323.55')
  assert.equal(formatMoney(null),'票价待确认')
})

test('按改选后的实际总价排序，缺价排末，复制包含跨日信息', () => {
  const base={legs, connections:[{wait_minutes:15,station:{station_name:'南京南'}}], total_minutes:300}
  const plans=[{...base,id:'unknown',selected_seat_codes:['ze','zy']}, {...base,id:'expensive',selected_seat_codes:['zy','ze']}, {...base,id:'cheap',selected_seat_codes:['ze','ze']}]
  assert.deepEqual(sortPlans(plans,'price').map(x=>x.id),['cheap','expensive','unknown'])
  const text=buildTransferText(plans[2])
  assert.match(text,/2026-10-11/)
  assert.match(text,/G1/)
  assert.match(text,/G2/)
  assert.match(text,/15 分钟/)
  assert.match(text,/323.55/)
})

test('晚返回的旧请求和已取消请求均不能覆盖新结果', async () => {
  const pending=[]
  const controller=createTransferQueryController(() => new Promise(resolve=>pending.push(resolve)))
  const a=controller.search({from_station:'SHH'})
  const b=controller.search({from_station:'BJP'})
  pending[1]({ok:true,json:async()=>({code:200,data:{plans:['B'],meta:{}}})})
  assert.deepEqual(await b,{plans:['B'],meta:{}})
  pending[0]({ok:true,json:async()=>({code:200,data:{plans:['A'],meta:{}}})})
  assert.equal(await a,null)
  const c=controller.search({})
  controller.cancel()
  pending[2]({ok:true,json:async()=>({code:200,data:{plans:['C'],meta:{}}})})
  assert.equal(await c,null)
})

test('非JSON和繁忙错误显示可理解的信息',async()=>{
  const nonJson=createTransferQueryController(async()=>({ok:false,status:502,json:async()=>{throw new SyntaxError()}}))
  await assert.rejects(nonJson.search({}),/服务暂不可用/)
  const busy=createTransferQueryController(async()=>({ok:false,status:429,json:async()=>({detail:'当前有中转查询正在进行，请稍后重试'})}))
  await assert.rejects(busy.search({}),/请稍后重试/)
})

test('缺少查询元信息的响应应明确报错而非进入页面',async()=>{
  const controller=createTransferQueryController(async()=>({ok:true,json:async()=>({code:200,data:{plans:[]}})}))
  await assert.rejects(controller.search({}),/响应格式异常/)
})

test('请求超过时限时退出加载并给出超时原因',async()=>{
  const controller=createTransferQueryController(()=>new Promise(()=>{}),5)
  await assert.rejects(controller.search({}),/查询超时/)
})
