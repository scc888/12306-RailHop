import test from 'node:test'
import assert from 'node:assert/strict'
import * as journey from '../src/lib/journey.js'
import {sortPlans} from '../src/lib/transfer.js'
import {createDefaultSettings,saveJourneySettings,loadJourneySettings} from '../src/lib/settings.js'
const scope={stations:[{name:'上海',telecode:'SHH'},{name:'上海虹桥',telecode:'AOH'},{name:'安亭北',telecode:'ASH'}],default_station_codes:['SHH']}
test('scope selection preserves explicit empty and city-bound choices, station is strictly anchor',()=>{
  assert.equal(typeof journey.endpointSelection,'function','endpoint scope selection must be implemented')
  assert.deepEqual(journey.endpointSelection(scope,{input:'上海',codes:['AOH']},'上海','city','SHH'),['AOH'])
  assert.deepEqual(journey.endpointSelection(scope,{input:'上海',codes:[]},'上海','city','SHH'),[])
  assert.deepEqual(journey.endpointSelection(scope,{input:'北京',codes:['BJP']},'上海','city','SHH'),['SHH'])
  assert.deepEqual(journey.endpointSelection(scope,{input:'上海',codes:['AOH']},'上海','station','SHH'),['SHH'])
})
test('explicit scope request chooses an included anchor and rejects empty',()=>{
  assert.equal(typeof journey.endpointRequest,'function','endpoint request must be implemented')
  assert.deepEqual(journey.endpointRequest('SHH',['AOH'] ),{anchor:'AOH',codes:['AOH']})
  assert.throws(()=>journey.endpointRequest('SHH',[]),/至少选择/)
})
test('endpoint selections persist only alongside matching input',()=>{
  let raw;const storage={setItem(k,v){raw=v},getItem(){return raw}}
  const settings={...createDefaultSettings('2026-10-14'),fromSelection:{input:'上海',codes:['AOH']},toSelection:{input:'天津',codes:['TJP']}}
  saveJourneySettings(settings,'2026-10-14',storage)
  const restored=loadJourneySettings('2026-10-14',storage)
  assert.deepEqual(restored.fromSelection,{input:'上海',codes:['AOH']})
  assert.equal(restored.toSelection,null)
})
test('equal duration sorts fewer transfers before lexicographic id',()=>{
  const plan=(id,n)=>({id,total_minutes:200,legs:Array(n+1).fill({}),connections:Array(n).fill({})})
  assert.deepEqual(sortPlans([plan('a',2),plan('z',1)],'duration').map(p=>p.id),['z','a'])
})
test('collapsed route facts expose intermediate actual station, wait, seats, cross-day and unverified status',()=>{
  assert.equal(typeof journey.compactJourneyFacts,'function','compact facts must be implemented')
  const legs=[{from_station_name:'上海虹桥',to_station_name:'南京南',departure_at:'2026-10-14T23:00:00+08:00',arrival_at:'2026-10-14T23:50:00+08:00',train_code:'G1',seats:[{code:'ze',name:'二等座'}]},{from_station_name:'南京南',to_station_name:'北京南',departure_at:'2026-10-15T01:00:00+08:00',arrival_at:'2026-10-15T05:00:00+08:00',train_code:'G2',seats:[{code:'yw',name:'硬卧'}]}]
  const facts=journey.compactJourneyFacts({legs,selected_seat_codes:['ze','yw'],connections:[{station:{station_name:'南京南',convenient_transfer_confirmed:false},wait_minutes:70}]})
  assert.match(facts.route,/上海虹桥.*南京南.*北京南/)
  assert.match(facts.wait,/南京南.*70/)
  assert.match(facts.seats,/二等座.*硬卧/)
  assert.match(facts.notes.join(' '),/未核实/)
  assert.match(facts.notes.join(' '),/跨夜候车/)
  assert.match(facts.notes.join(' '),/次日/)
})
