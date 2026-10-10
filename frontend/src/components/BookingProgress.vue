<template>
  <div class="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4" @click.self="$emit('close')">
    <section class="bg-white rounded-2xl shadow-xl max-w-2xl w-full p-5 max-h-[90vh] overflow-auto" role="dialog" aria-modal="true" aria-label="方案购票进度">
      <div class="flex justify-between items-center mb-4">
        <h2 class="font-bold text-slate-900">{{ task.train_code }} · 方案购票进度</h2>
        <button class="text-slate-500 px-2 py-1" @click="$emit('close')" aria-label="关闭进度窗口">✕</button>
      </div>
      <p class="text-sm mb-4">{{ task.title }}</p>
      <ol class="space-y-3">
        <li v-for="(step, index) in task.steps" :key="index" class="border rounded-xl p-3" :class="index === task.current_step ? 'border-blue-400 bg-blue-50' : 'border-slate-200'">
          <div class="flex justify-between gap-2 text-sm font-semibold">
            <span>{{ index + 1 }}. {{ step.segment.from_station }} → {{ step.segment.to_station }}</span>
            <span>{{ step.kind === 'WAITLIST' ? '候补' : '购票' }}</span>
          </div>
          <p class="text-xs text-slate-600 mt-1">{{ step.segment.train_date }} {{ step.segment.start_time }} · {{ step.segment.seat_name }}</p>
          <p class="text-xs mt-2">{{ labels[step.status] || step.status }}<span v-if="step.order_id"> · 订单号 {{ step.order_id }}</span></p>
        </li>
      </ol>
      <p class="text-sm mt-4 p-3 rounded-xl bg-amber-50 text-amber-900" role="status">{{ task.message }}</p>
      <p v-if="error" class="text-sm text-red-700 mt-3" role="alert">{{ error }}</p>
      <p class="text-xs text-slate-500 my-3">官方页面可能需要再次扫码登录。候补付款后才生效，付款不代表候补已兑现。关闭窗口会保留本次进度。</p>
      <div class="flex flex-wrap gap-2">
        <button v-if="current?.order_id && ['WAITING_PAYMENT', 'UNKNOWN'].includes(task.status)" :disabled="busy" @click="$emit('pay', current)" class="rounded-xl bg-blue-600 text-white text-sm px-4 py-2 disabled:opacity-50">前往12306付款</button>
        <button v-if="task.status === 'ACTION_REQUIRED'" @click="openOfficial" class="rounded-xl bg-blue-600 text-white text-sm px-4 py-2">前往12306完成候补</button>
        <button v-if="task.status === 'READY'" :disabled="busy" @click="$emit('advance')" class="rounded-xl bg-blue-600 text-white text-sm px-4 py-2 disabled:opacity-50">继续当前段</button>
        <button v-if="task.status === 'FAIL'" :disabled="busy" @click="$emit('retry')" class="rounded-xl bg-blue-600 text-white text-sm px-4 py-2 disabled:opacity-50">重试失败的当前段</button>
        <button :disabled="busy" @click="$emit('refresh')" class="rounded-xl border border-slate-300 text-sm px-4 py-2 disabled:opacity-50">刷新官方状态</button>
        <button v-if="!['COMPLETED', 'STOPPED'].includes(task.status)" :disabled="busy" @click="$emit('stop')" class="rounded-xl border border-slate-300 text-sm px-4 py-2 disabled:opacity-50">停止后续购票</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ task: { type: Object, required: true }, busy: Boolean, error: String })
defineEmits(['close', 'pay', 'advance', 'refresh', 'stop', 'retry'])
const current = computed(() => props.task.steps[props.task.current_step])
const labels = { READY: '尚未下单', WAITING_PAYMENT: '订单已创建，等待付款', PAID: '已确认支付', UNKNOWN: '结果待确认，禁止重复下单', FAIL: '提交失败', ACTION_REQUIRED: '需要官方身份核验', STOPPED: '已停止' }
function openOfficial() {
  window.open('https://kyfw.12306.cn/otn/leftTicket/init', '_blank', 'noopener,noreferrer')
}
</script>
