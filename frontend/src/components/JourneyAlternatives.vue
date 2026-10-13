<template>
  <div class="space-y-4" data-testid="journey-alternatives">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div><h3 class="font-bold text-slate-900">{{ train ? `${train.train_code} 的接续 / 中转方案` : '全部出行路线' }}</h3><p class="mt-1 text-xs text-slate-600 leading-relaxed">{{ train ? `从 ${train.from_station_name} 乘坐 ${train.train_code} 出发，查同车分段接续，或在沿途车站换车。` : '不限定出发车次，一起比较直达、同车接续和同站中转。' }}</p></div>
      <button v-if="!loading" type="button" @click="$emit('retry')" class="text-xs text-blue-700 font-semibold min-h-9">重新查询方案</button>
    </div>
    <div v-if="loading" role="status" class="panel-loading"><LoaderCircle class="w-5 h-5 animate-spin text-blue-600" /><div><p class="text-sm font-semibold">正在核对{{ train ? train.train_code : '各段' }}余票与换乘条件…</p><p class="mt-1 text-xs text-slate-500">多次换乘可能需要约一分钟。</p></div><button type="button" @click="$emit('cancel')" class="text-sm text-blue-700 min-h-10 ml-auto">取消</button></div>
    <div v-else-if="error" role="alert" class="notice-box bg-rose-50 border-rose-200 text-rose-900">{{ error }}</div>
    <template v-else-if="result">
      <div class="flex flex-wrap gap-2" role="group" aria-label="路线结果类型"><button v-for="tab in tabs" :key="tab.code" type="button" class="result-tab" :class="{'tab-active':activeTab===tab.code}" :aria-pressed="activeTab===tab.code" @click="activeTab=tab.code">{{ tab.name }}<span>{{ tab.count }}</span></button></div>
      <div v-for="kind in visibleKinds" :key="kind.code" class="query-status" :class="{'text-amber-800':result[kind.code].meta.status==='partial','text-rose-800':result[kind.code].meta.status==='upstream_error'}">
        <span>{{ kind.name }}：{{ statusText(result[kind.code]) }}</span><details v-if="groupNotices(result[kind.code]).length"><summary>查询范围与说明</summary><ul class="list-disc pl-5 mt-2 space-y-1"><li v-for="item in groupNotices(result[kind.code])" :key="item">{{ item }}</li></ul></details>
      </div>
      <JourneyPlanCard v-for="(plan,index) in displayedPlans.slice(0,visibleCount)" :key="`${plan.kind}-${plan.id}`" :plan="plan" :rank="index+1" @seat-change="$emit('seat-change',$event)" />
      <button v-if="displayedPlans.length>visibleCount" type="button" class="journey-secondary w-full" @click="visibleCount+=5">再显示 {{ Math.min(5,displayedPlans.length-visibleCount) }} 条方案（已展示 {{ visibleCount }} / {{ displayedPlans.length }}）</button>
      <div v-if="!displayedPlans.length" class="plan-empty">
        <p class="font-semibold text-slate-700">{{ allPlans.length ? '本次未找到这一类方案' : '本次范围内未找到全程有票的接续或中转方案' }}</p>
        <p class="mt-2 text-xs text-slate-500 leading-relaxed">{{ train ? '可以选择另一辆车，或调整席别、中转次数、指定站再查询。' : '可以调整日期、席别或中转条件再查询。' }}查询未完成或失败时，不能据此判断所有路线都无票。</p>
        <button v-if="!allPlans.length && !allowLargeDetour" type="button" @click="$emit('expanded')" class="journey-secondary mt-4">允许较大绕行并重查</button>
      </div>
      <div v-if="!hasFullRoute" class="short-fallback-section">
        <h4 class="font-semibold text-sm text-amber-950">短途有票／后续申请补票</h4><p class="mt-2 text-xs text-slate-600 leading-relaxed">每辆车只展示本次查到的最远可购区间。只确认前段有票，后续能否继续乘坐须由列车工作人员确认；被拒绝时须在原票到站下车。</p>
        <button v-if="result.short_fallback?.meta?.status==='skipped'" type="button" @click="$emit('short-fallback')" class="journey-secondary mt-3">查看短途有票／补票备选</button>
        <template v-else><p class="text-xs mt-3 text-amber-800">{{ result.short_fallback?.meta?.status==='upstream_error'?'备选查询失败':result.short_fallback?.meta?.status==='partial'?'备选查询范围有限或尚未查完':'备选查询完成' }}</p><ul class="mt-2 list-disc pl-5 text-xs text-slate-600 space-y-1"><li v-for="item in groupNotices(result.short_fallback)" :key="item">{{ item }}</li></ul><p v-if="!result.short_fallback?.options?.length" class="text-xs text-slate-500 mt-2">本次未查到有条件备选。</p></template>
      </div>
      <ShortTicketCard v-for="option in result.short_fallback?.options || []" :key="option.id" :option="option" @seat-change="$emit('short-seat-change',$event)" />
    </template>
    <p v-else role="status" class="text-xs text-slate-500">尚未取得方案，点击“重新查询方案”可继续查询。</p>
  </div>
</template>
<script setup>
import {computed,ref,watch} from 'vue'
import {LoaderCircle} from 'lucide-vue-next'
import JourneyPlanCard from './JourneyPlanCard.vue'
import ShortTicketCard from './ShortTicketCard.vue'
import {journeyKinds,groupNotices} from '../lib/journey.js'
import {sortPlans} from '../lib/transfer.js'
const props=defineProps({result:Object,train:Object,loading:Boolean,error:String,sortBy:String,allowLargeDetour:Boolean})
defineEmits(['retry','cancel','seat-change','short-seat-change','expanded','short-fallback'])
const activeTab=ref('same_train')
const visibleCount=ref(5)
const kinds=computed(()=>journeyKinds.filter(k=>!props.train || k.code!=='direct'))
const allPlans=computed(()=>kinds.value.flatMap(k=>props.result?.[k.code]?.plans || []))
const tabs=computed(()=>[...(!props.train?[{code:'all',name:'全部路线',count:allPlans.value.length}]:[]),...kinds.value.map(k=>({...k,count:props.result?.[k.code]?.plans.length || 0}))])
const visibleKinds=computed(()=>kinds.value.filter(k=>activeTab.value==='all'||k.code===activeTab.value))
const displayedPlans=computed(()=>sortPlans(activeTab.value==='all'?allPlans.value:(props.result?.[activeTab.value]?.plans || []),props.sortBy))
const hasFullRoute=computed(()=>journeyKinds.some(k=>props.result?.[k.code]?.plans.length))
watch(()=>props.result,()=>{activeTab.value=!props.train?'all':props.result?.same_train?.plans.length?'same_train':'transfer'},{immediate:true})
watch([activeTab,()=>props.result],()=>{visibleCount.value=5})
function statusText(group){const s=group.meta.status;return s==='upstream_error'?'铁路查询失败，请重试':s==='partial'?`${group.plans.length} 条 · 范围有限或尚未查完`:s==='skipped'?'本次未查询':group.plans.length?`${group.plans.length} 条 · 查询完成`:'本次范围内未查到'}
</script>
