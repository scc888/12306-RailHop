<template>
  <div class="app-frame bg-slate-50 text-slate-800">
    <header class="app-header border-b border-slate-200 bg-white">
      <div class="app-shell px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
        <a href="/" class="flex items-center gap-3 text-slate-900 no-underline" aria-label="铁跃路线查询首页">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white"><TrainFront class="w-5 h-5" /></span>
          <span class="font-bold text-base">铁跃 <span class="hidden sm:inline text-sm font-medium text-slate-500 ml-1">RailHop</span></span>
        </a>
        <span class="text-xs text-slate-500">查车次 · 找中转</span>
      </div>
    </header>
    <main class="app-main app-shell px-4 sm:px-6"><JourneySearch /></main>
    <footer class="app-footer app-shell px-4 sm:px-6 text-xs text-slate-500 leading-relaxed">余票、票价及乘车安排以铁路 12306 和车站为准。</footer>
  </div>
</template>
<script setup>
import {TrainFront} from 'lucide-vue-next'
import JourneySearch from './components/JourneySearch.vue'
</script>
