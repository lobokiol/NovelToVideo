<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="780px"
    destroy-on-close
    class="task-item-dialog"
    modal-class="task-dark-overlay"
    :close-on-click-modal="false"
  >
    <div v-if="loading && !item" class="state">加载条目详情中…</div>
    <div v-else-if="!item" class="state">未能加载条目详情</div>
    <div v-else class="content">
      <section class="meta-row">
        <div class="meta-cell">
          <label>状态</label>
          <TaskStatusTag :status="item.status" />
        </div>
        <div class="meta-cell">
          <label>序号</label>
          <span class="mono">#{{ item.seq }}</span>
        </div>
        <div class="meta-cell">
          <label>创建</label>
          <span>{{ formatTime(item.createdAt) }}</span>
        </div>
        <div class="meta-cell">
          <label>开始</label>
          <span>{{ formatTime(item.startedAt) }}</span>
        </div>
        <div class="meta-cell">
          <label>结束</label>
          <span>{{ formatTime(item.finishedAt) }}</span>
        </div>
        <div class="meta-cell">
          <label>更新</label>
          <span>{{ formatTime(item.updatedAt) }}</span>
        </div>
      </section>

      <section v-if="item.errorMessage" class="error-box">
        <label>错误信息</label>
        <pre>{{ item.errorMessage }}</pre>
      </section>

      <section v-if="item.diagnostics" class="diagnostics">
        <header>
          <h4>诊断信息</h4>
        </header>
        <div class="diag-grid">
          <div class="diag-cell">
            <label>模型</label>
            <span class="mono">{{ item.diagnostics.modelId || '—' }}</span>
          </div>
          <div class="diag-cell">
            <label>队列</label>
            <span class="mono">{{ item.diagnostics.providerKey || '—' }}</span>
          </div>
          <div class="diag-cell">
            <label>消费者</label>
            <span class="mono">{{ item.diagnostics.workerConsumerName || '—' }}</span>
          </div>
          <div v-if="hasFiniteNumber(item.diagnostics.claimToCallMs)" class="diag-cell">
            <label>认领→调用</label>
            <span class="mono">{{ formatMs(item.diagnostics.claimToCallMs) }}</span>
          </div>
          <div class="diag-cell">
            <label>总耗时</label>
            <span class="mono">{{ formatMs(item.diagnostics.durationMs) }}</span>
          </div>
          <div class="diag-cell">
            <label>尝试次数</label>
            <span class="mono">{{ item.diagnostics.attemptCount }}</span>
          </div>
          <div class="diag-cell">
            <label>提示词长度</label>
            <span class="mono">
              {{ item.diagnostics.composedPromptLength ?? '—' }}
            </span>
          </div>
        </div>
      </section>

      <section v-if="item.retryOfPublicId" class="retry-link">
        <label>重试来源</label>
        <span class="mono">{{ item.retryOfPublicId }}</span>
      </section>

      <section v-if="hasInputPayload" class="viewer-section">
        <MdPreview
          class="readonly-code-preview payload-code-preview"
          :model-value="payloadCodeMarkdown"
          theme="dark"
          preview-theme="github"
          code-theme="atom"
        />
      </section>

      <section v-if="finalPromptText" class="viewer-section">
        <div class="viewer-title" @click="toggle('prompt')">
          <div class="viewer-title-left">
            <span class="window-dots" aria-hidden="true">
              <i class="dot red"></i>
              <i class="dot yellow"></i>
              <i class="dot green"></i>
            </span>
            <h4>任务提示词</h4>
          </div>
          <div class="viewer-title-actions">
            <span class="viewer-language">markdown</span>
            <button class="title-copy-btn" type="button" @click.stop="copyViewerText('任务提示词', finalPromptText)">
              {{ promptCopied ? '已复制!' : '复制代码' }}
            </button>
            <el-tooltip content="最大化预览" placement="top">
              <button
                class="title-icon-btn preview-icon-btn"
                type="button"
                aria-label="最大化任务提示词"
                @click.stop="promptMaximized = true"
              >
                <el-icon><FullScreen /></el-icon>
              </button>
            </el-tooltip>
            <button
              class="title-icon-btn collapse-btn"
              :class="{ 'is-collapsed': !expanded.prompt }"
              type="button"
              :aria-label="expanded.prompt ? '收起任务提示词' : '展开任务提示词'"
              @click.stop="toggle('prompt')"
            >
              <el-icon><ArrowDownBold /></el-icon>
            </button>
          </div>
        </div>
        <MdEditor
          v-if="expanded.prompt"
          v-model="promptEditorValue"
          class="readonly-prompt-editor"
          theme="dark"
          :preview="false"
          :toolbars="[]"
          :footers="[]"
          :style="{ height: '320px' }"
          preview-theme="github"
          code-theme="atom"
          language="zh-CN"
          no-upload-img
          read-only
          @drop.prevent
          @paste.prevent
        />
      </section>

      <section v-if="imagePreviewUrl" class="viewer-section media-viewer-section">
        <div class="viewer-title media-viewer-title">
          <div class="viewer-title-left">
            <span class="window-dots" aria-hidden="true">
              <i class="dot red"></i>
              <i class="dot yellow"></i>
              <i class="dot green"></i>
            </span>
            <h4>{{ isVideoMedia ? '生成视频' : '生成图片' }}</h4>
          </div>
          <div class="viewer-title-actions">
            <span v-if="item.mediaPublicId" class="viewer-language">{{ item.mediaPublicId }}</span>
            <button
              class="title-copy-btn"
              type="button"
              @click="copyViewerText(isVideoMedia ? '视频地址' : '图片地址', imagePreviewUrl)"
            >
              {{ copiedLabel === (isVideoMedia ? '视频地址' : '图片地址') ? '已复制!' : '复制地址' }}
            </button>
            <el-tooltip content="新窗口打开" placement="top">
              <button
                class="title-icon-btn preview-icon-btn"
                type="button"
                :aria-label="isVideoMedia ? '新窗口打开生成视频' : '新窗口打开生成图片'"
                @click="openImageUrl"
              >
                <el-icon><Link /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
        <div class="image-preview-shell">
          <video
            v-if="isVideoMedia"
            class="generated-video-preview"
            :src="imagePreviewUrl"
            controls
            preload="metadata"
            playsinline
          ></video>
          <img
            v-else
            class="generated-image-preview"
            :src="imagePreviewUrl"
            alt="异步任务生成图片"
            loading="lazy"
            @click="imageViewerVisible = true"
          />
        </div>
      </section>

      <section v-if="item.outputText" class="viewer-section">
        <MdPreview
          class="readonly-code-preview output-code-preview"
          :model-value="outputCodeMarkdown"
          theme="dark"
          preview-theme="github"
          code-theme="atom"
        />
      </section>

    </div>

    <template #footer>
      <el-button class="dialog-btn" @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>

  <el-dialog
    v-model="promptMaximized"
    title="任务提示词"
    width="min(1180px, calc(100vw - 32px))"
    append-to-body
    class="task-markdown-preview-dialog"
    modal-class="task-dark-overlay"
  >
    <div class="markdown-maximize-scroll">
      <MdPreview
        class="readonly-markdown-preview maximized"
        :model-value="finalPromptText"
        theme="dark"
        preview-theme="github"
        code-theme="atom"
      />
    </div>
  </el-dialog>

  <el-image-viewer
    v-if="imageViewerVisible && imagePreviewUrl"
    :url-list="[imagePreviewUrl]"
    hide-on-click-modal
    teleported
    @close="imageViewerVisible = false"
  />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElButton, ElDialog, ElMessage } from 'element-plus'
import { ArrowDownBold, FullScreen, Link } from '@element-plus/icons-vue'
import { MdEditor, MdPreview } from 'md-editor-v3'
import { getTaskItemApi, type TaskItemResponse } from '@/api/task'
import { getErrorMessage } from '@/composables/usePollErrorNotice'
import TaskStatusTag from './TaskStatusTag.vue'

const props = defineProps<{
  modelValue: boolean
  projectPublicId: string
  jobPublicId: string
  /** 父批次任务类型，用于判定媒体产物按视频或图片展示。 */
  jobTaskType?: string
  itemPublicId: string | null
  initialItem?: TaskItemResponse | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const item = ref<TaskItemResponse | null>(null)
const loading = ref(false)
const promptMaximized = ref(false)
const imageViewerVisible = ref(false)
const copiedLabel = ref('')
let copyResetTimer: number | null = null

const expanded = reactive({
  prompt: true,
})

const dialogTitle = computed(() => {
  if (item.value) return `条目 #${item.value.seq} 详情`
  return '条目详情'
})

const hasInputPayload = computed(() => (
  item.value?.inputPayload !== null && item.value?.inputPayload !== undefined
))

const finalPromptText = computed(() => item.value?.finalPrompt || item.value?.composedPrompt || '')

const promptEditorValue = computed({
  get: () => finalPromptText.value,
  set: (_value: string) => undefined,
})

const payloadCopyText = computed(() => formatJson(item.value?.inputPayload))

const payloadCodeMarkdown = computed(() => toCodeMarkdown(payloadCopyText.value, 'json'))

const outputCopyText = computed(() => formatOutputText(item.value?.outputText || ''))

const outputCodeLanguage = computed(() => detectCodeLanguage(outputCopyText.value))

const outputCodeMarkdown = computed(() => toCodeMarkdown(outputCopyText.value, outputCodeLanguage.value))

const imagePreviewUrl = computed(() => item.value?.mediaUrl || '')

/** 视频类批次（如 storyboard.shot_video）的媒体产物用 video 播放器展示。 */
const isVideoMedia = computed(() => (props.jobTaskType || '').toLowerCase().includes('video'))

const promptCopied = computed(() => copiedLabel.value === '任务提示词')

const toggle = (key: keyof typeof expanded) => {
  expanded[key] = !expanded[key]
}

const clearCopyState = () => {
  if (copyResetTimer !== null) {
    window.clearTimeout(copyResetTimer)
    copyResetTimer = null
  }
  copiedLabel.value = ''
}

const showCopied = (label: string) => {
  clearCopyState()
  copiedLabel.value = label
  copyResetTimer = window.setTimeout(() => {
    copiedLabel.value = ''
    copyResetTimer = null
  }, 1500)
}

const copyViewerText = async (label: string, value: string) => {
  try {
    await navigator.clipboard.writeText(value || '')
    showCopied(label)
  } catch (error) {
    console.error(`${label}复制失败`, error)
    ElMessage.error(`${label}复制失败`)
  }
}

const openImageUrl = () => {
  if (!imagePreviewUrl.value) return
  window.open(imagePreviewUrl.value, '_blank', 'noopener,noreferrer')
}

const formatTime = (value: string | null | undefined) => {
  if (!value) return '—'
  const t = new Date(value)
  if (Number.isNaN(t.getTime())) return '—'
  const pad = (n: number) => n.toString().padStart(2, '0')
  return (
    `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())} ` +
    `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`
  )
}

const formatMs = (value: number | null | undefined) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(2)} s`
}

const hasFiniteNumber = (value: number | null | undefined) => (
  typeof value === 'number' && Number.isFinite(value)
)

const formatJson = (value: unknown) => {
  if (value === null || value === undefined) return ''
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const stripMarkdownCodeFence = (value: string) => {
  const text = value.trim()
  if (!text.startsWith('```') && !text.startsWith('~~~')) return text

  const lines = text.split(/\r?\n/)
  if (lines.length < 2) return text

  const opening = lines[0].trim()
  const closing = lines[lines.length - 1].trim()
  const openMatch = opening.match(/^(`{3,}|~{3,})[ \t]*[A-Za-z0-9_-]*[ \t]*$/)
  const closeMatch = closing.match(/^(`{3,}|~{3,})[ \t]*$/)
  if (!openMatch || !closeMatch) return text

  const openFence = openMatch[1]
  const closeFence = closeMatch[1]
  if (openFence[0] !== closeFence[0] || closeFence.length < openFence.length) return text

  return lines.slice(1, -1).join('\n').trim()
}

const formatOutputText = (value: string) => {
  const text = stripMarkdownCodeFence(value)
  if (!text) return ''
  try {
    const parsed = JSON.parse(text)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return text
  }
}

const detectCodeLanguage = (value: string) => {
  const text = value.trim()
  if (!text) return 'text'
  try {
    JSON.parse(text)
    return 'json'
  } catch {
    return 'text'
  }
}

const toCodeMarkdown = (value: string, language: string) => {
  const content = value || ''
  const maxBacktickRun = Math.max(2, ...Array.from(content.matchAll(/`+/g), (match) => match[0].length))
  const fence = '`'.repeat(maxBacktickRun + 1)
  return `${fence}${language}\n${content}\n${fence}`
}

const loadItem = async () => {
  if (!props.projectPublicId || !props.jobPublicId || !props.itemPublicId) return
  loading.value = true
  try {
    const { data } = await getTaskItemApi(
      props.projectPublicId,
      props.jobPublicId,
      props.itemPublicId,
    )
    item.value = {
      ...data,
      mediaUrl: data.mediaUrl || item.value?.mediaUrl || null,
      mediaPublicId: data.mediaPublicId || item.value?.mediaPublicId || null,
    }
  } catch (error) {
    console.error('加载条目详情失败', error)
    ElMessage.error(getErrorMessage(error, '加载条目详情失败'))
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.itemPublicId] as const,
  ([open, id]) => {
    if (open && id) {
      item.value = props.initialItem?.publicId === id ? props.initialItem : null
      expanded.prompt = true
      imageViewerVisible.value = false
      clearCopyState()
      void loadItem()
    } else if (!open) {
      item.value = null
      promptMaximized.value = false
      imageViewerVisible.value = false
      clearCopyState()
    }
  },
)

onBeforeUnmount(clearCopyState)
</script>

<style scoped>
.state {
  padding: 32px 0;
  text-align: center;
  color: #8b949e;
  font-size: 13px;
}

.content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.meta-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px 16px;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
}

.meta-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.meta-cell label {
  color: #6e7681;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.meta-cell span {
  color: #e6edf3;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mono {
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.error-box {
  border: 1px solid rgba(248, 113, 113, 0.35);
  background: rgba(248, 113, 113, 0.08);
  border-radius: 10px;
  padding: 12px 14px;
}

.error-box label {
  display: block;
  color: #fca5a5;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.error-box pre {
  margin: 0;
  color: #fecaca;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.diagnostics {
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.025);
}

.diagnostics header h4 {
  margin: 0 0 10px;
  color: #c5cdd6;
  font-size: 13px;
  font-weight: 600;
}

.diag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px 16px;
}

.diag-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.diag-cell label {
  color: #6e7681;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.diag-cell span {
  color: #e6edf3;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.retry-link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.retry-link label {
  color: #6e7681;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.retry-link span {
  color: #93c5fd;
  font-size: 12px;
  word-break: break-all;
}

.block {
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
}

.block header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  background: rgba(255, 255, 255, 0.03);
  transition: background 0.15s ease;
}

.block header:hover {
  background: rgba(255, 255, 255, 0.06);
}

.block header h4 {
  margin: 0;
  color: #e6edf3;
  font-size: 13px;
  font-weight: 600;
}

.block header .toggle {
  color: #8b949e;
  font-size: 11px;
}

.viewer-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.viewer-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 40px;
  padding: 0 14px 0 0;
  overflow: hidden;
  border-radius: 6px;
  background: #151a21;
  cursor: pointer;
  user-select: none;
}

.viewer-title-left {
  display: flex;
  align-items: stretch;
  min-width: 0;
  height: 40px;
  background: #111720;
}

.window-dots {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 52px;
  width: 52px;
  padding: 0 0 0 14px;
}

.window-dots .dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.window-dots .red {
  background: #ff6b5f;
}

.window-dots .yellow {
  background: #f4c860;
}

.window-dots .green {
  background: #69d37a;
}

.viewer-title-left h4 {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  height: 40px;
  margin: 0 0 0 20px;
  padding: 0 12px;
  background: #10151c;
  color: #e6edf3;
  font-size: 18px;
  font-weight: 800;
  white-space: nowrap;
}

.viewer-title-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
  height: 40px;
}

.viewer-language {
  color: #b9d7ff;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 14px;
  line-height: 40px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-copy-btn {
  border: 0;
  padding: 0;
  background: transparent;
  color: #b9d7ff;
  font-size: 14px;
  line-height: 40px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.18s ease;
}

.title-copy-btn:hover,
.title-copy-btn:focus {
  color: #ffffff;
}

.title-icon-btn {
  box-sizing: border-box;
  width: 16px;
  height: 16px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(185, 215, 255, 0.78);
  border-radius: 999px;
  background: transparent;
  color: #e8f2ff;
  line-height: 1;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.title-icon-btn:hover,
.title-icon-btn:focus {
  background: rgba(185, 215, 255, 0.1);
  border-color: #ffffff;
  color: #ffffff;
}

.title-icon-btn :deep(.el-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: inherit;
  font-size: 13px;
  line-height: 1;
}

.title-icon-btn :deep(svg) {
  display: block;
  width: 1em;
  height: 1em;
}

.preview-icon-btn :deep(svg) {
  width: 12px;
  height: 12px;
  transform: none;
}

.preview-icon-btn {
  margin-inline-end: -2px;
}

.collapse-btn :deep(.el-icon) {
  transition: transform 0.18s ease;
}

.collapse-btn.is-collapsed :deep(.el-icon) {
  transform: rotate(90deg);
}

.code {
  margin: 0;
  padding: 12px 14px;
  color: #cbd5e1;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 60vh;
  overflow: auto;
  background: rgba(0, 0, 0, 0.25);
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.code::-webkit-scrollbar {
  width: 6px;
}

.code::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
}

.readonly-code-preview,
.readonly-markdown-preview {
  max-height: 60vh;
  overflow: auto;
  background: transparent;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.35) transparent;
}

.readonly-code-preview :deep(.md-editor-code) {
  margin: 0;
}

.readonly-code-preview :deep(.md-editor-code .md-editor-code-head) {
  height: 40px;
  border-radius: 6px 6px 0 0;
  background: #151a21;
}

.readonly-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-code-flag) {
  display: flex;
  align-items: center;
  height: 40px;
  margin-inline-start: 0;
  padding: 0 14px;
  background: #111720;
}

.readonly-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-code-flag span) {
  flex: 0 0 auto;
  margin-block-start: 0;
}

.readonly-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-code-flag)::after {
  display: flex;
  align-items: center;
  height: 40px;
  margin-inline-start: 20px;
  padding: 0 12px;
  background: #10151c;
  color: #e6edf3;
  font-size: 18px;
  font-weight: 800;
  white-space: nowrap;
}

.payload-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-code-flag)::after {
  content: "任务载荷";
}

.output-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-code-flag)::after {
  content: "任务输出";
}

.readonly-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-code-action) {
  height: 40px;
}

.readonly-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-code-lang),
.readonly-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-copy-button:not(data-is-icon)) {
  color: #b9d7ff;
  font-size: 14px;
  line-height: 40px;
}

.readonly-code-preview :deep(.md-editor-code .md-editor-code-head .md-editor-collapse-tips) {
  color: #b9d7ff;
}

.readonly-code-preview :deep(.md-editor-code pre code) {
  background: #0d1117;
}

.readonly-prompt-editor {
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  background: #0d1117;
}

.readonly-prompt-editor :deep(.md-editor-toolbar-wrapper),
.readonly-prompt-editor :deep(.md-editor-footer) {
  display: none;
}

.readonly-prompt-editor :deep(.cm-editor) {
  background: #0d1117;
  color: #cbd5e1;
  font-size: 12px;
}

.readonly-prompt-editor :deep(.cm-focused) {
  outline: none;
}

.readonly-prompt-editor :deep(.cm-scroller) {
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  scrollbar-width: none;
}

.readonly-prompt-editor :deep(.cm-scroller::-webkit-scrollbar) {
  display: none;
}

.readonly-prompt-editor :deep(.cm-content) {
  padding: 12px 0;
  caret-color: transparent;
}

.readonly-prompt-editor :deep(.cm-line) {
  padding: 0 14px;
  line-height: 1.65;
}

.readonly-prompt-editor :deep(.cm-gutters) {
  border-right-color: rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.025);
  color: #6e7681;
}

.readonly-prompt-editor :deep(.cm-activeLine),
.readonly-prompt-editor :deep(.cm-activeLineGutter) {
  background: transparent;
}

.readonly-prompt-editor :deep(.cm-selectionBackground),
.readonly-prompt-editor :deep(.cm-focused .cm-selectionBackground) {
  background: rgba(122, 162, 247, 0.26);
}

.readonly-code-preview :deep(.md-editor-preview-wrapper),
.readonly-markdown-preview :deep(.md-editor-preview-wrapper),
.readonly-code-preview :deep(.md-editor-preview),
.readonly-markdown-preview :deep(.md-editor-preview) {
  padding: 0;
  background: transparent;
  color: #cbd5e1;
}

.readonly-code-preview :deep(.md-editor-preview) {
  padding: 0;
}

.readonly-markdown-preview :deep(.md-editor-preview) {
  padding: 0;
}

.readonly-code-preview :deep(pre),
.readonly-markdown-preview :deep(pre) {
  margin: 0;
  border-radius: 10px;
  background: #0d1117;
}

.readonly-markdown-preview.maximized {
  max-height: none;
}

.readonly-markdown-preview.maximized :deep(.md-editor-preview) {
  padding: 0;
}

.readonly-code-preview :deep(code),
.readonly-markdown-preview :deep(code) {
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.readonly-markdown-preview :deep(p) {
  margin: 0 0 10px;
  color: #d6dde7;
  line-height: 1.7;
}

.readonly-markdown-preview :deep(p:last-child) {
  margin-bottom: 0;
}

.readonly-markdown-preview :deep(h1),
.readonly-markdown-preview :deep(h2),
.readonly-markdown-preview :deep(h3),
.readonly-markdown-preview :deep(h4),
.readonly-markdown-preview :deep(h5),
.readonly-markdown-preview :deep(h6) {
  margin: 16px 0 8px;
  color: #f2f4f8;
  line-height: 1.35;
}

.readonly-markdown-preview :deep(h1:first-child),
.readonly-markdown-preview :deep(h2:first-child),
.readonly-markdown-preview :deep(h3:first-child),
.readonly-markdown-preview :deep(h4:first-child),
.readonly-markdown-preview :deep(h5:first-child),
.readonly-markdown-preview :deep(h6:first-child) {
  margin-top: 0;
}

.readonly-markdown-preview :deep(blockquote) {
  margin: 10px 0;
  padding: 8px 12px;
  border-left: 3px solid rgba(122, 162, 247, 0.58);
  color: #b8c2cc;
  background: rgba(122, 162, 247, 0.08);
}

.readonly-markdown-preview :deep(ul),
.readonly-markdown-preview :deep(ol) {
  margin: 8px 0 10px;
  padding-left: 22px;
  color: #d6dde7;
  line-height: 1.7;
}

.readonly-code-preview::-webkit-scrollbar,
.readonly-markdown-preview::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.readonly-code-preview::-webkit-scrollbar-track,
.readonly-markdown-preview::-webkit-scrollbar-track {
  background: transparent;
}

.readonly-code-preview::-webkit-scrollbar-thumb,
.readonly-markdown-preview::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.35);
  background-clip: padding-box;
}

.dialog-btn {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.12);
  color: #e6edf3;
}

.dialog-btn:hover,
.dialog-btn:focus {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.22);
}

.media-viewer-title {
  cursor: default;
}

.image-preview-shell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  max-height: min(58vh, 520px);
  padding: 12px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background:
    linear-gradient(45deg, rgba(255, 255, 255, 0.025) 25%, transparent 25%),
    linear-gradient(-45deg, rgba(255, 255, 255, 0.025) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, rgba(255, 255, 255, 0.025) 75%),
    linear-gradient(-45deg, transparent 75%, rgba(255, 255, 255, 0.025) 75%),
    #0d1117;
  background-position: 0 0, 0 10px, 10px -10px, -10px 0;
  background-size: 20px 20px;
}

.generated-image-preview {
  display: block;
  max-width: 100%;
  max-height: calc(min(58vh, 520px) - 24px);
  object-fit: contain;
  border-radius: 8px;
  cursor: zoom-in;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
}

/* 视频类任务产物：原生播放器直接预览，尺寸约束与图片一致。 */
.generated-video-preview {
  display: block;
  width: 100%;
  max-height: calc(min(58vh, 520px) - 24px);
  object-fit: contain;
  border-radius: 8px;
  background: #000;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
}
</style>

<style>
/* 任务条目详情弹窗会被 Element Plus 挂载到 body，需在组件内提供非 scoped 暗色样式。 */
.task-dark-overlay {
  background-color: rgba(0, 0, 0, 0.72);
  backdrop-filter: blur(2px);
}

.task-item-dialog.el-dialog {
  overflow: hidden;
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.task-item-dialog .el-dialog__header {
  margin: 0;
  padding: 18px 24px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.task-item-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 18px;
  font-weight: 700;
}

.task-item-dialog .el-dialog__headerbtn {
  top: 13px;
  right: 16px;
  width: 34px;
  height: 34px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.task-item-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
  font-size: 17px;
}

.task-item-dialog .el-dialog__headerbtn:hover,
.task-item-dialog .el-dialog__headerbtn:focus {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.18);
}

.task-item-dialog .el-dialog__headerbtn:hover .el-dialog__close,
.task-item-dialog .el-dialog__headerbtn:focus .el-dialog__close {
  color: #ffffff;
}

.task-item-dialog .el-dialog__body {
  max-height: calc(100vh - 220px);
  padding: 18px 24px 20px;
  overflow-y: auto;
  color: #b8c2cc;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.35) transparent;
}

.task-item-dialog .el-dialog__body::-webkit-scrollbar {
  width: 8px;
}

.task-item-dialog .el-dialog__body::-webkit-scrollbar-track {
  background: transparent;
  margin: 8px 0;
}

.task-item-dialog .el-dialog__body::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.3);
  border: 2px solid transparent;
  border-radius: 999px;
  background-clip: padding-box;
}

.task-item-dialog .el-dialog__body::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}

.task-item-dialog .el-dialog__footer {
  padding: 12px 24px 18px;
  background: rgba(255, 255, 255, 0.015);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.task-item-dialog .el-dialog__footer .el-button {
  height: 34px;
  padding: 0 16px;
  border-radius: 8px;
  font-weight: 600;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;
}

.task-item-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
}

.task-item-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):hover,
.task-item-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):focus {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
  transform: translateY(-1px);
}

.task-item-dialog .el-dialog__footer .el-button:active {
  transform: translateY(0);
}

.task-markdown-preview-dialog.el-dialog {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 32px);
  overflow: hidden;
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.task-markdown-preview-dialog .el-dialog__header {
  margin: 0;
  padding: 18px 24px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.task-markdown-preview-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 18px;
  font-weight: 700;
}

.task-markdown-preview-dialog .el-dialog__body {
  flex: 1 1 auto;
  min-height: 0;
  padding: 18px 24px 24px;
  overflow: hidden;
  background: transparent;
}

.task-markdown-preview-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
}

.task-markdown-preview-dialog .el-dialog__headerbtn:hover .el-dialog__close,
.task-markdown-preview-dialog .el-dialog__headerbtn:focus .el-dialog__close {
  color: #ffffff;
}

.markdown-maximize-scroll {
  box-sizing: border-box;
  width: 100%;
  height: min(72vh, 760px);
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.42) transparent;
}

.markdown-maximize-scroll::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.markdown-maximize-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.markdown-maximize-scroll::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.42);
  background-clip: content-box;
}

.markdown-maximize-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.62);
  background-clip: content-box;
}
</style>