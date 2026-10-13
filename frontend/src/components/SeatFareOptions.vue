<template>
  <fieldset class="seat-fare-options" :aria-label="label">
    <legend class="fare-options-label">{{ displayLabel || label }}<span>{{ seats.length===1 ? '仅 1 种符合条件' : '点击切换席别' }}</span></legend>
    <div class="seat-fare-grid">
      <label v-for="seat in seats" :key="seat.code" class="fare-option" :class="{'fare-option-selected':selectedCode===seat.code}">
        <input type="radio" :name="name" :value="seat.code" :checked="selectedCode===seat.code" :aria-label="`${label} ${seat.name}`" @change="$emit('select',seat.code)" />
        <span class="fare-option-name">{{ seat.name }}</span>
        <strong class="fare-option-price" :class="{'fare-price-unknown':seat.price_fen==null}">{{ formatMoney(seat.price_fen) }}</strong>
        <span class="fare-option-stock">{{ seat.availability==='有' ? '有票' : `${seat.availability} 张` }}</span>
        <span class="fare-option-check">{{ selectedCode===seat.code ? '已选' : '选择' }}</span>
      </label>
    </div>
  </fieldset>
</template>
<script setup>
import {formatMoney} from '../lib/transfer.js'
defineProps({seats:{type:Array,required:true},selectedCode:String,label:String,displayLabel:String,name:String})
defineEmits(['select'])
</script>
