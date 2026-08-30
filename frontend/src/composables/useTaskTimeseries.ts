import { ref, watch } from 'vue'
import {
  getTaskMetricsTimeseriesApi,
  type TaskMetricsTimeseriesResponse,
  type TimeseriesWindowSeconds,
} from '@/api/task'
import { useAdaptivePolling } from './useAdaptivePolling'
import { getErrorMessage } from './usePollErrorNotice'

export interface UseTaskTimeseriesOptions {
  /** 当前项目 public_id，返回空字符串时不发起请求。 */
  projectPublicId: () => string
  /** 时序窗口范围，例如最近 30 分钟、1 小时等。 */
  windowSeconds: () => TimeseriesWindowSeconds
  /** 外部控制是否启用时序轮询，通常只在指标面板展开后启用。 */
  enabled: () => boolean
  /** 时序数据刷新间隔，默认 10 秒。 */
  intervalMs?: number
}

/**
 * 加载任务指标时序数据。
 *
 * 用于任务页指标折线图，负责按时间窗口刷新数据，并在窗口切换或面板展开时主动刷新。
 */
export function useTaskTimeseries(opts: UseTaskTimeseriesOptions) {
  const interval = opts.intervalMs ?? 10000

  const timeseries = ref<TaskMetricsTimeseriesResponse | null>(null)
  const loading = ref(false)
  const errorMessage = ref<string | null>(null)
  const lastUpdatedAt = ref<number | null>(null)

  const loadTimeseries = async () => {
    const id = opts.projectPublicId()
    if (!id) return
    // 首次加载显示 loading，已有数据时静默刷新，保持图表稳定。
    if (!timeseries.value) loading.value = true
    try {
      const { data } = await getTaskMetricsTimeseriesApi(id, opts.windowSeconds())
      timeseries.value = data
      errorMessage.value = null
      lastUpdatedAt.value = Date.now()
    } catch (error) {
      errorMessage.value = getErrorMessage(error, '加载时序指标失败')
      console.error('加载任务时序指标失败', error)
    } finally {
      loading.value = false
    }
  }

  const poll = useAdaptivePolling({
    task: loadTimeseries,
    interval: () => interval,
    enabled: () => Boolean(opts.projectPublicId()) && opts.enabled(),
    // 图表默认折叠，不在 start 时立即请求，等展开后再刷新。
    immediate: false,
  })

  watch(
    () => opts.windowSeconds(),
    () => {
      // 切换时间窗口后清空旧图表，避免不同窗口的数据短暂混在一起。
      timeseries.value = null
      if (poll.running.value) {
        void poll.refreshNow()
      }
    },
  )

  watch(
    () => opts.enabled(),
    (next, prev) => {
      // 从折叠切换为展开时立刻加载一次，避免等待下一轮定时器。
      if (next && !prev && poll.running.value) {
        void poll.refreshNow()
      }
    },
  )

  return {
    timeseries,
    loading,
    errorMessage,
    lastUpdatedAt,
    start: poll.start,
    stop: poll.stop,
    refreshNow: poll.refreshNow,
    running: poll.running,
  }
}
