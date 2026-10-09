<template>
  <div class="min-h-screen bg-slate-50 text-slate-800 pb-16">
    <!-- 顶部轻量提示 Toast -->
    <transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform -translate-y-4 opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform -translate-y-4 opacity-0"
    >
      <div
        v-if="toast.show"
        class="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 rounded-xl shadow-lg border text-xs font-medium flex items-center space-x-2"
        :class="toast.type === 'error' ? 'bg-red-50 text-red-800 border-red-200' : (toast.type === 'success' ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-slate-800 text-white border-slate-700')"
      >
        <AlertTriangle v-if="toast.type === 'error'" class="w-4 h-4 text-red-500 shrink-0" />
        <CheckCircle2 v-else-if="toast.type === 'success'" class="w-4 h-4 text-emerald-500 shrink-0" />
        <Info v-else class="w-4 h-4 text-blue-400 shrink-0" />
        <span>{{ toast.message }}</span>
      </div>
    </transition>

    <!-- 顶部导航条 -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
      <div class="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
        <div class="flex items-center space-x-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
            <Train class="w-5 h-5" />
          </div>
          <div>
            <div class="flex items-center space-x-2">
              <h1 class="text-lg font-bold bg-gradient-to-r from-blue-700 to-indigo-700 bg-clip-text text-transparent">
                12306-RailHop
              </h1>
              <span class="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-bold">铁跃 · V1.0</span>
            </div>
            <p class="text-xs text-slate-500 hidden sm:block">节假日直达无票救星：车内接续换座、买短补长与跨站智能规划</p>
          </div>
        </div>

        <div class="flex items-center space-x-2">
          <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5 animate-pulse"></span>
            12306 免认证直连已就绪
          </span>
        </div>
      </div>
    </header>

    <main class="max-w-6xl mx-auto px-4 pt-6 space-y-6">
      <!-- 查询输入卡片 -->
      <section class="bg-white rounded-2xl p-5 shadow-xs border border-slate-200/80">
        <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <!-- 出发站 -->
          <div class="md:col-span-3 relative station-picker">
            <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">出发地</label>
            <div class="relative">
              <input
                v-model="fromStation"
                type="text"
                placeholder="汉字 / 拼音 (如: 上海)"
                class="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-300 rounded-xl text-sm font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                @focus="handleStationFocus('from')"
                @input="handleStationInput('from')"
                @keydown.enter="doQueryTickets"
              />
              <MapPin class="w-4 h-4 text-slate-400 absolute right-3 top-3 pointer-events-none" />
            </div>

            <!-- 出发站联想下拉 -->
            <div
              v-if="activeDropdown === 'from' && stationSuggestions.length > 0"
              class="absolute z-20 top-full left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-xl shadow-lg max-h-56 overflow-y-auto py-1"
            >
              <button
                v-for="st in stationSuggestions"
                :key="st.telecode"
                type="button"
                class="w-full px-3.5 py-2 text-left text-sm hover:bg-blue-50 flex items-center justify-between transition-colors cursor-pointer"
                @click="selectStation('from', st)"
              >
                <span class="font-medium text-slate-800">{{ st.name }}</span>
                <span class="text-xs text-slate-400 font-mono">{{ st.pinyin }}</span>
              </button>
            </div>
          </div>

          <!-- 车站互换按钮 -->
          <div class="md:col-span-1 flex justify-center py-1 md:py-0">
            <button
              type="button"
              @click="swapStations"
              class="w-9 h-9 rounded-xl bg-slate-100 hover:bg-blue-50 text-slate-500 hover:text-blue-600 flex items-center justify-center transition-all border border-slate-200 hover:border-blue-300 active:scale-95 cursor-pointer"
              title="互换出发站与到达站"
            >
              <ArrowLeftRight class="w-4 h-4" />
            </button>
          </div>

          <!-- 到达站 -->
          <div class="md:col-span-3 relative station-picker">
            <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">目的地</label>
            <div class="relative">
              <input
                v-model="toStation"
                type="text"
                placeholder="汉字 / 拼音 (如: 北京)"
                class="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-300 rounded-xl text-sm font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                @focus="handleStationFocus('to')"
                @input="handleStationInput('to')"
                @keydown.enter="doQueryTickets"
              />
              <MapPin class="w-4 h-4 text-slate-400 absolute right-3 top-3 pointer-events-none" />
            </div>

            <!-- 到达站联想下拉 -->
            <div
              v-if="activeDropdown === 'to' && stationSuggestions.length > 0"
              class="absolute z-20 top-full left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-xl shadow-lg max-h-56 overflow-y-auto py-1"
            >
              <button
                v-for="st in stationSuggestions"
                :key="st.telecode"
                type="button"
                class="w-full px-3.5 py-2 text-left text-sm hover:bg-blue-50 flex items-center justify-between transition-colors cursor-pointer"
                @click="selectStation('to', st)"
              >
                <span class="font-medium text-slate-800">{{ st.name }}</span>
                <span class="text-xs text-slate-400 font-mono">{{ st.pinyin }}</span>
              </button>
            </div>
          </div>

          <!-- 出发日期 -->
          <div class="md:col-span-3">
            <div class="flex items-center justify-between mb-1.5">
              <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider">出发日期</label>
              <div class="space-x-1.5">
                <button
                  type="button"
                  @click="setDateOffset(0)"
                  class="text-[11px] text-blue-600 hover:underline cursor-pointer"
                >今天</button>
                <button
                  type="button"
                  @click="setDateOffset(1)"
                  class="text-[11px] text-blue-600 hover:underline cursor-pointer"
                >明天</button>
                <button
                  type="button"
                  @click="setDateOffset(2)"
                  class="text-[11px] text-blue-600 hover:underline cursor-pointer"
                >后天</button>
              </div>
            </div>
            <div class="relative">
              <input
                v-model="trainDate"
                type="date"
                :min="todayStr"
                class="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-300 rounded-xl text-sm font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                @keydown.enter="doQueryTickets"
              />
            </div>
          </div>

          <!-- 查询按钮 -->
          <div class="md:col-span-2">
            <button
              type="button"
              :disabled="isLoading"
              @click="doQueryTickets"
              class="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-medium rounded-xl text-sm shadow-md shadow-blue-500/20 hover:shadow-lg hover:shadow-blue-500/30 transition-all flex items-center justify-center space-x-1.5 disabled:opacity-60 cursor-pointer"
            >
              <Search v-if="!isLoading" class="w-4 h-4" />
              <div v-else class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              <span>{{ isLoading ? '查询中...' : '查询车票' }}</span>
            </button>
          </div>
        </div>

        <!-- 常用快捷条件 & 热门线路 -->
        <div class="mt-4 pt-3.5 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div class="flex items-center space-x-2 sm:space-x-3">
            <span class="text-slate-400">热门路线:</span>
            <button
              v-for="route in hotRoutes"
              :key="route.label"
              type="button"
              @click="pickHotRoute(route)"
              class="px-2 py-1 rounded-md bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 transition-colors cursor-pointer"
            >
              {{ route.label }}
            </button>
          </div>

          <div class="flex items-center space-x-4">
            <label class="inline-flex items-center space-x-1.5 cursor-pointer text-slate-600 select-none">
              <input type="checkbox" v-model="filterHighSpeedOnly" class="rounded text-blue-600 focus:ring-blue-500" />
              <span>仅看高铁/动车 (G/D/C)</span>
            </label>
            <label class="inline-flex items-center space-x-1.5 cursor-pointer text-slate-600 select-none">
              <input type="checkbox" v-model="filterHasTicketOnly" class="rounded text-blue-600 focus:ring-blue-500" />
              <span>仅看直达有票</span>
            </label>
          </div>
        </div>

        <!-- 方案偏好定制 (席别偏好多选 + 车内最多换座次数) -->
        <div class="mt-3.5 pt-3.5 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-xs">
          <!-- 接受席别多选 -->
          <div class="flex flex-wrap items-center gap-1.5">
            <span class="text-slate-500 font-semibold mr-1 flex items-center space-x-1">
              <Armchair class="w-3.5 h-3.5 text-blue-600" />
              <span>可接受席别:</span>
            </span>
            <button
              v-for="s in availableSeatOptions"
              :key="s.code"
              type="button"
              @click="toggleSeatOption(s.code)"
              class="px-2.5 py-1 rounded-lg border font-medium transition-all cursor-pointer flex items-center space-x-1"
              :class="selectedSeatCodes.includes(s.code) ? 'bg-blue-600 text-white border-blue-600 shadow-xs' : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'"
            >
              <span>{{ s.name }}</span>
              <Check v-if="selectedSeatCodes.includes(s.code)" class="w-3 h-3 ml-0.5" />
            </button>
          </div>

          <!-- 最多购票张数 / 车内换乘次数 -->
          <div class="flex items-center space-x-2">
            <span class="text-slate-500 font-semibold flex items-center space-x-1" title="全程到达终点站最多购买车票张数">
              <Ticket class="w-3.5 h-3.5 text-indigo-600" />
              <span>最多购票张数:</span>
            </span>
            <div class="inline-flex rounded-xl bg-slate-100 p-0.5 border border-slate-200 text-xs">
              <button
                v-for="opt in [
                  { val: 1, label: '1张 (买短补长)' },
                  { val: 2, label: '2张 (换座1次·默认)' },
                  { val: 3, label: '3张 (最多换座2次)' }
                ]"
                :key="opt.val"
                type="button"
                @click="selectedMaxTickets = opt.val; reloadActivePlan()"
                class="px-2.5 py-1 rounded-lg font-medium transition-all cursor-pointer"
                :class="selectedMaxTickets === opt.val ? 'bg-white text-blue-700 shadow-xs font-bold' : 'text-slate-500 hover:text-slate-800'"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 查询结果展示区 -->
      <section v-if="queried" class="space-y-4">
        <!-- 统计状态条 -->
        <div class="flex flex-wrap items-center justify-between bg-white px-4 py-2.5 rounded-xl border border-slate-200 text-xs text-slate-600">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-slate-800">{{ fromStation }}</span>
            <span class="text-slate-400">→</span>
            <span class="font-bold text-slate-800">{{ toStation }}</span>
            <span class="text-slate-400">|</span>
            <span>乘车日期: <strong class="text-slate-700">{{ trainDate }}</strong></span>
          </div>
          <div>
            共找到 <strong class="text-blue-600">{{ filteredTrains.length }}</strong> 趟列车
            <span class="text-slate-400 ml-1">
              (直达有票 {{ countDirectAvailable }} 趟，无票待方案推算 {{ filteredTrains.length - countDirectAvailable }} 趟)
            </span>
          </div>
        </div>

        <!-- 空数据提示 -->
        <div v-if="filteredTrains.length === 0" class="bg-white rounded-2xl p-12 text-center border border-slate-200">
          <div class="w-12 h-12 mx-auto rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
            <AlertCircle class="w-6 h-6" />
          </div>
          <h3 class="text-base font-semibold text-slate-700">未查询到符合条件的列车</h3>
          <p class="text-xs text-slate-400 mt-1">请尝试更换乘车日期或放宽筛选条件</p>
        </div>

        <!-- 列车卡片列表 -->
        <div v-for="train in filteredTrains" :key="train.train_no" class="bg-white rounded-2xl border border-slate-200 shadow-xs hover:border-slate-300 transition-all overflow-hidden">
          <div class="p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <!-- 车次信息与运行时间 -->
            <div class="flex items-center space-x-4 sm:space-x-6 min-w-[280px]">
              <div>
                <span class="inline-block px-2.5 py-1 rounded-lg text-sm font-bold bg-slate-100 text-slate-800 border border-slate-200">
                  {{ train.train_code }}
                </span>
                <p class="text-[11px] text-slate-400 mt-1 text-center font-mono">
                  {{ train.duration }}
                </p>
              </div>

              <div class="flex items-center space-x-3 sm:space-x-4">
                <div class="text-left">
                  <div class="text-lg font-bold text-slate-900 font-mono">{{ train.start_time }}</div>
                  <div class="text-xs font-medium text-slate-600 flex items-center space-x-1">
                    <span v-if="train.from_station_name === train.start_station_name" class="w-3.5 h-3.5 rounded-full bg-amber-500 text-white text-[9px] flex items-center justify-center font-bold">始</span>
                    <span>{{ train.from_station_name }}</span>
                  </div>
                </div>

                <div class="flex flex-col items-center px-1">
                  <ArrowRight class="w-4 h-4 text-slate-300" />
                  <span class="text-[10px] text-slate-400">经停</span>
                </div>

                <div class="text-left">
                  <div class="text-lg font-bold text-slate-900 font-mono">{{ train.arrive_time }}</div>
                  <div class="text-xs font-medium text-slate-600 flex items-center space-x-1">
                    <span v-if="train.to_station_name === train.end_station_name" class="w-3.5 h-3.5 rounded-full bg-emerald-600 text-white text-[9px] flex items-center justify-center font-bold">终</span>
                    <span>{{ train.to_station_name }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 席别余票格子 (自适应高铁与普速席别) -->
            <div class="flex-1 grid grid-cols-4 sm:grid-cols-6 md:grid-cols-4 lg:grid-cols-6 gap-2">
              <div
                v-for="seat in getDisplaySeats(train)"
                :key="seat.name"
                class="px-2 py-1.5 rounded-xl border text-center transition-colors flex flex-col justify-between"
                :class="seat.hasTicket ? 'bg-emerald-50/60 border-emerald-200/80 text-emerald-800' : 'bg-slate-50 border-slate-100 text-slate-400'"
              >
                <div class="text-[10px] text-slate-500 truncate">{{ seat.name }}</div>
                <div class="text-xs font-bold font-mono mt-0.5 truncate" :class="seat.hasTicket ? 'text-emerald-600' : 'text-slate-400'">
                  {{ seat.count }}
                </div>
                <div v-if="seat.price" class="text-[10px] font-mono font-semibold text-slate-600 mt-0.5 truncate">
                  {{ seat.price }}
                </div>
              </div>
            </div>

            <!-- 操作按钮区 -->
            <div class="flex items-center space-x-2 md:pl-3 border-t md:border-t-0 md:border-l border-slate-100 pt-3 md:pt-0">
              <!-- 直达状态标识 -->
              <span v-if="train.seats.has_any_ticket" class="text-xs font-medium text-emerald-600 bg-emerald-50 px-2.5 py-1.5 rounded-xl border border-emerald-200">
                直达有票
              </span>
              <span v-else class="text-xs font-medium text-amber-700 bg-amber-50 px-2.5 py-1.5 rounded-xl border border-amber-200">
                直达候补
              </span>

              <!-- 智能推算方案按钮 -->
              <button
                type="button"
                @click="toggleSmartPlan(train)"
                class="px-3 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center space-x-1 cursor-pointer"
                :class="activePlanTrain?.train_no === train.train_no
                  ? 'bg-blue-700 text-white shadow-sm'
                  : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-sm shadow-blue-500/20'"
              >
                <Sparkles class="w-3.5 h-3.5" />
                <span>{{ activePlanTrain?.train_no === train.train_no ? '收起方案' : '✨ 跨站方案' }}</span>
                <ChevronUp v-if="activePlanTrain?.train_no === train.train_no" class="w-3.5 h-3.5" />
                <ChevronDown v-else class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <!-- 展开的智能方案面板 -->
          <div
            v-if="activePlanTrain?.train_no === train.train_no"
            class="bg-gradient-to-b from-blue-50/40 to-slate-50 p-4 sm:p-6 border-t border-blue-100 space-y-4"
          >
            <!-- 方案加载状态 -->
            <div v-if="isPlanLoading" class="py-8 text-center text-slate-500 space-y-2">
              <div class="w-6 h-6 mx-auto border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
              <p class="text-xs font-medium">正在拉取车次经停站并推算买短补长与换座方案...</p>
            </div>

            <!-- 方案结果 -->
            <template v-else>
              <!-- 经停站路线时间轴 -->
              <div v-if="activeStops.length > 0" class="bg-white p-3.5 rounded-xl border border-slate-200 text-xs">
                <div class="font-semibold text-slate-700 mb-2 flex items-center space-x-1.5">
                  <Clock class="w-3.5 h-3.5 text-blue-600" />
                  <span>{{ train.train_code }} 沿途经停站时刻表 (共 {{ activeStops.length }} 站)</span>
                </div>
                <div class="flex items-center space-x-2 overflow-x-auto pb-1 text-[11px]">
                  <div
                    v-for="(stop, sIdx) in activeStops"
                    :key="stop.station_no"
                    class="flex items-center shrink-0"
                  >
                    <div
                      class="px-2.5 py-1.5 rounded-lg border text-center"
                      :class="isStationInJourney(stop.station_name, train) ? 'bg-blue-50 border-blue-300 font-bold text-blue-800' : 'bg-slate-50 border-slate-200 text-slate-500'"
                    >
                      <div>{{ stop.station_name }}</div>
                      <div class="text-[10px] text-slate-400 font-mono">{{ stop.arrive_time === '----' ? stop.start_time : stop.arrive_time }}</div>
                    </div>
                    <span v-if="sIdx < activeStops.length - 1" class="text-slate-300 mx-1">→</span>
                  </div>
                </div>
              </div>

              <!-- 推荐方案列表 -->
              <div v-if="smartPlans.length > 0" class="space-y-3">
                <div class="flex items-center justify-between text-xs font-semibold text-slate-600">
                  <span>为您推算出 {{ smartPlans.length }} 个出行保障方案:</span>
                  <span class="text-slate-400 font-normal">按成功率与舒适度智能排序</span>
                </div>

                <div
                  v-for="(plan, pIdx) in smartPlans"
                  :key="pIdx"
                  class="bg-white rounded-xl p-4 border shadow-xs transition-all"
                  :class="getPlanBorderClass(plan.plan_type)"
                >
                  <div class="flex flex-wrap items-start justify-between gap-2 mb-3">
                    <div class="flex items-center space-x-2">
                      <span
                        class="px-2.5 py-0.5 rounded-full text-xs font-bold"
                        :class="getPlanBadgeClass(plan.plan_type)"
                      >
                        {{ plan.plan_type_name }}
                      </span>
                      <span
                        v-if="plan.ticket_count && plan.ticket_count > 1"
                        class="px-2 py-0.5 rounded-md text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center space-x-1"
                      >
                        <span>购票 {{ plan.ticket_count }} 张</span>
                        <span class="text-indigo-300">·</span>
                        <span>换座 {{ plan.transfer_count }} 次</span>
                      </span>
                      <span
                        v-else
                        class="px-2 py-0.5 rounded-md text-[11px] font-bold bg-slate-100 text-slate-600 border border-slate-200"
                      >
                        购票 1 张
                      </span>
                      <h4 class="text-sm font-bold text-slate-900">{{ plan.title }}</h4>
                    </div>

                    <div class="flex items-center space-x-3 text-xs">
                      <div class="flex items-center space-x-1">
                        <span class="text-slate-400">推荐指数:</span>
                        <span class="font-bold text-blue-600 font-mono">{{ plan.recommendation_score }}分</span>
                      </div>
                      <button
                        type="button"
                        @click="copyPlanDetails(plan)"
                        class="text-blue-600 hover:text-blue-800 font-medium flex items-center space-x-0.5 cursor-pointer"
                        title="复制本方案到剪贴板"
                      >
                        <Copy class="w-3.5 h-3.5" />
                        <span>复制方案</span>
                      </button>
                    </div>
                  </div>

                  <!-- 分段行程步骤卡片 -->
                  <div
                    class="grid gap-3 mb-3"
                    :class="plan.segments.length >= 4 ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4' : (plan.segments.length === 3 ? 'grid-cols-1 sm:grid-cols-3' : 'grid-cols-1 sm:grid-cols-2')"
                  >
                    <div
                      v-for="(seg, sIndex) in plan.segments"
                      :key="sIndex"
                      class="bg-slate-50/80 rounded-xl p-3 border border-slate-200/80 text-xs flex flex-col justify-between"
                    >
                      <div class="flex items-center justify-between font-bold text-slate-800 mb-1.5">
                        <span class="flex items-center space-x-1">
                          <span class="w-4 h-4 rounded-full bg-slate-200 text-slate-600 text-[10px] flex items-center justify-center">{{ sIndex + 1 }}</span>
                          <span>{{ seg.from_station }} → {{ seg.to_station }}</span>
                        </span>
                        <span
                          class="px-1.5 py-0.5 rounded text-[10px] font-bold"
                          :class="seg.is_extension ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'"
                        >
                          {{ seg.is_extension ? '车上补票' : '12306正常购票' }}
                        </span>
                      </div>

                      <div class="flex items-center justify-between text-slate-500 font-mono text-[11px] mb-1">
                        <span>{{ seg.start_time || '--' }} 出发</span>
                        <span>{{ seg.arrive_time || '--' }} 到达</span>
                      </div>

                      <div class="flex items-center justify-between pt-1 border-t border-slate-200/60 mt-1">
                        <span class="text-slate-600 font-medium">席位: {{ seg.seat_name }}</span>
                        <div class="flex items-center space-x-1.5">
                          <span v-if="seg.seat_price" class="text-slate-800 font-mono font-bold">{{ seg.seat_price }}</span>
                          <span :class="seg.is_extension ? 'text-amber-700 font-medium' : 'text-emerald-600 font-bold'">
                            {{ seg.seat_status }}
                          </span>
                        </div>
                      </div>
                      <p class="text-[10px] text-slate-400 mt-1">{{ seg.tip }}</p>
                    </div>
                  </div>

                  <!-- 风险提示与操作建议 -->
                  <div
                    class="p-3 rounded-xl text-xs flex items-start space-x-2"
                    :class="plan.risk_level === 0 ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-amber-50 text-amber-800 border border-amber-200'"
                  >
                    <ShieldCheck v-if="plan.risk_level === 0" class="w-4 h-4 shrink-0 text-emerald-600 mt-0.5" />
                    <AlertTriangle v-else class="w-4 h-4 shrink-0 text-amber-600 mt-0.5" />
                    <div class="leading-relaxed">
                      {{ plan.risk_notice }}
                    </div>
                  </div>
                </div>
              </div>

              <!-- 无方案提示 -->
              <div v-else class="bg-white p-6 rounded-xl border border-slate-200 text-center text-slate-500 text-xs">
                该车次暂未发现沿途有票的中间站或换座区间。建议尝试查询其他前后车次或开启官方候补。
              </div>
            </template>
          </div>
        </div>
      </section>
    </main>

    <!-- 底部简要免责声明 -->
    <footer class="max-w-6xl mx-auto px-4 mt-12 text-center text-xs text-slate-400 space-y-1">
      <p>12306-RailHop (铁跃) · 基于公开网络接口计算，所有最终购票请在铁路官方 12306 App 完成。</p>
      <p>客流极度高峰期列车严重超员时，列车长有权根据客运安全规程停止办理越站补票，请合理规划出行。</p>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  Train,
  Search,
  ArrowRight,
  ArrowLeftRight,
  MapPin,
  Clock,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  Info,
  Copy,
  ChevronDown,
  ChevronUp,
  Armchair,
  Repeat,
  Check,
  Ticket
} from 'lucide-vue-next'

// 轻量 Toast 消息提示
const toast = ref({
  show: false,
  message: '',
  type: 'info',
  timer: null
})

function showToast(message, type = 'info', duration = 2500) {
  if (toast.value.timer) {
    clearTimeout(toast.value.timer)
  }
  toast.value = {
    show: true,
    message,
    type,
    timer: setTimeout(() => {
      toast.value.show = false
    }, duration)
  }
}

// 响应式状态
const fromStation = ref('上海')
const toStation = ref('北京')
const trainDate = ref('')
const activeDropdown = ref('')
const stationSuggestions = ref([])

const isLoading = ref(false)
const queried = ref(false)
const trainResults = ref([])

const filterHighSpeedOnly = ref(true)
const filterHasTicketOnly = ref(false)

// 用户偏好: 允许席别 & 最多车内换座次数 (默认2次)
const availableSeatOptions = [
  { code: 'ze', name: '二等座' },
  { code: 'zy', name: '一等座' },
  { code: 'swz', name: '商务座' },
  { code: 'srrb', name: '动卧' },
  { code: 'yw', name: '硬卧' },
  { code: 'rw', name: '软卧' },
  { code: 'yz', name: '硬座' },
  { code: 'wz', name: '无座' }
]
const selectedSeatCodes = ref(['ze', 'zy'])
const selectedMaxTickets = ref(2)

function toggleSeatOption(code) {
  if (selectedSeatCodes.value.includes(code)) {
    if (selectedSeatCodes.value.length === 1) {
      showToast('至少保留一个可接受席别', 'info')
      return
    }
    selectedSeatCodes.value = selectedSeatCodes.value.filter(c => c !== code)
  } else {
    selectedSeatCodes.value.push(code)
  }
  reloadActivePlan()
}

function reloadActivePlan() {
  if (activePlanTrain.value) {
    toggleSmartPlan(activePlanTrain.value, true)
  }
}

const activePlanTrain = ref(null)
const isPlanLoading = ref(false)
const smartPlans = ref([])
const activeStops = ref([])

// 快捷热门路线
const hotRoutes = [
  { label: '上海 ⇋ 北京', from: '上海', to: '北京' },
  { label: '北京 ⇋ 西安', from: '北京', to: '西安' },
  { label: '上海 ⇋ 南京', from: '上海', to: '南京' },
  { label: '广州 ⇋ 长沙', from: '广州', to: '长沙' },
  { label: '杭州 ⇋ 武汉', from: '杭州', to: '武汉' }
]

// 解决本地时区与 UTC 偏差的日期工具
function getLocalDateStr(date = new Date()) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const todayStr = computed(() => getLocalDateStr(new Date()))

function setDateOffset(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  trainDate.value = getLocalDateStr(d)
}

onMounted(() => {
  // 默认设置为明天
  setDateOffset(1)

  // 全局点击监听：点击车站选择框外部时关闭下拉
  window.addEventListener('click', (e) => {
    if (!e.target.closest('.station-picker')) {
      activeDropdown.value = ''
    }
  })
})

// 车站输入联想 (Focus 时如列表为空即刻搜索)
let debounceTimer = null

async function fetchSuggestions(kw) {
  try {
    const res = await fetch(`/api/stations/search?keyword=${encodeURIComponent(kw || '')}&limit=12`)
    const json = await res.json()
    stationSuggestions.value = json.data || []
  } catch (err) {
    console.error('Search station failed', err)
  }
}

function handleStationFocus(type) {
  activeDropdown.value = type
  const kw = type === 'from' ? fromStation.value : toStation.value
  fetchSuggestions(kw)
}

function handleStationInput(type) {
  clearTimeout(debounceTimer)
  activeDropdown.value = type
  const kw = type === 'from' ? fromStation.value : toStation.value
  debounceTimer = setTimeout(() => {
    fetchSuggestions(kw)
  }, 120)
}

function selectStation(type, st) {
  if (type === 'from') {
    fromStation.value = st.name
  } else {
    toStation.value = st.name
  }
  activeDropdown.value = ''
  stationSuggestions.value = []
}

function swapStations() {
  const tmp = fromStation.value
  fromStation.value = toStation.value
  toStation.value = tmp
  if (queried.value) {
    doQueryTickets()
  }
}

function pickHotRoute(route) {
  fromStation.value = route.from
  toStation.value = route.to
  doQueryTickets()
}

// 查票主动作
async function doQueryTickets() {
  if (!fromStation.value.trim() || !toStation.value.trim() || !trainDate.value) {
    showToast('请输入出发站、到达站及乘车日期', 'error')
    return
  }

  isLoading.value = true
  activePlanTrain.value = null
  smartPlans.value = []
  activeStops.value = []

  try {
    const url = `/api/tickets/query?train_date=${trainDate.value}&from_station=${encodeURIComponent(fromStation.value.trim())}&to_station=${encodeURIComponent(toStation.value.trim())}`
    const res = await fetch(url)
    const json = await res.json()

    if (json.code === 200 && Array.isArray(json.data)) {
      trainResults.value = json.data
      queried.value = true
      if (json.data.length === 0) {
        showToast('未查询到相关车次，请确认站名或更换日期', 'info')
      }
    } else {
      showToast(json.msg || '查询失败，请稍后重试', 'error')
    }
  } catch (err) {
    console.error('Query tickets error', err)
    showToast('网络或后端连接失败，请确认后端运行在端口 8000', 'error')
  } finally {
    isLoading.value = false
  }
}

// 过滤列表
const filteredTrains = computed(() => {
  return trainResults.value.filter(t => {
    if (filterHighSpeedOnly.value) {
      const code = t.train_code.toUpperCase()
      if (!code.startsWith('G') && !code.startsWith('D') && !code.startsWith('C')) {
        return false
      }
    }
    if (filterHasTicketOnly.value && !t.seats.has_any_ticket) {
      return false
    }
    return true
  })
})

const countDirectAvailable = computed(() => {
  return filteredTrains.value.filter(t => t.seats.has_any_ticket).length
})

// 席别自适应展示 (包含高铁与普速列车的硬座/卧铺及具体票价)
function getDisplaySeats(train) {
  const seats = train.seats
  const prices = train.prices || {}
  const isHighSpeed = /^[GDC]/i.test(train.train_code)

  if (isHighSpeed) {
    return [
      { name: '二等座', count: seats.ze, price: prices.ze, hasTicket: isAvailable(seats.ze) },
      { name: '一等座', count: seats.zy, price: prices.zy, hasTicket: isAvailable(seats.zy) },
      { name: '商务座', count: seats.swz, price: prices.swz, hasTicket: isAvailable(seats.swz) },
      { name: '动卧/软卧', count: seats.srrb !== '--' ? seats.srrb : seats.rw, price: prices.srrb || prices.rw, hasTicket: isAvailable(seats.srrb) || isAvailable(seats.rw) },
      { name: '无座', count: seats.wz, price: prices.wz || prices.ze, hasTicket: isAvailable(seats.wz) },
      { name: '其他', count: seats.yw !== '--' ? seats.yw : seats.gr, price: prices.yw || prices.gr, hasTicket: isAvailable(seats.yw) || isAvailable(seats.gr) }
    ]
  } else {
    // 普速列车: 硬卧、软卧、硬座、无座
    return [
      { name: '硬卧', count: seats.yw, price: prices.yw, hasTicket: isAvailable(seats.yw) },
      { name: '软卧', count: seats.rw, price: prices.rw, hasTicket: isAvailable(seats.rw) },
      { name: '硬座', count: seats.yz, price: prices.yz, hasTicket: isAvailable(seats.yz) },
      { name: '无座', count: seats.wz, price: prices.wz || prices.yz, hasTicket: isAvailable(seats.wz) },
      { name: '高软', count: seats.gr, price: prices.gr, hasTicket: isAvailable(seats.gr) },
      { name: '软座', count: seats.rz, price: prices.rz, hasTicket: isAvailable(seats.rz) }
    ]
  }
}

function isAvailable(val) {
  return val && val !== '--' && val !== '无'
}

// 展开/收起某趟车的智能跨站方案 (带竞态防护)
let currentPlanRequestId = 0

async function toggleSmartPlan(train, forceRefresh = false) {
  if (!forceRefresh && activePlanTrain.value?.train_no === train.train_no) {
    activePlanTrain.value = null
    smartPlans.value = []
    activeStops.value = []
    return
  }

  activePlanTrain.value = train
  isPlanLoading.value = true
  smartPlans.value = []
  activeStops.value = []

  const reqId = ++currentPlanRequestId

  try {
    const allowedParam = selectedSeatCodes.value.length > 0 ? selectedSeatCodes.value.join(',') : ''

    // 使用车次实际的精确电报码或站名，防止同城站匹配歧义
    const stopsPromise = fetch(
      `/api/tickets/stops?train_no=${train.train_no}&from_station=${encodeURIComponent(train.from_station_name)}&to_station=${encodeURIComponent(train.to_station_name)}&depart_date=${trainDate.value}`
    ).then(r => r.json())

    const planPromise = fetch(
      `/api/smart-plans/calculate?train_date=${trainDate.value}&train_code=${train.train_code}&train_no=${train.train_no}&from_station=${encodeURIComponent(train.from_station_name)}&to_station=${encodeURIComponent(train.to_station_name)}&allowed_seats=${allowedParam}&max_tickets=${selectedMaxTickets.value}`
    ).then(r => r.json())

    const [stopsRes, planRes] = await Promise.all([stopsPromise, planPromise])

    // 防止用户快速切换不同车次时的竞态覆写
    if (reqId !== currentPlanRequestId || activePlanTrain.value?.train_no !== train.train_no) {
      return
    }

    if (stopsRes.code === 200) {
      activeStops.value = stopsRes.data || []
    }
    if (planRes.code === 200) {
      smartPlans.value = planRes.data || []
    }
  } catch (err) {
    console.error('Calculate smart plans error', err)
    if (reqId === currentPlanRequestId) {
      showToast('计算跨站方案异常，请稍后重试', 'error')
    }
  } finally {
    if (reqId === currentPlanRequestId) {
      isPlanLoading.value = false
    }
  }
}

function isStationInJourney(name, train) {
  // 精确匹配该趟车本次查询的发到站
  return name === train.from_station_name || name === train.to_station_name
}

function getPlanBorderClass(type) {
  if (type === 2) return 'border-emerald-200 hover:border-emerald-300'
  if (type === 3) return 'border-indigo-200 hover:border-indigo-300'
  return 'border-amber-200 hover:border-amber-300'
}

function getPlanBadgeClass(type) {
  if (type === 2) return 'bg-emerald-100 text-emerald-800'
  if (type === 3) return 'bg-indigo-100 text-indigo-800'
  return 'bg-amber-100 text-amber-800'
}

function copyPlanDetails(plan) {
  const ticketDesc = plan.ticket_count > 1 ? ` (需购${plan.ticket_count}张票/换座${plan.transfer_count}次)` : ' (需购1张票)'
  const lines = [
    `【12306出行方案】${plan.train_code} ${plan.title}${ticketDesc}`,
    ...plan.segments.map((s, idx) => `  ${idx + 1}. [${s.is_extension ? '车上补票' : '官方购票'}] ${s.from_station} -> ${s.to_station} (${s.seat_name} ${s.seat_status}${s.seat_price ? ' ' + s.seat_price : ''})`),
    `乘车建议: ${plan.risk_notice}`
  ]
  const text = lines.join('\n')
  navigator.clipboard.writeText(text).then(() => {
    showToast('方案详情已复制到剪贴板！', 'success')
  }).catch(() => {
    showToast('复制失败，请手动记录', 'info')
  })
}
</script>
