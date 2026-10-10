<template>
  <article class="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden" data-testid="transfer-plan">
    <div class="flex flex-wrap justify-between items-center gap-4 p-5 border-b border-slate-100 bg-slate-50/60">
      <div>
        <div class="flex items-center gap-2 text-xs text-indigo-700 font-semibold mb-2"><span class="rounded-full bg-indigo-50 px-2 py-1">同站换乘 {{ plan.connections.length }} 次</span><span v-if="rank === 1" class="text-slate-500">当前排序首选</span></div>
        <h3 class="font-bold text-lg">{{ plan.legs[0].from_station_name }} <span class="text-slate-400 mx-1">→</span> {{ plan.legs.at(-1).to_station_name }}</h3>
        <p class="text-xs text-slate-500 mt-1">{{ formatDateTime(plan.legs[0].departure_at) }} 出发 · {{ formatDateTime(plan.legs.at(-1).arrival_at) }} 到达</p>
      </div>
      <div class="flex gap-7 items-center">
        <div><p class="text-xs text-slate-500">全程含等待</p><p class="font-bold text-lg mt-1">{{ formatDuration(plan.total_minutes) }}</p></div>
        <div class="text-right"><p class="text-xs text-slate-500">所选席别合计</p><p class="font-bold text-lg text-blue-700 mt-1" data-testid="total-price">{{ formatMoney(fare.totalPriceFen) }}</p><p v-if="fare.totalPriceFen == null" class="text-xs text-amber-700">已知 {{ formatMoney(fare.knownPriceFen) }}</p></div>
      </div>
    </div>
    <div class="p-5 space-y-4">
      <template v-for="(leg, index) in plan.legs" :key="index">
        <div class="grid grid-cols-1 sm:grid-cols-[80px_1fr_1fr] gap-3 items-center">
          <div><span class="text-xs text-slate-400">第 {{ index + 1 }} 段</span><p class="font-bold text-blue-700">{{ leg.train_code }}</p></div>
          <div class="flex items-center gap-3 text-sm"><div><p class="font-semibold">{{ leg.from_station_name }}</p><p class="text-xs text-slate-500 mt-1">{{ formatDateTime(leg.departure_at) }}</p></div><span class="text-slate-300">→</span><div><p class="font-semibold">{{ leg.to_station_name }}</p><p class="text-xs text-slate-500 mt-1">{{ formatDateTime(leg.arrival_at) }}</p></div></div>
          <label class="block text-xs text-slate-500">本段席别
            <select :value="plan.selected_seat_codes[index]" @change="$emit('seat-change', {planId:plan.id,legIndex:index,seatCode:$event.target.value})" :aria-label="`第${index + 1}段席别`" class="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800">
              <option v-for="seat in leg.seats" :key="seat.code" :value="seat.code">{{ seat.name }} · {{ seat.availability }} · {{ formatMoney(seat.price_fen) }}</option>
            </select>
          </label>
        </div>
        <div v-if="plan.connections[index]" class="rounded-xl bg-indigo-50/70 border border-indigo-100 px-4 py-3 text-xs text-indigo-800">
          <p class="font-semibold">{{ plan.connections[index].station.station_name }} · 站内便捷换乘 · 等待 {{ plan.connections[index].wait_minutes }} 分钟</p>
          <p class="mt-1 opacity-80">满足本次至少 {{ plan.connections[index].required_minutes }} 分钟的条件，请按站内指引换乘。</p>
          <details class="mt-2"><summary class="cursor-pointer">便捷换乘资料</summary><p class="mt-2">{{ plan.connections[index].station.applicable_conditions }}</p><p class="mt-1">资料发布 {{ plan.connections[index].station.source_published_at }} · 资料核验 {{ plan.connections[index].station.verified_at }}</p><a :href="plan.connections[index].source_url" target="_blank" rel="noopener noreferrer" class="underline inline-block mt-1">查看车站资料来源</a></details>
        </div>
      </template>
    </div>
    <div class="px-5 py-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
      <span>余票采集 {{ formatDateTime(plan.legs[0].queried_at) }} · 计划时刻不含晚点预测</span>
      <button type="button" @click="copy" class="font-semibold text-blue-700 hover:underline cursor-pointer">{{ copied ? '已复制' : '复制完整路线' }}</button>
    </div>
    <p v-if="copyError" role="alert" class="px-5 pb-3 text-xs text-amber-700">{{ copyError }}</p>
  </article>
</template>

<script setup>
import { computed, ref } from 'vue'
import { calculateFare, formatMoney, formatDuration, formatDateTime, buildTransferText } from '../lib/transfer.js'
const props = defineProps({ plan: {type:Object,required:true}, rank:Number })
defineEmits(['seat-change'])
const fare = computed(() => calculateFare(props.plan.legs, props.plan.selected_seat_codes))
const copied = ref(false)
const copyError = ref('')
async function copy() {
  try { await navigator.clipboard.writeText(buildTransferText(props.plan)); copied.value = true; copyError.value = '' }
  catch { copyError.value = '复制失败，请手动记录路线。' }
}
</script>
