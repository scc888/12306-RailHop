import {addDays} from './journey.js'
import {defaultSeatCodes,seatOptions} from './transfer.js'

export const SETTINGS_STORAGE_KEY='railhop.journey.settings.v1'

export function createDefaultSettings(today) {
  return {fromText:'上海',toText:'北京',fromScope:'city',toScope:'city',trainDate:today,
    trainType:'all',sortBy:'duration',trainSort:'departure',allowedSeats:[...defaultSeatCodes],
    transferCount:1,maxSameSegments:2,officialTime:true,minMinutes:15,viaTexts:[''],
    allowLargeDetour:false,advancedOpen:false,fromSelection:null,toSelection:null}
}

function normalizeSettings(value,today) {
  const defaults=createDefaultSettings(today)
  if(!value || typeof value!=='object' || Array.isArray(value))return defaults
  const normalized={...defaults}
  for(const field of ['fromText','toText']){
    if(typeof value[field]==='string' && value[field].length<=100)normalized[field]=value[field]
  }
  for(const [field,choices] of Object.entries({fromScope:['city','station'],toScope:['city','station'],
    trainType:['all','high_speed','regular'],sortBy:['duration','arrival','price'],trainSort:['departure','duration']})){
    if(choices.includes(value[field]))normalized[field]=value[field]
  }
  for(const [field,minimum,maximum] of [['transferCount',1,3],['maxSameSegments',2,3],['minMinutes',1,1440]]){
    if(Number.isInteger(value[field]) && value[field]>=minimum && value[field]<=maximum)normalized[field]=value[field]
  }
  for(const field of ['officialTime','allowLargeDetour','advancedOpen']){
    if(typeof value[field]==='boolean')normalized[field]=value[field]
  }
  const day=value.trainDate
  if(typeof day==='string' && /^\d{4}-\d{2}-\d{2}$/.test(day) && day>=today && day<=addDays(today,14)){
    const parsed=new Date(`${day}T12:00:00Z`)
    if(Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0,10)===day)normalized.trainDate=day
  }
  if(Array.isArray(value.allowedSeats)){
    const known=new Set(seatOptions.map(seat=>seat.code))
    const selected=[...new Set(value.allowedSeats.filter(code=>known.has(code)))]
    if(selected.length)normalized.allowedSeats=selected
  }
  if(Array.isArray(value.viaTexts)){
    const stations=value.viaTexts.filter(station=>typeof station==='string' && station.length<=100).slice(0,normalized.transferCount)
    if(stations.length)normalized.viaTexts=stations
  }
  for(const side of ['from','to']){
    const saved=value[`${side}Selection`]
    if(saved?.input===normalized[`${side}Text`] && Array.isArray(saved.codes)){
      normalized[`${side}Selection`]={input:saved.input,codes:[...new Set(saved.codes.filter(code=>typeof code==='string' && /^[A-Z]{3}$/.test(code)))]}
    }
  }
  return normalized
}

export function loadJourneySettings(today,storage) {
  try {
    const browser=storage ?? window.localStorage
    const stored=JSON.parse(browser.getItem(SETTINGS_STORAGE_KEY))
    return stored?.version===1 ? normalizeSettings(stored.settings,today) : createDefaultSettings(today)
  } catch { return createDefaultSettings(today) }
}

export function saveJourneySettings(settings,today,storage) {
  try {
    const browser=storage ?? window.localStorage
    browser.setItem(SETTINGS_STORAGE_KEY,JSON.stringify({version:1,settings:normalizeSettings(settings,today)}))
    return true
  } catch { return false }
}
