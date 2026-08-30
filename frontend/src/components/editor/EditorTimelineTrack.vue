<template>
  <div
    class="timeline-track"
    :class="[`is-${track.kind}`, { 'is-magnetic': track.magnetic, 'is-drop-target': dropActive, 'is-hidden': track.hidden }]"
  >
    <div class="track-head" :title="track.name">
      <button
        v-if="track.kind === 'video'"
        class="track-btn"
        :class="{ 'is-active': track.hidden }"
        type="button"
        :title="track.hidden ? '显示轨道' : '隐藏轨道'"
        @click="emit('toggle-hidden')"
      >
        <el-icon><Hide v-if="track.hidden" /><View v-else /></el-icon>
      </button>
      <button
        class="track-btn"
        :class="{ 'is-active': track.muted }"
        type="button"
        :title="track.muted ? '取消轨道静音' : '静音轨道'"
        @click="emit('toggle-mute')"
      >
        <el-icon><Mute /></el-icon>
      </button>
      <button
        v-if="canRemove"
        class="track-btn is-danger"
        type="button"
        title="删除轨道"
        @click="emit('remove')"
      >
        <el-icon><Close /></el-icon>
      </button>
    </div>

    <div
      ref="laneEl"
      class="track-lane"
      :data-track-id="track.id"
      @pointerdown.self="emit('lane-pointerdown', $event)"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <div
        v-for="clip in track.clips"
        :key="clip.id"
        class="timeline-clip"
        :class="[
          `is-${clip.mediaType}`,
          {
            'is-selected': selectedClipIds.includes(clip.id),
            'is-dragging': clip.id === draggingClipId,
            'is-muted': track.muted || clip.muted,
          },
        ]"
        :style="clipStyle(clip)"
        @pointerdown.stop="emit('clip-pointerdown', $event, clip)"
      >
        <span class="clip-caption">
          <span class="clip-caption__name">{{ clipDisplayName(clip) }}</span>
          <span v-if="clip.mediaType !== 'image'" class="clip-caption__duration">
            {{ formatTimecodeMs(clipDurationMs(clip)) }}
          </span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, type CSSProperties } from 'vue'
import { Close, Hide, Mute, View } from '@element-plus/icons-vue'
import { mediaContentUrl } from '@/api/media'
import { clipDurationMs, clipEndMs, formatTimecodeMs } from './timelineDoc'
import { mediaDragMime, type MediaDragPayload, type TimelineClip, type TimelineTrack } from './types'

const props = defineProps<{
  projectPublicId: string
  track: TimelineTrack
  pxPerSecond: number
  /** 选中片段集合（支持 Ctrl 多选）。 */
  selectedClipIds: string[]
  /** 正被指针拖拽的片段，半透明显示原位置。 */
  draggingClipId: string
  canRemove: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-mute'): void
  (e: 'toggle-hidden'): void
  (e: 'remove'): void
  (e: 'clip-pointerdown', event: PointerEvent, clip: TimelineClip): void
  (e: 'lane-pointerdown', event: PointerEvent): void
  (e: 'media-drop', payload: MediaDragPayload, ms: number): void
}>()

const laneEl = ref<HTMLElement | null>(null)
const dropActive = ref(false)

const msToPx = (ms: number) => (ms / 1000) * props.pxPerSecond

/** 片段定位与外观：图片片段以自身内容为平铺背景（近似剪映缩略图填充）。 */
const clipStyle = (clip: TimelineClip): CSSProperties => {
  const style: CSSProperties = {
    left: `${msToPx(clip.startMs)}px`,
    width: `${msToPx(clipDurationMs(clip))}px`,
  }
  if (clip.mediaType === 'image' && clip.mediaPublicId) {
    style.backgroundImage = `url(${mediaContentUrl(props.projectPublicId, clip.mediaPublicId)})`
    style.backgroundSize = 'auto 100%'
    style.backgroundRepeat = 'repeat-x'
  }
  return style
}

/** 角标名称：文本片段直接展示内容，其余展示素材文件名/标签。 */
const clipDisplayName = (clip: TimelineClip) => (
  clip.mediaType === 'text' ? (clip.text || clip.label) : clip.label
)

const acceptsDrag = (event: DragEvent) => (
  Boolean(event.dataTransfer?.types.includes(mediaDragMime(props.track.kind)))
)

const onDragOver = (event: DragEvent) => {
  if (!acceptsDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
  dropActive.value = true
}

const onDragLeave = () => {
  dropActive.value = false
}

const onDrop = (event: DragEvent) => {
  dropActive.value = false
  const raw = event.dataTransfer?.getData(mediaDragMime(props.track.kind))
  if (!raw) return
  event.preventDefault()
  try {
    const payload = JSON.parse(raw) as MediaDragPayload
    const rect = laneEl.value?.getBoundingClientRect()
    let ms = rect ? Math.max(0, ((event.clientX - rect.left) / props.pxPerSecond) * 1000) : 0
    // 落点贴边吸附：靠近本轨已有片段首尾时严丝合缝，避免留缝播放黑屏。
    const thresholdMs = (12 / props.pxPerSecond) * 1000
    let bestDistance = thresholdMs
    for (const clip of props.track.clips) {
      for (const edge of [clip.startMs, clipEndMs(clip)]) {
        const distance = Math.abs(ms - edge)
        if (distance < bestDistance) {
          bestDistance = distance
          ms = edge
        }
      }
    }
    emit('media-drop', payload, Math.round(ms))
  } catch {
    // 负载非法时忽略本次拖放
  }
}
</script>

<style scoped>
/* 统一盒模型：轨头 width 含 padding/边框，保证片段坐标系与播放头/标尺共用同一原点。 */
.timeline-track,
.timeline-track *,
.timeline-track *::before,
.timeline-track *::after {
  box-sizing: border-box;
}

.timeline-track {
  display: flex;
  min-width: 100%;
  height: 36px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.timeline-track.is-audio {
  height: 28px;
}

.timeline-track.is-hidden .track-lane {
  opacity: 0.35;
}

.timeline-track.is-drop-target .track-lane {
  background: rgba(96, 165, 250, 0.08);
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.45);
}

.timeline-track.is-audio.is-drop-target .track-lane {
  background: rgba(74, 222, 128, 0.08);
  box-shadow: inset 0 0 0 1px rgba(74, 222, 128, 0.45);
}

.track-head {
  position: sticky;
  left: 0;
  z-index: 6;
  width: 64px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 0 2px;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  background: #10151d;
}

.track-btn {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: #6e7681;
  cursor: pointer;
  font-size: 11px;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.track-btn:hover {
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.08);
}

.track-btn.is-active {
  color: #fbbf24;
  border-color: rgba(251, 191, 36, 0.5);
  background: rgba(251, 191, 36, 0.12);
}

.track-btn.is-danger:hover {
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.14);
}

.track-lane {
  position: relative;
  flex: 1;
  min-width: 0;
  /* 与标尺一致的左留白，保证 0 点片段不被轨头压边。 */
  margin-left: 8px;
  transition: opacity 0.15s ease;
}

/* 片段统一形制：直角矩形、左上角小号角标（文件名 + 时间码），仅以色相区分素材类型。 */
.timeline-clip {
  position: absolute;
  top: 3px;
  bottom: 3px;
  border-radius: 0;
  border: 1px solid rgba(96, 165, 250, 0.55);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.4), rgba(37, 99, 235, 0.2));
  background-color: #101828;
  overflow: hidden;
  cursor: grab;
  user-select: none;
  touch-action: none;
}

.timeline-clip.is-audio {
  border-color: rgba(74, 222, 128, 0.55);
  background: linear-gradient(180deg, rgba(22, 163, 74, 0.38), rgba(22, 163, 74, 0.18));
}

.timeline-clip.is-image {
  border-color: rgba(192, 132, 252, 0.55);
  background-color: #1b1030;
}

.timeline-clip.is-text {
  border-color: rgba(251, 191, 36, 0.55);
  background: linear-gradient(180deg, rgba(217, 119, 6, 0.34), rgba(217, 119, 6, 0.14));
}

.timeline-clip.is-selected {
  outline: 2px solid #93c5fd;
  outline-offset: -1px;
}

.timeline-clip.is-dragging {
  opacity: 0.45;
  cursor: grabbing;
}

.timeline-clip.is-muted::after {
  content: '静音';
  position: absolute;
  right: 4px;
  bottom: 2px;
  color: rgba(251, 191, 36, 0.9);
  font-size: 10px;
}

.clip-caption {
  position: absolute;
  top: 0;
  left: 0;
  max-width: 100%;
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  padding: 1px 4px;
  background: rgba(0, 0, 0, 0.55);
  pointer-events: none;
}

.clip-caption__name {
  font-size: 10px;
  color: rgba(230, 237, 243, 0.95);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.clip-caption__duration {
  flex-shrink: 0;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: rgba(230, 237, 243, 0.7);
}
</style>