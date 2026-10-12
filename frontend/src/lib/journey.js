import { calculateFare, formatMoney, formatDateTime } from './transfer.js'

export const journeyKinds = [
  {code:'direct', name:'直达', description:'一趟列车直达目的地'},
  {code:'same_train', name:'同车接续', description:'同一趟车分段查询，按实际席位接续'},
  {code:'transfer', name:'站内中转', description:'在同一车站换乘另一趟列车'}
]

export const sameTrainReminder = '各段需分别有有效车票，按实际席位接续；重联列车可能需按工作人员指引经站台换厢。'

export function shanghaiDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now)
  const value = key => parts.find(p=>p.type===key).value
  return `${value('year')}-${value('month')}-${value('day')}`
}

export function addDays(day, offset) {
  const date = new Date(`${day}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + offset)
  return date.toISOString().slice(0,10)
}

export function formatJourneyDuration(minutes) {
  const hours = Math.floor(minutes / 60), remainder = minutes % 60
  return `${hours ? `${hours}小时` : ''}${remainder || !hours ? `${remainder}分` : ''}`
}

export function findExactStation(stations, value, scope = 'station') {
  const word = value.trim().toLowerCase()
  const matches = keys => stations.filter(s=>keys.some(key=>String(s[key] || '').toLowerCase()===word))
  // A station name or code is more specific than a shared city or abbreviation.
  const exact = matches(['name','telecode','station_name','station_code'])
  if (!exact.length && scope==='city') {
    const cities = matches(['city_name'])
    if (new Set(cities.map(s=>s.city_code)).size===1 && cities[0]?.city_code) {
      return [...cities].sort((a,b)=>a.telecode.localeCompare(b.telecode))[0]
    }
  }
  const choices = exact.length ? exact : matches(['pinyin','pinyin_abbr'])
  if (choices.length > 1) throw new Error(`“${value}”对应多个车站，请输入完整站名或从提示中选择`)
  if (!choices.length) throw new Error(`无法识别“${value}”，请从提示中选择车站名称`)
  return choices[0]
}

export function groupNotices(group) {
  return (group?.meta?.notices || []).map(value=>typeof value==='string' ? value : value?.message).filter(Boolean)
}

export function journeySummary(group) {
  switch(group?.meta?.status) {
    case 'upstream_error': return '铁路查询暂未成功，不能判断是否有票。请稍后重试。'
    case 'partial': return '本次查询未完整完成，以下仅为已查到的结果。'
    case 'skipped': return '本次未查询此方式。可选择“所有方式”或单独查询。'
    default: return group?.plans?.length ? '以下为本次查询到的可接续方案。' : '本次查询范围内未找到符合条件的方案，可调整日期、席别或查询方式。'
  }
}

export function buildJourneyText(plan) {
  const title = plan.kind==='same_train' ? '同一列车分段接续' : plan.kind==='transfer' ? '同站中转' : '直达'
  const lines = [`${title} · 全程 ${formatJourneyDuration(plan.total_minutes)}`]
  plan.legs.forEach((leg,index)=>{
    const seat=leg.seats.find(s=>s.code===plan.selected_seat_codes[index])
    lines.push(`${index+1}. ${leg.train_code} ${leg.from_station_name} → ${leg.to_station_name}`,
      `   ${formatDateTime(leg.departure_at)} → ${formatDateTime(leg.arrival_at)} ${seat?.name || seat?.code || ''} ${formatMoney(seat?.price_fen)}`)
    const connection=plan.connections?.[index]
    if(connection) lines.push(`   ${connection.station.station_name}站内换乘，等待 ${connection.wait_minutes} 分钟（本次至少 ${connection.required_minutes} 分钟）`)
  })
  const fare=calculateFare(plan.legs,plan.selected_seat_codes)
  lines.push(`总价：${formatMoney(fare.totalPriceFen)}${fare.totalPriceFen==null ? `（已知 ${formatMoney(fare.knownPriceFen)}）` : ''}`)
  if(plan.kind==='same_train') lines.push(sameTrainReminder)
  lines.push(...(plan.route_assessment?.warnings || []))
  lines.push('余票、票价及计划时刻为查询快照，以铁路12306和车站实际安排为准。')
  return lines.join('\n')
}

export function buildShortTicketText(option) {
  const leg=option.ticketed_leg,seat=leg.seats.find(s=>s.code===option.selected_seat_code)
  return ['有条件备选，后续未确认，不是全程有票路线',
    `${leg.train_code} 已查到有票：${leg.from_station_name} → ${leg.to_station_name}`,
    `${formatDateTime(leg.departure_at)} → ${formatDateTime(leg.arrival_at)} ${seat?.name || ''} ${formatMoney(seat?.price_fen)}`,
    `原票到站：${leg.to_station_name}；后续需申请补票：${leg.to_station_name} → ${option.destination_station_name}`,
    `列车计划到达 ${formatDateTime(option.scheduled_arrival_at)}，是否允许继续乘坐尚未确认。`,
    '补票金额和全程总价待确认。',option.conditions,option.source_url].join('\n')
}

function errorMessage(payload) {
  if(typeof payload?.detail==='string') return payload.detail
  if(Array.isArray(payload?.detail)) {
    return payload.detail.map(item=>String(item.msg || '').replace(/^Value error,\s*/, '')).filter(Boolean).join('；') || '查询条件有误，请检查日期、地点与席别'
  }
  return payload?.msg || '查询服务繁忙，请稍后重试'
}

export function createJourneyQueryController(fetchImpl = fetch, timeoutMs = 75000) {
  let sequence=0, active=null
  return {
    cancel() { sequence++;active?.abort();active=null },
    async search(request, prepareRequest = null) {
      active?.abort()
      const id=++sequence, abort=new AbortController()
      active=abort
      let timer, onAbort, timedOut=false
      try {
        const interrupted=new Promise((_,reject)=>{
          onAbort=()=>reject(new Error(timedOut ? '查询超时，请稍后重试，或减少中转次数' : '查询已取消'))
          abort.signal.addEventListener('abort',onAbort,{once:true})
          timer=setTimeout(()=>{timedOut=true;abort.abort()},timeoutMs)
        })
        const work=(async()=>{
          const prepared=prepareRequest ? await prepareRequest(request,abort.signal) : request
          if(id!==sequence || abort.signal.aborted) return null
          const response=await fetchImpl('/api/journeys/query', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(prepared),signal:abort.signal})
          if(id!==sequence) return null
          let payload
          try { payload=await response.json() } catch { throw new Error('路线查询服务暂不可用，请稍后重试') }
          if(id!==sequence) return null
          if(!response.ok || payload.code!==200) throw new Error(errorMessage(payload))
          if(!journeyKinds.every(({code})=>Array.isArray(payload.data?.[code]?.plans) && ['complete','partial','upstream_error','skipped'].includes(payload.data?.[code]?.meta?.status))) {
            throw new Error('路线查询响应格式异常，请稍后重试')
          }
          return payload.data
        })()
        return await Promise.race([work,interrupted])
      } catch(error) {
        if(id!==sequence) return null
        throw new Error(error.name==='AbortError' ? '查询已取消' : error.message || '网络连接失败，请稍后重试')
      } finally {
        clearTimeout(timer)
        abort.signal.removeEventListener('abort',onAbort)
        if(active===abort) active=null
      }
    }
  }
}
