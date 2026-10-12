<template>
  <section class="journey-card p-5 sm:p-7" aria-labelledby="search-heading">
    <div class="flex flex-wrap justify-between items-start gap-3 mb-6"><div><h1 id="search-heading" class="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">从一座城，到另一座城</h1><p class="mt-2 text-sm text-slate-600 leading-relaxed">直达无票时，继续找同车接续和同站中转。每段都查余票，路线一起比较。</p></div><span class="kind-badge kind-direct shrink-0">仅查询</span></div>
    <form @submit.prevent="search" class="space-y-5">
      <div class="search-main-grid">
        <div><label for="journey-from" class="journey-label">出发地</label><input id="journey-from" v-model="fromText" list="journey-from-list" @input="suggest('from')" @focus="suggest('from')" class="journey-input" placeholder="城市或完整车站名" required autocomplete="off" /><datalist id="journey-from-list"><option v-for="s in suggestions.from" :key="s.telecode" :value="s.name">{{ s.city_name ? `${s.city_name} · ` : '' }}{{ s.telecode }}</option></datalist><label class="scope-control"><span>出发范围</span><select v-model="fromScope" aria-label="出发范围"><option value="city">同城车站</option><option value="station">仅此车站</option></select></label></div>
        <button type="button" @click="swap" class="swap-button" aria-label="交换出发地与目的地"><ArrowLeftRight class="w-4 h-4" /></button>
        <div><label for="journey-to" class="journey-label">目的地</label><input id="journey-to" v-model="toText" list="journey-to-list" @input="suggest('to')" @focus="suggest('to')" class="journey-input" placeholder="城市或完整车站名" required autocomplete="off" /><datalist id="journey-to-list"><option v-for="s in suggestions.to" :key="s.telecode" :value="s.name">{{ s.city_name ? `${s.city_name} · ` : '' }}{{ s.telecode }}</option></datalist><label class="scope-control"><span>到达范围</span><select v-model="toScope" aria-label="到达范围"><option value="city">同城车站</option><option value="station">仅此车站</option></select></label></div>
        <div><label for="journey-date" class="journey-label">出发日期</label><input id="journey-date" v-model="trainDate" type="date" :min="today" :max="lastDate" class="journey-input" required /><div class="flex gap-3 mt-2 text-xs text-blue-700"><button type="button" @click="trainDate=today">今天</button><button type="button" @click="trainDate=addDays(today,1)">明天</button><span class="text-slate-500">15 天内</span></div></div>
        <button type="submit" :disabled="loading" class="journey-primary query-button"><Search v-if="!loading" class="w-4 h-4" /><LoaderCircle v-else class="w-4 h-4 animate-spin" />{{ loading ? '正在查询…' : '查询出行路线' }}</button>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 border-t border-slate-100 pt-5">
        <label class="journey-label">查询方式<select v-model="mode" class="journey-input"><option value="auto">智能查询 · 直达无票时找替代</option><option value="all">所有方式 · 一起比较</option><option value="direct">仅直达</option><option value="same_train">仅同车接续</option><option value="transfer">仅同站中转</option></select></label>
        <label class="journey-label">列车类型<select v-model="trainType" class="journey-input"><option value="all">全部列车 · 可混合中转</option><option value="high_speed">仅高铁 / 动车（G/D/C）</option><option value="regular">仅普速（Z/T/K/其他）</option></select></label>
        <label class="journey-label">结果排序<select v-model="sortBy" class="journey-input"><option value="duration">本次结果 · 全程耗时最短</option><option value="arrival">本次结果 · 最早到达</option><option value="price">本次结果 · 所选总价最低</option></select></label>
      </div>
      <fieldset><legend class="journey-label mb-2">可接受席别 <span class="font-normal text-slate-500">各段可分别选择</span></legend><div class="flex flex-wrap gap-2"><label v-for="seat in seatOptions" :key="seat.code" class="seat-chip" :class="{'seat-selected':allowedSeats.includes(seat.code)}"><input v-model="allowedSeats" type="checkbox" :value="seat.code" class="accent-blue-600" />{{ seat.name }}</label></div></fieldset>
      <details class="advanced-settings">
        <summary class="flex items-center justify-between cursor-pointer font-semibold text-sm text-slate-700"><span>更多路线条件</span><span class="text-xs font-normal text-slate-500">中转次数、指定站、换乘时间</span></summary>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-5"><label class="journey-label">同站换乘次数<select v-model.number="transferCount" class="journey-input"><option v-for="n in 3" :key="n" :value="n">{{ n }} 次换车 · {{ n+1 }} 段列车</option></select></label><label class="journey-label">同车最多分段<select v-model.number="maxSameSegments" class="journey-input"><option :value="2">最多 2 段 · 接续 1 次</option><option :value="3">最多 3 段 · 接续 2 次</option></select></label><div><label class="flex items-start gap-2 text-sm text-slate-700"><input v-model="officialTime" type="checkbox" class="mt-1 accent-blue-600" />按各站官方参考换乘时间</label><label v-if="!officialTime" class="journey-label mt-2">个人最少时间（分钟）<input v-model.number="minMinutes" type="number" min="15" max="1440" required class="journey-input" /></label><p class="mt-2 text-xs text-slate-500 leading-relaxed">缺少适用官方数据时按 15 分钟；个人设置更长时取较大值。同车接续无需套用换车间隔。</p></div></div>
        <div class="mt-4"><div class="flex justify-between items-center gap-2"><label for="via-0" class="journey-label">指定中转站（可选，按顺序经过）</label><button type="button" @click="viaTexts.push('')" :disabled="viaTexts.length>=transferCount" class="text-xs font-semibold text-blue-700 disabled:text-slate-400 min-h-9">添加指定站</button></div><div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2"><div v-for="(_,i) in viaTexts" :key="i" class="flex items-center gap-2"><input :id="`via-${i}`" v-model="viaTexts[i]" :aria-label="`第${i+1}个指定中转站`" list="journey-via-list" class="journey-input" placeholder="留空自动规划" /><button v-if="viaTexts.length>1" type="button" @click="viaTexts.splice(i,1)" :aria-label="`移除第${i+1}个指定站`" class="min-w-9 min-h-10 text-slate-600">×</button></div></div><datalist id="journey-via-list"><option v-for="s in transferStations" :key="s.station_code" :value="s.station_name">{{ s.station_code }}</option></datalist><p class="mt-2 text-xs text-slate-500">目前 {{ transferStations.length }} 个有便捷换乘资料的候选站；指定站只约束同站中转路线。</p><p v-if="stationError" class="mt-2 text-xs text-amber-800">{{ stationError }} <button type="button" @click="loadTransferStations" class="underline">重试加载</button></p></div>
        <div class="mt-4 border-t border-slate-200 pt-4"><label class="flex items-center gap-2 text-sm font-medium text-slate-700"><input v-model="allowLargeDetour" type="checkbox" class="accent-blue-600" />允许较大绕行（默认关闭）</label><p class="mt-2 text-xs text-slate-500 leading-relaxed">默认排除明显折返和过长行程；开启后扩大候选并提示绕行。手动指定站可按要求查询，余票、同站和换乘时间仍须满足。</p></div>
      </details>
      <p class="text-xs text-slate-500 leading-relaxed">城市范围包含官方字典归属的同城车站，结果会标明实际上、下车站。中途只同站换乘；仅推荐各段已查到现票的路线。</p>
    </form>
  </section>
  <div v-if="notice" role="status" class="notice-box text-blue-900 bg-blue-50 border-blue-200">{{ notice }}</div>
  <div v-if="error" role="alert" class="notice-box text-rose-900 bg-rose-50 border-rose-200">{{ error }}</div>
  <section v-if="loading" class="journey-card p-7 text-center" role="status"><LoaderCircle class="mx-auto w-6 h-6 animate-spin text-blue-600" /><p class="mt-3 font-semibold">正在查余票并核对接续条件</p><p class="mt-2 text-sm text-slate-600">智能查询先查直达，无票时继续找替代。多次中转可能需要约一分钟。</p><button type="button" @click="cancel" class="mt-4 text-sm font-semibold text-blue-700 min-h-10">取消本次查询</button></section>
  <section v-if="result && !loading" aria-live="polite" class="space-y-4" aria-labelledby="results-heading">
    <div><h2 id="results-heading" class="font-bold text-xl">{{ result.scope.from_label }} <span class="text-slate-400">→</span> {{ result.scope.to_label }}</h2><p class="mt-1 text-xs text-slate-500">查询 {{ formatDateTime(result.queried_at) }} · 共 {{ allPlans.length }} 条符合本次条件的路线</p></div>
    <div v-if="mode==='auto' && result.direct.plans.length" class="notice-box text-blue-900 bg-blue-50 border-blue-200">已找到所选席别的直达票，本次智能查询未继续搜索替代路线。<button type="button" @click="queryAll" class="font-semibold underline ml-1 min-h-9">仍比较所有方式</button></div>
    <div class="flex flex-wrap gap-2" role="group" aria-label="路线结果类型"><button v-for="tab in tabs" :key="tab.code" type="button" :aria-pressed="activeTab===tab.code" @click="activeTab=tab.code" class="result-tab" :class="{'tab-active':activeTab===tab.code}">{{ tab.name }} <span>{{ tab.count }}</span></button></div>
    <div v-for="kind in visibleKinds" :key="kind.code" class="rounded-xl border p-4 text-sm" :class="statusClasses(result[kind.code].meta.status)"><p class="font-semibold">{{ kind.name }} · {{ statusNames[result[kind.code].meta.status] }}</p><p class="mt-1 leading-relaxed">{{ journeySummary(result[kind.code]) }}</p><details v-if="groupNotices(result[kind.code]).length" class="mt-2 text-xs text-slate-600"><summary class="cursor-pointer py-1">查看查询范围与说明</summary><ul class="mt-2 list-disc pl-5 space-y-1"><li v-for="item in groupNotices(result[kind.code])" :key="item">{{ item }}</li></ul></details></div>
    <JourneyPlanCard v-for="(plan,index) in displayedPlans" :key="`${plan.kind}-${plan.id}`" :plan="plan" :rank="index+1" @seat-change="changeSeat" />
    <div v-if="!displayedPlans.length && allPlans.length" class="journey-card p-7 text-center"><MapPin class="mx-auto w-6 h-6 text-slate-400" /><p class="mt-3 font-semibold">当前分类没有可展示的路线</p><p class="mt-2 text-sm text-slate-600">先查看上方的查询状态，再尝试调整日期、席别或查询方式。</p></div>
  </section>
  <section v-if="result && !loading && !allPlans.length" class="journey-card border-amber-200 p-5 space-y-4" aria-labelledby="fallback-heading">
    <div><h2 id="fallback-heading" class="font-bold text-lg text-amber-950">本次范围内未找到全程有票路线</h2><p class="text-sm text-slate-600 mt-2">可调整日期、席别或扩大绕行范围。若上方提示未查完或接口失败，不能据此判断所有路线都无票。</p></div>
    <button v-if="!allowLargeDetour" type="button" @click="queryExpanded" class="journey-secondary">允许较大绕行并重新查询</button>
    <div class="border-t border-slate-100 pt-4"><h3 class="font-semibold text-amber-950">短途有票，后续申请补票（有条件备选）</h3><p class="mt-2 text-sm text-slate-600 leading-relaxed">只能确认前段有票，后半程能否继续乘坐由列车运输能力和工作人员决定；被拒绝时须在原票到站下车。不计入全程有票路线数量和排名。</p><button v-if="!includeShortFallback" type="button" @click="queryShortFallback" class="journey-secondary mt-3">查看短途有票／补票备选</button><template v-else><p class="mt-3 text-sm font-medium">{{ statusNames[result.short_fallback?.meta?.status || 'skipped'] }}</p><ul class="mt-2 list-disc pl-5 text-xs text-slate-600 space-y-1"><li v-for="item in groupNotices(result.short_fallback)" :key="item">{{ item }}</li></ul><p v-if="!result.short_fallback?.options?.length" class="text-sm text-slate-600 mt-3">本次未查到可展示的有条件备选，请结合查询状态判断。</p></template></div>
    <ShortTicketCard v-for="option in result.short_fallback?.options || []" :key="option.id" :option="option" @seat-change="changeShortSeat" />
  </section>
  <section v-if="!result && !loading" class="grid grid-cols-1 sm:grid-cols-3 gap-4" aria-label="三种路线方式"><div v-for="(kind,i) in journeyKinds" :key="kind.code" class="rounded-xl border border-slate-200 bg-white/70 p-5"><component :is="[TrainFront,Armchair,ArrowLeftRight][i]" class="w-5 h-5 text-blue-600" /><h2 class="font-semibold mt-3">{{ kind.name }}</h2><p class="mt-2 text-sm leading-relaxed text-slate-600">{{ kind.description }}</p></div></section>
  <details class="text-xs text-slate-600 leading-relaxed px-1 pb-3"><summary class="cursor-pointer py-2 font-medium">查询规则与数据说明</summary><div class="mt-2 space-y-2"><p>全程有票结果只查询各段现票，不将候补或待补票区间当作可到达方案。同车接续需持覆盖全程的有效车票，按票面席位调整；重联列车可能需经站台换厢。有条件补票备选独立展示，后续能否继续乘坐尚未确认。</p><p>便捷换乘通道与参考时间来自已采集资料；余票和票价是查询快照，计划时刻不含晚点。请结合检票截止时间、行李和步行情况留足余量，实际安排以车站为准。</p><p>中转候选目前限12站便捷换乘资料，行程范围72小时，查询有时间和次数上限；城市代表站返回不等于全部站对穷举。本次结果不保证全国最优。</p><p>绕行判断使用 <a href="https://www.geonames.org/export/" target="_blank" rel="noopener noreferrer" class="text-blue-700 underline">GeoNames 城市中心坐标（CC BY 4.0）</a> 和全程耗时；地理距离不等于铁路里程，缺失或歧义坐标不猜测。默认可能排除部分可行路线，可主动扩大范围或指定站。</p><p><a href="https://mobile.12306.cn/otsmobile/h5/otsbussiness/info/transportationRules.html" target="_blank" rel="noopener noreferrer" class="text-blue-700 underline">12306 旅客运输规程</a> · <a href="https://m.thepaper.cn/newsDetail_forward_29181361" target="_blank" rel="noopener noreferrer" class="text-blue-700 underline">铁路部门同车接续说明</a></p></div></details>
</template>
<script setup>
import {ref,computed,watch,onMounted,onUnmounted} from 'vue'
import {Search,LoaderCircle,ArrowLeftRight,TrainFront,Armchair,MapPin} from 'lucide-vue-next'
import JourneyPlanCard from './JourneyPlanCard.vue'
import ShortTicketCard from './ShortTicketCard.vue'
import {seatOptions,defaultSeatCodes,sortPlans,calculateFare,formatDateTime} from '../lib/transfer.js'
import {journeyKinds,shanghaiDate,addDays,findExactStation,createJourneyQueryController,groupNotices,journeySummary} from '../lib/journey.js'
const today=shanghaiDate(),lastDate=addDays(today,14)
const fromText=ref('上海'),toText=ref('北京'),fromScope=ref('city'),toScope=ref('city'),trainDate=ref(today)
const mode=ref('auto'),trainType=ref('all'),sortBy=ref('duration'),allowedSeats=ref([...defaultSeatCodes])
const transferCount=ref(1),maxSameSegments=ref(2),officialTime=ref(true),minMinutes=ref(15),viaTexts=ref([''])
const allowLargeDetour=ref(false),includeShortFallback=ref(false)
const transferStations=ref([]),stationError=ref(''),suggestions=ref({from:[],to:[]})
const loading=ref(false),error=ref(''),notice=ref(''),result=ref(null),activeTab=ref('all')
const controller=createJourneyQueryController()
let sequence=0,disposed=false
const suggestionIds={from:0,to:0}
const statusNames={complete:'查询完成',partial:'范围有限或查询未完成',upstream_error:'查询失败',skipped:'本次未查询'}
const allPlans=computed(()=>journeyKinds.flatMap(k=>result.value?.[k.code].plans || []))
const tabs=computed(()=>[{code:'all',name:'全部路线',count:allPlans.value.length},...journeyKinds.map(k=>({...k,count:result.value?.[k.code].plans.length || 0}))])
const visibleKinds=computed(()=>journeyKinds.filter(k=>activeTab.value==='all'||activeTab.value===k.code))
const displayedPlans=computed(()=>sortPlans(activeTab.value==='all'?allPlans.value:(result.value?.[activeTab.value]?.plans || []),sortBy.value))
function invalidate(){sequence++;controller.cancel();loading.value=false;result.value=null;error.value='';notice.value=''}
watch([fromText,toText,fromScope,toScope,trainDate,mode,trainType,allowedSeats,transferCount,maxSameSegments,officialTime,minMinutes,viaTexts,allowLargeDetour,includeShortFallback],()=>{const had=!!result.value;invalidate();if(had)notice.value='查询条件已变更，请重新查询。'},{deep:true,flush:'sync'})
watch(sortBy,()=>{const had=!!result.value;invalidate();if(had)notice.value='排序条件已变更，请重新查询，以获取对应条件下的前列路线。'},{flush:'sync'})
onUnmounted(()=>{disposed=true;invalidate()})
onMounted(loadTransferStations)
async function loadTransferStations(){
  stationError.value=''
  try{const response=await fetch('/api/transfers/stations?limit=100');if(!response.ok)throw Error();const body=await response.json();if(!disposed)transferStations.value=body.data || []}
  catch{if(!disposed)stationError.value='中转站资料暂未加载，自动规划仍由服务端核验；指定站请重试加载。'}
}
async function stationLookup(value,signal){
  const response=await fetch(`/api/stations/search?keyword=${encodeURIComponent(value.trim())}&limit=30`,{signal})
  if(!response.ok)throw Error('车站搜索暂不可用，请稍后重试')
  const body=await response.json();return body.data || []
}
async function suggest(which){
  const id=++suggestionIds[which],value=which==='from'?fromText.value:toText.value
  try{const found=await stationLookup(value);if(!disposed&&id===suggestionIds[which])suggestions.value[which]=found}catch{/* Submission reports lookup failure. */}
}
function swap(){const a=fromText.value,s=fromScope.value;fromText.value=toText.value;toText.value=a;fromScope.value=toScope.value;toScope.value=s}
function cancel(){invalidate();notice.value='已取消本次查询。'}
function statusClasses(status){return status==='upstream_error'?'border-rose-200 bg-rose-50 text-rose-900':status==='partial'?'border-amber-200 bg-amber-50 text-amber-950':'border-slate-200 bg-white text-slate-700'}
function changeSeat({id,kind,index,code}){
  const plan=result.value?.[kind].plans.find(p=>p.id===id)
  if(!plan||!plan.legs[index].seats.some(s=>s.code===code))return
  plan.selected_seat_codes[index]=code
  const fare=calculateFare(plan.legs,plan.selected_seat_codes);plan.total_price_fen=fare.totalPriceFen;plan.known_price_fen=fare.knownPriceFen
}
function queryAll(){mode.value='all';search()}
function queryExpanded(){allowLargeDetour.value=true;mode.value='all';search()}
function queryShortFallback(){includeShortFallback.value=true;mode.value='all';search()}
function changeShortSeat({id,code}){
  const option=result.value?.short_fallback?.options.find(o=>o.id===id)
  const seat=option?.ticketed_leg.seats.find(s=>s.code===code)
  if(!seat)return
  option.selected_seat_code=code;option.known_price_fen=seat.price_fen ?? 0
}
async function search(){
  invalidate();const id=++sequence;loading.value=true
  try{
    if(!allowedSeats.value.length)throw Error('请至少选择一种可接受席别')
    const specified=viaTexts.value.map(s=>s.trim()).filter(Boolean)
    if(specified.length>transferCount.value)throw Error('请移除多出的指定站，或增加同站换乘次数')
    const via=specified.map(value=>findExactStation(transferStations.value,value).station_code)
    const from=fromText.value,to=toText.value
    const request={train_date:trainDate.value,from_scope:fromScope.value,to_scope:toScope.value,mode:mode.value,train_type:trainType.value,sort_by:sortBy.value,allowed_seats:[...allowedSeats.value],transfer_count:transferCount.value,max_same_train_segments:maxSameSegments.value,min_transfer_minutes:officialTime.value?null:minMinutes.value,ordered_via_stations:via,allow_large_detour:allowLargeDetour.value,include_short_fallback:includeShortFallback.value}
    const data=await controller.search(request,async(body,signal)=>{
      const [a,b]=await Promise.all([stationLookup(from,signal),stationLookup(to,signal)])
      return {...body,from_station:findExactStation(a,from,body.from_scope).telecode,to_station:findExactStation(b,to,body.to_scope).telecode}
    })
    if(id!==sequence||!data)return
    result.value=data;activeTab.value='all'
  }catch(e){if(id===sequence)error.value=e.message}
  finally{if(id===sequence)loading.value=false}
}
</script>
