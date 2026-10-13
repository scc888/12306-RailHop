import test from 'node:test'
import assert from 'node:assert/strict'
import {trainSeatQuery as selection} from '../src/lib/fares.js'

test('只选硬卧查看高铁时使用默认席别，保留原始偏好且不主动加入无座商务座',()=>{
  const preferred=['yw']
  const query=selection({train_code:'G1',seats:{ze:'有',zy:'无',yw:'--',swz:'有',wz:'有'},
    prices:{ze:'¥550',zy:'¥850',swz:'¥1600',wz:'¥550'}},preferred)
  assert.equal(query.fallback,true)
  assert.deepEqual(query.allowedSeats,['ze','zy','yz','yw','rw'])
  assert.deepEqual(query.applicableSeats,['ze','zy'])
  assert.deepEqual(preferred,['yw'])
})

test('所选席别售罄候补或价格存在时不更换查询偏好',()=>{
  for(const availability of ['无','0','候补','未开售','--']){
    const query=selection({seats:{ze:'有',yw:availability},prices:{ze:'¥550',yw:'¥300'}},['yw'])
    assert.equal(query.fallback,false)
    assert.deepEqual(query.allowedSeats,['yw'])
  }
})

test('存在适用的所选席别时保留混合偏好，动卧按实际席别识别',()=>{
  for(const [train,preferred] of [
    [{seats:{ze:'无',zy:'有'},prices:{ze:'¥550'}},['yw','ze']],
    [{train_code:'D1',seats:{rw:'无',ze:'有'},prices:{rw:'¥900'}},['rw']],
    [{seats:{wz:'无',ze:'有'},prices:{wz:'¥550'}},['wz']]
  ]){
    const query=selection(train,preferred)
    assert.equal(query.fallback,false)
    assert.deepEqual(query.allowedSeats,preferred)
  }
})

test('只选二等座查看仅有普速席别的车也回退默认，未知资料不猜测',()=>{
  const regular=selection({train_code:'K1',seats:{yw:'有',yz:'无',rw:'有'},prices:{}},['ze'])
  assert.equal(regular.fallback,true)
  assert.deepEqual(regular.applicableSeats,['yz','yw','rw'])
  const unknown=selection({seats:{ze:'--',yw:'*'},prices:{}},['yw'])
  assert.equal(unknown.fallback,false)
  assert.deepEqual(unknown.allowedSeats,['yw'])
})
