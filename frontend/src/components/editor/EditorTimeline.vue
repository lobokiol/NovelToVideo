<template>
  <section class="timeline-panel">
    <div class="timeline-toolbar">
      <div class="toolbar-group">
        <el-tooltip content="撤销 Ctrl+Z" placement="top">
          <span>
            <el-button size="small" class="ghost-button is-icon" :disabled="!canUndo" @click="emit('undo')">
              <el-icon><RefreshLeft /></el-icon>
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip content="重做 Ctrl+Shift+Z" placement="top">
          <span>
            <el-button size="small" class="ghost-button is-icon" :disabled="!canRedo" @click="emit('redo')">
              <el-icon><RefreshRight /></el-icon>
            </el-button>
          </span>
        </el-tooltip>
        <span class="toolbar-divider"></span>
        <el-tooltip content="在播放头处切割选中片段" placement="top">
          <span>
            <el-button size="small" class="ghost-button" :disabled="!canSplit" @click="emit('split-selected')">
              <el-icon><Scissor /></el-icon>
              切割
            </el-button>
          </span>
        </el-tooltip>
        <el-button
          size="small"
          class="danger-button"
          :disabled="selectedClipIds.length === 0"
          @click="emit('remove-selected')"
        >
          <el-icon><Delete /></el-icon>
          删除片段{{ selectedClipIds.length > 1 ? `（${selectedClipIds.length}）` : '' }}
        </el-button>
        <el-tooltip content="把选中视频片段的声音分离到音轨" placement="top">
          <span>
            <el-button size="small" class="ghost-button" :disabled="!canDetach" @click="emit('detach-audio')">
              <el-icon><Headset /></el-icon>
              分离音频
            </el-button>
          </span>
        </el-tooltip>
        <span class="toolbar-divider"></span>
        <el-button size="small" class="ghost-button" @click="emit('add-text')">
          <el-icon><EditPen /></el-icon>
          添加文本
        </el-button>
        <span class="toolbar-hint">Ctrl+点击多选 · Ctrl+滚轮缩放</span>
      </div>
      <div class="toolbar-right">
        <el-tooltip content="拖拽时对齐播放头与相邻片段边缘" placement="top">
          <button class="snap-btn" :class="{ 'is-active': snapEnabled }" type="button" @click="snapEnabled = !snapEnabled">
            吸附
          </button>
        </el-tooltip>
        <div class="toolbar-zoom">
          <button class="zoom-btn" type="button" title="缩小" @click="stepZoom(-12)">
            <el-icon><ZoomOut /></el-icon>
          </button>
          <el-slider
            :model-value="pxPerSecond"
            :min="24"
            :max="180"
            :step="4"
            size="small"
            @update:model-value="onZoomChange"
          />
          <button class="zoom-btn" type="button" title="放大" @click="stepZoom(12)">
            <el-icon><ZoomIn /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <div ref="scrollEl" class="timeline-scroll" @wheel="onWheelZoom">
      <div ref="innerEl" class="timeline-inner" :style="{ width: `${innerWidthPx}px` }">
        <div class="ruler-row">
          <div class="ruler-head">{{ formatShortMs(playheadMs) }}</div>
          <div class="ruler-body" @pointerdown="onScrubPointerDown">
            <div
              v-for="tick in rulerTicks"
              :key="tick.ms"
              class="ruler-tick"
              :class="{ 'is-major': tick.major }"
              :style="{ left: `${msToPx(tick.ms)}px` }"
            >
              <span v-if="tick.major">{{ formatShortMs(tick.ms) }}</span>
            </div>
          </div>
        </div>

        <div
          v-show="showVideoZones"
          ref="newVideoZoneEl"
          class="new-track-zone is-video"
          :class="{ 'is-active': videoZoneActive }"
          @dragover="onZoneDragOver($event, 'video')"
          @dragleave="videoZoneHover = false"
          @drop="onZoneDrop($event, 'video')"
        >
          <span>拖拽视频到此处新建视频轨</span>
        </div>

        <template v-for="track in tracks" :key="track.id">
          <EditorTimelineTrack
            :project-public-id="projectPublicId"
            :track="track"
            :px-per-second="pxPerSecond"
            :selected-clip-ids="selectedClipIds"
            :dragging-clip-id="dragState?.moved ? dragState.clip.id : ''"
            :can-remove="canRemoveTrack(track)"
            @toggle-mute="emit('toggle-track-mute', track.id)"
            @toggle-hidden="emit('toggle-track-hidden', track.id)"
            @remove="emit('remove-track', track.id)"
            @clip-pointerdown="(event, clip) => onClipPointerDown(event, clip, track)"
            @lane-pointerdown="onLanePointerDown"
            @media-drop="(payload, ms) => emit('media-drop', payload, { type: 'track', trackId: track.id, ms })"
          />
          <div
            v-if="track.magnetic"
            v-show="showVideoZones"
            ref="belowVideoZoneEl"
            class="new-track-zone is-video"
            :class="{ 'is-active': belowZoneActive }"
            @dragover="onZoneDragOver($event, 'video-below')"
            @dragleave="belowZoneHover = false"
            @drop="onZoneDrop($event, 'video-below')"
          >
            <span>拖拽视频到此处新建下方视频轨</span>
          </div>
        </template>

        <div
          v-show="showAudioZone"
          ref="newAudioZoneEl"
          class="new-track-zone is-audio"
          :class="{ 'is-active': audioZoneActive }"
          @dragover="onZoneDragOver($event, 'audio')"
          @dragleave="audioZoneHover = false"
          @drop="onZoneDrop($event, 'audio')"
        >
          <span>拖拽音频到此处新建音轨</span>
        </div>

        <div
          v-if="insertIndicator"
          class="insert-indicator"
          :style="{
            left: `${LANE_ORIGIN_PX + msToPx(insertIndicator.ms)}px`,
            top: `${insertIndicator.top}px`,
            height: `${insertIndicator.height}px`,
          }"
        ></div>

        <div
          v-if="dragGhost"
          class="drag-ghost"
          :class="`is-${dragGhost.kind}`"
          :style="{
            left: `${dragGhost.left}px`,
            top: `${dragGhost.top}px`,
            width: `${dragGhost.width}px`,
            height: `${dragGhost.height}px`,
          }"
        >
          {{ dragGhost.label }}
        </div>

        <div class="playhead" :style="{ left: `${playheadPx}px` }">
          <div class="playhead-handle" @pointerdown.stop="onScrubPointerDown"></div>
          <div class="playhead-line" @pointerdown.stop="onScrubPointerDown"></div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Delete,
  EditPen,
  Headset,
  RefreshLeft,
  RefreshRight,
  Scissor,
  ZoomIn,
  ZoomOut,
} from '@element-plus/icons-vue'
import EditorTimelineTrack from './EditorTimelineTrack.vue'
import {
  clipDurationMs,
  clipEndMs,
  formatShortMs,
  magneticInsertIndex,
  rulerTickSpec,
} from './timelineDoc'
import {
  MIN_CLIP_MS,
  TIMELINE_LANE_PAD,
  TRACK_HEAD_WIDTH,
  mediaDragMime,
  type ClipDropTarget,
  type MediaDragPayload,
  type TimelineClip,
  type TimelineTrack,
  type TrackKind,
} from './types'

/** 时间线 0 点在 inner 中的横向原点：轨头列宽 + 内容区左留白。 */
const LANE_ORIGIN_PX = TRACK_HEAD_WIDTH + TIMELINE_LANE_PAD

/** 新建轨道放置区标识：视频组上方 / 主轨下方 / 音轨组下方。 */
type ZoneId = 'video' | 'video-below' | 'audio'

const props = defineProps<{
  projectPublicId: string
  /** 全部轨道，自上而下顺序：视频副轨 → 磁性主轨 → 音轨。 */
  tracks: TimelineTrack[]
  playheadMs: number
  playing: boolean
  pxPerSecond: number
  /** 选中片段集合，末位为主选中（属性条/切割目标）。 */
  selectedClipIds: string[]
  totalDurationMs: number
  canUndo: boolean
  canRedo: boolean
}>()

const emit = defineEmits<{
  (e: 'update:pxPerSecond', value: number): void
  (e: 'seek', ms: number): void
  (e: 'scrub-start'): void
  (e: 'undo'): void
  (e: 'redo'): void
  (e: 'select-clip', clipId: string, additive: boolean): void
  (e: 'clear-selection'): void
  (e: 'split-selected'): void
  (e: 'remove-selected'): void
  (e: 'detach-audio'): void
  (e: 'add-text'): void
  (e: 'toggle-track-mute', trackId: string): void
  (e: 'toggle-track-hidden', trackId: string): void
  (e: 'remove-track', trackId: string): void
  (e: 'media-drop', payload: MediaDragPayload, target: ClipDropTarget): void
  (e: 'clip-move', clipId: string, fromTrackId: string, target: ClipDropTarget): void
  (e: 'clips-shift', clipIds: string[], deltaMs: number): void
}>()

const scrollEl = ref<HTMLElement | null>(null)
const innerEl = ref<HTMLElement | null>(null)
const newVideoZoneEl = ref<HTMLElement | null>(null)
const belowVideoZoneEl = ref<HTMLElement | null>(null)
const newAudioZoneEl = ref<HTMLElement | null>(null)
const videoZoneHover = ref(false)
const belowZoneHover = ref(false)
const audioZoneHover = ref(false)

const msToPx = (ms: number) => (ms / 1000) * props.pxPerSecond

const timelineWidthPx = computed(() => Math.max(760, msToPx(props.totalDurationMs) + 320))
const innerWidthPx = computed(() => LANE_ORIGIN_PX + timelineWidthPx.value)
const playheadPx = computed(() => LANE_ORIGIN_PX + msToPx(props.playheadMs))

/** 标尺刻度随缩放自适应：主刻度间隔由 rulerTickSpec 按像素密度选定，细分为 1/5。 */
const rulerTicks = computed(() => {
  const { majorMs, subMs } = rulerTickSpec(props.pxPerSecond)
  const ticks: { ms: number; major: boolean }[] = []
  const end = Math.max(props.totalDurationMs + majorMs * 2, majorMs * 6)
  for (let ms = 0; ms <= end; ms += subMs) {
    ticks.push({ ms, major: ms % majorMs === 0 })
  }
  return ticks
})

/** 磁性主轨与主音轨（音轨组首条）不可删，其余轨道均可手动删除。 */
const canRemoveTrack = (track: TimelineTrack) => {
  if (track.kind === 'video') return !track.magnetic
  const audioTracks = props.tracks.filter((item) => item.kind === 'audio')
  return audioTracks.indexOf(track) > 0
}

/** 主选中（集合末位）：属性条、切割、分离音频的作用对象。 */
const selectedInfo = computed(() => {
  const primaryId = props.selectedClipIds[props.selectedClipIds.length - 1]
  if (!primaryId) return null
  for (const track of props.tracks) {
    const clip = track.clips.find((item) => item.id === primaryId)
    if (clip) return { track, clip }
  }
  return null
})

const canSplit = computed(() => {
  const info = selectedInfo.value
  if (!info) return false
  const localMs = props.playheadMs - info.clip.startMs
  return localMs >= MIN_CLIP_MS && localMs <= clipDurationMs(info.clip) - MIN_CLIP_MS
})

/** 仅视频轨上的视频片段可分离音频。 */
const canDetach = computed(() => (
  selectedInfo.value?.track.kind === 'video' && selectedInfo.value.clip.mediaType === 'video'
))

const onZoomChange = (value: number | number[]) => {
  if (Array.isArray(value)) return
  emit('update:pxPerSecond', value)
}

const stepZoom = (delta: number) => {
  emit('update:pxPerSecond', Math.min(180, Math.max(24, props.pxPerSecond + delta)))
}

/** Ctrl+滚轮缩放时间线：以鼠标下的时间点为锚，缩放后调整横向滚动保持锚点不动；普通滚轮保持原生滚动。 */
const onWheelZoom = (event: WheelEvent) => {
  if (!event.ctrlKey && !event.metaKey) return
  event.preventDefault()
  const next = Math.min(180, Math.max(24, props.pxPerSecond + (event.deltaY > 0 ? -8 : 8)))
  if (next === props.pxPerSecond) return
  const scroll = scrollEl.value
  const rect = scroll?.getBoundingClientRect()
  const anchorMs = clientXToMs(event.clientX)
  const pointerOffsetPx = rect ? event.clientX - rect.left : 0
  emit('update:pxPerSecond', next)
  void nextTick(() => {
    if (!scroll) return
    scroll.scrollLeft = Math.max(0, LANE_ORIGIN_PX + (anchorMs / 1000) * next - pointerOffsetPx)
  })
}

// ---------------------------------------------------------------------------
// 拖拽吸附：对齐播放头与其他片段首尾边缘（0 点不吸附，仅磁性主轨天然回到起点）
// ---------------------------------------------------------------------------

const SNAP_PX = 10
const snapEnabled = ref(true)

const applySnap = (excludeIds: ReadonlySet<string>, durationMs: number, ghostMs: number): number => {
  if (!snapEnabled.value) return ghostMs
  const thresholdMs = (SNAP_PX / props.pxPerSecond) * 1000
  // 0 点不作为吸附目标（含停在 0 点的播放头），辅轨片段不被拉回起点。
  const points: number[] = props.playheadMs > 0 ? [props.playheadMs] : []
  for (const track of props.tracks) {
    for (const clip of track.clips) {
      if (excludeIds.has(clip.id)) continue
      points.push(clip.startMs, clipEndMs(clip))
    }
  }
  let best = ghostMs
  let bestDistance = thresholdMs
  for (const point of points) {
    const headDistance = Math.abs(ghostMs - point)
    if (headDistance < bestDistance) {
      bestDistance = headDistance
      best = point
    }
    const tailDistance = Math.abs(ghostMs + durationMs - point)
    if (tailDistance < bestDistance) {
      bestDistance = tailDistance
      best = point - durationMs
    }
  }
  return Math.max(0, Math.round(best))
}

/** clientX → 时间线毫秒（轨头列宽与内容留白已扣除，含横向滚动偏移）。 */
const clientXToMs = (clientX: number) => {
  const rect = innerEl.value?.getBoundingClientRect()
  if (!rect) return 0
  return Math.max(0, Math.round(((clientX - rect.left - LANE_ORIGIN_PX) / props.pxPerSecond) * 1000))
}

// ---------------------------------------------------------------------------
// CTI（播放头）拖动：标尺与播放头把手共用同一逻辑
// ---------------------------------------------------------------------------

const onScrubPointerDown = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  emit('scrub-start')
  emit('seek', clientXToMs(event.clientX))
  const onMove = (moveEvent: PointerEvent) => {
    emit('seek', clientXToMs(moveEvent.clientX))
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

/** 点击轨道空白：定位播放头并取消选中。 */
const onLanePointerDown = (event: PointerEvent) => {
  if (event.button !== 0) return
  emit('clear-selection')
  emit('seek', clientXToMs(event.clientX))
}

// ---------------------------------------------------------------------------
// 片段指针拖拽：轨内移动 / 跨轨移动 / 拖入新建轨道放置区
// ---------------------------------------------------------------------------

interface ClipDragState {
  clip: TimelineClip
  fromTrackId: string
  kind: TrackKind
  grabOffsetPx: number
  originClientX: number
  originClientY: number
  moved: boolean
  ghostMs: number
  target: ClipDropTarget | null
  targetTop: number
  targetHeight: number
  /** 批量模式：拖动多选集合（仅时间平移，不换轨）。 */
  multiIds: string[] | null
  /** 普通按下时片段已在多选集合中：onUp 未移动则收敛为单选。 */
  wasSelected: boolean
}

const dragState = ref<ClipDragState | null>(null)

const innerTopOf = (rect: DOMRect) => {
  const innerRect = innerEl.value?.getBoundingClientRect()
  return innerRect ? rect.top - innerRect.top : 0
}

/** 依据指针纵坐标求拖拽目标：优先命中同类型轨道 lane，其次命中各新建轨道放置区。 */
const hitDropTarget = (state: ClipDragState, clientY: number, ghostMs: number): void => {
  state.target = null
  const lanes = Array.from(scrollEl.value?.querySelectorAll<HTMLElement>('[data-track-id]') ?? [])
  for (const lane of lanes) {
    const rect = lane.getBoundingClientRect()
    if (clientY < rect.top || clientY > rect.bottom) continue
    const trackId = lane.dataset.trackId || ''
    const track = props.tracks.find((item) => item.id === trackId)
    if (!track || track.kind !== state.kind) return
    state.target = { type: 'track', trackId, ms: ghostMs }
    state.targetTop = innerTopOf(rect)
    state.targetHeight = rect.height
    return
  }
  const zones: Array<{ el: HTMLElement | null; type: 'new-video' | 'new-video-below' | 'new-audio' }> =
    state.kind === 'video'
      ? [
          { el: newVideoZoneEl.value, type: 'new-video' },
          { el: belowVideoZoneEl.value, type: 'new-video-below' },
        ]
      : [{ el: newAudioZoneEl.value, type: 'new-audio' }]
  for (const zone of zones) {
    if (!zone.el) continue
    const rect = zone.el.getBoundingClientRect()
    if (clientY < rect.top || clientY > rect.bottom) continue
    state.target = { type: zone.type, ms: ghostMs }
    state.targetTop = innerTopOf(rect)
    state.targetHeight = rect.height
    return
  }
}

/** 批量模式目标恒为源轨（仅平移）：ghost 吸附到源轨行。 */
const hitSourceLane = (state: ClipDragState, ghostMs: number): void => {
  state.target = { type: 'track', trackId: state.fromTrackId, ms: ghostMs }
  const lane = scrollEl.value?.querySelector<HTMLElement>(`[data-track-id="${state.fromTrackId}"]`)
  if (!lane) return
  const rect = lane.getBoundingClientRect()
  state.targetTop = innerTopOf(rect)
  state.targetHeight = rect.height
}

const onClipPointerDown = (event: PointerEvent, clip: TimelineClip, track: TimelineTrack) => {
  if (event.button !== 0) return
  event.preventDefault()
  // Ctrl/Cmd + 点击：切换选中态，不启动拖拽。
  if (event.ctrlKey || event.metaKey) {
    emit('select-clip', clip.id, true)
    return
  }
  const wasSelected = props.selectedClipIds.includes(clip.id)
  if (!wasSelected) emit('select-clip', clip.id, false)
  // 批量拖动：按下片段已在多选集合且非磁性轨（磁性轨片段按插入排序，退化单拖）。
  const multiIds =
    wasSelected && props.selectedClipIds.length > 1 && !track.magnetic
      ? [...props.selectedClipIds]
      : null
  const clipLeftPx = LANE_ORIGIN_PX + msToPx(clip.startMs)
  const innerRect = innerEl.value?.getBoundingClientRect()
  const pointerInnerX = innerRect ? event.clientX - innerRect.left : clipLeftPx
  const state: ClipDragState = {
    clip,
    fromTrackId: track.id,
    kind: track.kind,
    grabOffsetPx: Math.max(0, pointerInnerX - clipLeftPx),
    originClientX: event.clientX,
    originClientY: event.clientY,
    moved: false,
    ghostMs: clip.startMs,
    target: null,
    targetTop: 0,
    targetHeight: 0,
    multiIds,
    wasSelected,
  }
  dragState.value = state
  const excludeIds = new Set(multiIds ?? [clip.id])

  const onMove = (moveEvent: PointerEvent) => {
    if (!state.moved) {
      const dx = Math.abs(moveEvent.clientX - state.originClientX)
      const dy = Math.abs(moveEvent.clientY - state.originClientY)
      if (dx < 3 && dy < 3) return
      state.moved = true
    }
    const rect = innerEl.value?.getBoundingClientRect()
    if (!rect) return
    const leftPx = moveEvent.clientX - rect.left - state.grabOffsetPx - LANE_ORIGIN_PX
    const rawMs = Math.max(0, Math.round((leftPx / props.pxPerSecond) * 1000))
    state.ghostMs = applySnap(excludeIds, clipDurationMs(state.clip), rawMs)
    if (state.multiIds) hitSourceLane(state, state.ghostMs)
    else hitDropTarget(state, moveEvent.clientY, state.ghostMs)
    // 触发响应式更新（deep 字段变化）。
    dragState.value = { ...state }
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    const final = dragState.value
    dragState.value = null
    if (!final) return
    if (final.moved && final.multiIds) {
      emit('clips-shift', final.multiIds, final.ghostMs - final.clip.startMs)
      return
    }
    if (final.moved && final.target) {
      emit('clip-move', final.clip.id, final.fromTrackId, final.target)
      return
    }
    // 多选集合内普通点击且未拖动：收敛为单选该片段。
    if (!final.moved && final.wasSelected) emit('select-clip', final.clip.id, false)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

/** 拖拽幽灵条：位置吸附到目标轨道行，宽度与片段实际时长一致；批量模式标注数量。 */
const dragGhost = computed(() => {
  const state = dragState.value
  if (!state?.moved || !state.target) return null
  return {
    kind: state.kind,
    label: state.multiIds ? `${state.multiIds.length} 个片段` : state.clip.label,
    left: LANE_ORIGIN_PX + msToPx(state.ghostMs),
    top: state.targetTop + 4,
    width: Math.max(8, msToPx(clipDurationMs(state.clip))),
    height: Math.max(24, state.targetHeight - 8),
  }
})

/** 目标为磁性主轨时的插入位置指示线。 */
const insertIndicator = computed(() => {
  const state = dragState.value
  if (!state?.moved) return null
  const target = state.target
  if (!target || target.type !== 'track') return null
  const track = props.tracks.find((item) => item.id === target.trackId)
  if (!track?.magnetic) return null
  const others = track.clips.filter((item) => item.id !== state.clip.id)
  const index = magneticInsertIndex(others, target.ms)
  let ms = 0
  for (let i = 0; i < index; i += 1) ms += clipDurationMs(others[i])
  return { ms, top: state.targetTop, height: state.targetHeight }
})

const videoZoneActive = computed(() => (
  videoZoneHover.value || dragState.value?.target?.type === 'new-video'
))
const belowZoneActive = computed(() => (
  belowZoneHover.value || dragState.value?.target?.type === 'new-video-below'
))
const audioZoneActive = computed(() => (
  audioZoneHover.value || dragState.value?.target?.type === 'new-audio'
))

// ---------------------------------------------------------------------------
// 新建轨道放置区仅在拖拽会话期间显示：平时时间线只呈现实际轨道
// ---------------------------------------------------------------------------

/** HTML5 DnD 会话中的素材类型（从库面板拖出时由负载 MIME 判定）。 */
const dndKind = ref<'' | TrackKind>('')

const onDocDragEnter = (event: DragEvent) => {
  const types = event.dataTransfer?.types ?? []
  if (types.includes(mediaDragMime('video'))) dndKind.value = 'video'
  else if (types.includes(mediaDragMime('audio'))) dndKind.value = 'audio'
}

const onDocDragEnd = () => {
  dndKind.value = ''
}

onMounted(() => {
  document.addEventListener('dragenter', onDocDragEnter)
  document.addEventListener('drop', onDocDragEnd)
  document.addEventListener('dragend', onDocDragEnd)
})

onBeforeUnmount(() => {
  document.removeEventListener('dragenter', onDocDragEnter)
  document.removeEventListener('drop', onDocDragEnd)
  document.removeEventListener('dragend', onDocDragEnd)
})

const showVideoZones = computed(() => dndKind.value === 'video' || dragState.value?.kind === 'video')
const showAudioZone = computed(() => dndKind.value === 'audio' || dragState.value?.kind === 'audio')

// ---------------------------------------------------------------------------
// 素材从库面板拖入新建轨道放置区（HTML5 DnD）
// ---------------------------------------------------------------------------

const zoneHoverRef = (zone: ZoneId) => (
  zone === 'video' ? videoZoneHover : zone === 'video-below' ? belowZoneHover : audioZoneHover
)

const zoneDropTargetType = (zone: ZoneId) => (
  zone === 'video' ? 'new-video' as const : zone === 'video-below' ? 'new-video-below' as const : 'new-audio' as const
)

const onZoneDragOver = (event: DragEvent, zone: ZoneId) => {
  const kind: TrackKind = zone === 'audio' ? 'audio' : 'video'
  if (!event.dataTransfer?.types.includes(mediaDragMime(kind))) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
  zoneHoverRef(zone).value = true
}

const onZoneDrop = (event: DragEvent, zone: ZoneId) => {
  zoneHoverRef(zone).value = false
  const kind: TrackKind = zone === 'audio' ? 'audio' : 'video'
  const raw = event.dataTransfer?.getData(mediaDragMime(kind))
  if (!raw) return
  event.preventDefault()
  try {
    const payload = JSON.parse(raw) as MediaDragPayload
    emit('media-drop', payload, { type: zoneDropTargetType(zone), ms: clientXToMs(event.clientX) })
  } catch {
    // 负载非法时忽略本次拖放
  }
}

// ---------------------------------------------------------------------------
// 播放时自动跟随滚动
// ---------------------------------------------------------------------------

watch(
  () => props.playheadMs,
  () => {
    if (!props.playing) return
    const scroll = scrollEl.value
    if (!scroll) return
    const px = playheadPx.value
    const viewLeft = scroll.scrollLeft + LANE_ORIGIN_PX
    const viewRight = scroll.scrollLeft + scroll.clientWidth
    if (px > viewRight - 80 || px < viewLeft) {
      scroll.scrollLeft = Math.max(0, px - scroll.clientWidth * 0.4)
    }
  },
)
</script>

<style scoped>
/* 统一盒模型：标尺头/轨头 width 含边框，保证刻度、片段与播放头共用同一 0 点。 */
.timeline-panel,
.timeline-panel *,
.timeline-panel *::before,
.timeline-panel *::after {
  box-sizing: border-box;
}

.timeline-panel {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  height: 180px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(13, 17, 23, 0.86);
  overflow: hidden;
}

.timeline-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 4px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-divider {
  width: 1px;
  height: 16px;
  background: rgba(255, 255, 255, 0.12);
}

.toolbar-hint {
  color: #4b5563;
  font-size: 11px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.snap-btn {
  height: 24px;
  padding: 0 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: #8b949e;
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.snap-btn:hover {
  color: #e6edf3;
}

.snap-btn.is-active {
  color: #93c5fd;
  border-color: rgba(96, 165, 250, 0.55);
  background: rgba(37, 99, 235, 0.16);
}

.toolbar-zoom {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 210px;
  color: #8b949e;
  font-size: 12px;
}

.zoom-btn {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  padding: 0;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: #8b949e;
  cursor: pointer;
  font-size: 14px;
  transition: color 0.15s ease, background 0.15s ease;
}

.zoom-btn:hover {
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.08);
}

.ghost-button.is-icon {
  padding: 5px 7px;
}

.timeline-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.34) transparent;
}

.timeline-scroll::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.timeline-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.timeline-scroll::-webkit-scrollbar-thumb {
  min-width: 48px;
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.32);
  background-clip: padding-box;
}

.timeline-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(203, 213, 225, 0.46);
  background-clip: padding-box;
}

.timeline-inner {
  position: relative;
  min-width: 100%;
  min-height: 100%;
}

.ruler-row {
  position: sticky;
  top: 0;
  z-index: 7;
  display: flex;
  height: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: #0d1117;
}

.ruler-head {
  position: sticky;
  left: 0;
  z-index: 8;
  width: 64px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  color: #93c5fd;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  background: #10151d;
}

.ruler-body {
  position: relative;
  flex: 1;
  /* 与轨道内容区一致的左留白，保证 0 点刻度不被轨头压边。 */
  margin-left: 8px;
  cursor: ew-resize;
}

.ruler-tick {
  position: absolute;
  top: 13px;
  bottom: 0;
  width: 1px;
  background: rgba(255, 255, 255, 0.14);
  pointer-events: none;
}

.ruler-tick.is-major {
  top: 9px;
  background: rgba(255, 255, 255, 0.3);
}

.ruler-tick.is-major span {
  position: absolute;
  top: -9px;
  left: 3px;
  color: #8b949e;
  font-size: 9px;
  line-height: 1;
  white-space: nowrap;
}

.new-track-zone {
  display: flex;
  align-items: center;
  height: 18px;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.08);
  color: #4b5563;
  font-size: 11px;
  transition: background 0.15s ease, color 0.15s ease;
}

.new-track-zone span {
  position: sticky;
  left: 72px;
  display: inline-block;
  pointer-events: none;
}

.new-track-zone.is-active {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.14);
  border-bottom-color: rgba(96, 165, 250, 0.5);
}

.new-track-zone.is-audio.is-active {
  color: #4ade80;
  background: rgba(22, 163, 74, 0.14);
  border-bottom-color: rgba(74, 222, 128, 0.5);
}

.playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 5;
  width: 2px;
  background: #f87171;
  pointer-events: none;
  box-shadow: 0 0 8px rgba(248, 113, 113, 0.6);
}

.playhead-handle {
  position: absolute;
  top: 0;
  left: 0;
  width: 12px;
  height: 14px;
  pointer-events: auto;
  cursor: ew-resize;
  background: #f87171;
  /* 右向旗帜形，不向左溢出，避免播放头位于 0 点时被轨头遮挡。 */
  clip-path: polygon(0 0, 100% 0, 100% 55%, 0 100%);
}

/* 竖线全高可拖：透明热区比 2px 线宽更宽，便于命中。 */
.playhead-line {
  position: absolute;
  top: 14px;
  bottom: 0;
  left: -4px;
  width: 10px;
  pointer-events: auto;
  cursor: ew-resize;
}

.insert-indicator {
  position: absolute;
  z-index: 4;
  width: 2px;
  background: #fbbf24;
  box-shadow: 0 0 6px rgba(251, 191, 36, 0.7);
  pointer-events: none;
}

.drag-ghost {
  position: absolute;
  z-index: 9;
  display: flex;
  align-items: center;
  padding: 0 8px;
  border-radius: 0;
  border: 1px dashed rgba(147, 197, 253, 0.9);
  background: rgba(37, 99, 235, 0.35);
  color: #e6edf3;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  pointer-events: none;
}

.drag-ghost.is-audio {
  border-color: rgba(74, 222, 128, 0.9);
  background: rgba(22, 163, 74, 0.35);
}

.ghost-button {
  --el-button-bg-color: rgba(255, 255, 255, 0.04);
  --el-button-border-color: rgba(255, 255, 255, 0.14);
  --el-button-text-color: #c5cdd6;
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.08);
  --el-button-hover-border-color: rgba(255, 255, 255, 0.24);
  --el-button-hover-text-color: #fff;
  --el-button-disabled-bg-color: rgba(255, 255, 255, 0.02);
  --el-button-disabled-border-color: rgba(255, 255, 255, 0.08);
  --el-button-disabled-text-color: #4b5563;
}

.danger-button {
  --el-button-bg-color: rgba(248, 113, 113, 0.12);
  --el-button-border-color: rgba(248, 113, 113, 0.4);
  --el-button-text-color: #fca5a5;
  --el-button-hover-bg-color: rgba(248, 113, 113, 0.2);
  --el-button-hover-border-color: rgba(248, 113, 113, 0.6);
  --el-button-hover-text-color: #fecaca;
  --el-button-disabled-bg-color: rgba(248, 113, 113, 0.05);
  --el-button-disabled-border-color: rgba(248, 113, 113, 0.16);
  --el-button-disabled-text-color: rgba(252, 165, 165, 0.35);
}

:deep(.el-slider__runway) {
  background: rgba(255, 255, 255, 0.1);
}
</style>