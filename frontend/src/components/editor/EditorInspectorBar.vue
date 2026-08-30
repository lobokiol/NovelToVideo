<template>
  <div class="inspector-bar">
    <span class="inspector-bar__name">{{ clip.mediaType === 'text' ? '文本片段' : clip.label }}</span>

    <template v-if="isStill">
      <div v-if="clip.mediaType === 'text'" class="inspector-bar__field is-text">
        <span>文本内容</span>
        <el-input
          :model-value="clip.text"
          size="small"
          maxlength="120"
          placeholder="输入要显示的文字"
          @update:model-value="onTextChange"
        />
      </div>
      <div v-if="clip.mediaType === 'text'" class="inspector-bar__field is-scale">
        <span>缩放 x{{ (clip.textScale || 1).toFixed(1) }}</span>
        <el-slider
          :model-value="clip.textScale || 1"
          :min="TEXT_SCALE_MIN"
          :max="TEXT_SCALE_MAX"
          :step="0.1"
          size="small"
          @update:model-value="onTextScaleChange"
        />
      </div>
      <div class="inspector-bar__field is-duration">
        <span>时长（秒）</span>
        <el-input-number
          :model-value="durationSeconds"
          size="small"
          :min="1"
          :max="600"
          :step="1"
          @update:model-value="onDurationChange"
        />
      </div>
    </template>

    <template v-else>
      <div class="inspector-bar__field">
        <span>入点 {{ formatClockMs(clip.inMs) }} · 出点 {{ formatClockMs(clip.outMs) }}</span>
        <el-slider
          :model-value="[clip.inMs, clip.outMs]"
          range
          :min="0"
          :max="clip.srcDurationMs"
          :step="100"
          size="small"
          @update:model-value="onTrimChange"
        />
      </div>
      <div class="inspector-bar__field is-volume">
        <span>音量 {{ Math.round(clip.volume * 100) }}%</span>
        <el-slider
          :model-value="clip.volume"
          :min="0"
          :max="1"
          :step="0.05"
          size="small"
          @update:model-value="onVolumeChange"
        />
      </div>
      <el-checkbox :model-value="clip.muted" @update:model-value="onMutedChange">片段静音</el-checkbox>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { clipDurationMs, formatClockMs, isStillClip } from './timelineDoc'
import { TEXT_SCALE_MAX, TEXT_SCALE_MIN, type TimelineClip } from './types'

const props = defineProps<{
  clip: TimelineClip
}>()

const emit = defineEmits<{
  (e: 'update-trim', range: [number, number]): void
  (e: 'update-volume', volume: number): void
  (e: 'update-muted', muted: boolean): void
  (e: 'update-text', text: string): void
  (e: 'update-text-scale', scale: number): void
  (e: 'update-duration', durationMs: number): void
}>()

const isStill = computed(() => isStillClip(props.clip))
const durationSeconds = computed(() => Math.max(1, Math.round(clipDurationMs(props.clip) / 1000)))

const onTrimChange = (value: number | number[]) => {
  if (!Array.isArray(value) || value.length < 2) return
  emit('update-trim', [value[0], value[1]])
}

const onVolumeChange = (value: number | number[]) => {
  if (Array.isArray(value)) return
  emit('update-volume', value)
}

const onMutedChange = (value: string | number | boolean) => {
  emit('update-muted', Boolean(value))
}

const onTextChange = (value: string) => {
  emit('update-text', value)
}

const onTextScaleChange = (value: number | number[]) => {
  if (Array.isArray(value)) return
  emit('update-text-scale', value)
}

const onDurationChange = (value: number | undefined) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return
  emit('update-duration', Math.round(value * 1000))
}
</script>

<style scoped>
.inspector-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 6px 14px;
  border: 1px solid rgba(96, 165, 250, 0.25);
  border-radius: 10px;
  background: rgba(37, 99, 235, 0.1);
  flex-wrap: wrap;
}

.inspector-bar__name {
  font-weight: 700;
  font-size: 12px;
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.inspector-bar__field {
  flex: 1;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  gap: 0;
  font-size: 11px;
  color: #8b949e;
}

.inspector-bar__field.is-volume {
  max-width: 180px;
}

.inspector-bar__field.is-text {
  gap: 4px;
}

.inspector-bar__field.is-scale {
  flex: 0 0 auto;
  min-width: 150px;
  max-width: 180px;
}

.inspector-bar__field.is-duration {
  flex: 0 0 auto;
  min-width: 120px;
  gap: 4px;
}

.inspector-bar__field.is-duration :deep(.el-input-number) {
  width: 110px;
}

:deep(.el-checkbox__label) {
  color: #c5cdd6;
  font-size: 12px;
}

:deep(.el-slider__runway) {
  background: rgba(255, 255, 255, 0.1);
}

:deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.05);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.14) inset;
}

:deep(.el-input__inner) {
  color: #e6edf3;
}
</style>