import test from 'node:test'
import assert from 'node:assert/strict'

const modulePath='../src/lib/settings.js'
async function settingsModule() {
  try { return await import(modulePath) }
  catch(error) { if(error.code==='ERR_MODULE_NOT_FOUND')assert.fail('browser query settings persistence is not implemented');throw error }
}
function storage() {
  const values=new Map()
  return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)}
}

test('浏览器设置保存路线、席别和个人10分钟，重开后恢复且排除查询结果',async()=>{
  const {createDefaultSettings,loadJourneySettings,saveJourneySettings}=await settingsModule()
  const browser=storage(),today='2026-10-13'
  const chosen={...createDefaultSettings(today),fromText:'北京',toText:'上海',fromScope:'station',
    trainDate:'2026-10-14',trainType:'regular',allowedSeats:['yw','rw'],sortBy:'price',trainSort:'duration',
    transferCount:2,maxSameSegments:3,officialTime:false,minMinutes:10,viaTexts:['郑州东','南京南'],
    allowLargeDetour:true,advancedOpen:true,result:{trains:['stale-ticket']}}
  assert.equal(saveJourneySettings(chosen,today,browser),true)
  const restored=loadJourneySettings(today,browser)
  const {result,...expected}=chosen
  assert.deepEqual(restored,expected)
  assert.equal('result' in restored,false)
})

test('过期、超出预售范围和不存在的日期恢复今天，其余偏好保留',async()=>{
  const {SETTINGS_STORAGE_KEY,loadJourneySettings}=await settingsModule()
  for(const trainDate of ['2026-10-12','2026-10-28','2026-02-30','not-a-date']){
    const browser=storage()
    browser.setItem(SETTINGS_STORAGE_KEY,JSON.stringify({version:1,settings:{trainDate,fromText:'北京',minMinutes:10}}))
    const restored=loadJourneySettings('2026-10-13',browser)
    assert.equal(restored.trainDate,'2026-10-13')
    assert.equal(restored.fromText,'北京')
    assert.equal(restored.minMinutes,10)
  }
})

test('损坏或旧版本缓存回退默认，异常字段逐项处理并限制指定站数量',async()=>{
  const {SETTINGS_STORAGE_KEY,createDefaultSettings,loadJourneySettings}=await settingsModule()
  const today='2026-10-13',browser=storage(),defaults=createDefaultSettings(today)
  for(const raw of ['broken','null','[]','{"version":0,"settings":{"fromText":"北京"}}']){
    browser.setItem(SETTINGS_STORAGE_KEY,raw)
    assert.deepEqual(loadJourneySettings(today,browser),defaults)
  }
  browser.setItem(SETTINGS_STORAGE_KEY,JSON.stringify({version:1,settings:{fromText:12,toText:'北京南',
    trainType:'bogus',allowedSeats:['bogus','yw','yw'],officialTime:'false',minMinutes:0,
    transferCount:1,viaTexts:['南京南','郑州东'],extra:'discard'}}))
  const restored=loadJourneySettings(today,browser)
  assert.equal(restored.fromText,'上海')
  assert.equal(restored.toText,'北京南')
  assert.equal(restored.trainType,'all')
  assert.deepEqual(restored.allowedSeats,['yw'])
  assert.equal(restored.officialTime,true)
  assert.equal(restored.minMinutes,15)
  assert.deepEqual(restored.viaTexts,['南京南'])
  assert.equal('extra' in restored,false)
})

test('浏览器禁止存储时仍可使用默认设置，保存失败不会抛异常',async()=>{
  const {createDefaultSettings,loadJourneySettings,saveJourneySettings}=await settingsModule()
  const browser={getItem(){throw Error('blocked')},setItem(){throw Error('full')}}
  const defaults=createDefaultSettings('2026-10-13')
  assert.deepEqual(loadJourneySettings('2026-10-13',browser),defaults)
  assert.equal(saveJourneySettings(defaults,'2026-10-13',browser),false)
})
