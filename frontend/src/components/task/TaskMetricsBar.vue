<template>
  <section class="metrics-bar" :class="{ expanded }">
    <header class="bar-row">
      <div class="seg queue-seg">
        <div class="seg-head">
          <span class="seg-label">队列堆积</span>
          <span class="seg-value mono">{{ formatNumber(queueStats?.pendingItemCount) }}</span>
        </div>
        <div class="seg-meta">
          <span class="dim">排队</span>
          <span class="mono">{{ formatNumber(queueStats?.pendingItemCount) }}</span>
          <span class="sep">·</span>
          <span class="dim">运行</span>
          <span class="mono">{{ formatNumber(queueStats?.runningItemCount) }}</span>
          <span class="sep">·</span>
          <span class="dim">5 分钟重排</span>
          <span class="mono">{{ formatNumber(queueStats?.requeueLast5Min) }}</span>
        </div>
      </div>

      <div class="seg activity-seg">
        <div class="seg-head">
          <span class="seg-label">最近 1 分钟</span>
          <span class="seg-value mono">{{ formatNumber(lastMinute?.completedItemCount) }}</span>
        </div>
        <div class="seg-meta">
          <span class="dim">提交</span>
          <span class="mono">{{ formatNumber(lastMinute?.submittedItemCount) }}</span>
          <span class="sep">·</span>
          <span class="dim">完成</span>
          <span class="mono">{{ formatNumber(lastMinute?.completedItemCount) }}</span>
          <span class="sep">·</span>
          <span class="dim">失败</span>
          <span class="mono failed">{{ formatNumber(lastMinute?.failedItemCount) }}</span>
          <span class="sep">·</span>
          <span class="dim">均耗时</span>
          <span class="mono">{{ formatMs(lastMinute?.avgDurationMs) }}</span>
        </div>
      </div>

      <div class="bar-trailing">
        <span v-if="errorMessage" class="err" :title="errorMessage">
          <el-icon><Warning /></el-icon>
        </span>
        <span v-else-if="lastUpdatedAt" class="updated dim" :title="`更新于 ${formatTimestamp(lastUpdatedAt)}`">
          {{ formatRelative(lastUpdatedAt, now) }}
        </span>
        <button class="toggle-btn" type="button" @click="toggleExpanded">
          <el-icon class="caret" :class="{ rotated: expanded }"><ArrowDownBold /></el-icon>
          <span>{{ expanded ? '收起' : '展开' }}</span>
        </button>
      </div>
    </header>

    <div v-if="expanded" class="bar-panel">
      <aside class="panel-side">
        <section class="side-card">
          <div class="card-head">队列堆积</div>
          <ul class="card-list">
            <li><span>排队中</span><span class="mono">{{ formatNumber(queueStats?.pendingItemCount) }}</span></li>
            <li><span>运行中</span><span class="mono">{{ formatNumber(queueStats?.runningItemCount) }}</span></li>
            <li><span>5 分钟重排</span><span class="mono">{{ formatNumber(queueStats?.requeueLast5Min) }}</span></li>
          </ul>
        </section>
        <section class="side-card">
          <div class="card-head">窗口汇总</div>
          <ul class="card-list">
            <li><span class="dim">提交</span><span class="mono">{{ formatNumber(windowTotals.submitted) }}</span></li>
            <li><span class="dim">完成</span><span class="mono">{{ formatNumber(windowTotals.completed) }}</span></li>
            <li><span class="dim">失败</span><span class="mono failed">{{ formatNumber(windowTotals.failed) }}</span></li>
            <li><span class="dim">均耗时</span><span class="mono">{{ formatMs(windowTotals.avgDurationMs) }}</span></li>
          </ul>
        </section>
      </aside>

      <section class="panel-chart">
        <div class="chart-head">
          <div class="chart-title">
            <span class="title-label">活跃度时序</span>
            <span v-if="timeseriesErrorMessage" class="title-err" :title="timeseriesErrorMessage">
              <el-icon><Warning /></el-icon>
              加载失败
            </span>
            <span
              v-else-if="timeseriesUpdatedAt"
              class="title-meta dim"
              :title="`更新于 ${formatTimestamp(timeseriesUpdatedAt)}`"
            >
              {{ formatRelative(timeseriesUpdatedAt, now) }} · 每桶 {{ bucketSecondsLabel }}
            </span>
            <span v-else class="title-meta dim">加载中…</span>
          </div>
          <el-select
            v-model="windowSeconds"
            class="window-select"
            popper-class="metrics-window-popper"
            size="small"
            :teleported="true"
          >
            <el-option
              v-for="opt in windowOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div class="chart-body">
          <VueApexCharts
            v-if="hasChartData"
            type="line"
            height="300"
            :options="chartOptions"
            :series="chartSeries"
          />
          <div v-else class="chart-empty">
            <span>{{ timeseriesErrorMessage ? '加载失败,稍后重试' : '暂无数据' }}</span>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue'
import { ElIcon, ElOption, ElSelect } from 'element-plus'
import { ArrowDownBold, Warning } from '@element-plus/icons-vue'
import VueApexCharts from 'vue3-apexcharts'
import type { ApexAxisChartSeries, ApexFormatterOpts, ApexOptions } from 'apexcharts'
import {
  TIMESERIES_WINDOW_OPTIONS,
  type TimeseriesPoint,
  type TimeseriesWindowSeconds,
} from '@/api/task'
import { useTaskMetrics } from '@/composables/useTaskMetrics'
import { useTaskTimeseries } from '@/composables/useTaskTimeseries'

const props = defineProps<{
  projectPublicId: string
}>()

const expanded = ref(false)
const now = ref(Date.now())
const windowSeconds = ref<TimeseriesWindowSeconds>(1800)
const windowOptions = TIMESERIES_WINDOW_OPTIONS
let tickHandle: ReturnType<typeof setInterval> | null = null

const { metrics, errorMessage, lastUpdatedAt, start } = useTaskMetrics({
  projectPublicId: () => props.projectPublicId,
  expanded: () => expanded.value,
})

const {
  timeseries,
  errorMessage: timeseriesErrorMessage,
  lastUpdatedAt: timeseriesUpdatedAt,
  start: startTimeseries,
} = useTaskTimeseries({
  projectPublicId: () => props.projectPublicId,
  windowSeconds: () => windowSeconds.value,
  enabled: () => expanded.value,
})

const queueStats = computed(() => metrics.value?.queueStats ?? null)
const recentActivity = computed(() => metrics.value?.recentActivity ?? null)
const lastMinute = computed(() => recentActivity.value?.lastMinute ?? null)

const toggleExpanded = () => {
  expanded.value = !expanded.value
}

const formatNumber = (value: number | null | undefined) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (Number.isInteger(value)) return value.toLocaleString('zh-CN')
  return value.toFixed(2)
}

const formatMs = (value: number | null | undefined) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '—'
  if (value < 1000) return `${value.toFixed(0)} ms`
  return `${(value / 1000).toFixed(2)} s`
}

const formatTimestamp = (value: number) => {
  const t = new Date(value)
  if (Number.isNaN(t.getTime())) return '—'
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`
}

const formatRelative = (ts: number, current: number) => {
  const diff = Math.max(0, Math.floor((current - ts) / 1000))
  if (diff < 5) return '刚刚'
  if (diff < 60) return `${diff} 秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  return `${Math.floor(diff / 3600)} 小时前`
}

const points = computed(() => timeseries.value?.points ?? [])

const hasChartData = computed(() => points.value.length > 0)

const windowTotals = computed(() => {
  const data = points.value
  if (!data.length) {
    return { submitted: 0, completed: 0, failed: 0, avgDurationMs: 0 }
  }
  let submitted = 0
  let completed = 0
  let failed = 0
  let durationSum = 0
  let durationCount = 0
  for (const p of data) {
    submitted += p.submittedItemCount
    completed += p.completedItemCount
    failed += p.failedItemCount
    if (p.avgDurationMs > 0 && p.completedItemCount > 0) {
      durationSum += p.avgDurationMs * p.completedItemCount
      durationCount += p.completedItemCount
    }
  }
  return {
    submitted,
    completed,
    failed,
    avgDurationMs: durationCount > 0 ? Math.round(durationSum / durationCount) : 0,
  }
})

const bucketSecondsLabel = computed(() => {
  const sec = timeseries.value?.bucketSeconds ?? 0
  if (!sec) return '—'
  if (sec < 60) return `${sec} 秒`
  if (sec < 3600) return `${Math.round(sec / 60)} 分钟`
  return `${Math.round(sec / 3600)} 小时`
})

const chartSeries = computed<ApexAxisChartSeries>(() => {
  const data = points.value
  const toXY = (key: 'submittedItemCount' | 'completedItemCount' | 'failedItemCount' | 'avgDurationMs') =>
    data.map((p: TimeseriesPoint): [number, number] => [new Date(p.bucketStart).getTime(), p[key]])
  return [
    { name: '提交', data: toXY('submittedItemCount') },
    { name: '完成', data: toXY('completedItemCount') },
    { name: '失败', data: toXY('failedItemCount') },
    { name: '均耗时 (ms)', data: toXY('avgDurationMs') },
  ]
})

const chartOptions = computed((): ApexOptions => ({
  chart: {
    type: 'line',
    background: 'transparent',
    toolbar: { show: false },
    zoom: { enabled: false },
    animations: { enabled: false },
  },
  theme: { mode: 'dark' },
  colors: ['#7aa2f7', '#9ece6a', '#f7768e', '#e0af68'],
  stroke: {
    curve: 'smooth',
    width: [2, 2, 2, 2],
    dashArray: [0, 0, 0, 4],
  },
  markers: { size: 0, hover: { size: 4 } },
  grid: {
    borderColor: 'rgba(255, 255, 255, 0.08)',
    strokeDashArray: 3,
    padding: { left: 4, right: 4, top: 0, bottom: 0 },
  },
  legend: {
    position: 'top',
    horizontalAlign: 'right',
    labels: { colors: '#cbd5e1' },
    markers: { size: 10, shape: 'circle' },
    itemMargin: { horizontal: 12, vertical: 0 },
  },
  dataLabels: { enabled: false },
  xaxis: {
    type: 'datetime',
    labels: {
      style: { colors: '#8b949e', fontSize: '11px' },
      datetimeUTC: false,
    },
    axisBorder: { show: false },
    axisTicks: { color: 'rgba(255, 255, 255, 0.08)' },
  },
  yaxis: [
    {
      seriesName: ['提交', '完成', '失败'],
      labels: {
        style: { colors: '#8b949e', fontSize: '11px' },
        formatter: (val: number) => (Number.isInteger(val) ? val.toString() : val.toFixed(0)),
      },
      title: { text: '条目数', style: { color: '#6e7681', fontSize: '11px' } },
      forceNiceScale: true,
      min: 0,
    },
    { show: false, seriesName: '提交' },
    { show: false, seriesName: '完成' },
    {
      opposite: true,
      seriesName: '均耗时 (ms)',
      labels: {
        style: { colors: '#8b949e', fontSize: '11px' },
        formatter: (val: number) => {
          if (val < 1000) return `${val.toFixed(0)}ms`
          return `${(val / 1000).toFixed(1)}s`
        },
      },
      title: { text: '均耗时', style: { color: '#6e7681', fontSize: '11px' } },
      forceNiceScale: true,
      min: 0,
    },
  ],
  tooltip: {
    theme: 'dark',
    shared: true,
    x: { format: 'yyyy-MM-dd HH:mm:ss' },
    y: {
      formatter: (val: number, opts?: ApexFormatterOpts) => {
        if (opts?.seriesIndex === 3) {
          if (val < 1000) return `${val.toFixed(0)} ms`
          return `${(val / 1000).toFixed(2)} s`
        }
        return val.toString()
      },
    },
  },
}))

onMounted(() => {
  start()
  startTimeseries()
  tickHandle = setInterval(() => {
    now.value = Date.now()
  }, 5000)
})

onScopeDispose(() => {
  if (tickHandle !== null) {
    clearInterval(tickHandle)
    tickHandle = null
  }
})
</script>

<style scoped>
.metrics-bar {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.015));
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.32);
  overflow: hidden;
}

.bar-row {
  display: grid;
  grid-template-columns: 1fr 1.4fr auto;
  gap: 18px;
  align-items: center;
  padding: 14px 18px;
}

.seg {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.seg-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
}

.seg-label {
  color: #c5cdd6;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.seg-value {
  color: #f2f4f8;
  font-size: 14px;
  font-weight: 700;
}

.seg-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  font-size: 11px;
  color: #cbd5e1;
}

.seg-meta .dim {
  color: #6e7681;
}

.seg-meta .sep {
  color: #4a5563;
  margin: 0 1px;
}

.seg-meta .failed {
  color: #fca5a5;
}

.bar-trailing {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-self: end;
}

.bar-trailing .err {
  color: #fca5a5;
  display: inline-flex;
}

.bar-trailing .updated {
  font-size: 11px;
  color: #6e7681;
}

.toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #e6edf3;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.toggle-btn:hover,
.toggle-btn:focus {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
}

.toggle-btn .caret {
  font-size: 12px;
  transition: transform 0.18s ease;
}

.toggle-btn .caret.rotated {
  transform: rotate(180deg);
}

.mono {
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.bar-panel {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 14px;
  padding: 0 18px 16px;
}

.panel-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.side-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.025);
}

.side-card .card-head {
  color: #c5cdd6;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.card-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-list li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  color: #cbd5e1;
  font-size: 12px;
}

.card-list li span:first-child {
  color: #8b949e;
}

.card-list .failed {
  color: #fca5a5;
}

.dim {
  color: #6e7681;
}

.panel-chart {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px 8px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.025);
  min-width: 0;
}

.chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chart-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.chart-title .title-label {
  color: #e6edf3;
  font-size: 13px;
  font-weight: 600;
}

.chart-title .title-meta {
  font-size: 11px;
  color: #6e7681;
}

.chart-title .title-err {
  color: #fca5a5;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.window-select {
  width: 148px;
}

.window-select :deep(.el-select__wrapper) {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: none;
}

.window-select :deep(.el-select__wrapper.is-hovering) {
  border-color: rgba(255, 255, 255, 0.18);
}

.window-select :deep(.el-select__wrapper.is-focused) {
  border-color: #7aa2f7;
  box-shadow: 0 0 0 1px #7aa2f7;
}

.window-select :deep(.el-select__placeholder),
.window-select :deep(.el-select__selected-item) {
  color: #e6edf3;
}

.window-select :deep(.el-select__caret) {
  color: #8b949e;
}

.chart-body {
  min-height: 300px;
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: #6e7681;
  font-size: 12px;
  border: 1px dashed rgba(255, 255, 255, 0.08);
  border-radius: 10px;
}

@media (max-width: 1180px) {
  .bar-row {
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .bar-trailing {
    grid-column: 1 / -1;
    justify-self: flex-end;
  }
  .bar-panel {
    grid-template-columns: 1fr;
  }
  .panel-side {
    flex-direction: row;
  }
  .side-card {
    flex: 1;
  }
}

@media (max-width: 720px) {
  .panel-side {
    flex-direction: column;
  }
}
</style>

<style>
/* 时序窗口下拉框 teleport 到 body 后无法被 scoped 命中,使用全局样式确保暗黑配色 */
.metrics-window-popper.el-popper {
  background: #1a1d23 !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}

.metrics-window-popper .el-select-dropdown {
  background: #1a1d23;
  border: none;
}

.metrics-window-popper .el-select-dropdown__wrap,
.metrics-window-popper .el-scrollbar,
.metrics-window-popper .el-scrollbar__wrap,
.metrics-window-popper .el-scrollbar__view {
  background: #1a1d23;
}

.metrics-window-popper .el-select-dropdown__list {
  padding: 6px 4px;
}

.metrics-window-popper .el-select-dropdown__item {
  color: #c5cdd6;
  border-radius: 8px;
  margin: 2px 4px;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.metrics-window-popper .el-select-dropdown__item:hover,
.metrics-window-popper .el-select-dropdown__item.hover,
.metrics-window-popper .el-select-dropdown__item.is-hovering {
  background: rgba(255, 255, 255, 0.04);
  color: #ffffff;
}

.metrics-window-popper .el-select-dropdown__item.selected,
.metrics-window-popper .el-select-dropdown__item.is-selected {
  color: #7aa2f7;
  background: rgba(122, 162, 247, 0.12);
  font-weight: 600;
}

.metrics-window-popper .el-select-dropdown__item.is-disabled {
  color: #4d5560;
  background: transparent;
}

.metrics-window-popper .el-select-dropdown__wrap::-webkit-scrollbar {
  width: 6px;
}

.metrics-window-popper .el-select-dropdown__wrap::-webkit-scrollbar-track {
  background: transparent;
}

.metrics-window-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.3);
  border-radius: 999px;
}

.metrics-window-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}

.metrics-window-popper .el-popper__arrow::before {
  background: #1a1d23 !important;
  border-color: rgba(255, 255, 255, 0.08) !important;
}

/* ApexCharts 的 tooltip/menu 使用库内绝对定位，需额外覆盖浅色默认样式。 */
.metrics-bar .apexcharts-tooltip,
.metrics-bar .apexcharts-tooltip.apexcharts-theme-light,
.metrics-bar .apexcharts-tooltip.apexcharts-theme-dark {
  background: rgba(13, 17, 23, 0.96) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45) !important;
  color: #e6edf3;
}

.metrics-bar .apexcharts-tooltip-title {
  background: rgba(255, 255, 255, 0.04) !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
  color: #cbd5e1;
}

.metrics-bar .apexcharts-tooltip-text,
.metrics-bar .apexcharts-tooltip-y-group,
.metrics-bar .apexcharts-tooltip-series-group,
.metrics-bar .apexcharts-tooltip-text-y-label,
.metrics-bar .apexcharts-tooltip-text-y-value {
  color: #e6edf3 !important;
}

.metrics-bar .apexcharts-xaxistooltip,
.metrics-bar .apexcharts-yaxistooltip {
  background: rgba(13, 17, 23, 0.96) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  color: #e6edf3 !important;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.38) !important;
}

.metrics-bar .apexcharts-xaxistooltip::before,
.metrics-bar .apexcharts-xaxistooltip::after,
.metrics-bar .apexcharts-yaxistooltip::before,
.metrics-bar .apexcharts-yaxistooltip::after {
  border-bottom-color: rgba(13, 17, 23, 0.96) !important;
}

.metrics-bar .apexcharts-menu {
  background: #1a1d23 !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45) !important;
}

.metrics-bar .apexcharts-menu-item {
  color: #cbd5e1 !important;
  background: transparent !important;
}

.metrics-bar .apexcharts-menu-item:hover {
  color: #ffffff !important;
  background: rgba(255, 255, 255, 0.06) !important;
}
</style>
