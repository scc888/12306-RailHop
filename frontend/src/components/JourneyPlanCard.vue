<template>
  <article class="journey-card" data-testid="journey-plan" :data-kind="plan.kind">
    <div class="plan-heading">
      <div>
        <span class="kind-badge" :class="`kind-${plan.kind}`">{{ kindName }}</span><span v-if="rank===1 && sortBy==='duration'" class="ml-2 text-xs text-slate-500">本次已查范围内最快</span>
        <h3 class="mt-3 text-lg font-bold text-slate-900">{{ plan.legs[0].from_station_name }} <span class="mx-1 text-slate-400">→</span> {{ plan.legs.at(-1).to_station_name }}</h3>
        <p class="mt-1 text-xs text-slate-600">{{ formatDateTime(plan.legs[0].departure_at) }} 出发 · {{ formatDateTime(plan.legs.at(-1).arrival_at) }} 到达</p>
      </div>
      <div class="plan-totals">
        <div><p class="text-xs text-slate-500">全程含等待</p><p class="mt-1 font-bold">{{ formatJourneyDuration(plan.total_minutes) }}</p></div>
        <div class="text-right"><p class="text-xs text-slate-500">所选席别合计</p><p class="mt-1 text-xl font-bold text-blue-700" data-testid="total-price">{{ formatMoney(fare.totalPriceFen) }}</p><p v-if="fare.totalPriceFen==null" class="text-xs text-amber-800">已知 {{ formatMoney(fare.knownPriceFen) }}</p></div>
      </div>
    </div>
    <div class="plan-trip-summary">
      <TrainFront class="w-4 h-4 shrink-0" aria-hidden="true" /><p>{{ tripSummary }}</p>
      <button v-if="collapsible" type="button" class="plan-details-toggle" :aria-expanded="expanded" :aria-controls="detailsId" @click="expanded=!expanded">
        {{ expanded ? '收起详情' : '展开详情' }}<ChevronDown class="w-4 h-4" :class="{'rotate-180':expanded}" aria-hidden="true" />
      </button>
    </div>
    <div class="px-5 pb-3 text-xs text-slate-600 space-y-1" data-testid="compact-facts">
      <p class="font-semibold">{{ compact.route }}</p>
      <p v-if="compact.wait">{{ compact.wait }}</p><p>{{ compact.seats }}</p>
      <p v-if="compact.notes.length" class="text-amber-800">{{ compact.notes.join(' · ') }}</p>
      <p v-if="baseline && baseline.id!==plan.id">比最快中转多 {{ plan.total_minutes-baseline.total_minutes }} 分钟 · 等待{{ waitDifference>=0 ? '多' : '少' }} {{ Math.abs(waitDifference) }} 分钟</p>
    </div>
    <div :id="detailsId" v-show="!collapsible || expanded">
    <div class="plan-itinerary">
      <div v-if="plan.route_assessment?.warnings?.length" class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950 mb-4"><p v-for="warning in plan.route_assessment.warnings" :key="warning">{{ warning }}</p><p class="mt-2">{{ plan.route_assessment.mode==='manual' ? '已按手动指定站查询' : '已按允许较大绕行查询' }} · 请结合经由站和全程含等待时间决定。</p></div>
      <ol class="journey-legs">
        <li v-for="(leg,index) in plan.legs" :key="index">
          <section class="fare-leg-section" data-testid="journey-leg" :aria-label="`第${index+1}段 ${leg.from_station_name}到${leg.to_station_name}`">
            <div class="leg-route-heading"><span class="leg-step">第 {{ index+1 }} 段</span><h4>{{ leg.from_station_name }} → {{ leg.to_station_name }}</h4></div>
            <p class="leg-train-meta"><strong>{{ leg.train_code }}</strong><span>乘车 {{ legDuration(leg) }}</span></p>
            <div class="leg-schedule">
              <div class="leg-moment">
                <span class="leg-moment-label">{{ leg.from_station_name }} · {{ index>0 && plan.kind==='same_train' ? '接续出发' : '上车出发' }}</span>
                <div><span v-if="dayLabel(leg.departure_at)" class="leg-day-label">{{ dayLabel(leg.departure_at) }}</span><time :datetime="leg.departure_at">{{ leg.departure_at.slice(11,16) }}</time></div>
                <span class="leg-date">{{ leg.departure_at.slice(0,10) }}</span>
              </div>
              <ArrowRight class="leg-time-arrow" aria-hidden="true" />
              <div class="leg-moment">
                <span class="leg-moment-label">{{ leg.to_station_name }} · {{ index===plan.legs.length-1 ? '到达终点' : plan.kind==='same_train' ? '接续到站' : '下车换乘' }}</span>
                <div><span v-if="dayLabel(leg.arrival_at)" class="leg-day-label">{{ dayLabel(leg.arrival_at) }}</span><time :datetime="leg.arrival_at">{{ leg.arrival_at.slice(11,16) }}</time></div>
                <span class="leg-date">{{ leg.arrival_at.slice(0,10) }}</span>
              </div>
            </div>
            <SeatFareOptions :seats="leg.seats" :selected-code="plan.selected_seat_codes[index]" :label="`第${index+1}段席别`" display-label="选择本段席别" :name="`${plan.kind}-${plan.id}-${index}`" @select="$emit('seat-change',{id:plan.id,kind:plan.kind,index,code:$event})" />
          </section>
          <div v-if="plan.connections[index]" class="journey-connection connection-transfer" data-testid="journey-connection">
            <div class="connection-title"><ArrowLeftRight class="w-4 h-4 shrink-0" aria-hidden="true" /><strong>{{ plan.connections[index].station.station_name }} · 同站换车 · 等待 {{ plan.connections[index].wait_minutes }} 分钟</strong></div>
            <p class="connection-action">{{ leg.train_code }} → {{ plan.legs[index+1].train_code }}<span>在本站下车，换乘下一趟列车</span></p>
            <p class="connection-note">满足本次至少 {{ plan.connections[index].required_minutes }} 分钟；{{ plan.connections[index].official_min_minutes!=null ? `12306 本站参考 ${plan.connections[index].official_min_minutes} 分钟` : `无适用官方时间，默认参考 ${plan.connections[index].station.convenient_transfer_confirmed ? 15 : 60} 分钟` }}。</p>
            <p v-if="!plan.connections[index].station.convenient_transfer_confirmed" class="connection-note font-semibold">便捷换乘状态未核实，可能需要出站重新安检进站；请核对通道开放时段和检票截止时间。</p>
            <details class="connection-sources"><summary>换乘资料及适用条件</summary><p class="mt-2 leading-relaxed">{{ plan.connections[index].station.applicable_conditions }}</p><p v-if="plan.connections[index].station.verified_at" class="mt-1">资料发布 {{ plan.connections[index].station.source_published_at }} · 核验 {{ plan.connections[index].station.verified_at }}</p><a v-if="plan.connections[index].source_url" :href="plan.connections[index].source_url" target="_blank" rel="noopener noreferrer" class="inline-block mt-2 underline">便捷换乘资料来源</a><p v-if="plan.connections[index].station.reference_time_source_url" class="mt-2"><a :href="plan.connections[index].station.reference_time_source_url" target="_blank" rel="noopener noreferrer" class="underline">12306 时间参考来源</a> · 采集 {{ plan.connections[index].station.reference_time_checked_at }}</p></details>
          </div>
          <div v-else-if="plan.kind==='same_train' && index<plan.legs.length-1" class="journey-connection connection-same" data-testid="journey-connection">
            <div class="connection-title"><Route class="w-4 h-4 shrink-0" aria-hidden="true" /><strong>{{ leg.to_station_name }} · 同一列车接续</strong></div>
            <p class="connection-action">{{ selectedSeat(index)?.name || '席别待确认' }} → {{ selectedSeat(index+1)?.name || '席别待确认' }}<span>继续乘坐 {{ plan.legs[index+1].train_code }}</span></p>
            <p class="connection-note">{{ plan.selected_seat_codes[index]===plan.selected_seat_codes[index+1] ? '同席别接续，座位或铺位仍可能变化，请按各段票面调整。' : '到站接续时，请按下一段票面调整座位或铺位。' }}</p>
          </div>
        </li>
      </ol>
      <div class="plan-fare-summary" aria-live="polite" aria-atomic="true" data-testid="fare-summary">
        <div><p>已选 {{ plan.legs.length }} 段票价</p><p class="fare-addends">{{ plan.legs.map((_,index)=>formatMoney(selectedSeat(index)?.price_fen)).join(' + ') }}</p></div>
        <div class="text-right"><p>合计 <strong>{{ formatMoney(fare.totalPriceFen) }}</strong></p><p v-if="fare.totalPriceFen==null" class="mt-1">已知部分 {{ formatMoney(fare.knownPriceFen) }}</p></div>
      </div>
      <p v-if="plan.kind==='same_train'" class="fare-scope-note mt-3">{{ sameTrainReminder }}</p>
      <p class="fare-scope-note mt-2">各段列出本次可接受且有票的席别；可在“席别与中转设置”中调整范围。</p>
    </div>
    <div class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-5 py-3 text-xs text-slate-500"><span>余票快照 {{ formatDateTime(plan.legs[0].queried_at) }} · 时刻不含晚点预测</span><button type="button" @click="copy" class="min-h-9 font-semibold text-blue-700 cursor-pointer">{{ copied ? '已复制路线' : '复制完整路线' }}</button></div><p v-if="copyError" role="alert" class="px-5 pb-3 text-xs text-amber-800">{{ copyError }}</p>
    </div>
  </article>
</template>
<script setup>
import {computed,ref,watch,useId} from 'vue'
import {ArrowRight,ArrowLeftRight,Route,TrainFront,ChevronDown} from 'lucide-vue-next'
import SeatFareOptions from './SeatFareOptions.vue'
import {calculateFare,formatMoney,formatDateTime} from '../lib/transfer.js'
import {journeyKinds,formatJourneyDuration,buildJourneyText,sameTrainReminder,journeyDayLabel,compactJourneyFacts} from '../lib/journey.js'
const props=defineProps({plan:{type:Object,required:true},rank:Number,sortBy:String,baseline:Object,expanded:Boolean})
const emit=defineEmits(['seat-change','update:expanded'])
const detailsId=useId()
const expanded=computed({get:()=>props.expanded,set:value=>emit('update:expanded',value)})
const collapsible=computed(()=>props.plan.kind==='same_train' || props.plan.kind==='transfer')
const compact=computed(()=>compactJourneyFacts(props.plan))
const waitDifference=computed(()=>(props.plan.connections || []).reduce((n,c)=>n+c.wait_minutes,0)-(props.baseline?.connections || []).reduce((n,c)=>n+c.wait_minutes,0))
const fare=computed(()=>calculateFare(props.plan.legs,props.plan.selected_seat_codes))
const kindName=computed(()=>journeyKinds.find(k=>k.code===props.plan.kind)?.name)
const tripSummary=computed(()=>props.plan.kind==='same_train' ? `全程乘坐 ${props.plan.legs[0].train_code} · 分 ${props.plan.legs.length} 段接续` : props.plan.kind==='transfer' ? `同站换车 ${props.plan.connections.length} 次 · 共 ${props.plan.legs.length} 段行程` : `乘坐 ${props.plan.legs[0].train_code} 直达`)
const copied=ref(false),copyError=ref('')
function selectedSeat(index){return props.plan.legs[index]?.seats.find(seat=>seat.code===props.plan.selected_seat_codes[index])}
function dayLabel(value){return journeyDayLabel(value,props.plan.legs[0].departure_at)}
function legDuration(leg){return formatJourneyDuration(Math.round((Date.parse(leg.arrival_at)-Date.parse(leg.departure_at))/60000))}
watch(()=>props.plan.selected_seat_codes.join(','),()=>{copied.value=false;copyError.value=''})
async function copy(){try{await navigator.clipboard.writeText(buildJourneyText(props.plan));copied.value=true;copyError.value=''}catch{copyError.value='复制失败，请手动记录路线。'}}
</script>
