<template>
  <article class="journey-card border-amber-200 p-5" data-testid="short-ticket-option">
    <div class="flex flex-wrap justify-between gap-3"><div><span class="kind-badge bg-amber-100 text-amber-900">有条件备选 · 后续未确认</span><h3 class="mt-3 font-bold text-lg">{{ leg.train_code }} · {{ leg.from_station_name }} → {{ option.destination_station_name }}</h3></div><div class="text-right text-sm"><p class="font-semibold text-amber-900">全程总价待确认</p><p class="text-slate-500 mt-1">前段 {{ formatMoney(seat?.price_fen) }}</p></div></div>
    <div class="mt-4 rounded-xl bg-slate-50 border border-slate-200 p-4"><p class="font-semibold text-sm">已查到有票：{{ leg.from_station_name }} → {{ leg.to_station_name }}</p><p class="text-xs text-slate-600 mt-2">{{ formatDateTime(leg.departure_at) }} → {{ formatDateTime(leg.arrival_at) }}</p><label class="journey-label mt-3">前段席别<select :value="option.selected_seat_code" @change="$emit('seat-change',{id:option.id,code:$event.target.value})" class="journey-input"><option v-for="s in leg.seats" :key="s.code" :value="s.code">{{ s.name }} · {{ s.availability }} · {{ formatMoney(s.price_fen) }}</option></select></label></div>
    <div class="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><p class="font-semibold">原票到站：{{ leg.to_station_name }}</p><p class="mt-2">后续需申请补票：{{ leg.to_station_name }} → {{ option.destination_station_name }}</p><p class="mt-1 text-xs">同一列车计划到达 {{ formatDateTime(option.scheduled_arrival_at) }}；是否能继续乘坐、后续席位和补票金额均未确认。</p><p class="mt-3 leading-relaxed">{{ option.conditions }}</p></div>
    <div class="mt-4 flex flex-wrap justify-between gap-2 text-xs text-slate-500"><a :href="option.source_url" target="_blank" rel="noopener noreferrer" class="underline text-blue-700 min-h-9 flex items-center">12306 越站补票规则</a><button type="button" @click="copy" class="text-blue-700 font-semibold min-h-9">{{ copied ? '已复制备选及条件' : '复制备选及条件' }}</button></div><p v-if="copyError" role="alert" class="mt-2 text-xs text-amber-800">{{ copyError }}</p>
  </article>
</template>
<script setup>
import {computed,ref} from 'vue'
import {formatMoney,formatDateTime} from '../lib/transfer.js'
import {buildShortTicketText} from '../lib/journey.js'
const props=defineProps({option:{type:Object,required:true}})
defineEmits(['seat-change'])
const leg=computed(()=>props.option.ticketed_leg)
const seat=computed(()=>leg.value.seats.find(s=>s.code===props.option.selected_seat_code))
const copied=ref(false),copyError=ref('')
async function copy(){try{await navigator.clipboard.writeText(buildShortTicketText(props.option));copied.value=true;copyError.value=''}catch{copyError.value='复制失败，请手动记录路线和条件。'}}
</script>
