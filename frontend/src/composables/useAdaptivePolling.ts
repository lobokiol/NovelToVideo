import { onScopeDispose, ref, watch } from 'vue'

export interface AdaptivePollingOptions {
  /** 实际要执行的轮询任务，内部异常会被捕获并输出日志，避免中断后续调度。 */
  task: () => Promise<void> | void
  /** 每轮任务完成后重新计算下一次轮询间隔，便于根据业务状态动态调整频率。 */
  interval: () => number
  /** 返回 false 时暂停执行任务，但仍保留调度循环，等待条件恢复。 */
  enabled?: () => boolean
  /** 是否在 start 后立即执行一次任务，默认立即执行。 */
  immediate?: boolean
  /** 最小轮询间隔保护，避免外部传入过小值造成高频请求。 */
  minIntervalMs?: number
}

/**
 * 通用自适应轮询工具。
 *
 * 适用于任务列表、任务详情、指标面板等需要定时刷新且刷新频率会随状态变化的场景。
 */
export function useAdaptivePolling(opts: AdaptivePollingOptions) {
  const running = ref(false)
  const minInterval = Math.max(0, opts.minIntervalMs ?? 500)
  let timer: ReturnType<typeof setTimeout> | null = null
  let visibilityHandler: (() => void) | null = null
  let inFlight: Promise<void> | null = null

  const clearTimer = () => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const scheduleNext = () => {
    clearTimer()
    if (!running.value) return
    const wait = Math.max(minInterval, opts.interval())
    timer = setTimeout(() => {
      void tick()
    }, wait)
  }

  const runTask = async () => {
    if (inFlight) {
      await inFlight
      return
    }
    // 串行化任务执行，避免手动刷新和定时刷新同时打到后端。
    const exec = (async () => {
      try {
        await opts.task()
      } catch (err) {
        console.error('[useAdaptivePolling] task error', err)
      }
    })()
    inFlight = exec
    try {
      await exec
    } finally {
      inFlight = null
    }
  }

  const tick = async () => {
    if (!running.value) return
    // 条件未满足或页面在后台时，只安排下一轮，不执行实际请求。
    if (opts.enabled && !opts.enabled()) {
      scheduleNext()
      return
    }
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
      scheduleNext()
      return
    }
    await runTask()
    scheduleNext()
  }

  const refreshNow = async () => {
    clearTimer()
    if (!running.value) return
    try {
      await runTask()
    } finally {
      scheduleNext()
    }
  }

  const start = () => {
    if (running.value) return
    running.value = true
    if (opts.immediate !== false) {
      void tick()
    } else {
      scheduleNext()
    }
    // 页面从后台恢复到前台时立即刷新一次，减少用户看到旧数据的时间。
    if (typeof document !== 'undefined') {
      visibilityHandler = () => {
        if (document.visibilityState === 'visible' && running.value) {
          void refreshNow()
        }
      }
      document.addEventListener('visibilitychange', visibilityHandler)
    }
  }

  const stop = () => {
    if (!running.value && timer === null && visibilityHandler === null) return
    running.value = false
    clearTimer()
    if (visibilityHandler && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', visibilityHandler)
    }
    visibilityHandler = null
  }

  watch(
    () => opts.interval(),
    () => {
      // 外部状态导致轮询间隔变化时，重新安排下一轮。
      if (running.value) scheduleNext()
    },
  )

  onScopeDispose(stop)

  return { start, stop, refreshNow, running }
}
