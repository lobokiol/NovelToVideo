<template>
  <div class="player-shell">
    <div class="player-titlebar">
      <button
        class="tool-btn"
        type="button"
        :title="libraryCollapsed ? '展开素材区' : '收起素材区'"
        @click="emit('toggle-library')"
      >
        <el-icon><Expand v-if="libraryCollapsed" /><Fold v-else /></el-icon>
      </button>
      <span class="player-title">播放器</span>
      <span v-if="projectName" class="player-subtitle">{{ projectName }}</span>
      <span class="player-meta">{{ resolutionText }}</span>
      <button
        class="tool-btn is-right"
        type="button"
        :title="timelineCollapsed ? '展开轨道区' : '收起轨道区'"
        @click="emit('toggle-timeline')"
      >
        <el-icon><ArrowUp v-if="timelineCollapsed" /><ArrowDown v-else /></el-icon>
      </button>
    </div>
    <div
      ref="previewWrapEl"
      class="preview-wrap"
      :class="{ 'is-portrait': isPortrait }"
      @wheel.prevent="onPreviewWheel"
      @dblclick.self="previewScale = 1"
    >
      <div class="preview-viewport" :style="{ transform: `scale(${previewScale})` }">
        <div
          v-for="(track, index) in videoTracks"
          :key="track.id"
          class="preview-layer-slot"
          :style="{ zIndex: videoTracks.length - index }"
        >
          <video
            v-for="layer in 2"
            :key="layer"
            :ref="(el) => onVideoRef(track.id, layer - 1, el)"
            class="preview-video-layer"
            playsinline
            preload="auto"
          ></video>
          <img
            v-if="imageOverlays[track.id]"
            class="preview-image-layer"
            :src="imageOverlays[track.id]"
            alt=""
          />
          <div
            v-if="textOverlays[track.id]"
            class="preview-text-layer"
            :class="{ 'is-selected': textOverlays[track.id].clipId === selectedClipId }"
            :style="textLayerStyle(textOverlays[track.id])"
            @pointerdown="onTextMovePointerDown($event, textOverlays[track.id])"
          >
            {{ textOverlays[track.id].text }}
            <template v-if="textOverlays[track.id].clipId === selectedClipId">
              <span
                class="text-scale-handle"
                title="拖拽缩放文本"
                @pointerdown.stop.prevent="onTextScalePointerDown($event, textOverlays[track.id].scale)"
              ></span>
              <span
                class="text-rotate-handle"
                title="拖拽旋转文本"
                @pointerdown.stop.prevent="onTextRotatePointerDown($event, textOverlays[track.id].rotate)"
              ></span>
              <span
                class="text-width-handle"
                title="拖拽调整文本框宽度"
                @pointerdown.stop.prevent="onTextWidthPointerDown($event, textOverlays[track.id].boxWidth)"
              ></span>
            </template>
          </div>
        </div>
      </div>
      <div v-if="!hasContent" class="preview-empty">从左侧素材库把镜头片段加入主轨，或直接拖拽入轨开始剪辑</div>
      <span v-if="previewScale !== 1" class="zoom-tag">画面缩放 {{ Math.round(previewScale * 100) }}%</span>
      <button
        v-if="hasContent"
        class="center-play"
        type="button"
        :title="playing ? '暂停' : '播放'"
        @click="emit('toggle-play')"
      >
        <el-icon><VideoPause v-if="playing" /><VideoPlay v-else /></el-icon>
      </button>
      <div v-if="totalDurationMs > 0" class="progress-rail" @pointerdown="onProgressPointerDown">
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${progressPct}%` }"></div>
        </div>
      </div>
    </div>
    <div class="transport-bar">
      <div class="transport-times">
        <span class="time-current">{{ formatTimecodeMs(playheadMs) }}</span>
        <span class="time-total">{{ formatTimecodeMs(totalDurationMs) }}</span>
      </div>
      <div class="transport-right">
        <span class="transport-hint">空格 播放/暂停 · 滚轮缩放画面</span>
        <button class="tool-btn" type="button" title="预览全屏" @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, type CSSProperties, type ComponentPublicInstance } from 'vue'
import { ArrowDown, ArrowUp, Expand, Fold, FullScreen, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { mediaContentUrl } from '@/api/media'
import { clipEndMs, formatTimecodeMs } from './timelineDoc'
import {
  TEXT_BOX_WIDTH_MAX,
  TEXT_BOX_WIDTH_MIN,
  TEXT_OFFSET_LIMIT,
  TEXT_SCALE_MAX,
  TEXT_SCALE_MIN,
  type TimelineClip,
  type TimelineTrack,
} from './types'

/** 预览文本层的变换快照（来自当前时刻命中的文本片段）。 */
interface TextOverlay {
  clipId: string
  text: string
  scale: number
  x: number
  y: number
  rotate: number
  boxWidth: number
}

const props = defineProps<{
  projectPublicId: string
  projectName: string
  /** 画幅比例（'16:9' 或竖屏），用于标题栏分辨率展示。 */
  ratio: string
  /** 视频轨道，自上而下顺序（副轨在前、磁性主轨在后），层级按此叠放。 */
  videoTracks: TimelineTrack[]
  playing: boolean
  playheadMs: number
  totalDurationMs: number
  isPortrait: boolean
  hasContent: boolean
  /** 当前选中片段：命中文本层时显示变换手柄。 */
  selectedClipId: string
  /** 左侧素材区 / 底部轨道区折叠态，仅用于切换按钮图标。 */
  libraryCollapsed: boolean
  timelineCollapsed: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-play'): void
  (e: 'register-video', trackId: string, layerIndex: number, el: HTMLVideoElement | null): void
  (e: 'update-text-scale', scale: number): void
  (e: 'update-text-transform', patch: { x?: number; y?: number; rotate?: number; boxWidth?: number }): void
  (e: 'toggle-library'): void
  (e: 'toggle-timeline'): void
  (e: 'seek', ms: number): void
  (e: 'scrub-start'): void
}>()

/** 导出分辨率与画幅比例（标题栏展示）。 */
const resolutionText = computed(() => {
  const [width, height] = props.ratio === '16:9' ? [1280, 720] : [720, 1280]
  return `${width}×${height} · ${props.ratio || '9:16'}`
})

const previewWrapEl = ref<HTMLElement | null>(null)

/** 画面查看缩放（滚轮调节，双击空白还原），仅影响预览不入工程数据。 */
const previewScale = ref(1)

const onPreviewWheel = (event: WheelEvent) => {
  const step = event.deltaY > 0 ? -0.1 : 0.1
  previewScale.value = Math.min(3, Math.max(0.5, Math.round((previewScale.value + step) * 10) / 10))
}

const progressPct = computed(() => (
  props.totalDurationMs > 0 ? Math.min(100, (props.playheadMs / props.totalDurationMs) * 100) : 0
))

/** 进度条按下/拖拽定位：先暂停（scrub-start）再按比例 seek。 */
const onProgressPointerDown = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  const rail = event.currentTarget as HTMLElement
  emit('scrub-start')
  const seekTo = (clientX: number) => {
    const rect = rail.getBoundingClientRect()
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
    emit('seek', Math.round(ratio * props.totalDurationMs))
  }
  seekTo(event.clientX)
  const onMove = (moveEvent: PointerEvent) => seekTo(moveEvent.clientX)
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

const onVideoRef = (trackId: string, layerIndex: number, el: Element | ComponentPublicInstance | null) => {
  emit('register-video', trackId, layerIndex, el instanceof HTMLVideoElement ? el : null)
}

const toggleFullscreen = () => {
  const el = previewWrapEl.value
  if (!el) return
  if (document.fullscreenElement) void document.exitFullscreen()
  else void el.requestFullscreen().catch(() => undefined)
}

const activeClipOf = (track: TimelineTrack): TimelineClip | null => {
  for (const clip of track.clips) {
    if (props.playheadMs >= clip.startMs && props.playheadMs < clipEndMs(clip)) return clip
  }
  return null
}

/** 各视频轨当前时刻命中的图片片段（响应式静帧层，视频层由播放引擎驱动）；隐藏轨跳过。 */
const imageOverlays = computed<Record<string, string>>(() => {
  const result: Record<string, string> = {}
  for (const track of props.videoTracks) {
    if (track.hidden) continue
    const clip = activeClipOf(track)
    if (clip?.mediaType === 'image') {
      result[track.id] = mediaContentUrl(props.projectPublicId, clip.mediaPublicId)
    }
  }
  return result
})

/** 各视频轨当前时刻命中的文本片段（内容 + 变换 + 选中判定）；隐藏轨跳过。 */
const textOverlays = computed<Record<string, TextOverlay>>(() => {
  const result: Record<string, TextOverlay> = {}
  for (const track of props.videoTracks) {
    if (track.hidden) continue
    const clip = activeClipOf(track)
    if (clip?.mediaType === 'text') {
      result[track.id] = {
        clipId: clip.id,
        text: clip.text || clip.label,
        scale: clip.textScale || 1,
        x: clip.textX || 0,
        y: clip.textY || 0,
        rotate: clip.textRotate || 0,
        boxWidth: clip.textBoxWidth || 0.88,
      }
    }
  }
  return result
})

/** 文本层定位：中心坐标系（left/top 百分比）+ 平移居中 + 旋转，字号随缩放倍率。 */
const textLayerStyle = (overlay: TextOverlay): CSSProperties => ({
  left: `${50 + overlay.x * 100}%`,
  top: `${50 + overlay.y * 100}%`,
  width: `${overlay.boxWidth * 100}%`,
  fontSize: `calc(clamp(16px, 4.5vh, 42px) * ${overlay.scale})`,
  transform: `translate(-50%, -50%) rotate(${overlay.rotate}deg)`,
})

const clampOffset = (value: number) => Math.min(TEXT_OFFSET_LIMIT, Math.max(-TEXT_OFFSET_LIMIT, value))

/** 拖拽文本层本体移动位置（仅选中层可交互），位移换算为相对画面比例。 */
const onTextMovePointerDown = (event: PointerEvent, overlay: TextOverlay) => {
  if (overlay.clipId !== props.selectedClipId || event.button !== 0) return
  event.preventDefault()
  const wrap = previewWrapEl.value
  if (!wrap) return
  const wrapRect = wrap.getBoundingClientRect()
  const startX = event.clientX
  const startY = event.clientY
  const originX = overlay.x
  const originY = overlay.y
  const onMove = (moveEvent: PointerEvent) => {
    const dx = (moveEvent.clientX - startX) / Math.max(1, wrapRect.width)
    const dy = (moveEvent.clientY - startY) / Math.max(1, wrapRect.height)
    emit('update-text-transform', {
      x: clampOffset(originX + dx),
      y: clampOffset(originY + dy),
    })
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

/** 拖拽右上手柄旋转：以文本层中心为轴，跟随指针角度增量。 */
const onTextRotatePointerDown = (event: PointerEvent, startRotate: number) => {
  const layer = (event.currentTarget as HTMLElement).parentElement
  if (!layer) return
  const rect = layer.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  const startAngle = Math.atan2(event.clientY - centerY, event.clientX - centerX)
  const onMove = (moveEvent: PointerEvent) => {
    const angle = Math.atan2(moveEvent.clientY - centerY, moveEvent.clientX - centerX)
    const rotate = startRotate + ((angle - startAngle) * 180) / Math.PI
    emit('update-text-transform', { rotate: Math.round(rotate * 10) / 10 })
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

/** 拖拽右中手柄调整文本框宽度（中心对称，换行盒随之变化）。 */
const onTextWidthPointerDown = (event: PointerEvent, startBoxWidth: number) => {
  const wrap = previewWrapEl.value
  if (!wrap) return
  const wrapWidth = Math.max(1, wrap.getBoundingClientRect().width)
  const startX = event.clientX
  const onMove = (moveEvent: PointerEvent) => {
    const delta = ((moveEvent.clientX - startX) * 2) / wrapWidth
    const boxWidth = Math.min(TEXT_BOX_WIDTH_MAX, Math.max(TEXT_BOX_WIDTH_MIN, startBoxWidth + delta))
    emit('update-text-transform', { boxWidth: Math.round(boxWidth * 100) / 100 })
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

/** 拖拽右下手柄缩放文本：以文本层中心为基准，按指针距离比例调整倍率。 */
const onTextScalePointerDown = (event: PointerEvent, startScale: number) => {
  const layer = (event.currentTarget as HTMLElement).parentElement
  if (!layer) return
  const rect = layer.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  const startDistance = Math.max(12, Math.hypot(event.clientX - centerX, event.clientY - centerY))
  const onMove = (moveEvent: PointerEvent) => {
    const distance = Math.hypot(moveEvent.clientX - centerX, moveEvent.clientY - centerY)
    const scale = Math.min(TEXT_SCALE_MAX, Math.max(TEXT_SCALE_MIN, startScale * (distance / startDistance)))
    emit('update-text-scale', Math.round(scale * 100) / 100)
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}
</script>

<style scoped>
.player-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: #0b0e14;
  overflow: hidden;
}

.player-titlebar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}

.player-titlebar .tool-btn.is-right {
  margin-left: auto;
}

.player-title {
  color: #c5cdd6;
  font-size: 12px;
  font-weight: 600;
}

.player-subtitle {
  color: #6e7681;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 分辨率与画幅比例：位于项目名右侧 20px 处。 */
.player-meta {
  margin-left: 20px;
  flex-shrink: 0;
  color: #8b949e;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.preview-wrap {
  position: relative;
  flex: 1;
  min-height: 220px;
  background: #05070b;
  overflow: hidden;
}

.preview-viewport {
  position: absolute;
  inset: 0;
  transform-origin: center center;
  transition: transform 0.12s ease;
}

.zoom-tag {
  position: absolute;
  top: 8px;
  right: 10px;
  z-index: 30;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: #93c5fd;
  font-size: 11px;
  pointer-events: none;
}

/* 中央播放键：默认完全透明，鼠标进入播放区显现，悬停按钮本体提亮。 */
.center-play {
  position: absolute;
  inset: 0;
  margin: auto;
  z-index: 28;
  width: 76px;
  height: 76px;
  display: grid;
  place-items: center;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: rgba(13, 17, 23, 0.4);
  color: rgba(255, 255, 255, 0.85);
  font-size: 40px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.18s ease, background 0.18s ease;
}

.preview-wrap:hover .center-play {
  opacity: 0.4;
}

.preview-wrap .center-play:hover {
  opacity: 0.85;
  background: rgba(13, 17, 23, 0.62);
}

/* 底部播放进度条：默认近乎透明，悬停半透明；全宽热区便于点击拖拽。 */
.progress-rail {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 29;
  height: 16px;
  display: flex;
  align-items: flex-end;
  padding: 0 2px 3px;
  cursor: pointer;
  opacity: 0.14;
  transition: opacity 0.18s ease;
}

.progress-rail:hover {
  opacity: 0.55;
}

.progress-track {
  position: relative;
  width: 100%;
  height: 4px;
  border-radius: 999px;
  background: rgba(230, 237, 243, 0.28);
  overflow: hidden;
  transition: height 0.15s ease;
}

.progress-rail:hover .progress-track {
  height: 6px;
}

.progress-fill {
  height: 100%;
  background: #38bdf8;
}

.preview-layer-slot {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.preview-video-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  /* 初始不可见，由播放引擎按当前时刻是否命中视频片段控制显隐。 */
  visibility: hidden;
}

.preview-image-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

/* 位置/宽度/字号/旋转均由内联样式控制（中心坐标系 + 片段变换字段）。 */
.preview-text-layer {
  position: absolute;
  text-align: center;
  color: #ffffff;
  font-weight: 600;
  line-height: 1.35;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.85);
  word-break: break-word;
  white-space: pre-wrap;
}

.preview-text-layer.is-selected {
  pointer-events: auto;
  cursor: move;
  outline: 1px dashed rgba(147, 197, 253, 0.75);
  outline-offset: 6px;
}

.text-scale-handle {
  position: absolute;
  right: -14px;
  bottom: -14px;
  width: 14px;
  height: 14px;
  border: 2px solid #93c5fd;
  border-radius: 999px;
  background: #0d1117;
  cursor: nwse-resize;
}

.text-rotate-handle {
  position: absolute;
  right: -14px;
  top: -14px;
  width: 14px;
  height: 14px;
  border: 2px solid #fbbf24;
  border-radius: 999px;
  background: #0d1117;
  cursor: grab;
}

.text-width-handle {
  position: absolute;
  right: -12px;
  top: 50%;
  width: 8px;
  height: 22px;
  transform: translateY(-50%);
  border: 2px solid #4ade80;
  border-radius: 4px;
  background: #0d1117;
  cursor: ew-resize;
}

.preview-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #6e7681;
  font-size: 13px;
}

.transport-bar {
  position: relative;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 5px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.transport-times {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}

.time-current {
  color: #38bdf8;
}

.time-total {
  color: #6e7681;
}

.transport-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.transport-hint {
  color: #4b5563;
  font-size: 11px;
}

.tool-btn {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: #c5cdd6;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.tool-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}

.ghost-button {
  --el-button-bg-color: rgba(255, 255, 255, 0.04);
  --el-button-border-color: rgba(255, 255, 255, 0.14);
  --el-button-text-color: #c5cdd6;
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.08);
  --el-button-hover-border-color: rgba(255, 255, 255, 0.24);
  --el-button-hover-text-color: #fff;
}
</style>