<template>
  <article class="journey-card" data-testid="journey-plan" :data-kind="plan.kind">
    <div class="plan-heading">
      <div><span class="kind-badge" :class="`kind-${plan.kind}`">{{ kindName }}</span><span v-if="rank===1" class="ml-2 text-xs text-slate-500">本次排序首选</span><h3 class="mt-3 text-lg font-bold text-slate-900">{{ plan.legs[0].from_station_name }} <span class="mx-1 text-slate-400">→</span> {{ plan.legs.at(-1).to_station_name }}</h3><p class="mt-1 text-xs text-slate-600">{{ formatDateTime(plan.legs[0].departure_at) }} 出发 · {{ formatDateTime(plan.legs.at(-1).arrival_at) }} 到达</p></div>
      <div class="plan-totals"><div><p class="text-xs text-slate-500">全程含等待</p><p class="mt-1 font-bold">{{ formatJourneyDuration(plan.total_minutes) }}</p></div><div class="text-right"><p class="text-xs text-slate-500">所选席别合计</p><p class="mt-1 text-xl font-bold text-blue-700" data-testid="total-price">{{ formatMoney(fare.totalPriceFen) }}</p><p v-if="fare.totalPriceFen==null" class="text-xs text-amber-800">已知 {{ formatMoney(fare.knownPriceFen) }}</p></div></div>
    </div>
    <div class="p-5 space-y-4">
      <div v-if="plan.route_assessment?.warnings?.length" class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950"><p v-for="warning in plan.route_assessment.warnings" :key="warning">{{ warning }}</p><p class="mt-2">{{ plan.route_assessment.mode==='manual' ? '已按手动指定站查询' : '已按允许较大绕行查询' }} · 请结合经由站和全程含等待时间决定。</p></div>
      <template v-for="(leg,index) in plan.legs" :key="index">
        <div class="plan-leg"><div><p class="text-xs text-slate-500">第 {{ index+1 }} 段</p><p class="mt-1 font-bold text-blue-700">{{ leg.train_code }}</p></div><div class="flex items-start gap-3 text-sm min-w-0"><div class="flex-1"><p class="font-semibold">{{ leg.from_station_name }}</p><p class="mt-1 text-xs text-slate-600">{{ formatDateTime(leg.departure_at) }}</p></div><ArrowRight class="mt-1 w-4 h-4 shrink-0 text-slate-400" /><div class="flex-1"><p class="font-semibold">{{ leg.to_station_name }}</p><p class="mt-1 text-xs text-slate-600">{{ formatDateTime(leg.arrival_at) }}</p></div></div><label class="text-xs font-medium text-slate-600">本段席别<select :value="plan.selected_seat_codes[index]" :aria-label="`第${index+1}段席别`" class="journey-input mt-1" @change="$emit('seat-change',{id:plan.id,kind:plan.kind,index,code:$event.target.value})"><option v-for="seat in leg.seats" :key="seat.code" :value="seat.code">{{ seat.name }} · {{ seat.availability }} · {{ formatMoney(seat.price_fen) }}</option></select></label></div>
        <div v-if="plan.connections[index]" class="rounded-xl border border-indigo-100 bg-indigo-50/60 p-3 text-xs text-indigo-900"><p class="font-semibold">{{ plan.connections[index].station.station_name }} · 同站换车 · 等待 {{ plan.connections[index].wait_minutes }} 分钟</p><p class="mt-1">满足本次至少 {{ plan.connections[index].required_minutes }} 分钟；{{ plan.connections[index].official_min_minutes!=null ? `12306 本站参考 ${plan.connections[index].official_min_minutes} 分钟` : '无适用官方数据，基础参考 15 分钟' }}。</p><details class="mt-2"><summary class="cursor-pointer py-1">换乘资料及适用条件</summary><p class="mt-2 leading-relaxed">{{ plan.connections[index].station.applicable_conditions }}</p><p class="mt-1">资料发布 {{ plan.connections[index].station.source_published_at }} · 核验 {{ plan.connections[index].station.verified_at }}</p><a :href="plan.connections[index].source_url" target="_blank" rel="noopener noreferrer" class="inline-block mt-2 underline">便捷换乘资料来源</a><p v-if="plan.connections[index].station.reference_time_source_url" class="mt-2"><a :href="plan.connections[index].station.reference_time_source_url" target="_blank" rel="noopener noreferrer" class="underline">12306 时间参考来源</a> · 采集 {{ plan.connections[index].station.reference_time_checked_at }}</p></details></div>
        <div v-else-if="plan.kind==='same_train' && index<plan.legs.length-1" class="rounded-lg bg-teal-50 border border-teal-100 px-3 py-2 text-xs text-teal-900">{{ leg.to_station_name }} · 同一列车接续，按下一段票面席位调整</div>
      </template>
      <p v-if="plan.kind==='same_train'" class="text-xs text-slate-600 leading-relaxed">{{ sameTrainReminder }}</p>
    </div>
    <div class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-5 py-3 text-xs text-slate-500"><span>余票快照 {{ formatDateTime(plan.legs[0].queried_at) }} · 时刻不含晚点预测</span><button type="button" @click="copy" class="min-h-9 font-semibold text-blue-700 cursor-pointer">{{ copied ? '已复制路线' : '复制完整路线' }}</button></div><p v-if="copyError" role="alert" class="px-5 pb-3 text-xs text-amber-800">{{ copyError }}</p>
  </article>
</template>
<script setup>
import {computed,ref} from 'vue'
import {ArrowRight} from 'lucide-vue-next'
import {calculateFare,formatMoney,formatDateTime} from '../lib/transfer.js'
import {journeyKinds,formatJourneyDuration,buildJourneyText,sameTrainReminder} from '../lib/journey.js'
const props=defineProps({plan:{type:Object,required:true},rank:Number})
defineEmits(['seat-change'])
const fare=computed(()=>calculateFare(props.plan.legs,props.plan.selected_seat_codes))
const kindName=computed(()=>journeyKinds.find(k=>k.code===props.plan.kind)?.name)
const copied=ref(false),copyError=ref('')
async function copy(){try{await navigator.clipboard.writeText(buildJourneyText(props.plan));copied.value=true;copyError.value=''}catch{copyError.value='复制失败，请手动记录路线。'}}
</script>
