<template>
  <div class="markdown-editor-shell">
    <MdEditor
      v-model="editorValue"
      class="markdown-editor-instance"
      :theme="editorTheme"
      :toolbars="editorToolbars"
      :def-toolbars="previewToolbars"
      :footers="[]"
      :style="{ height }"
      preview-theme="github"
      code-theme="atom"
      language="zh-CN"
      no-upload-img
      :placeholder="placeholder"
      @onUploadImg="handleUploadImg"
      @drop.prevent
      @paste="preventMediaPaste"
    />

    <el-dialog
      v-model="previewMaximized"
      title="Markdown 预览"
      width="min(1180px, calc(100vw - 32px))"
      append-to-body
      class="markdown-preview-dialog"
    >
      <div class="markdown-preview-scroll">
        <MdPreview
          class="markdown-preview-instance"
          :model-value="editorValue"
          :theme="editorTheme"
          preview-theme="github"
          code-theme="atom"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Fragment, computed, h, ref } from 'vue'
import { FullScreen } from '@element-plus/icons-vue'
import { MdEditor, MdPreview, NormalToolbar } from 'md-editor-v3'
import type { ToolbarNames, UploadImgCallBack } from 'md-editor-v3'
import {
  MARKDOWN_EDITOR_TOOLBARS,
  normalizeMarkdownEditorTheme,
  type MarkdownEditorTheme,
} from '@/utils/markdownEditorConfig'

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  height?: string
  theme?: MarkdownEditorTheme
}>(), {
  modelValue: '',
  placeholder: '输入 Markdown 内容',
  height: '520px',
  theme: 'dark',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const previewMaximized = ref(false)

const editorValue = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})

const editorTheme = computed(() => normalizeMarkdownEditorTheme(props.theme))

const editorToolbars = computed<ToolbarNames[]>(() => {
  const previewMaximizeToolbarIndex = 0
  const toolbars: ToolbarNames[] = [...MARKDOWN_EDITOR_TOOLBARS]
  const rightToolbarIndex = toolbars.indexOf('=')

  if (rightToolbarIndex === -1) {
    toolbars.push(previewMaximizeToolbarIndex)
  } else {
    toolbars.splice(rightToolbarIndex + 1, 0, previewMaximizeToolbarIndex)
  }

  return toolbars
})

const previewToolbars = computed(() => (
  h(Fragment, [
    h(
      NormalToolbar,
      {
        title: '预览最大化',
        onClick: () => {
          previewMaximized.value = true
        },
      },
      {
        default: () => h(FullScreen, { class: 'markdown-preview-toolbar-icon' }),
      },
    ),
  ])
))

const handleUploadImg = (_files: File[], callback: UploadImgCallBack) => {
  callback([])
}

const preventMediaPaste = (event: ClipboardEvent) => {
  const items = event.clipboardData?.items
  if (!items) return

  for (const item of items) {
    if (item.type.startsWith('image/') || item.type.startsWith('video/')) {
      event.preventDefault()
      return
    }
  }
}
</script>

<style scoped>
.markdown-editor-shell {
  display: flex;
  flex-direction: column;
}

.markdown-editor-instance {
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: #0c1015;
}

.markdown-editor-instance :deep(.md-editor-toolbar-wrapper),
.markdown-editor-instance :deep(.md-editor-footer) {
  border-color: rgba(255, 255, 255, 0.1);
}

.markdown-editor-instance :deep(.md-editor-toolbar) {
  background: rgba(255, 255, 255, 0.025);
}

.markdown-editor-instance :deep(.cm-editor),
.markdown-editor-instance :deep(.md-editor-preview-wrapper) {
  font-size: 13px;
}

.markdown-editor-instance :deep(.markdown-preview-toolbar-icon) {
  width: 16px;
  height: 16px;
}

.markdown-editor-instance :deep(.cm-scroller),
.markdown-editor-instance :deep(.md-editor-preview-wrapper) {
  scrollbar-width: none;
}

.markdown-editor-instance :deep(.cm-scroller::-webkit-scrollbar),
.markdown-editor-instance :deep(.md-editor-preview-wrapper::-webkit-scrollbar) {
  display: none;
}
</style>

<style>
.markdown-preview-dialog {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 32px);
  overflow: hidden;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  color: #e6edf3;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
}

.markdown-preview-dialog .el-dialog__header {
  margin: 0;
  padding: 20px 24px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.markdown-preview-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 18px;
  font-weight: 800;
}

.markdown-preview-dialog .el-dialog__body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  overflow: hidden;
  padding: 18px 24px 24px;
  background: transparent;
}

.markdown-preview-dialog .markdown-preview-scroll {
  flex: 1 1 auto;
  min-height: 0;
  height: min(72vh, 760px);
  width: 100%;
  overflow-x: auto;
  overflow-y: scroll;
  scrollbar-gutter: stable;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 22px 26px;
  box-sizing: border-box;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.42) transparent;
}

.markdown-preview-dialog .markdown-preview-scroll::-webkit-scrollbar {
  display: block;
  width: 10px;
  height: 10px;
}

.markdown-preview-dialog .markdown-preview-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.markdown-preview-dialog .markdown-preview-scroll::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.42);
  background-clip: content-box;
}

.markdown-preview-dialog .markdown-preview-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.62);
  background-clip: content-box;
}

.markdown-preview-dialog .markdown-preview-instance {
  min-height: 100%;
  width: 100%;
  overflow: visible;
}

.markdown-preview-dialog .markdown-preview-instance .md-editor-preview {
  padding: 0;
}

.markdown-preview-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
}

.markdown-preview-dialog .el-dialog__headerbtn:hover .el-dialog__close,
.markdown-preview-dialog .el-dialog__headerbtn:focus .el-dialog__close {
  color: #ffffff;
}
</style>