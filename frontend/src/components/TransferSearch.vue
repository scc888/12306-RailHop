<template>
  <div class="space-y-5">
    <section class="bg-white rounded-2xl p-5 sm:p-6 border border-slate-200 shadow-xs">
      <div class="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div><h2 class="text-lg font-bold">找一条有票的中转路线</h2><p class="text-sm text-slate-500 mt-1">同一个车站换乘，连接不同车次；全程耗时包含中间等待。</p></div>
        <span class="rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold px-3 py-1.5">仅查询 · 不下单</span>
      </div>
      <form @submit.prevent="search" class="space-y-5">
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label class="text-xs font-semibold text-slate-600">出发站
            <input v-model="fromText" @input="suggest('from')" @focus="suggest('from')" list="transfer-from-stations" required placeholder="汉字 / 拼音 / 简拼" class="transfer-input" />
            <datalist id="transfer-from-stations"><option v-for="s in fromSuggestions" :key="s.telecode" :value="s.name">{{ s.pinyin }} · {{ s.pinyin_abbr }}</option></datalist>
          </label>
          <label class="text-xs font-semibold text-slate-600">到达站
            <input v-model="toText" @input="suggest('to')" @focus="suggest('to')" list="transfer-to-stations" required placeholder="汉字 / 拼音 / 简拼" class="transfer-input" />
            <datalist id="transfer-to-stations"><option v-for="s in toSuggestions" :key="s.telecode" :value="s.name">{{ s.pinyin }} · {{ s.pinyin_abbr }}</option></datalist>
          </label>
          <label class="text-xs font-semibold text-slate-600">首段出发日期
            <input v-model="trainDate" type="date" :min="today" required class="transfer-input" />
          </label>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label class="text-xs font-semibold text-slate-600">中转站数量
            <select v-model.number="transferCount" class="transfer-input"><option v-for="n in 3" :key="n" :value="n">{{ n }} 个站 · {{ n + 1 }} 段车次</option></select>
          </label>
          <label class="text-xs font-semibold text-slate-600">每次最少换乘时间（分钟）
            <input v-model.number="minMinutes" type="number" min="15" max="1440" step="1" required class="transfer-input" />
          </label>
          <label class="text-xs font-semibold text-slate-600">结果排序
            <select v-model="sortBy" class="transfer-input"><option value="duration">全程耗时最短</option><option value="arrival">最早到达</option><option value="price">所选席别总价最低</option></select>
          </label>
        </div>
        <div class="rounded-xl bg-slate-50 border border-slate-100 p-4">
          <div class="flex justify-between items-center gap-2"><label for="transfer-via-0" class="text-xs font-semibold text-slate-600">指定中转站（可选，按顺序经过）</label><button type="button" @click="addVia" :disabled="viaTexts.length >= transferCount" class="text-xs text-blue-700 font-semibold disabled:text-slate-400 cursor-pointer">＋ 添加指定站</button></div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
            <div v-for="(_,index) in viaTexts" :key="index" class="flex gap-2 items-center">
              <input :id="`transfer-via-${index}`" v-model="viaTexts[index]" list="transfer-via-stations" :aria-label="`第${index + 1}个指定中转站`" :placeholder="`指定站 ${index + 1}，留空自动规划`" class="transfer-input !mt-0" />
              <button v-if="viaTexts.length > 1" type="button" @click="viaTexts.splice(index,1)" :aria-label="`移除第${index + 1}个指定站`" class="text-slate-400 hover:text-rose-600 px-1 cursor-pointer">×</button>
            </div>
          </div>
          <datalist id="transfer-via-stations"><option v-for="s in stations" :key="s.station_code" :value="s.station_name">{{ s.pinyin }} · {{ s.pinyin_abbr }}</option></datalist>
          <p class="text-xs text-slate-500 mt-2">已收录 {{ stations.length }} 个有便捷换乘资料的车站；未指定的位置由系统推荐。</p>
          <p v-if="stationError" role="alert" class="text-xs text-rose-700 mt-2">{{ stationError }}</p>
        </div>
        <fieldset><legend class="text-xs font-semibold text-slate-600 mb-2">可接受席别（各段可分别选择）</legend>
          <div class="flex flex-wrap gap-2"><label v-for="seat in seatOptions" :key="seat.code" class="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs cursor-pointer" :class="allowedSeats.includes(seat.code) ? 'bg-blue-50 text-blue-800 border-blue-200' : 'bg-white text-slate-500 border-slate-200'"><input v-model="allowedSeats" type="checkbox" :value="seat.code" class="accent-blue-600" />{{ seat.name }}</label></div>
        </fieldset>
        <div class="flex flex-wrap justify-between items-center gap-4 border-t border-slate-100 pt-4">
          <p class="text-xs text-slate-500 max-w-xl leading-relaxed">15 分钟是默认查询阈值，车站有更高参考值时按较高值筛选。请结合行李、步行速度及现场检票安排预留时间。</p>
          <button type="submit" :disabled="loading" class="px-6 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 disabled:opacity-60 cursor-pointer">{{ loading ? '正在寻找路线…' : '查询中转方案' }}</button>
        </div>
      </form>
    </section>

    <div v-if="error" role="alert" class="rounded-xl border border-rose-200 bg-rose-50 text-rose-800 p-4 text-sm">{{ error }}</div>
    <div v-if="loading" role="status" class="rounded-2xl bg-white border border-slate-200 p-8 text-center"><div class="mx-auto mb-3 h-6 w-6 rounded-full border-2 border-blue-100 border-t-blue-600 animate-spin"></div><p class="font-semibold text-slate-700">正在查询各段余票并核对换乘时间</p><p class="text-xs text-slate-500 mt-2">多次中转需要查询更多区间，通常需要数十秒。</p><button type="button" @click="invalidate" class="text-sm text-blue-700 mt-4 cursor-pointer">取消本次查询</button></div>
    <section v-if="result && !loading" class="space-y-4" aria-live="polite">
      <div class="flex flex-wrap justify-between items-center gap-2"><h2 class="font-bold">找到 {{ result.plans.length }} 条有票中转方案</h2><span class="text-xs text-slate-500">查询 {{ formatDateTime(result.meta.queried_at) }} · 按{{ sortNames[sortBy] }}排序</span></div>
      <div v-if="result.meta.status === 'upstream_error'" role="alert" class="rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-sm p-4">铁路接口暂未查询成功，不能据此判断是否有票。请稍后重试。</div>
      <div v-else-if="result.meta.truncated || result.meta.failed_pairs.length" class="rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-sm p-4"><p class="font-semibold">以下是已查询范围内的推荐，结果可能不完整。</p><p class="text-xs mt-1">{{ truncationText }}<span v-if="result.meta.failed_pairs.length"> {{ result.meta.failed_pairs.length }} 个区间查询失败或数据异常。</span></p></div>
      <p v-if="!result.plans.length && result.meta.status !== 'upstream_error'" class="p-7 text-center bg-white rounded-2xl border border-slate-200 text-sm text-slate-500">本次搜索范围内未找到符合席别与换乘条件的路线，可尝试修改日期、指定站或中转次数。</p>
      <TransferPlanCard v-for="(plan,index) in sortedPlans" :key="plan.id" :plan="plan" :rank="index + 1" @seat-change="changeSeat" />
      <details class="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-500"><summary class="cursor-pointer font-semibold">查看本次查询范围与车站资料</summary><p class="mt-3 leading-relaxed">候选中转站：{{ candidateNames }}。首段按所选日期查询，后续行程最多 {{ result.meta.limits.horizon_hours }} 小时；最多查询 {{ result.meta.limits.max_queries }} 个日期区间、处理 {{ result.meta.limits.max_states }} 个搜索状态，展示前 {{ result.meta.limits.max_results }} 条路线。</p><p class="mt-2">余票为短期快照；便捷换乘资料不是通道实时开放状态。当前收录站按同日 G/D/C 列车换乘筛选，临时调整以车站公告为准。</p></details>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import TransferPlanCard from './TransferPlanCard.vue'
import { seatOptions, sortPlans, createTransferQueryController, formatDateTime } from '../lib/transfer.js'
const props = defineProps({ initialFrom:String, initialTo:String, initialDate:String, initialSeats:Array })
const today = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
const fromText = ref(props.initialFrom || '')
const toText = ref(props.initialTo || '')
const trainDate = ref(props.initialDate || today)
const transferCount = ref(1)
const minMinutes = ref(15)
const viaTexts = ref([''])
const allowedSeats = ref(props.initialSeats?.length ? [...props.initialSeats] : ['ze','zy'])
const sortBy = ref('duration')
const stations = ref([])
const fromSuggestions = ref([])
const toSuggestions = ref([])
const loading = ref(false)
const result = ref(null)
const error = ref('')
const stationError = ref('')
const controller = createTransferQueryController()
let requestId = 0
const sortNames = {duration:'全程耗时',arrival:'到达时间',price:'当前所选总价'}
const reasons = {candidate_limit:'候选站范围受限',query_limit:'达到区间查询上限',time_limit:'达到查询时间上限',state_limit:'达到组合搜索上限',result_limit:'仅展示前列方案',horizon_limit:'已排除超出行程时间范围的车次'}
const sortedPlans = computed(() => sortPlans(result.value?.plans || [],sortBy.value))
const truncationText = computed(() => (result.value?.meta.truncation_reasons || []).map(r=>reasons[r] || r).join('；'))
const candidateNames = computed(() => (result.value?.meta.candidate_station_codes || []).map(c=>stations.value.find(s=>s.station_code===c)?.station_name || c).join('、'))
function invalidate() { requestId++; controller.cancel(); loading.value=false; result.value=null; error.value='' }
watch([fromText,toText,trainDate,transferCount,minMinutes,viaTexts,allowedSeats],invalidate,{deep:true,flush:'sync'})
watch(() => [props.initialFrom,props.initialTo,props.initialDate],([from,to,day])=>{fromText.value=from || '';toText.value=to || '';trainDate.value=day || today})
onUnmounted(() => controller.cancel())
onMounted(async()=>{
  try { const response=await fetch('/api/transfers/stations?limit=100'); if(!response.ok) throw new Error(); const body=await response.json(); stations.value=body.data || [] }
  catch { stationError.value='便捷换乘车站资料暂未加载，请刷新后重试。' }
})
const suggestionIds = {from:0,to:0}
async function suggest(which) {
  const id=++suggestionIds[which]
  const value=which==='from' ? fromText.value : toText.value
  try { const response=await fetch(`/api/stations/search?keyword=${encodeURIComponent(value)}&limit=20`); if(!response.ok) return; const body=await response.json(); if(id===suggestionIds[which]) (which==='from' ? fromSuggestions : toSuggestions).value=body.data || [] }
  catch { /* Submission reports lookup failures; typing keeps its value. */ }
}
async function resolveStation(text) {
  const word=text.trim()
  const response=await fetch(`/api/stations/search?keyword=${encodeURIComponent(word)}&limit=20`)
  if(!response.ok) throw new Error('车站搜索暂不可用，请稍后重试')
  const body=await response.json()
  const station=body.data?.find(s=>[s.name,s.telecode,s.pinyin,s.pinyin_abbr].some(v=>v.toLowerCase()===word.toLowerCase()))
  if(!station) throw new Error(`无法识别“${word}”，请从站点提示中选择具体车站`)
  return station.telecode
}
function addVia() { if(viaTexts.value.length<transferCount.value) viaTexts.value.push('') }
async function search() {
  invalidate()
  const id=++requestId
  loading.value=true
  try {
    if(!allowedSeats.value.length) throw new Error('请至少选择一种可接受席别')
    const specified=viaTexts.value.map(s=>s.trim()).filter(Boolean)
    if(specified.length>transferCount.value) throw new Error('请移除多出的指定站，或增加中转站数量')
    const via=specified.map(word=>{
      const s=stations.value.find(s=>[s.station_name,s.station_code,s.pinyin,s.pinyin_abbr].some(v=>v.toLowerCase()===word.toLowerCase()))
      if(!s) throw new Error(`“${word}”尚无可用的便捷换乘资料，请从已收录站中选择`)
      return s.station_code
    })
    const [from,to]=await Promise.all([resolveStation(fromText.value),resolveStation(toText.value)])
    if(id!==requestId) return
    const data=await controller.search({from_station:from,to_station:to,train_date:trainDate.value,transfer_count:transferCount.value,min_transfer_minutes:minMinutes.value,ordered_via_stations:via,allowed_seats:[...allowedSeats.value],sort_by:sortBy.value})
    if(id===requestId && data) result.value=data
  } catch(e) { if(id===requestId) error.value=e instanceof SyntaxError ? '查询服务响应异常，请稍后重试' : e.message }
  finally { if(id===requestId) loading.value=false }
}
function changeSeat({planId,legIndex,seatCode}) {
  const plan=result.value?.plans.find(p=>p.id===planId)
  if(plan?.legs[legIndex]?.seats.some(s=>s.code===seatCode)) plan.selected_seat_codes[legIndex]=seatCode
}
</script>

<style scoped>
@reference "../style.css";
.transfer-input { @apply mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100; }
</style>
