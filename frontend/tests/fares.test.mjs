import test from 'node:test'
import assert from 'node:assert/strict'
import {trainSeatQuotes} from '../src/lib/fares.js'

test('车次票价展示独立于可接受席别，无票价格也保留',()=>{
  const rows=trainSeatQuotes({can_buy:true,seats:{ze:'有',zy:'无',swz:'1',wz:'0'},
    prices:{ze:'¥550',zy:'¥850',swz:'¥1600',wz:'¥550'}})
  assert.deepEqual(rows.map(s=>s.code),['ze','zy','swz','wz'])
  assert.equal(rows.find(s=>s.code==='zy').price,'¥850')
  assert.equal(rows.find(s=>s.code==='zy').available,false)
  assert.equal(rows.find(s=>s.code==='swz').available,true)
})

test('缺价和不可售明确显示，不伪造0元或虚构无席别的票价',()=>{
  const rows=trainSeatQuotes({can_buy:false,seats:{ze:'有',zy:'--',yw:'候补',rw:'*'},prices:{ze:'0',yw:'¥0'}})
  assert.equal(rows.length,2)
  assert.equal(rows[0].price,'票价待确认')
  assert.equal(rows[0].availability,'不可售')
  assert.equal(rows[0].available,false)
  assert.equal(rows[1].price,'¥0')
})

test('特等座价格使用原字段，不能显示成商务座价格或制造两份余票',()=>{
  const rows=trainSeatQuotes({can_buy:true,seats:{swz:'有'},prices:{tz:'¥900'}})
  assert.equal(rows.length,1)
  assert.equal(rows[0].code,'swz')
  assert.equal(rows[0].name,'特等座')
  assert.equal(rows[0].price,'¥900')
})

test('价格存在不能把缺失或占位余票解释为售罄',()=>{
  for(const availability of [null,undefined,'','--','*','**']){
    const rows=trainSeatQuotes({can_buy:true,seats:{wz:availability},prices:{wz:'¥550'}})
    assert.equal(rows[0].price,'¥550')
    assert.equal(rows[0].availability,'余票待确认')
    assert.equal(rows[0].available,false)
  }
})
