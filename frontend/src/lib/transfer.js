export const seatOptions = [
  ['ze', '二等座'], ['zy', '一等座'], ['swz', '商务座'], ['yw', '硬卧'],
  ['rw', '软卧'], ['srrb', '动卧'], ['yz', '硬座'], ['rz', '软座'], ['gr', '高级软卧'], ['wz', '无座']
].map(([code, name]) => ({ code, name }))

export function calculateFare(legs, selectedCodes) {
  let knownPriceFen = 0
  let complete = true
  legs.forEach((leg, index) => {
    const price = leg.seats.find(seat => seat.code === selectedCodes[index])?.price_fen
    if (Number.isSafeInteger(price) && price >= 0) knownPriceFen += price
    else complete = false
  })
  return { totalPriceFen: complete ? knownPriceFen : null, knownPriceFen }
}

export function formatMoney(fen) {
  return fen == null ? '票价待确认' : `¥${(fen / 100).toFixed(2).replace(/\.00$/, '')}`
}

export function formatDuration(minutes) {
  return `${Math.floor(minutes / 60)}小时${minutes % 60 ? `${minutes % 60}分` : ''}`
}

export function formatDateTime(value) {
  return value.slice(0, 16).replace('T', ' ')
}

export function sortPlans(plans, sortBy) {
  return [...plans].sort((a, b) => {
    if (sortBy === 'price') {
      const ap = calculateFare(a.legs, a.selected_seat_codes).totalPriceFen
      const bp = calculateFare(b.legs, b.selected_seat_codes).totalPriceFen
      if ((ap == null) !== (bp == null)) return ap == null ? 1 : -1
      if (ap != null && ap !== bp) return ap - bp
    }
    if (sortBy === 'arrival') {
      const diff = Date.parse(a.legs.at(-1).arrival_at) - Date.parse(b.legs.at(-1).arrival_at)
      if (diff) return diff
    }
    return a.total_minutes - b.total_minutes || a.id.localeCompare(b.id)
  })
}

export function buildTransferText(plan) {
  const lines = [`同站中转 · 全程 ${formatDuration(plan.total_minutes)}`]
  plan.legs.forEach((leg, i) => {
    const seat = leg.seats.find(s => s.code === plan.selected_seat_codes[i])
    lines.push(`${i + 1}. ${leg.train_code} ${leg.from_station_name} → ${leg.to_station_name}`,
      `   ${formatDateTime(leg.departure_at)} → ${formatDateTime(leg.arrival_at)} ${seat?.name || seat?.code || ''} ${formatMoney(seat?.price_fen)}`)
    if (plan.connections[i]) lines.push(`   ${plan.connections[i].station.station_name}站内换乘，等待 ${plan.connections[i].wait_minutes} 分钟`)
  })
  const fare = calculateFare(plan.legs, plan.selected_seat_codes)
  lines.push(`总价：${formatMoney(fare.totalPriceFen)}${fare.totalPriceFen == null ? `（已知 ${formatMoney(fare.knownPriceFen)}）` : ''}`,
    '余票及票价为查询快照，请在铁路12306核实购票；换乘按计划时刻计算。')
  return lines.join('\n')
}

export function createTransferQueryController(fetchImpl = fetch, timeoutMs = 55000) {
  let sequence = 0
  let active = null
  return {
    cancel() { sequence++; active?.abort() },
    async search(request, prepareRequest = null) {
      active?.abort()
      const id = ++sequence
      const abort = new AbortController()
      active = abort
      let timer
      let onAbort
      let timedOut = false
      try {
        const interrupted = new Promise((_, reject) => {
          onAbort = () => reject(new Error(timedOut ? '查询超时，请稍后重试' : '查询已取消'))
          abort.signal.addEventListener('abort', onAbort, { once: true })
          timer = setTimeout(() => { timedOut = true; abort.abort() }, timeoutMs)
        })
        const work = (async () => {
          const prepared = prepareRequest ? await prepareRequest(request, abort.signal) : request
          if (id !== sequence || abort.signal.aborted) return null
          const response = await fetchImpl('/api/transfers/query', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prepared), signal: abort.signal
          })
          if (id !== sequence) return null
          let payload
          try { payload = await response.json() }
          catch { throw new Error('中转查询服务暂不可用，请稍后重试') }
          if (id !== sequence) return null
          if (!response.ok || payload.code !== 200) {
            throw new Error(typeof payload.detail === 'string' ? payload.detail : payload.msg || '查询条件无效或服务繁忙，请检查后重试')
          }
          if (!payload.data || !Array.isArray(payload.data.plans) || !payload.data.meta) {
            throw new Error('中转查询响应格式异常，请稍后重试')
          }
          return payload.data
        })()
        return await Promise.race([work, interrupted])
      } catch (error) {
        if (id !== sequence) return null
        throw new Error(error.name === 'AbortError' ? '查询已取消' : error.message || '网络连接失败，请稍后重试')
      } finally {
        clearTimeout(timer)
        abort.signal.removeEventListener('abort', onAbort)
      }
    }
  }
}
