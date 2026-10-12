<template>
  <div class="min-h-screen bg-slate-50 text-slate-800">
    <header class="border-b border-slate-200 bg-white"><div class="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3"><a href="/" class="flex items-center gap-3 text-slate-900 no-underline" aria-label="铁跃路线查询首页"><span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white"><TrainFront class="w-5 h-5" /></span><span class="font-bold">铁跃 <span class="hidden sm:inline text-sm font-medium text-slate-500 ml-1">RailHop</span></span></a><span class="text-xs text-slate-600">城市出行 · 路线查询</span></div></header>
    <main class="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-5"><JourneySearch /></main>
    <footer class="max-w-6xl mx-auto px-4 sm:px-6 pb-8 text-xs text-slate-500 leading-relaxed">铁跃 · 基于铁路公开查询数据规划路线。余票、票价及现场安排以铁路 12306 和车站为准。</footer>
  </div>
</template>
<script setup>
import {TrainFront} from 'lucide-vue-next'
import JourneySearch from './components/JourneySearch.vue'
</script>
