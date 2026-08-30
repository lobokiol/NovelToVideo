import { computed, ref, watch, type Ref } from 'vue'
import type { TimelineTrack } from '@/components/editor/types'

export interface TimelineHistoryOptions {
  tracks: Ref<TimelineTrack[]>
  /** 加载/恢复等程序性变更期间返回 true，此间不记录快照，仅刷新基线。 */
  isSuppressed: () => boolean
  /** 撤销/重做恢复完成后触发（页面用于清理失效选中并刷新预览）。 */
  onRestore?: () => void
}

const HISTORY_LIMIT = 50
const COMMIT_DEBOUNCE_MS = 400

/**
 * 时间线撤销/重做历史：以轨道 JSON 快照为单元。
 *
 * 依赖 tracks 的 deep watch 自动记录，连续变更（拖拽/滑杆）在防抖窗口内合并为
 * 一条历史；撤销与重做前会先落盘未提交的挂起快照，避免丢失最近一次编辑。
 */
export function useTimelineHistory(opts: TimelineHistoryOptions) {
  const past = ref<string[]>([])
  const future = ref<string[]>([])
  let current = ''
  let restoring = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const capture = () => JSON.stringify(opts.tracks.value)

  const commitNow = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    if (restoring || opts.isSuppressed()) {
      current = capture()
      return
    }
    const snapshot = capture()
    if (snapshot === current) return
    past.value.push(current)
    if (past.value.length > HISTORY_LIMIT) past.value.shift()
    future.value = []
    current = snapshot
  }

  watch(
    opts.tracks,
    () => {
      if (restoring || opts.isSuppressed()) return
      if (timer) clearTimeout(timer)
      timer = setTimeout(commitNow, COMMIT_DEBOUNCE_MS)
    },
    { deep: true },
  )

  const apply = (snapshot: string) => {
    restoring = true
    opts.tracks.value = JSON.parse(snapshot) as TimelineTrack[]
    current = snapshot
    // 恢复引发的 deep watch 在微任务后触发，宏任务里再解除拦截。
    setTimeout(() => {
      restoring = false
    }, 0)
    opts.onRestore?.()
  }

  const undo = () => {
    commitNow()
    const snapshot = past.value.pop()
    if (snapshot === undefined) return
    future.value.push(current)
    apply(snapshot)
  }

  const redo = () => {
    commitNow()
    const snapshot = future.value.pop()
    if (snapshot === undefined) return
    past.value.push(current)
    apply(snapshot)
  }

  /** 以当前状态为新基线并清空历史（加载工程后调用）。 */
  const reset = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    past.value = []
    future.value = []
    current = capture()
  }

  const canUndo = computed(() => past.value.length > 0)
  const canRedo = computed(() => future.value.length > 0)

  return { undo, redo, reset, canUndo, canRedo }
}