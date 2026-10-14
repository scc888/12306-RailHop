<template>
  <div class="journey-workspace">
  <div v-if="isNarrow && settingsOpen" class="settings-backdrop" aria-hidden="true" @click="closeSettings" />
  <aside id="journey-settings" ref="settingsPanel" class="journey-card settings-panel" :class="{'settings-panel-open':settingsOpen}" :role="isNarrow && settingsOpen ? 'dialog' : 'complementary'" :aria-modal="isNarrow && settingsOpen ? true : undefined" aria-labelledby="search-heading" tabindex="-1" @keydown="settingsKeydown">
    <form ref="settingsForm" @submit.prevent="search('direct')">
      <div class="search-title settings-heading"><div><h1 id="search-heading">查询设置</h1><p>调整行程，查车次与接续方案</p></div><button v-if="isNarrow" type="button" class="settings-close" aria-label="关闭查询设置" @click="closeSettings"><X class="w-5 h-5" /></button></div>
      <div class="settings-scroll">
      <div class="search-main-grid">
        <div><label for="journey-from" class="journey-label">出发地</label><input id="journey-from" v-model="fromText" list="journey-from-list" @input="suggest('from')" @focus="suggest('from')" class="journey-input" placeholder="城市或完整车站名" required autocomplete="off" /><datalist id="journey-from-list"><option v-for="s in suggestions.from" :key="s.telecode" :value="s.name">{{ s.city_name }} · {{ s.telecode }}</option></datalist><label class="scope-control"><span>出发范围</span><select v-model="fromScope" aria-label="出发范围"><option value="city">同城车站</option><option value="station">仅此车站</option></select></label></div>
        <button type="button" @click="swap" class="swap-button" aria-label="交换出发地与目的地"><ArrowLeftRight class="w-4 h-4" /></button>
        <div><label for="journey-to" class="journey-label">目的地</label><input id="journey-to" v-model="toText" list="journey-to-list" @input="suggest('to')" @focus="suggest('to')" class="journey-input" placeholder="城市或完整车站名" required autocomplete="off" /><datalist id="journey-to-list"><option v-for="s in suggestions.to" :key="s.telecode" :value="s.name">{{ s.city_name }} · {{ s.telecode }}</option></datalist><label class="scope-control"><span>到达范围</span><select v-model="toScope" aria-label="到达范围"><option value="city">同城车站</option><option value="station">仅此车站</option></select></label></div>
        <div><label for="journey-date" class="journey-label">出发日期</label><input id="journey-date" v-model="trainDate" type="date" :min="today" :max="lastDate" class="journey-input" required /><div class="flex gap-3 mt-2 text-xs text-blue-700"><button type="button" @click="trainDate=today">今天</button><button type="button" @click="trainDate=addDays(today,1)">明天</button><span class="text-slate-500">15 天内</span></div></div>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
        <fieldset v-for="side in ['from','to']" :key="side" class="rounded-xl border border-slate-200 p-3 min-w-0">
          <legend class="text-xs font-semibold text-slate-700">{{ side==='from' ? '出发实际车站' : '到达实际车站' }}</legend>
          <p v-if="endpointScopes[side].loading" class="text-xs text-slate-500">正在加载车站范围…</p>
          <p v-else-if="endpointScopes[side].error" class="text-xs text-amber-800">{{ endpointScopes[side].error }} <button type="button" class="underline" @click="refreshScope(side)">重试</button></p>
          <template v-else>
            <p class="text-xs text-slate-500 mb-2">已选 {{ endpointScopes[side].codes.length }} 站 · 按实际站点查询</p>
            <div class="flex flex-wrap gap-x-3 gap-y-2 max-h-28 overflow-y-auto">
              <label v-for="station in endpointScopes[side].stations" :key="station.telecode" class="text-xs flex items-center gap-1">
                <input type="checkbox" :aria-label="`${side==='from'?'出发':'到达'} ${station.name}`" :checked="endpointScopes[side].codes.includes(station.telecode)" :disabled="settings[`${side}Scope`]==='station'" @change="selectScopeStation(side,station.telecode,$event.target.checked)" />{{ station.name }}
              </label>
            </div>
          </template>
        </fieldset>
      </div>
      <div class="search-filters">
        <label>列车类型<select v-model="trainType" aria-label="列车类型"><option value="all">全部列车</option><option value="high_speed">高铁 / 动车</option><option value="regular">普速列车</option></select></label>
        <label>方案排序<select v-model="sortBy" aria-label="方案排序"><option value="duration">耗时最短</option><option value="arrival">最早到达</option><option value="price">总价最低</option></select><span class="sort-scope">对本次已查到方案排序</span></label>
        <span class="filter-summary">最多 {{ transferCount }} 次同站换乘 · {{ officialTime ? '官方参考时间' : `至少 ${minMinutes} 分钟` }}</span>
      </div>
      <details class="advanced-settings" :open="advancedOpen" @toggle="advancedOpen=$event.target.open">
        <summary><span>席别与中转设置</span><span class="settings-summary">{{ seatSummary }}</span></summary>
        <fieldset class="mt-4"><legend class="journey-label mb-2">可接受席别（各段可分别选择）</legend><div class="flex flex-wrap gap-2"><label v-for="seat in seatOptions" :key="seat.code" class="seat-chip" :class="{'seat-selected':allowedSeats.includes(seat.code)}"><input v-model="allowedSeats" type="checkbox" :value="seat.code" class="accent-blue-600" />{{ seat.name }}</label></div></fieldset>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-5">
          <label class="journey-label">最多换乘<select v-model.number="transferCount" class="journey-input"><option v-for="n in 3" :key="n" :value="n">最多 {{ n }} 次 · {{ n+1 }} 段列车</option></select></label>
          <label class="journey-label">同车最多分段<select v-model.number="maxSameSegments" class="journey-input"><option :value="2">最多 2 段</option><option :value="3">最多 3 段</option></select></label>
          <div><label class="flex items-start gap-2 text-sm text-slate-700"><input v-model="officialTime" type="checkbox" class="mt-1 accent-blue-600" />按各站官方参考换乘时间</label><label v-if="!officialTime" class="journey-label mt-2">个人最少时间（分钟）<input v-model.number="minMinutes" type="number" min="1" max="1440" required class="journey-input" /></label><p class="mt-2 text-xs text-slate-500 leading-relaxed">自定义时完全按个人时间筛选；无官方时间时，已核实便捷换乘参考15分钟，便捷换乘状态未核实默认60分钟。同车接续不套用换车间隔。</p></div>
        </div>
        <div class="mt-4"><div class="via-station-heading"><label for="via-0" class="journey-label">指定中转站（可选，按顺序经过）</label><button type="button" @click="viaTexts.push('')" :disabled="viaTexts.length>=transferCount" class="text-xs font-semibold text-blue-700 disabled:text-slate-400 min-h-9">添加指定站</button></div><div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2"><div v-for="(_,i) in viaTexts" :key="i" class="flex items-center gap-2"><input :id="`via-${i}`" v-model="viaTexts[i]" @input="suggestVia(viaTexts[i])" @focus="suggestVia(viaTexts[i])" :aria-label="`第${i+1}个指定中转站`" list="journey-via-list" class="journey-input" placeholder="留空自动规划" /><button v-if="viaTexts.length>1" type="button" @click="viaTexts.splice(i,1)" :aria-label="`移除第${i+1}个指定站`" class="min-w-9 min-h-10 text-slate-600">×</button></div></div><datalist id="journey-via-list"><option v-for="s in viaSuggestions.length ? viaSuggestions : transferStations" :key="s.station_code" :value="s.station_name">{{ s.station_code }}</option></datalist><p class="mt-2 text-xs text-slate-500">可搜索完整车站字典；{{ transferStations.length }} 站便捷换乘资料仅供参考，不限制候选范围。指定站只约束同站中转路线。</p><p v-if="stationError" class="mt-2 text-xs text-amber-800">{{ stationError }} <button type="button" @click="loadTransferStations" class="underline">重试加载</button></p></div>
        <label class="flex items-center gap-2 text-sm text-slate-700 mt-4"><input v-model="allowLargeDetour" type="checkbox" class="accent-blue-600" />允许较大绕行（默认关闭）</label>
      </details>
      </div>
      <div class="settings-actions">
        <button type="button" :disabled="loading" class="journey-primary query-button" @click="submitQuery('fastest')">查最快中转</button>
        <button type="submit" :disabled="loading" class="journey-primary query-button"><Search v-if="!loading" class="w-4 h-4" /><LoaderCircle v-else class="w-4 h-4 animate-spin" />{{ loading ? '正在查询…' : '查询车次' }}</button>
        <div class="settings-save-row"><p v-if="!settingsSaved" role="status">此浏览器暂时无法保存设置</p><button type="button" @click="resetSettings">恢复默认设置</button></div>
      </div>
    </form>
  </aside>
  <div class="journey-results-column" :inert="isNarrow && settingsOpen">
  <div v-if="!settingsOpen" class="mobile-query-bar">
    <div class="mobile-query-summary"><strong>{{ fromText || '出发地' }} → {{ toText || '目的地' }}</strong><span>{{ trainDate }} · {{ officialTime ? '官方换乘时间' : `换乘至少 ${minMinutes} 分钟` }}</span></div>
    <div class="mobile-query-buttons"><button ref="settingsTrigger" type="button" class="journey-secondary" @click="openSettings"><SlidersHorizontal class="w-4 h-4" />修改条件</button><button type="button" class="journey-primary" :disabled="loading" @click="submitQuery('fastest')">查最快中转</button><button type="button" class="journey-secondary" :disabled="loading" @click="submitQuery">{{ loading ? '正在查询…' : '查询车次' }}</button></div>
  </div>
  <div class="journey-results-scroll" role="region" aria-label="车次与路线结果" tabindex="0">
  <div v-if="notice" role="status" class="notice-box text-blue-900 bg-blue-50 border-blue-200">{{ notice }}</div>
  <div v-if="error" role="alert" class="notice-box text-rose-900 bg-rose-50 border-rose-200">{{ error }}</div>
  <section v-if="loading" class="journey-card p-6 flex flex-wrap items-center gap-4" role="status"><LoaderCircle class="w-5 h-5 animate-spin text-blue-600" /><p class="text-sm font-semibold">{{ showGlobal ? '正在查询全部出行路线…' : '正在查询车次与直达余票…' }}</p><button type="button" @click="cancel" class="ml-auto text-sm text-blue-700 min-h-10">取消本次查询</button></section>
  <section v-if="result && !loading" class="space-y-3" aria-labelledby="results-heading">
    <div class="results-toolbar">
      <div><h2 id="results-heading" class="font-bold text-lg">{{ result.scope.from_label }} <span class="text-slate-400">→</span> {{ result.scope.to_label }}</h2><p class="text-xs text-slate-500 mt-1">{{ queryMode==='fastest' ? '最快中转 · 含等待的总耗时' : showGlobal ? '全局路线查询' : `共 ${trains.length} 趟 · 所选席别直达有票 ${availableCount} 趟` }} · {{ formatDateTime(result.queried_at) }} 更新</p></div>
      <button type="button" @click="showGlobal ? backToTrains() : search('all')" class="journey-secondary">{{ showGlobal ? '返回车次列表' : '不限定车次，查全部路线' }}</button>
    </div>
    <template v-if="!showGlobal">
      <div class="train-list-toolbar"><p>点击车次或右侧按钮，展开这辆车的接续 / 中转方案</p><label>车次排序<select v-model="trainSort" aria-label="车次排序"><option value="departure">出发时间</option><option value="duration">运行时长</option></select></label></div>
      <details v-if="groupNotices(result.direct).length" class="list-query-notes"><summary :class="{'text-rose-800':result.direct.meta.status==='upstream_error'}">{{ result.direct.meta.status==='upstream_error' ? '车次查询失败，不能判断是否有票' : '本次车次查询范围与说明' }}</summary><ul class="list-disc pl-5 mt-2 space-y-1"><li v-for="item in groupNotices(result.direct)" :key="item">{{ item }}</li></ul></details>
      <JourneyTrainCard v-for="train in sortedTrains" :key="train.id" :train="train" :allowed-seats="allowedSeats" :expanded="selectedTrain?.id===train.id" @toggle="toggleTrain(train)">
        <JourneyAlternatives :train="train" :result="selectedResult" :loading="planning" :error="planError" :sort-by="sortBy" :allow-large-detour="allowLargeDetour" @retry="planTrain(train)" @cancel="cancelPlan" @seat-change="changeSeat($event,selectedResult)" @short-seat-change="changeShortSeat($event,selectedResult)" @expanded="expandSearch" @short-fallback="planTrain(train,true)" />
      </JourneyTrainCard>
      <div v-if="!trains.length" class="journey-card plan-empty"><p class="font-semibold">{{ result.direct.meta.status==='upstream_error' ? '车次查询暂未成功' : '本次范围内未查到符合条件的直达车次' }}</p><p class="text-sm text-slate-500 mt-2">可以调整日期或列车类型，也可以不限定车次，查询同站中转路线。</p><button type="button" @click="search('all')" class="journey-primary mt-4">查询全局路线</button></div>
    </template>
    <div v-else class="journey-card p-4 sm:p-5"><JourneyAlternatives :result="result" :sort-by="sortBy" :allow-large-detour="allowLargeDetour" :fastest="queryMode==='fastest'" :max-transfers="transferCount" @more-transfers="expandTransfers" @retry="search(queryMode)" @seat-change="changeSeat($event,result)" @short-seat-change="changeShortSeat($event,result)" @expanded="expandSearch" @short-fallback="search(queryMode,true)" /></div>
  </section>
  <section v-if="!result && !loading && !error" class="start-hint"><TrainFront class="w-6 h-6 text-blue-500 shrink-0" /><div><p class="font-semibold text-sm">无票车次也能查方案</p><p class="text-xs text-slate-500 mt-1 leading-relaxed">查询后点击某辆车，查看同车换座或沿途同站换车；也可<button type="button" @click="search('all')" class="text-blue-700 underline min-h-9">不限定车次查全部路线</button>。</p></div></section>
  <details class="text-xs text-slate-500 leading-relaxed px-1 pb-3"><summary class="cursor-pointer py-2 font-medium">查询规则与数据说明</summary><div class="mt-2 space-y-2"><p>全程有票路线仅包含已查到现票的区间，候补、不可售及待补票区间不算现票。同车接续需持连续区间有效车票，按票面席位调整；重联列车换厢可能需经站台。</p><p>中途只接受同一实际车站换乘。中转站动态发现，便捷换乘资料独立维护；行程范围72小时，查询有时间和次数上限；城市代表站返回不等于全部站对穷举，不保证全国最优。</p><p>默认采用已采集的官方参考换乘时间，无适用时间时，已核实便捷换乘参考15分钟，便捷换乘状态未核实默认60分钟；自定义时完全采用个人设置。余票、票价是查询快照，计划时刻不含晚点，须结合检票截止时间和现场安排留足余量。</p><p>绕行筛选使用 <a href="https://www.geonames.org/export/" target="_blank" rel="noopener noreferrer" class="text-blue-700 underline">GeoNames 城市中心坐标（CC BY 4.0）</a>及全程耗时，地理距离不等于铁路里程。可主动允许较大绕行或指定站。</p><p><a href="https://mobile.12306.cn/otsmobile/h5/otsbussiness/info/transportationRules.html" target="_blank" rel="noopener noreferrer" class="text-blue-700 underline">12306 旅客运输规程</a> · <a href="https://m.thepaper.cn/newsDetail_forward_29181361" target="_blank" rel="noopener noreferrer" class="text-blue-700 underline">铁路部门同车接续说明</a></p></div></details>
  </div>
  </div>
  </div>
</template>
<script setup>
import {ref,reactive,toRefs,computed,watch,nextTick,onMounted,onUnmounted} from 'vue'
import {Search,LoaderCircle,ArrowLeftRight,TrainFront,X,SlidersHorizontal} from 'lucide-vue-next'
import JourneyTrainCard from './JourneyTrainCard.vue'
import JourneyAlternatives from './JourneyAlternatives.vue'
import {seatOptions,calculateFare,formatDateTime} from '../lib/transfer.js'
import {shanghaiDate,addDays,findExactStation,resolveViaStations,createJourneyQueryController,groupNotices,trainHasSeats,endpointSelection,endpointRequest} from '../lib/journey.js'
import {createDefaultSettings,loadJourneySettings,saveJourneySettings} from '../lib/settings.js'
import {trainSeatQuery} from '../lib/fares.js'
const today=shanghaiDate(),lastDate=addDays(today,14)
const settings=reactive(loadJourneySettings(today)),settingsSaved=ref(true)
const {fromText,toText,fromScope,toScope,trainDate,trainType,sortBy,allowedSeats,trainSort,
  transferCount,maxSameSegments,officialTime,minMinutes,viaTexts,allowLargeDetour,advancedOpen}=toRefs(settings)
watch(settings,()=>{settingsSaved.value=saveJourneySettings(settings,today)},{deep:true,immediate:true})
const narrowScreen=window.matchMedia('(max-width: 1199px)'),isNarrow=ref(narrowScreen.matches)
const settingsOpen=ref(false),settingsPanel=ref(null),settingsTrigger=ref(null),settingsForm=ref(null)
let previousBodyOverflow=null
function screenChanged(event){isNarrow.value=event.matches;if(!event.matches)settingsOpen.value=false}
async function openSettings(){settingsOpen.value=true;await nextTick();settingsPanel.value?.focus()}
async function closeSettings(){settingsOpen.value=false;await nextTick();if(isNarrow.value)settingsTrigger.value?.focus()}
async function submitQuery(mode='direct'){
  if(!settingsForm.value.checkValidity()){
    advancedOpen.value=true
    await openSettings()
    settingsForm.value.reportValidity()
    return
  }
  if(mode==='fastest')await search('fastest')
  else settingsForm.value.requestSubmit()
}
function resetSettings(){
  invalidate()
  Object.assign(settings,createDefaultSettings(today))
  refreshScope('from');refreshScope('to')
  notice.value='已恢复默认查询设置。'
}
function settingsKeydown(event){
  if(!isNarrow.value || !settingsOpen.value)return
  if(event.key==='Escape'){event.preventDefault();closeSettings();return}
  if(event.key!=='Tab')return
  const controls=[...settingsPanel.value.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),summary,a[href]')].filter(el=>el.getClientRects().length)
  const first=controls[0],last=controls.at(-1),active=document.activeElement
  if(event.shiftKey && (active===first || active===settingsPanel.value)){event.preventDefault();last?.focus()}
  else if(!event.shiftKey && (active===last || active===settingsPanel.value)){event.preventDefault();first?.focus()}
}
watch([settingsOpen,isNarrow],([open,narrow])=>{
  if(open && narrow && previousBodyOverflow===null){previousBodyOverflow=document.body.style.overflow;document.body.style.overflow='hidden'}
  else if((!open || !narrow) && previousBodyOverflow!==null){document.body.style.overflow=previousBodyOverflow;previousBodyOverflow=null}
},{flush:'sync'})
const transferStations=ref([]),viaSuggestions=ref([]),stationError=ref(''),suggestions=ref({from:[],to:[]})
const queryMode=ref('direct')
const endpointScopes=reactive({from:{stations:[],codes:[],loading:true,error:''},to:{stations:[],codes:[],loading:true,error:''}})
const scopeControllers={from:null,to:null}
const loading=ref(false),error=ref(''),notice=ref(''),result=ref(null),showGlobal=ref(false)
const selectedTrain=ref(null),selectedResult=ref(null),planning=ref(false),planError=ref('')
const controller=createJourneyQueryController(),planController=createJourneyQueryController()
let sequence=0,planSequence=0,disposed=false,resolvedRequest=null
const suggestionIds={from:0,to:0,via:0}
const trains=computed(()=>result.value?.trains || [])
const sortedTrains=computed(()=>[...trains.value].sort((a,b)=>trainSort.value==='departure'?a.start_time.localeCompare(b.start_time):minutes(a.duration)-minutes(b.duration)))
const availableCount=computed(()=>trains.value.filter(t=>trainHasSeats(t,allowedSeats.value)).length)
const seatSummary=computed(()=>seatOptions.filter(s=>allowedSeats.value.includes(s.code)).map(s=>s.name).join(' / ') || '请选择席别')
function minutes(duration){const [h,m]=duration.split(':').map(Number);return h*60+m}
function clearPlan(){planSequence++;planController.cancel();planning.value=false;selectedTrain.value=null;selectedResult.value=null;planError.value=''}
function invalidate(){sequence++;controller.cancel();clearPlan();loading.value=false;result.value=null;resolvedRequest=null;error.value='';notice.value=''}
watch([fromText,toText,fromScope,toScope,trainDate,trainType],()=>{const had=!!result.value;invalidate();if(had)notice.value='查询条件已变更，请重新查询车次。'},{flush:'sync'})
watch([allowedSeats,transferCount,maxSameSegments,officialTime,minMinutes,viaTexts,allowLargeDetour],()=>{
  if(showGlobal.value){const had=!!result.value;invalidate();if(had)notice.value='路线条件已更新，请重新查询全部路线。';return}
  const train=selectedTrain.value
  clearPlan();selectedTrain.value=train
  if(result.value)notice.value='席别或中转条件已更新，车次列表已保留；请重新查询所选车次的方案。'
},{deep:true,flush:'sync'})
onUnmounted(()=>{disposed=true;scopeControllers.from?.abort();scopeControllers.to?.abort();invalidate();narrowScreen.removeEventListener('change',screenChanged);if(previousBodyOverflow!==null)document.body.style.overflow=previousBodyOverflow})
onMounted(()=>{narrowScreen.addEventListener('change',screenChanged);loadTransferStations();refreshScope('from');refreshScope('to')})
async function loadTransferStations(){
  stationError.value=''
  try{const response=await fetch('/api/transfers/stations?limit=100');if(!response.ok)throw Error();const body=await response.json();if(!disposed)transferStations.value=body.data || []}
  catch{if(!disposed)stationError.value='便捷换乘参考资料暂未加载；仍可搜索和指定其他车站。'}
}
async function stationLookup(value,signal){
  const response=await fetch(`/api/stations/search?keyword=${encodeURIComponent(value.trim())}&limit=30`,{signal})
  if(!response.ok)throw Error('车站搜索暂不可用，请稍后重试')
  const body=await response.json();return body.data || []
}
async function resolveEndpoint(side,signal){
  const input=settings[`${side}Text`],mode=settings[`${side}Scope`]
  const anchor=findExactStation(await stationLookup(input,signal),input,mode).telecode
  if(signal.aborted)throw Error('查询已取消')
  const response=await fetch(`/api/stations/scope?station_code=${anchor}`,{signal})
  const body=await response.json()
  if(!response.ok || body.code!==200 || !Array.isArray(body.data?.stations) || !Array.isArray(body.data?.default_station_codes))throw Error('车站范围加载失败，请重试')
  if(signal.aborted || settings[`${side}Text`]!==input || settings[`${side}Scope`]!==mode)throw Error('查询条件已变化')
  const scope=body.data,codes=endpointSelection(scope,settings[`${side}Selection`],input,mode,anchor)
  Object.assign(endpointScopes[side],{stations:mode==='station'?scope.stations.filter(s=>s.telecode===anchor):scope.stations,codes,loading:false,error:''})
  return {anchor,codes}
}
async function refreshScope(side){
  scopeControllers[side]?.abort()
  const abort=new AbortController();scopeControllers[side]=abort
  Object.assign(endpointScopes[side],{stations:[],codes:[],loading:true,error:''})
  try{await resolveEndpoint(side,abort.signal)}catch(e){if(!abort.signal.aborted && !disposed)Object.assign(endpointScopes[side],{loading:false,error:e.message})}
}
watch([fromText,fromScope],()=>refreshScope('from'),{flush:'sync'})
watch([toText,toScope],()=>refreshScope('to'),{flush:'sync'})
function selectScopeStation(side,code,checked){
  const codes=endpointScopes[side].codes.filter(c=>c!==code)
  if(checked)codes.push(code)
  endpointScopes[side].codes=codes
  settings[`${side}Selection`]={input:settings[`${side}Text`],codes:[...codes]}
  invalidate();notice.value='车站范围已更新，请重新查询。'
}
async function suggest(which){const id=++suggestionIds[which],value=which==='from'?fromText.value:toText.value;try{const found=await stationLookup(value);if(!disposed&&id===suggestionIds[which])suggestions.value[which]=found}catch{/* Submission reports failures. */}}
async function suggestVia(value){const id=++suggestionIds.via;try{const found=await stationLookup(value);if(!disposed&&id===suggestionIds.via)viaSuggestions.value=found.map(s=>({...s,station_name:s.name,station_code:s.telecode}))}catch{/* Submission reports lookup failures. */}}
function swap(){const a=fromText.value,s=fromScope.value;fromText.value=toText.value;toText.value=a;fromScope.value=toScope.value;toScope.value=s}
function cancel(){invalidate();notice.value='已取消本次查询。'}
function cancelPlan(){planSequence++;planController.cancel();planning.value=false;notice.value='已取消方案查询，车次列表已保留。'}
function backToTrains(){clearPlan();showGlobal.value=false}
function toggleTrain(train){if(selectedTrain.value?.id===train.id)clearPlan();else planTrain(train)}
async function planTrain(train,includeShortFallback=false){
  if(!train.selection || !resolvedRequest)return
  clearPlan();const id=++planSequence;selectedTrain.value=train;planning.value=true
  try{const options=requestOptions('all',includeShortFallback);const seats=trainSeatQuery(train,options.allowed_seats);const data=await planController.search({...resolvedRequest,...options,allowed_seats:seats.allowedSeats,selected_train:train.selection},async(body,signal)=>({...body,ordered_via_stations:await resolveViaStations([...viaTexts.value],stationLookup,signal)}));if(id===planSequence&&data)selectedResult.value=data}
  catch(e){if(id===planSequence)planError.value=e.message}
  finally{if(id===planSequence)planning.value=false}
}
async function expandSearch(){
  const train=selectedTrain.value
  allowLargeDetour.value=true
  if(train){notice.value='已允许较大绕行，本次仍从所选车次出发。';await planTrain(train)}
  else await search(queryMode.value)
}
async function expandTransfers(){const mode=queryMode.value;transferCount.value=Math.max(2,transferCount.value);await search(mode)}
function changeSeat({id,kind,index,code},data){const plan=data?.[kind]?.plans.find(p=>p.id===id);if(!plan||!plan.legs[index].seats.some(s=>s.code===code))return;plan.selected_seat_codes[index]=code;const fare=calculateFare(plan.legs,plan.selected_seat_codes);plan.total_price_fen=fare.totalPriceFen;plan.known_price_fen=fare.knownPriceFen}
function changeShortSeat({id,code},data){const option=data?.short_fallback?.options.find(o=>o.id===id),seat=option?.ticketed_leg.seats.find(s=>s.code===code);if(seat){option.selected_seat_code=code;option.known_price_fen=seat.price_fen ?? 0}}
function requestOptions(mode,includeShortFallback=false){
  if(!allowedSeats.value.length)throw Error('请至少选择一种可接受席别')
  const specified=viaTexts.value.map(s=>s.trim()).filter(Boolean)
  if(specified.length>transferCount.value)throw Error('请移除多出的指定站，或增加同站换乘次数')
  const via=[]
  return {train_date:trainDate.value,from_scope:fromScope.value,to_scope:toScope.value,mode,train_type:trainType.value,sort_by:mode==='fastest'?'duration':sortBy.value,allowed_seats:[...allowedSeats.value],transfer_count:transferCount.value,max_transfers:transferCount.value,max_same_train_segments:maxSameSegments.value,min_transfer_minutes:officialTime.value?null:minMinutes.value,ordered_via_stations:via,allow_large_detour:allowLargeDetour.value,include_short_fallback:includeShortFallback}
}
async function search(mode='direct',includeShortFallback=false){
  if(isNarrow.value)closeSettings()
  if(mode==='fastest')sortBy.value='duration'
  invalidate();queryMode.value=mode;showGlobal.value=mode!=='direct';const id=++sequence;loading.value=true
  try{
    const request=requestOptions(mode,includeShortFallback)
    let prepared
    const data=await controller.search(request,async(body,signal)=>{const [a,b,via]=await Promise.all([resolveEndpoint('from',signal),resolveEndpoint('to',signal),resolveViaStations([...viaTexts.value],stationLookup,signal)]);const from=endpointRequest(a.anchor,a.codes),to=endpointRequest(b.anchor,b.codes);prepared={...body,from_station:from.anchor,to_station:to.anchor,from_station_codes:from.codes,to_station_codes:to.codes,ordered_via_stations:via};return prepared})
    if(id!==sequence||!data)return
    if(!Array.isArray(data.trains))throw Error('车次列表响应格式异常，请刷新服务后重试')
    resolvedRequest=prepared;result.value=data
  }catch(e){if(id===sequence)error.value=e.message}
  finally{if(id===sequence)loading.value=false}
}
</script>
