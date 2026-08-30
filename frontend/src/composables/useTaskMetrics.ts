import { ref } from 'vue'
import { getTaskMetricsApi, type TaskMetricsResponse } from '@/api/task'
import { useAdaptivePolling } from './useAdaptivePolling'
import { getErrorMessage } from './usePollErrorNotice'

export interface UseTaskMetricsOptions {
  /** 当前项目 public_id，返回空字符串时不发起请求。 */
  projectPublicId: () => string
  /** 指标面板是否展开，展开后使用更高刷新频率。 */
  expanded: () => boolean
  /** 展开状态下的刷新间隔，默认 5 秒。 */
  expandedIntervalMs?: number
  /** 收起状态下的刷新间隔，默认 10 秒。 */
  collapsedIntervalMs?: number
}

/**
 * 加载任务指标快照。
 *
 * 主要供任务页顶部指标条使用，负责维护加载状态、错误信息、最后更新时间和轮询控制。
 */
export function useTaskMetrics(opts: UseTaskMetricsOptions) {
  const expandedInterval = opts.expandedIntervalMs ?? 5000
  const collapsedInterval = opts.collapsedIntervalMs ?? 10000

  const metrics = ref<TaskMetricsResponse | null>(null)
  const loading = ref(false)
  const errorMessage = ref<string | null>(null)
  const lastUpdatedAt = ref<number | null>(null)

  const loadMetrics = async () => {
    const id = opts.projectPublicId()
    if (!id) return
    // 首次加载显示 loading，后续静默刷新，避免指标条频繁闪烁。
    if (!metrics.value) loading.value = true
    try {
      const { data } = await getTaskMetricsApi(id)
      metrics.value = data
      errorMessage.value = null
      lastUpdatedAt.value = Date.now()
    } catch (error) {
      errorMessage.value = getErrorMessage(error, '加载指标失败')
      console.error('加载任务指标失败', error)
    } finally {
      loading.value = false
    }
  }

  const poll = useAdaptivePolling({
    task: loadMetrics,
    // 面板展开时用户正在查看图表细节，使用更短刷新间隔。
    interval: () => (opts.expanded() ? expandedInterval : collapsedInterval),
    enabled: () => Boolean(opts.projectPublicId()),
  })

  return {
    metrics,
    loading,
    errorMessage,
    lastUpdatedAt,
    start: poll.start,
    stop: poll.stop,
    refreshNow: poll.refreshNow,
    running: poll.running,
  }
}
