<template>
  <footer class="assistant-composer">
    <div class="composer-toolbar">
      <el-tooltip content="新对话" placement="top">
        <button type="button" class="composer-tool" aria-label="新对话" @click="emit('new-conversation')">
          <el-icon><Plus /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="创作历史" placement="top">
        <button type="button" class="composer-tool" aria-label="创作历史" @click="emit('open-history')">
          <el-icon><Clock /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="插入当前阶段提示" placement="top">
        <button type="button" class="composer-tool" aria-label="插入当前阶段提示" @click="emit('insert-stage-prompt')">
          <el-icon><MagicStick /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="引用项目小说事件" placement="top">
        <button type="button" class="composer-tool" aria-label="引用项目小说事件" @click="emit('quote-events')">
          <el-icon><Connection /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="创作配置" placement="top">
        <button type="button" class="composer-tool" aria-label="创作配置" @click="emit('open-config')">
          <el-icon><Setting /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="清空输入" placement="top">
        <button
          type="button"
          class="composer-tool"
          aria-label="清空输入"
          :disabled="!modelValue"
          @click="emit('clear-composer')"
        >
          <el-icon><Delete /></el-icon>
        </button>
      </el-tooltip>

      <span class="composer-toolbar__spacer"></span>

      <span class="composer-counter" :class="{ 'is-limit': modelValue.length >= inputLimit }">
        {{ modelValue.length }} / {{ inputLimit }}
      </span>
    </div>

    <el-input
      ref="composerRef"
      v-model="inputValue"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      resize="none"
      :maxlength="inputLimit"
      placeholder="描述你的创作目标，例如：先梳理前十章的主线故事骨架。"
      @keydown.ctrl.enter.prevent="emit('send')"
    />

    <div class="assistant-composer__actions">
      <span class="composer-hint">Ctrl + Enter 发送</span>
      <el-button
        class="assistant-send-btn"
        type="primary"
        :disabled="!modelValue.trim() || isSending"
        :loading="isSending"
        @click="emit('send')"
      >
        <el-icon><MagicStick /></el-icon>
        &nbsp;发送
      </el-button>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { InputInstance } from 'element-plus'
import {
  Clock,
  Connection,
  Delete,
  MagicStick,
  Plus,
  Setting,
} from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{
  modelValue: string
  isSending: boolean
  inputLimit?: number
}>(), {
  inputLimit: 2000,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  'new-conversation': []
  'open-history': []
  'insert-stage-prompt': []
  'quote-events': []
  'open-config': []
  'clear-composer': []
}>()

const composerRef = ref<InputInstance | null>(null)

const inputValue = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const focusComposer = () => {
  nextTick(() => composerRef.value?.focus?.())
}

defineExpose({
  focusComposer,
})
</script>

<style scoped>
.assistant-composer {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent),
    rgba(9, 14, 22, 0.92);
}

.composer-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.composer-toolbar__spacer {
  flex: 1;
}

.composer-tool {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
  color: #8b949e;
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: color 0.18s ease, background-color 0.18s ease, border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.composer-tool :deep(.el-icon) {
  font-size: 16px;
}

.composer-tool:hover:not(:disabled) {
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.42);
  background: rgba(37, 99, 235, 0.14);
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.18);
}

.composer-tool:focus-visible {
  outline: none;
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.55);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
}

.composer-tool:active:not(:disabled) {
  transform: translateY(0) scale(0.94);
  background: rgba(37, 99, 235, 0.2);
}

.composer-tool:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.composer-counter {
  flex-shrink: 0;
  color: #6e7681;
  font-size: 12px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.composer-counter.is-limit {
  color: #fca5a5;
}

.composer-hint {
  color: #6e7681;
  font-size: 12px;
  line-height: 1.45;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.assistant-composer :deep(.el-textarea__inner) {
  padding: 10px 13px;
  border: none;
  border-radius: 10px;
  color: #e6edf3;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  font-size: 13px;
  line-height: 1.6;
}

.assistant-composer :deep(.el-textarea__inner:hover) {
  background-color: #0f151d;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.2) inset;
}

.assistant-composer :deep(.el-textarea__inner:focus) {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.assistant-composer :deep(.el-textarea__inner::placeholder) {
  color: #7e8893;
}

.assistant-composer :deep(.el-input__count) {
  color: #6e7681 !important;
  background: transparent !important;
  background-color: transparent !important;
}

.assistant-composer__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.assistant-composer__actions span {
  min-width: 0;
  color: #6e7681;
  font-size: 12px;
  line-height: 1.45;
}

.assistant-send-btn {
  --el-button-disabled-bg-color: rgba(255, 255, 255, 0.04);
  --el-button-disabled-border-color: rgba(255, 255, 255, 0.08);
  --el-button-disabled-text-color: #4d5560;
  flex-shrink: 0;
  height: 36px;
  min-width: 86px;
  padding: 0 16px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
}

.assistant-send-btn:hover,
.assistant-send-btn:focus {
  transform: translateY(-1px);
}

.assistant-send-btn :deep(.el-icon) {
  margin-right: 0;
  font-size: 15px;
}
</style>