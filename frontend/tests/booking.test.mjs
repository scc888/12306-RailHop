import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function submitContext() {
  return {
    selectedBookingPassengers: { value: [{ passenger_name: '测试' }] },
    orderSubmitting: { value: false }, submitStepText: { value: '' },
    bookingTrain: { value: { train_date: '2026-10-10' } }, trainDate: { value: '2026-10-11' },
    chooseSeatLetter: { value: '' }, orderSuccessResult: { value: null },
    bookingPlan: { value: null }, queryDate: { value: '2026-10-10' },
    showToast: () => {}, fetchUnpaidOrder: () => {},
    apiFetch: async () => ({ json: async () => ({ code: 200, data: { success: true, order_id: 'E-TEST' } }) }),
  }
}

function runSubmit(context) {
  const source = fs.readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const start = source.indexOf('async function doSubmitOrder()')
  const end = source.indexOf('// ==================== 车站输入联想与查票', start)
  return new Function(...Object.keys(context), source.slice(start, end) + '; return doSubmitOrder();')(...Object.values(context))
}

test('下单成功后显示结果并结束加载状态', async () => {
  const context = submitContext()
  await runSubmit(context)
  assert.equal(context.orderSuccessResult.value.order_id, 'E-TEST')
  assert.equal(context.orderSubmitting.value, false)
})

test('修改查询日期后不能将旧车次按新日期下单', async () => {
  const context = submitContext()
  let submittedDate
  context.apiFetch = async (_url, options) => {
    submittedDate = JSON.parse(options.body).train_date
    return { json: async () => ({ code: 200, data: { success: true, order_id: 'E-TEST' } }) }
  }
  await runSubmit(context)
  assert.equal(submittedDate, '2026-10-10')
})

test('查票请求发出后修改日期仍保留实际查询日期', async () => {
  const context = { fromStation: { value: '上海' }, toStation: { value: '北京' }, trainDate: { value: '2026-10-10' },
    queryDate: { value: '' }, isLoading: { value: false }, activePlanTrain: { value: null }, smartPlans: { value: [] },
    activeStops: { value: [] }, trainResults: { value: [] }, queried: { value: false }, showToast: () => {},
    currentTicketRequestId: 0, currentPlanRequestId: 0,
    apiFetch: async () => { context.trainDate.value = '2026-10-11'; return { json: async () => ({ code: 200, data: [{ train_code: 'G1' }] }) } },
  }
  const source = fs.readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const start = source.indexOf('async function doQueryTickets()')
  const end = source.indexOf('// 过滤列表', start)
  await new Function(...Object.keys(context), source.slice(start, end) + '; return doQueryTickets();')(...Object.values(context))
  assert.equal(context.trainResults.value[0].train_date, '2026-10-10')
})

test('无座不能冒用硬座编码，售罄席别不能展示为可预订', () => {
  const source = fs.readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const start = source.indexOf('function isHighSpeedTrain(')
  const end = source.indexOf('function openBookingModal(', start)
  const seats = new Function(source.slice(start, end) + '; return getAvailableBookingSeats({train_code:"G1", seats:{ze:"0",zy:"2",wz:"有"},prices:{}});')()
  assert.deepEqual(seats.map(s => s.name), ['一等座'])
  assert.deepEqual(seats.map(s => s.code), ['M'])
})

test('普通购票结果未知时保留查询入口并结束加载', async () => {
  const context = submitContext()
  context.apiFetch = async () => ({ json: async () => ({ code: 200, data: { success: false, status: 'UNKNOWN', order_id: null, msg: '结果未知' } }) })
  await runSubmit(context)
  assert.equal(context.orderSuccessResult.value.status, 'UNKNOWN')
  assert.equal(context.orderSuccessResult.value.success, false)
  assert.equal(context.orderSubmitting.value, false)
})
