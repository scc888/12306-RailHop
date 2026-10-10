<template>
  <div class="min-h-screen bg-slate-50 text-slate-800 pb-16 font-sans">
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
              <span class="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-bold">铁跃 · V2.0</span>
            </div>
            <p class="text-xs text-slate-500 hidden sm:block">智能查票 · 车内接续换座 · 官方扫码登录与购票</p>
          </div>
        </div>

        <!-- 登录状态与用户操作区 -->
        <div class="flex items-center space-x-2 sm:space-x-3">
          <button v-if="bookingTask" @click="showBookingProgress = true" class="px-3 py-1.5 rounded-xl bg-indigo-50 text-indigo-700 text-xs font-semibold">方案购票进度</button>
          <!-- 待支付订单提示徽章 -->
          <button
            v-if="unpaidOrder"
            type="button"
            @click="openUnpaidModal"
            class="px-2.5 py-1 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 text-xs font-semibold flex items-center space-x-1.5 transition-all shadow-xs cursor-pointer animate-pulse"
            title="您有待支付订单，点击查看"
          >
            <Clock class="w-3.5 h-3.5 text-amber-600 shrink-0" />
            <span>待支付 ({{ formatCountdown(unpaidOrder.countdown_seconds) }})</span>
          </button>

          <!-- 未登录状态 -->
          <button
            v-if="!auth.loggedIn"
            type="button"
            @click="openLoginModal"
            class="px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-xs font-medium flex items-center space-x-1.5 shadow-sm shadow-blue-500/20 transition-all cursor-pointer"
          >
            <QrCode class="w-3.5 h-3.5" />
            <span>12306 扫码登录</span>
          </button>

          <!-- 已登录状态 -->
          <div v-else class="flex items-center space-x-2">
            <div class="flex items-center space-x-1.5 px-3 py-1 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-xl text-xs font-medium">
              <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <User class="w-3.5 h-3.5 text-emerald-600" />
              <span>{{ auth.username || '铁路用户' }}</span>
            </div>
            <button
              type="button"
              @click="doLogout"
              class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors cursor-pointer"
              title="退出登录"
            >
              <LogOut class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </header>

    <main class="max-w-6xl mx-auto px-4 pt-6 space-y-6">
      <!-- 待支付订单全局横幅 (若存在) -->
      <section
        v-if="unpaidOrder"
        class="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-4 shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
      >
        <div class="flex items-center space-x-3">
          <div class="w-10 h-10 rounded-xl bg-amber-500/10 text-amber-600 flex items-center justify-center shrink-0">
            <Clock class="w-5 h-5" />
          </div>
          <div>
            <div class="flex items-center space-x-2">
              <span class="text-xs font-bold text-amber-900 bg-amber-100 px-2 py-0.5 rounded-md">待支付订单</span>
              <span class="text-sm font-bold text-slate-800 font-mono">{{ unpaidOrder.train_code }} ({{ unpaidOrder.from_station_name }} → {{ unpaidOrder.to_station_name }})</span>
            </div>
            <p class="text-xs text-amber-700 mt-0.5">
              席位已锁定！总计 <strong>{{ unpaidOrder.total_price }}</strong>，支付剩余倒计时：
              <span class="font-bold font-mono text-red-600">{{ formatCountdown(unpaidOrder.countdown_seconds) }}</span>
              ，请尽快在官方 12306 完成支付。
            </p>
          </div>
        </div>
        <div class="flex items-center space-x-2 shrink-0">
          <button
            type="button"
            @click="openUnpaidModal"
            class="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-xs font-semibold shadow-xs cursor-pointer"
          >
            查看订单明细
          </button>
          <button
            type="button"
            @click="cancelCurrentOrder(unpaidOrder.sequence_no)"
            class="px-3 py-1.5 bg-white hover:bg-red-50 text-slate-600 hover:text-red-600 border border-slate-200 hover:border-red-200 rounded-xl text-xs font-medium cursor-pointer"
          >
            取消订单
          </button>
        </div>
      </section>

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
              <!-- 立即预订按钮 (直达有票时亮起) -->
              <button
                type="button"
                @click="openBookingModal(train)"
                class="px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center space-x-1 shadow-xs cursor-pointer"
                :class="train.seats.has_any_ticket
                  ? 'bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 text-white shadow-emerald-500/20'
                  : 'bg-slate-100 hover:bg-slate-200 text-slate-600 border border-slate-200'"
              >
                <Ticket class="w-3.5 h-3.5" />
                <span>预订</span>
              </button>

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
                <span>{{ activePlanTrain?.train_no === train.train_no ? '收起' : '✨ 换座' }}</span>
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
                        @click="openPlanBooking(plan, train)"
                        class="px-3 py-1.5 rounded-lg bg-blue-600 text-white font-semibold"
                      >按此方案购票</button>
                      <button
                        type="button"
                        @click="copyPlanDetails(plan)"
                        class="text-blue-600 hover:text-blue-700 font-medium flex items-center space-x-1 cursor-pointer"
                      >
                        <Copy class="w-3.5 h-3.5" />
                        <span>复制方案</span>
                      </button>
                    </div>
                  </div>

                  <!-- 分段行程步骤详情 -->
                  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 mb-3">
                    <div
                      v-for="(seg, sIdx) in plan.segments"
                      :key="sIdx"
                      class="p-3 rounded-xl border text-xs"
                      :class="seg.is_extension ? 'bg-amber-50/50 border-amber-200/80' : 'bg-slate-50 border-slate-200'"
                    >
                      <div class="flex items-center justify-between mb-1.5">
                        <span class="font-bold text-slate-800 flex items-center space-x-1">
                          <span class="w-4 h-4 rounded-full bg-slate-200 text-slate-700 text-[10px] flex items-center justify-center font-mono">
                            {{ sIdx + 1 }}
                          </span>
                          <span>{{ seg.from_station }} → {{ seg.to_station }}</span>
                        </span>
                        <span
                          class="px-1.5 py-0.5 rounded text-[10px] font-semibold"
                          :class="seg.is_extension ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'"
                        >
                          {{ seg.seat_status }}
                        </span>
                      </div>

                      <div class="flex items-center justify-between text-slate-600 text-[11px]">
                        <span>{{ seg.seat_name }}</span>
                        <span v-if="seg.seat_price" class="font-mono font-bold text-slate-800">{{ seg.seat_price }}</span>
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

    <!-- ==================== 模态框 1: 12306 扫码登录 ==================== -->
    <div
      v-if="showLoginModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4"
      @click.self="closeLoginModal"
    >
      <div class="bg-white rounded-2xl max-w-sm w-full p-6 shadow-2xl border border-slate-100 relative">
        <button
          type="button"
          @click="closeLoginModal"
          class="absolute right-4 top-4 text-slate-400 hover:text-slate-600 p-1 rounded-lg"
        >
          <X class="w-5 h-5" />
        </button>

        <div class="text-center space-y-1 mb-5">
          <div class="w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 mx-auto flex items-center justify-center mb-2">
            <QrCode class="w-6 h-6" />
          </div>
          <h3 class="text-base font-bold text-slate-900">12306 官方客户端扫码登录</h3>
          <p class="text-xs text-slate-500">打开【铁路 12306】手机 App 首页扫一扫</p>
        </div>

        <!-- 二维码显示区 -->
        <div class="relative w-52 h-52 mx-auto bg-slate-50 rounded-2xl border-2 border-slate-200 p-2 flex items-center justify-center overflow-hidden">
          <!-- 正在获取二维码 -->
          <div v-if="qrState.loading" class="text-center text-xs text-slate-400 space-y-2">
            <div class="w-7 h-7 mx-auto border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
            <p>正在生成二维码...</p>
          </div>

          <!-- 显示二维码图片 -->
          <template v-else-if="qrState.image">
            <img :src="qrState.image" alt="12306登录二维码" class="w-full h-full object-contain rounded-xl" />

            <!-- 已扫码待手机确认状态覆盖 -->
            <div
              v-if="qrState.status === 'SCANNED'"
              class="absolute inset-0 bg-emerald-900/80 backdrop-blur-xs flex flex-col items-center justify-center p-4 text-center text-white space-y-2"
            >
              <CheckCircle2 class="w-10 h-10 text-emerald-400 animate-bounce" />
              <div class="text-sm font-bold">已成功扫码！</div>
              <div class="text-xs text-emerald-200">请在手机 12306 端点击【确认登录】</div>
            </div>

            <!-- 二维码过期覆盖 -->
            <div
              v-if="qrState.status === 'EXPIRED'"
              class="absolute inset-0 bg-slate-900/80 backdrop-blur-xs flex flex-col items-center justify-center p-4 text-center text-white space-y-2"
            >
              <AlertCircle class="w-8 h-8 text-amber-400" />
              <div class="text-xs font-semibold">二维码已过期</div>
              <button
                type="button"
                @click="loadQrCode"
                class="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium cursor-pointer"
              >
                点击刷新
              </button>
            </div>
          </template>
        </div>

        <!-- 状态提示文字 -->
        <div class="mt-4 text-center text-xs">
          <p v-if="qrState.status === 'WAITING'" class="text-slate-500 flex items-center justify-center space-x-1">
            <span class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping mr-1"></span>
            等待扫码中...
          </p>
          <p v-else-if="qrState.status === 'SUCCESS'" class="text-emerald-600 font-bold flex items-center justify-center space-x-1">
            <CheckCircle2 class="w-4 h-4 mr-1" />
            登录成功，正在加载数据...
          </p>
          <p v-else class="text-slate-400">{{ qrState.msg }}</p>
        </div>

        <!-- 底部安全说明 -->
        <div class="mt-5 pt-3.5 border-t border-slate-100 text-[11px] text-slate-400 text-center leading-relaxed">
          🔒 会话直接与铁路 12306 官方加密握手，系统不保存任何用户密码，保障隐私安全。
        </div>
      </div>
    </div>

    <!-- ==================== 模态框 2: 车票预订与锁座 ==================== -->
    <div
      v-if="showBookingModal && bookingTrain"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 overflow-y-auto"
      @click.self="closeBookingModal"
    >
      <div class="bg-white rounded-2xl max-w-xl w-full p-6 shadow-2xl border border-slate-100 relative my-8">
        <button
          type="button"
          @click="closeBookingModal"
          class="absolute right-4 top-4 text-slate-400 hover:text-slate-600 p-1 rounded-lg"
        >
          <X class="w-5 h-5" />
        </button>

        <!-- 车次基本信息摘要 -->
        <div class="border-b border-slate-100 pb-4 mb-4">
          <div class="flex items-center space-x-2">
            <span class="px-2.5 py-0.5 rounded-lg text-sm font-bold bg-blue-100 text-blue-800">
              {{ bookingTrain.train_code }}
            </span>
            <span class="text-sm font-bold text-slate-900">
              {{ bookingTrain.from_station_name }} → {{ bookingTrain.to_station_name }}
            </span>
            <span class="text-xs text-slate-400">({{ bookingTrain.train_date }})</span>
          </div>
          <div class="flex items-center space-x-4 text-xs text-slate-500 mt-2 font-mono">
            <span>发车时刻: <strong>{{ bookingTrain.start_time }}</strong></span>
            <span>到达时刻: <strong>{{ bookingTrain.arrive_time }}</strong></span>
            <span>历时: {{ bookingTrain.duration }}</span>
          </div>
        </div>

        <!-- 锁座中或成功状态 -->
        <div v-if="orderSubmitting" class="py-12 text-center space-y-4">
          <div class="w-10 h-10 mx-auto border-3 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          <div class="space-y-1">
            <h4 class="text-sm font-bold text-slate-800">正在与 12306 排队流水线通信...</h4>
            <p class="text-xs text-slate-500">{{ submitStepText }}</p>
          </div>
        </div>

        <div v-else-if="orderSuccessResult" class="py-6 text-center space-y-4">
          <div class="w-14 h-14 rounded-full mx-auto flex items-center justify-center" :class="orderSuccessResult.success ? 'bg-emerald-100 text-emerald-600' : 'bg-amber-100 text-amber-600'">
            <CheckCircle2 v-if="orderSuccessResult.success" class="w-8 h-8" />
            <AlertTriangle v-else class="w-8 h-8" />
          </div>
          <div class="space-y-1.5">
            <h4 class="text-lg font-bold text-slate-900">{{ orderSuccessResult.success ? '订单已创建' : '订单结果待确认' }}</h4>
            <p v-if="orderSuccessResult.order_id" class="text-xs text-slate-600">
              12306 订单号: <strong class="text-blue-600 font-mono text-sm">{{ orderSuccessResult.order_id }}</strong>
            </p>
            <div class="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800 max-w-md mx-auto text-left leading-relaxed">
              {{ orderSuccessResult.msg }}<br />
              请在12306官方订单页核对订单。支付截止时间以官方显示为准，结果待确认时请勿重复提交。
            </div>
          </div>
          <div class="pt-4 flex justify-center space-x-3">
            <button
              v-if="orderSuccessResult.success"
              type="button"
              @click="closeBookingModal(); openUnpaidModal();"
              class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold cursor-pointer"
            >
              查看待支付详情
            </button>
            <button v-else type="button" @click="refreshSingleOrder" class="px-4 py-2 bg-blue-600 text-white rounded-xl text-xs font-semibold">查询原订单结果</button>
            <button
              type="button"
              @click="closeBookingModal"
              class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-medium cursor-pointer"
            >
              关闭
            </button>
          </div>
        </div>

        <!-- 购票配置表单 (常规状态) -->
        <template v-else>
          <div v-if="bookingPlan" class="mb-4 p-3 rounded-xl bg-blue-50 text-xs text-blue-900 space-y-2">
            <p class="font-bold">{{ bookingPlan.title }}</p>
            <p v-for="(segment, index) in bookingPlan.segments" :key="index">{{ segment.train_date }} · {{ segment.from_station }} → {{ segment.to_station }} · {{ segment.is_extension ? '后段候补' : segment.seat_name }}</p>
            <p>按每段推荐席别购票；当前段付款并核验后继续下一段。已有订单不会因后段失败而自动取消。</p>
          </div>
          <!-- 步骤 1: 常用乘车人选择 -->
          <div class="space-y-3 mb-5">
            <div class="flex items-center justify-between">
              <label class="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center space-x-1.5">
                <User class="w-4 h-4 text-blue-600" />
                <span>选择乘车人 (可多选)</span>
              </label>
              <span class="text-[11px] text-slate-400">已自动同步 12306 常用联系人</span>
            </div>

            <!-- 乘车人列表加载中 -->
            <div v-if="passengersLoading" class="py-4 text-center text-xs text-slate-400">
              正在同步常用乘车人...
            </div>

            <!-- 未查到乘车人 -->
            <div v-else-if="passengers.length === 0" class="p-4 bg-slate-50 border border-slate-200 rounded-xl text-center text-xs text-slate-500">
              暂未获取到乘车人。请确保您已登录并在 12306 App 中维护了常用联系人。
            </div>

            <!-- 乘车人多选卡片 -->
            <div v-else class="space-y-2 max-h-48 overflow-y-auto pr-1">
              <div
                v-for="p in passengers"
                :key="p.passenger_id_no_raw"
                class="p-2.5 rounded-xl border transition-all flex items-center justify-between cursor-pointer"
                :class="isPassengerSelected(p) ? 'bg-blue-50/70 border-blue-400 shadow-xs' : 'bg-slate-50 border-slate-200 hover:bg-slate-100'"
                @click="togglePassenger(p)"
              >
                <div class="flex items-center space-x-2.5">
                  <input
                    type="checkbox"
                    :checked="isPassengerSelected(p)"
                    class="rounded text-blue-600 focus:ring-blue-500"
                    @click.stop="togglePassenger(p)"
                  />
                  <div>
                    <div class="flex items-center space-x-1.5">
                      <span class="text-xs font-bold text-slate-800">{{ p.passenger_name }}</span>
                      <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-200 text-slate-600">{{ p.passenger_type_name }}</span>
                    </div>
                    <div class="text-[11px] text-slate-400 font-mono mt-0.5">{{ p.passenger_id_no }}</div>
                  </div>
                </div>

                <!-- 选中的席别与票种选择 -->
                <div v-if="isPassengerSelected(p) && !bookingPlan" class="flex items-center space-x-2 text-xs" @click.stop>
                  <select
                    v-model="getSelectedPassengerItem(p).seat_type"
                    class="px-2 py-1 bg-white border border-slate-300 rounded-lg text-xs font-medium focus:ring-1 focus:ring-blue-500"
                  >
                    <option v-for="s in getAvailableBookingSeats(bookingTrain)" :key="s.code" :value="s.code">
                      {{ s.name }} {{ s.price }}
                    </option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          <!-- 步骤 2: 高铁在线选座偏好 -->
          <div v-if="isHighSpeedTrain(bookingTrain)" class="space-y-2 mb-5">
            <div class="flex items-center justify-between">
              <label class="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center space-x-1.5">
                <Armchair class="w-4 h-4 text-indigo-600" />
                <span>在线选座偏好 (靠窗 / 过道)</span>
              </label>
              <span class="text-[11px] text-slate-400">系统将尽最大可能优先分配</span>
            </div>

            <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-center justify-center space-x-3 text-xs">
              <span class="text-[11px] text-slate-400">靠窗</span>
              <button
                v-for="letter in ['1A', '1B', '1C']"
                :key="letter"
                type="button"
                @click="chooseSeatLetter = (chooseSeatLetter === letter ? '' : letter)"
                class="w-8 h-8 rounded-lg font-bold font-mono transition-all border cursor-pointer"
                :class="chooseSeatLetter === letter ? 'bg-blue-600 text-white border-blue-600 shadow-xs' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'"
              >
                {{ letter.slice(1) }}
              </button>
              <span class="text-[11px] text-slate-300 px-1 font-mono">过道</span>
              <button
                v-for="letter in ['1D', '1F']"
                :key="letter"
                type="button"
                @click="chooseSeatLetter = (chooseSeatLetter === letter ? '' : letter)"
                class="w-8 h-8 rounded-lg font-bold font-mono transition-all border cursor-pointer"
                :class="chooseSeatLetter === letter ? 'bg-blue-600 text-white border-blue-600 shadow-xs' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'"
              >
                {{ letter.slice(1) }}
              </button>
              <span class="text-[11px] text-slate-400">靠窗</span>
            </div>
          </div>

          <!-- 底部提交操作栏 -->
          <div class="pt-4 border-t border-slate-100 flex items-center justify-between">
            <div class="text-xs text-slate-500">
              已选乘车人: <strong class="text-blue-600">{{ selectedBookingPassengers.length }}</strong> 人
            </div>

            <div class="flex items-center space-x-2">
              <button
                type="button"
                @click="closeBookingModal"
                class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-medium cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                :disabled="selectedBookingPassengers.length === 0"
                @click="doSubmitOrder"
                class="px-5 py-2 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 text-white rounded-xl text-xs font-bold shadow-md shadow-blue-500/20 transition-all cursor-pointer flex items-center space-x-1"
              >
                <Lock class="w-3.5 h-3.5" />
                <span>立即提交并锁座</span>
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- ==================== 模态框 3: 未完成/待支付订单详情 ==================== -->
    <div
      v-if="showUnpaidModal && unpaidOrder"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4"
      @click.self="showUnpaidModal = false"
    >
      <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100 relative">
        <button
          type="button"
          @click="showUnpaidModal = false"
          class="absolute right-4 top-4 text-slate-400 hover:text-slate-600 p-1 rounded-lg"
        >
          <X class="w-5 h-5" />
        </button>

        <div class="flex items-center space-x-2.5 mb-4">
          <div class="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center">
            <Clock class="w-5 h-5" />
          </div>
          <div>
            <h3 class="text-base font-bold text-slate-900">12306 待支付订单</h3>
            <p class="text-xs text-slate-500 font-mono">订单号: {{ unpaidOrder.sequence_no }}</p>
          </div>
        </div>

        <div class="bg-slate-50 rounded-xl p-4 border border-slate-200 space-y-3 mb-4 text-xs">
          <div class="flex items-center justify-between pb-2 border-b border-slate-200">
            <div class="flex items-center space-x-2">
              <span class="px-2 py-0.5 rounded-md font-bold bg-blue-600 text-white font-mono">{{ unpaidOrder.train_code }}</span>
              <span class="font-bold text-slate-800">{{ unpaidOrder.from_station_name }} → {{ unpaidOrder.to_station_name }}</span>
            </div>
            <span class="font-mono text-slate-500">{{ unpaidOrder.start_time }} 发车</span>
          </div>

          <!-- 车票明细 -->
          <div class="space-y-2">
            <div
              v-for="(t, idx) in unpaidOrder.tickets"
              :key="idx"
              class="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200"
            >
              <div>
                <span class="font-bold text-slate-800 mr-2">{{ t.passenger_name }}</span>
                <span class="text-slate-500">{{ t.seat_name }} · <strong>{{ t.coach_no }} {{ t.seat_no }}</strong></span>
              </div>
              <div class="font-bold font-mono text-slate-800">{{ t.price }}</div>
            </div>
          </div>

          <div class="flex items-center justify-between pt-2 border-t border-slate-200 text-sm">
            <span class="font-medium text-slate-600">应付总额:</span>
            <span class="font-bold font-mono text-red-600 text-base">{{ unpaidOrder.total_price }}</span>
          </div>
        </div>

        <!-- 倒计时提示 -->
        <div class="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800 leading-relaxed mb-5">
          ⏱️ 剩余支付时间: <strong class="font-mono text-red-600 text-sm">{{ formatCountdown(unpaidOrder.countdown_seconds) }}</strong><br />
          请打开 <strong>铁路 12306 App</strong> 或官网，在【订单 - 本人车票/待支付】中完成支付。
        </div>

        <div class="flex items-center justify-between">
          <button
            type="button"
            @click="cancelCurrentOrder(unpaidOrder.sequence_no)"
            class="text-xs text-red-600 hover:text-red-700 hover:underline cursor-pointer"
          >
            取消该订单 (每天限3次)
          </button>
          <button
            type="button"
            @click="openOfficialPayment({ order_id: unpaidOrder.sequence_no, kind: 'TICKET' })"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold cursor-pointer"
          >
            前往12306付款
          </button>
        </div>
      </div>
    </div>

    <BookingProgress v-if="showBookingProgress && bookingTask" :task="bookingTask" :busy="bookingTaskBusy" :error="bookingTaskError" @close="showBookingProgress = false" @pay="openOfficialPayment" @refresh="refreshBookingTask" @advance="advanceBookingTask" @stop="stopBookingTask" @retry="retryBookingTask" />

    <!-- 底部简要免责声明 -->
    <footer class="max-w-6xl mx-auto px-4 mt-12 text-center text-xs text-slate-400 space-y-1">
      <p>12306-RailHop (铁跃) · 基于公开网络接口计算与排队锁座，所有最终支付请在铁路官方 12306 渠道完成。</p>
      <p>后段候补兑现前没有对应区间车票，请按已购车票区间规划行程。</p>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import BookingProgress from './components/BookingProgress.vue'
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
  Ticket,
  Check,
  X,
  QrCode,
  User,
  LogOut,
  Lock
} from 'lucide-vue-next'

// 会话管理
const sessionId = ref('')

function getOrCreateSessionId() {
  let sid = localStorage.getItem('railhop_session_id')
  if (!sid) {
    sid = 'sess_' + Math.random().toString(36).substring(2, 12) + Date.now().toString(36)
    localStorage.setItem('railhop_session_id', sid)
  }
  return sid
}

// 统一封装带 Session Header 的 Fetch
async function apiFetch(url, options = {}) {
  const headers = options.headers || {}
  headers['X-Session-Id'] = sessionId.value
  return fetch(url, { ...options, headers })
}

// 登录与用户认证状态
const auth = ref({
  loggedIn: false,
  username: null
})

// 扫码登录模态框状态
const showLoginModal = ref(false)
const qrState = ref({
  loading: false,
  image: '',
  uuid: '',
  status: 'IDLE', // WAITING, SCANNED, SUCCESS, EXPIRED, ERROR
  msg: '',
  pollTimer: null
})

// 常用乘车人
const passengers = ref([])
const passengersLoading = ref(false)

// 待支付订单
const unpaidOrder = ref(null)
const showUnpaidModal = ref(false)
let countdownTimer = null

// 购票模态框状态
const showBookingModal = ref(false)
const bookingTrain = ref(null)
const bookingPlan = ref(null)
const bookingTask = ref(null)
const showBookingProgress = ref(false)
const bookingTaskBusy = ref(false)
const bookingTaskError = ref('')
let bookingPollTimer = null
let autoContinueBooking = false
const selectedBookingPassengers = ref([]) // 每项为 { passenger_name, id_no, seat_type, passenger_type, allEncStr }
const chooseSeatLetter = ref('')
const orderSubmitting = ref(false)
const submitStepText = ref('')
const orderSuccessResult = ref(null)

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
const queryDate = ref('')
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

function formatCountdown(sec) {
  if (sec == null) return '以官方页面为准'
  if (sec <= 0) return '00:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

onMounted(async () => {
  sessionId.value = getOrCreateSessionId()
  setDateOffset(1)

  // 全局点击监听：点击车站选择框外部时关闭下拉
  window.addEventListener('click', (e) => {
    if (!e.target.closest('.station-picker')) {
      activeDropdown.value = ''
    }
  })

  // 初始化会话并检查登录态
  await checkAuthStatus()
  const savedBooking = localStorage.getItem('railhop_booking_id')
  if (savedBooking && auth.value.loggedIn) {
    bookingTask.value = { id: savedBooking, steps: [], current_step: 0 }
    autoContinueBooking = true
    await refreshBookingTask()
  }

  // 倒计时定时器
  countdownTimer = setInterval(() => {
    if (unpaidOrder.value && unpaidOrder.value.countdown_seconds > 0) {
      unpaidOrder.value.countdown_seconds--
    }
  }, 1000)
})

onUnmounted(() => {
  if (qrState.value.pollTimer) clearTimeout(qrState.value.pollTimer)
  if (countdownTimer) clearInterval(countdownTimer)
  if (bookingPollTimer) clearTimeout(bookingPollTimer)
})

// ==================== 登录认证逻辑 ====================

async function checkAuthStatus() {
  try {
    const res = await apiFetch('/api/auth/status')
    const json = await res.json()
    if (json.code === 200 && json.data) {
      auth.value.loggedIn = json.data.logged_in
      auth.value.username = json.data.username
      if (auth.value.loggedIn) {
        fetchPassengers()
        fetchUnpaidOrder()
      }
    }
  } catch (err) {
    console.error('Check auth status error', err)
  }
}

function openLoginModal() {
  showLoginModal.value = true
  loadQrCode()
}

function closeLoginModal() {
  showLoginModal.value = false
  if (qrState.value.pollTimer) {
    clearTimeout(qrState.value.pollTimer)
    qrState.value.pollTimer = null
  }
}

async function loadQrCode() {
  qrState.value.loading = true
  qrState.value.status = 'WAITING'
  qrState.value.msg = '正在请求 12306 二维码...'
  qrState.value.image = ''
  qrState.value.uuid = ''
  if (qrState.value.pollTimer) {
    clearTimeout(qrState.value.pollTimer)
  }

  try {
    const res = await apiFetch('/api/auth/qr')
    let json
    try {
      json = await res.json()
    } catch {
      throw new Error('登录服务返回了无法读取的响应，请稍后重试')
    }
    if (res.ok && json?.code === 200 && json.data) {
      qrState.value.image = json.data.image
      qrState.value.uuid = json.data.uuid
      qrState.value.loading = false
      startQrPolling()
    } else {
      qrState.value.status = 'ERROR'
      qrState.value.msg = json?.detail || json?.msg || '获取二维码失败，请稍后重试'
      qrState.value.loading = false
    }
  } catch (err) {
    qrState.value.status = 'ERROR'
    qrState.value.msg = err.message || '网络通信失败，请稍后重试'
    qrState.value.loading = false
  }
}

function startQrPolling() {
  const uuid = qrState.value.uuid
  const poll = async () => {
    if (!showLoginModal.value || qrState.value.uuid !== uuid) return
    try {
      const res = await apiFetch('/api/auth/qr/status')
      let json
      try {
        json = await res.json()
      } catch {
        throw new Error('登录服务返回了无法读取的响应，请稍后重试或刷新二维码')
      }
      if (!showLoginModal.value || qrState.value.uuid !== uuid) return
      if (!res.ok || !json?.data) throw new Error(json?.detail || '暂时无法核验二维码')
      const state = json.data.status
      qrState.value.status = state
      qrState.value.msg = json.data.msg
      if (state === 'SUCCESS') {
        auth.value.loggedIn = true
        auth.value.username = json.data.username
        showToast(`登录成功！欢迎，${auth.value.username || '铁路用户'}`, 'success')
        fetchPassengers()
        fetchUnpaidOrder()
        closeLoginModal()
        return
      }
      if (['EXPIRED', 'ERROR'].includes(state)) return
    } catch (err) {
      qrState.value.msg = err.message
    }
    // 等本次请求结束再安排下一次，防止网络缓慢时重复换取扫码凭据。
    if (showLoginModal.value && qrState.value.uuid === uuid) qrState.value.pollTimer = setTimeout(poll, 1500)
  }
  qrState.value.pollTimer = setTimeout(poll, 1500)
}

async function doLogout() {
  try {
    const res = await apiFetch('/api/auth/logout', { method: 'POST' })
    if (!res.ok) throw new Error('退出失败')
    auth.value.loggedIn = false
    auth.value.username = null
    passengers.value = []
    unpaidOrder.value = null
    autoContinueBooking = false
    clearTimeout(bookingPollTimer)
    bookingTask.value = null
    showBookingProgress.value = false
    showBookingModal.value = false
    localStorage.removeItem('railhop_booking_id')
    showToast('已安全退出 12306 登录', 'info')
  } catch (err) {
    showToast('登出失败', 'error')
  }
}

// ==================== 乘车人与未完成订单 ====================

async function fetchPassengers() {
  passengersLoading.value = true
  try {
    const res = await apiFetch('/api/passengers')
    const json = await res.json()
    if (json.code === 200 && Array.isArray(json.data)) {
      passengers.value = json.data
    }
  } catch (err) {
    console.error('Fetch passengers error', err)
  } finally {
    passengersLoading.value = false
  }
}

async function fetchUnpaidOrder() {
  try {
    const res = await apiFetch('/api/orders/unpaid')
    const json = await res.json()
    if (json.code === 200 && json.data) {
      unpaidOrder.value = json.data
    } else if (json.code === 200) {
      unpaidOrder.value = null
    } else {
      showToast(json.detail || '订单暂时查询失败，请稍后刷新', 'error')
    }
  } catch (err) {
    console.error('Fetch unpaid order error', err)
  }
}

function openUnpaidModal() {
  showUnpaidModal.value = true
}

async function cancelCurrentOrder(sequenceNo) {
  if (!confirm(`确定要取消订单 ${sequenceNo} 吗？\n特别提示：12306 规定每天最多取消 3 次订单，请谨慎操作。`)) {
    return
  }
  try {
    const res = await apiFetch(`/api/orders/cancel?sequence_no=${sequenceNo}`, { method: 'POST' })
    const json = await res.json()
    if (json.code === 200) {
      showToast('订单已成功取消', 'success')
      unpaidOrder.value = null
      showUnpaidModal.value = false
    } else {
      showToast(json.detail || json.msg || '取消失败', 'error')
    }
  } catch (err) {
    showToast('操作异常', 'error')
  }
}

// ==================== 购票预订流水线 ====================

function isHighSpeedTrain(train) {
  if (!train) return false
  return /^[GDC]/i.test(train.train_code)
}

function getAvailableBookingSeats(train) {
  if (!train) return []
  const prices = train.prices || {}
  const options = [['ze', 'O', '二等座'], ['zy', 'M', '一等座'], ['swz', '9', '商务座'],
    ['yw', '3', '硬卧'], ['rw', '4', '软卧'], ['srrb', 'F', '动卧'], ['yz', '1', '硬座']]
  // 无座需根据官方车种和票额单独处理，不能用硬座代码冒充无座。
  return options.filter(([key]) => train.seats?.[key] === '有' || Number(train.seats?.[key]) > 0)
    .map(([key, code, name]) => ({ code, name, price: prices[key] ? `(${prices[key]})` : '' }))
}

function openBookingModal(train) {
  if (!auth.value.loggedIn) {
    showToast('请先登录 12306 账号再进行预订', 'info')
    openLoginModal()
    return
  }

  bookingTrain.value = train
  bookingPlan.value = null
  orderSubmitting.value = false
  orderSuccessResult.value = null
  chooseSeatLetter.value = ''
  selectedBookingPassengers.value = []

  // 默认勾选第一个乘车人 (若存在)
  if (passengers.value.length > 0) {
    const firstP = passengers.value[0]
    const defaultSeat = getAvailableBookingSeats(train)[0]?.code || ''
    selectedBookingPassengers.value.push({
      passenger_name: firstP.passenger_name,
      passenger_id_type_code: firstP.passenger_id_type_code || '1',
      passenger_id_no: firstP.passenger_id_no_raw,
      passenger_type: firstP.passenger_type || '1',
      mobile_no: firstP.mobile_no || '',
      seat_type: defaultSeat,
      allEncStr: firstP.allEncStr || ''
    })
  }

  showBookingModal.value = true
}

function closeBookingModal() {
  if (orderSubmitting.value) return
  showBookingModal.value = false
  bookingTrain.value = null
}

function isPassengerSelected(p) {
  return selectedBookingPassengers.value.some(sp => sp.passenger_id_no === p.passenger_id_no_raw)
}

function getSelectedPassengerItem(p) {
  return selectedBookingPassengers.value.find(sp => sp.passenger_id_no === p.passenger_id_no_raw)
}

function togglePassenger(p) {
  const idx = selectedBookingPassengers.value.findIndex(sp => sp.passenger_id_no === p.passenger_id_no_raw)
  if (idx >= 0) {
    selectedBookingPassengers.value.splice(idx, 1)
  } else {
    const defaultSeat = getAvailableBookingSeats(bookingTrain.value)[0]?.code || ''
    selectedBookingPassengers.value.push({
      passenger_name: p.passenger_name,
      passenger_id_type_code: p.passenger_id_type_code || '1',
      passenger_id_no: p.passenger_id_no_raw,
      passenger_type: p.passenger_type || '1',
      mobile_no: p.mobile_no || '',
      seat_type: defaultSeat,
      allEncStr: p.allEncStr || ''
    })
  }
}

async function doSubmitOrder() {
  if (orderSubmitting.value) return
  if (selectedBookingPassengers.value.length === 0) {
    showToast('请至少选择一位乘车人', 'error')
    return
  }

  orderSubmitting.value = true
  submitStepText.value = '第 1/4 步: 校验乘车人与排队余票...'

  if (bookingPlan.value) {
    try {
      const res = await apiFetch('/api/bookings', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: bookingPlan.value.plan_id, passengers: selectedBookingPassengers.value, choose_seats: chooseSeatLetter.value })
      })
      const json = await res.json()
      if (!res.ok || !json.data?.id) throw new Error(json.detail || '无法建立方案购票任务')
      bookingTask.value = json.data
      localStorage.setItem('railhop_booking_id', json.data.id)
      autoContinueBooking = true
      showBookingProgress.value = true
      orderSubmitting.value = false
      closeBookingModal()
      await advanceBookingTask()
    } catch (err) {
      showToast(err.message, 'error', 5000)
    } finally {
      orderSubmitting.value = false
    }
    return
  }

  const payload = {
    secret_str: bookingTrain.value.secret_str,
    train_date: bookingTrain.value.train_date || queryDate.value,
    back_train_date: bookingTrain.value.train_date || queryDate.value,
    train_code: bookingTrain.value.train_code,
    train_no: bookingTrain.value.train_no,
    from_station_name: bookingTrain.value.from_station_name,
    to_station_name: bookingTrain.value.to_station_name,
    from_station_telecode: bookingTrain.value.from_station_telecode,
    to_station_telecode: bookingTrain.value.to_station_telecode,
    purpose_codes: 'ADULT',
    passengers: selectedBookingPassengers.value,
    choose_seats: chooseSeatLetter.value || ''
  }

  try {
    submitStepText.value = '第 2/4 步: 提交 12306 排队流水线...'
    const res = await apiFetch('/api/orders/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const json = await res.json()

    if (json.code === 200 && json.data?.success) {
      submitStepText.value = '第 3/4 步: 锁座成功！'
      orderSuccessResult.value = json.data
      orderSubmitting.value = false
      fetchUnpaidOrder()
    } else if (json.data?.status === 'UNKNOWN') {
      orderSuccessResult.value = json.data
      orderSubmitting.value = false
    } else {
      const errMsg = json.detail || json.data?.msg || json.msg || '购票排队失败'
      showToast(errMsg, 'error', 4000)
      orderSubmitting.value = false
    }
  } catch (err) {
    console.error('Submit order error', err)
    orderSuccessResult.value = { success: false, status: 'UNKNOWN', order_id: null, msg: '连接中断，请先查询原订单结果，避免重复提交' }
    showToast('提交结果未确认，请先查询原订单', 'error')
    orderSubmitting.value = false
  }
}

async function refreshSingleOrder() {
  if (orderSubmitting.value) return
  orderSubmitting.value = true
  try {
    const res = await apiFetch('/api/orders/pending')
    const json = await res.json()
    if (!res.ok) throw new Error(json.detail || '暂时无法查询原订单')
    orderSuccessResult.value = json.data
    fetchUnpaidOrder()
  } catch (err) {
    showToast(err.message, 'error')
  } finally {
    orderSubmitting.value = false
  }
}

function openPlanBooking(plan, train) {
  openBookingModal(train)
  if (showBookingModal.value) bookingPlan.value = plan
}

async function openOfficialPayment(step) {
  // 点击时先打开窗口，避免网络请求完成后被浏览器判定为弹窗拦截。
  const popup = window.open('about:blank', '_blank')
  if (popup) popup.opener = null
  try {
    const res = await apiFetch(`/api/orders/${encodeURIComponent(step.order_id)}/payment?kind=${step.kind}`, { method: 'POST' })
    const json = await res.json()
    if (!res.ok) throw new Error(json.detail || '无法进入官方付款页面')
    const url = new URL(json.data.url)
    if (url.protocol !== 'https:' || url.hostname !== 'kyfw.12306.cn') throw new Error('付款地址不是12306官方地址')
    if (popup) popup.location.href = url.href
    else window.open(url.href, '_blank', 'noopener,noreferrer')
    showToast(json.data.msg, 'info', 7000)
  } catch (err) {
    popup?.close()
    showToast(err.message, 'error', 5000)
  }
}

function scheduleBookingRefresh() {
  clearTimeout(bookingPollTimer)
  if (bookingTask.value && !['COMPLETED', 'STOPPED'].includes(bookingTask.value.status)) {
    bookingPollTimer = setTimeout(refreshBookingTask, 5000)
  }
}

async function refreshBookingTask() {
  if (!bookingTask.value?.id || bookingTaskBusy.value) return
  bookingTaskBusy.value = true
  try {
    const res = await apiFetch(`/api/bookings/${bookingTask.value.id}`)
    const json = await res.json()
    if (res.status === 404) {
      bookingTask.value = null
      autoContinueBooking = false
      localStorage.removeItem('railhop_booking_id')
      showBookingProgress.value = false
      showToast('本地购票任务已失效，请在12306核对已有订单后重新选择方案', 'info', 7000)
      return
    }
    if (!res.ok) throw new Error(json.detail || '暂时无法查询购票进度')
    bookingTask.value = json.data
    bookingTaskError.value = ''
  } catch (err) {
    bookingTaskError.value = err.message
  } finally {
    bookingTaskBusy.value = false
  }
  if (autoContinueBooking && bookingTask.value?.status === 'READY' && !bookingTaskError.value) {
    await advanceBookingTask()
  }
  scheduleBookingRefresh()
}

async function advanceBookingTask() {
  if (bookingTaskBusy.value || bookingTask.value?.status !== 'READY') return
  bookingTaskBusy.value = true
  autoContinueBooking = true
  try {
    const res = await apiFetch(`/api/bookings/${bookingTask.value.id}/advance`, { method: 'POST' })
    const json = await res.json()
    if (!res.ok) throw new Error(json.detail || '当前段下单失败')
    bookingTask.value = json.data
    bookingTaskError.value = ''
    if (json.data.status === 'FAIL') autoContinueBooking = false
    fetchUnpaidOrder()
  } catch (err) {
    bookingTaskError.value = err.message
    autoContinueBooking = false
  } finally {
    bookingTaskBusy.value = false
    scheduleBookingRefresh()
  }
}

async function stopBookingTask() {
  if (!confirm('停止后续自动购票？已有12306订单会保留，请自行支付或取消。')) return
  autoContinueBooking = false
  try {
    const res = await apiFetch(`/api/bookings/${bookingTask.value.id}/stop`, { method: 'POST' })
    const json = await res.json()
    if (!res.ok) throw new Error(json.detail || '停止失败')
    bookingTask.value = json.data
    clearTimeout(bookingPollTimer)
  } catch (err) {
    bookingTaskError.value = err.message
  }
}

async function retryBookingTask() {
  if (bookingTaskBusy.value || bookingTask.value?.status !== 'FAIL') return
  bookingTaskBusy.value = true
  autoContinueBooking = true
  try {
    const res = await apiFetch(`/api/bookings/${bookingTask.value.id}/retry`, { method: 'POST' })
    const json = await res.json()
    if (!res.ok) throw new Error(json.detail || '重试失败，请刷新官方状态')
    bookingTask.value = json.data
    bookingTaskError.value = ''
  } catch (err) {
    bookingTaskError.value = err.message
    autoContinueBooking = false
  } finally {
    bookingTaskBusy.value = false
    scheduleBookingRefresh()
  }
}

// ==================== 车站输入联想与查票 ====================

let debounceTimer = null

async function fetchSuggestions(kw) {
  try {
    const res = await apiFetch(`/api/stations/search?keyword=${encodeURIComponent(kw || '')}&limit=12`)
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
let currentTicketRequestId = 0
async function doQueryTickets() {
  if (!fromStation.value.trim() || !toStation.value.trim() || !trainDate.value) {
    showToast('请输入出发站、到达站及乘车日期', 'error')
    return
  }

  const reqId = ++currentTicketRequestId
  const requestedDate = trainDate.value
  currentPlanRequestId++
  isLoading.value = true
  activePlanTrain.value = null
  smartPlans.value = []
  activeStops.value = []

  try {
    const url = `/api/tickets/query?train_date=${requestedDate}&from_station=${encodeURIComponent(fromStation.value.trim())}&to_station=${encodeURIComponent(toStation.value.trim())}`
    const res = await apiFetch(url)
    const json = await res.json()
    if (reqId !== currentTicketRequestId) return

    if (json.code === 200 && Array.isArray(json.data)) {
      queryDate.value = requestedDate
      trainResults.value = json.data.map(t => ({ ...t, train_date: queryDate.value }))
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
    if (reqId === currentTicketRequestId) isLoading.value = false
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

// 展开/收起某趟车的智能跨站方案
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

    const stopsPromise = apiFetch(
      `/api/tickets/stops?train_no=${train.train_no}&from_station=${encodeURIComponent(train.from_station_name)}&to_station=${encodeURIComponent(train.to_station_name)}&depart_date=${train.train_date}`
    ).then(r => r.json())

    const planPromise = apiFetch(
      `/api/smart-plans/calculate?train_date=${train.train_date}&train_code=${train.train_code}&train_no=${train.train_no}&from_station=${encodeURIComponent(train.from_station_name)}&to_station=${encodeURIComponent(train.to_station_name)}&allowed_seats=${allowedParam}&max_tickets=${selectedMaxTickets.value}`
    ).then(r => r.json())

    const [stopsRes, planRes] = await Promise.all([stopsPromise, planPromise])

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
    ...plan.segments.map((s, idx) => `  ${idx + 1}. [${s.is_extension ? '官方候补' : '官方购票'}] ${s.train_date} ${s.from_station} -> ${s.to_station} (${s.seat_name} ${s.seat_status}${s.seat_price ? ' ' + s.seat_price : ''})`),
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
