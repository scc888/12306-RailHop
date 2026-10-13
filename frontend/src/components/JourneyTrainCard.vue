<template>
  <article class="train-card" :class="{'train-card-open':expanded}" data-testid="train-row" :data-train="train.train_code">
    <div class="train-row-main">
      <div class="train-code-cell">
        <button type="button" class="train-code" :disabled="!train.selection" :aria-label="`查看 ${train.train_code} 的接续中转方案`" :aria-expanded="expanded" :aria-controls="`plans-${train.id}`" @click="$emit('toggle')">{{ train.train_code }}</button>
        <span class="train-type">{{ /^[GDC]/i.test(train.train_code) ? '高铁 / 动车' : '普速列车' }}</span>
      </div>
      <div class="train-times">
        <div><strong>{{ train.start_time }}</strong><span>{{ train.from_station_name }}</span></div>
        <div class="train-duration"><span>{{ duration }}</span><span class="train-track" aria-hidden="true"></span><small v-if="arrivalDay">{{ arrivalDay }}到达</small><small v-else>{{ train.arrival_at ? '当日到达' : '日期待核验' }}</small></div>
        <div><strong>{{ train.arrive_time }}</strong><span>{{ train.to_station_name }}</span></div>
      </div>
      <div class="train-seats" aria-label="直达区间席别余票">
        <div v-for="seat in visibleSeats" :key="seat.code" class="train-seat" :class="{'seat-available':seat.available}">
          <span>{{ seat.name }}</span><strong class="train-seat-price">{{ seat.price }}</strong><small>{{ seat.availability }}</small>
        </div>
      </div>
      <div class="train-action">
        <span class="train-availability" :class="{'text-emerald-700':available}">{{ seatQuery.fallback ? (available ? '默认席别有票' : '默认席别无现票') : (available ? '所选席别有票' : '所选席别无现票') }}</span>
        <button type="button" class="train-plan-button" :disabled="!train.selection" :aria-expanded="expanded" :aria-controls="`plans-${train.id}`" @click="$emit('toggle')">{{ !train.selection ? '时刻待核验' : expanded ? '收起方案' : '接续 / 中转' }}<ChevronDown v-if="train.selection" class="w-4 h-4" :class="{'rotate-180':expanded}" /></button>
      </div>
    </div>
    <p v-if="!train.selection" class="px-5 pb-3 text-xs text-amber-800">运行日期或时刻尚未核验，暂不能查询这辆车的接续方案。</p>
    <div v-if="expanded" :id="`plans-${train.id}`" class="train-expanded" role="region" :aria-label="`${train.train_code} 的接续中转方案`"><p v-if="seatQuery.fallback" role="status" class="mb-4 text-sm text-blue-800">该车未提供所选席别，本次按默认席别查询；本车适用：{{ fallbackSeatNames }}。席别偏好仍保留原设置。</p><slot /></div>
  </article>
</template>
<script setup>
import {computed} from 'vue'
import {ChevronDown} from 'lucide-vue-next'
import {trainSeatQuotes,trainSeatQuery} from '../lib/fares.js'
import {seatOptions} from '../lib/transfer.js'
import {trainHasSeats,trainArrivalDay} from '../lib/journey.js'
const props=defineProps({train:{type:Object,required:true},allowedSeats:{type:Array,required:true},expanded:Boolean})
defineEmits(['toggle'])
const seatQuery=computed(()=>trainSeatQuery(props.train,props.allowedSeats))
const available=computed(()=>trainHasSeats(props.train,seatQuery.value.allowedSeats))
const fallbackSeatNames=computed(()=>seatOptions.filter(seat=>seatQuery.value.applicableSeats.includes(seat.code)).map(seat=>seat.name).join(' / '))
const duration=computed(()=>{if(!/^\d+:[0-5]\d$/.test(props.train.duration))return '历时待核验';const [h,m]=props.train.duration.split(':').map(Number);return `${h}小时${m ? `${m}分` : ''}`})
const arrivalDay=computed(()=>trainArrivalDay(props.train))
const visibleSeats=computed(()=>trainSeatQuotes(props.train))
</script>
