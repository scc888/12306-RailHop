import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const source = fs.readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

function qrContext(response) {
  return {
    qrState: { value: { loading: false, status: 'WAITING', msg: '', image: 'old-image', uuid: 'old-qr', pollTimer: null } },
    apiFetch: async () => response,
    clearTimeout: () => {},
    startQrPolling: () => {},
  }
}

async function loadQr(context) {
  const start = source.indexOf('async function loadQrCode()')
  const end = source.indexOf('function startQrPolling()', start)
  return new Function(...Object.keys(context), source.slice(start, end) + '; return loadQrCode();')(...Object.values(context))
}

test('获取二维码失败时显示后端的具体原因并清理旧二维码', async () => {
  const detail = '获取登录二维码失败：12306返回网页内容（HTTP 200），请稍后刷新二维码重试'
  const context = qrContext({ ok: false, json: async () => ({ detail }) })
  await loadQr(context)
  assert.equal(context.qrState.value.status, 'ERROR')
  assert.equal(context.qrState.value.msg, detail)
  assert.equal(context.qrState.value.loading, false)
  assert.equal(context.qrState.value.image, '')
  assert.equal(context.qrState.value.uuid, '')
})

test('登录服务返回非JSON时显示可理解的提示', async () => {
  const context = qrContext({ ok: false, json: async () => { throw new SyntaxError('Unexpected token <') } })
  await loadQr(context)
  assert.equal(context.qrState.value.status, 'ERROR')
  assert.match(context.qrState.value.msg, /登录服务.*响应/)
  assert.doesNotMatch(context.qrState.value.msg, /Unexpected token/)
  assert.equal(context.qrState.value.loading, false)
})

test('获取二维码成功后展示新二维码并开始查询扫码状态', async () => {
  const context = qrContext({ ok: true, json: async () => ({ code: 200, data: { uuid: 'new-qr', image: 'new-image' } }) })
  let started = false
  context.startQrPolling = () => { started = true }
  await loadQr(context)
  assert.equal(context.qrState.value.uuid, 'new-qr')
  assert.equal(context.qrState.value.image, 'new-image')
  assert.equal(context.qrState.value.loading, false)
  assert.equal(started, true)
})

test('扫码状态返回登录失败时保留具体原因并停止自动查询', async () => {
  const callbacks = []
  const detail = '换取登录凭据失败：12306返回空响应（HTTP 200），请稍后刷新二维码重试'
  const context = {
    showLoginModal: { value: true },
    qrState: { value: { uuid: 'sample-qr', status: 'SCANNED' } },
    apiFetch: async () => ({ ok: true, json: async () => ({ data: { status: 'ERROR', msg: detail } }) }),
    setTimeout: (callback) => { callbacks.push(callback); return callbacks.length },
    auth: { value: { loggedIn: false } }, showToast: () => {},
    fetchPassengers: () => {}, fetchUnpaidOrder: () => {}, closeLoginModal: () => {},
  }
  const start = source.indexOf('function startQrPolling()')
  const end = source.indexOf('async function doLogout()', start)
  new Function(...Object.keys(context), source.slice(start, end) + '; startQrPolling();')(...Object.values(context))
  await callbacks.shift()()
  assert.equal(context.qrState.value.status, 'ERROR')
  assert.equal(context.qrState.value.msg, detail)
  assert.equal(context.auth.value.loggedIn, false)
  assert.equal(callbacks.length, 0)
})
