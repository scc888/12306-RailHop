import {seatOptions,defaultSeatCodes} from './transfer.js'
import {hasTicket} from './journey.js'

function validPrice(value) {
  return typeof value==='string' && /^[¥￥][0-9]+(?:\.[0-9]{1,2})?$/.test(value.trim())
}

// Display is independent of planning preferences: sold-out and unselected fares
// still help compare trains. Placeholder-only classes are not offered classes.
export function trainSeatQuotes(train) {
  return seatOptions.flatMap(seat=>{
    const raw=train.seats?.[seat.code]
    const special=seat.code==='swz' && !validPrice(train.prices?.swz) && validPrice(train.prices?.tz)
    const price=special ? train.prices.tz : train.prices?.[seat.code]
    if(!validPrice(price) && (raw==null || ['', '--', '*', '**'].includes(raw)))return []
    const available=!!train.can_buy && hasTicket(raw)
    return [{...seat,name:special?'特等座':seat.name,available,
      availability:!train.can_buy?'不可售':hasTicket(raw)?(raw==='有'?'有票':`${raw} 张`):raw==='候补'?'候补':['无','0'].includes(raw)?'无票':'余票待确认',
      price:validPrice(price)?price.trim().replace('￥','¥'):'票价待确认'}]
  })
}

export function trainSeatQuery(train, preferred) {
  // An offered but sold-out class still matches the preference. Availability
  // alone must never trigger a switch to another class.
  const offered=new Set(trainSeatQuotes(train).map(seat=>seat.code))
  const fallback=preferred.length>0 && offered.size>0
    && !preferred.some(code=>offered.has(code)) && defaultSeatCodes.some(code=>offered.has(code))
  const allowedSeats=[...(fallback ? defaultSeatCodes : preferred)]
  return {allowedSeats,fallback,applicableSeats:allowedSeats.filter(code=>offered.has(code))}
}
