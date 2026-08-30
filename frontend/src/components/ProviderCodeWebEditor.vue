<template>
  <div class="provider-code-web-editor">
    <Codemirror
      v-model="codeValue"
      placeholder="在这里编辑服务文件源码..."
      :style="{ height }"
      :autofocus="true"
      :disabled="disabled"
      :indent-with-tab="true"
      :tab-size="4"
      :extensions="extensions"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'

const props = withDefaults(defineProps<{
  modelValue: string
  height?: string
  disabled?: boolean
}>(), {
  height: '62vh',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const extensions = [python(), oneDark]

const codeValue = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})
</script>

<style scoped>
.provider-code-web-editor {
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  background: #0d1117;
}

.provider-code-web-editor :deep(.cm-editor) {
  width: 100%;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.58;
  outline: none;
}

.provider-code-web-editor :deep(.cm-scroller) {
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.32) transparent;
}

.provider-code-web-editor :deep(.cm-scroller::-webkit-scrollbar) {
  width: 8px;
  height: 8px;
}

.provider-code-web-editor :deep(.cm-scroller::-webkit-scrollbar-track) {
  background: transparent;
}

.provider-code-web-editor :deep(.cm-scroller::-webkit-scrollbar-thumb) {
  border: 2px solid transparent;
  border-radius: 999px;
  background-color: rgba(148, 163, 184, 0.28);
  background-clip: padding-box;
}

.provider-code-web-editor :deep(.cm-scroller::-webkit-scrollbar-thumb:hover) {
  background-color: rgba(148, 163, 184, 0.5);
}
</style>
