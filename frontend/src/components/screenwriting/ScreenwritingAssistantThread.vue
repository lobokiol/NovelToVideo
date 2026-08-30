<template>
  <div class="assistant-thread-wrap">
    <div
      ref="assistantThreadRef"
      class="assistant-thread"
      aria-label="对话记录"
      @scroll="onAssistantThreadScroll"
      @wheel.passive="pauseAssistantAutoScroll"
      @pointerdown="onAssistantThreadPointerDown"
      @touchmove.passive="pauseAssistantAutoScroll"
    >
      <article
        v-for="message in messages"
        :key="message.id"
        class="assistant-message"
        :class="[
          `assistant-message--${message.role}`,
          { 'is-streaming': message.id === streamingMessageId },
        ]"
      >
        <div class="assistant-bubble">
          <div
            v-if="message.actions?.length"
            class="assistant-process"
            :class="{ 'is-collapsed': isProcessCollapsed(message) }"
          >
            <button
              type="button"
              class="assistant-process__toggle"
              :aria-expanded="!isProcessCollapsed(message)"
              @click="toggleProcess(message)"
            >
              <el-icon class="assistant-process__toggle-icon"><CaretBottom /></el-icon>
              <span class="assistant-process__latest">{{ latestActionMessage(message) }}</span>
              <span class="assistant-process__count">{{ message.actions.length }} 步</span>
            </button>
            <ul
              v-show="!isProcessCollapsed(message)"
              class="assistant-process__list"
              aria-label="执行过程"
            >
              <li v-for="(action, index) in message.actions" :key="index">
                <div class="assistant-process__row">
                  <code>{{ action.phase }}</code>
                  <span>{{ action.message }}</span>
                </div>
                <p v-if="action.detail" class="assistant-process__detail">{{ action.detail }}</p>
              </li>
            </ul>
          </div>
          <div
            v-if="isAssistantThinking(message)"
            class="assistant-thinking"
            aria-label="AI 正在思考"
          >
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div
            v-else-if="isAssistantStreaming(message)"
            class="assistant-streaming-text"
          >
            {{ message.content }}<span class="assistant-type-caret"></span>
          </div>
          <MdPreview
            v-else
            class="assistant-markdown-preview"
            :model-value="message.content"
            theme="dark"
            preview-theme="github"
            code-theme="atom"
          />
          <div
            v-if="hasAssistantDiagnostics(message)"
            class="assistant-diagnostics"
            :class="{
              'is-collapsed': isAssistantDiagnosticsCollapsed(message),
              'has-failure': hasRagFailure(message),
            }"
          >
            <button
              type="button"
              class="assistant-diagnostics__toggle"
              :aria-expanded="!isAssistantDiagnosticsCollapsed(message)"
              @click="toggleAssistantDiagnostics(message)"
            >
              <el-icon class="assistant-diagnostics__toggle-icon"><CaretBottom /></el-icon>
              <span>
                {{ isAssistantDiagnosticsCollapsed(message) ? '展开检索详情' : '收起检索详情' }}
              </span>
            </button>
            <div
              v-if="message.rag"
              class="assistant-rag"
            >
              <div class="assistant-rag__summary" aria-label="本轮资料检索状态">
                <span>{{ ragRetrievalModeLabel(message) }}</span>
                <span>命中 {{ message.rag.hitCount }} / 文档 {{ message.rag.documentCount }}</span>
                <span v-if="message.rag.runtime.indexCacheHit">索引缓存命中</span>
                <span v-if="hasRagFailure(message)">资料检索降级</span>
              </div>
            </div>
            <div
              v-show="!isAssistantDiagnosticsCollapsed(message)"
              class="assistant-diagnostics__details"
            >
              <ul
                v-if="message.rag && visibleRagHits(message).length"
                class="assistant-rag__hits"
                aria-label="本轮参考资料"
              >
                <li
                  v-for="hit in visibleRagHits(message)"
                  :key="hit.sourceId"
                >
                  <span class="assistant-rag__hit-title" :title="hit.title">{{ hit.title }}</span>
                  <span class="assistant-rag__hit-type">{{ ragSourceTypeLabel(hit.sourceType) }}</span>
                  <span class="assistant-rag__hit-score">{{ ragScoreLabel(hit.score) }}</span>
                </li>
              </ul>
              <div
                v-if="message.serverTimings"
                class="assistant-server-timings"
                aria-label="服务端阶段耗时"
              >
                <span>服务端 {{ formatDurationMs(message.serverTimings.totalMs) }}</span>
                <span v-if="shouldShowClientToServerTiming(message)">
                  请求 {{ formatDurationMs(message.serverTimings.clientToServerMs) }}
                </span>
                <span
                  v-for="stage in visibleServerTimingStages(message)"
                  :key="stage.name"
                >
                  {{ serverTimingStageLabel(stage.name) }} {{ formatDurationMs(stage.durationMs) }}
                </span>
              </div>
            </div>
          </div>
          <time class="assistant-bubble__time">{{ message.time }}</time>
          <div
            v-if="shouldShowThinkingElapsed(message)"
            class="assistant-bubble__thinking-time"
          >
            思考 {{ formatThinkingElapsed(message.thinkingElapsedMs) }}
          </div>
        </div>
      </article>
    </div>

    <button
      v-if="showAssistantScrollBottom"
      type="button"
      class="assistant-scroll-bottom-btn"
      aria-label="回到最新消息"
      @click="resumeAssistantAutoScroll"
    >
      <el-icon><CaretBottom /></el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { MdPreview } from 'md-editor-v3'
import { CaretBottom } from '@element-plus/icons-vue'
import type { ScreenwritingRagHit, ScreenwritingServerTimingStage } from '@/api/screenwriting'
import type { ChatMessage } from './types'

const props = defineProps<{
  messages: ChatMessage[]
  streamingMessageId: number | null
}>()

const assistantThreadRef = ref<HTMLElement | null>(null)
const showAssistantScrollBottom = ref(false)
const assistantAutoScrollEnabled = ref(true)
const collapsedDiagnosticsMessageIds = ref<Set<number>>(new Set())
const SERVER_TIMING_STAGE_ORDER = ['project', 'rag', 'agentSetup', 'agentRun', 'modelStream']
const SERVER_TIMING_STAGE_LABELS: Record<string, string> = {
  project: '项目',
  rag: '检索',
  agentSetup: 'Agent',
  agentRun: '生成',
  modelStream: '生成',
}

const isAssistantThinking = (message: ChatMessage) => (
  message.role === 'assistant' && !message.content.trim()
)

const isAssistantStreaming = (message: ChatMessage) => (
  message.role === 'assistant'
  && message.id === props.streamingMessageId
  && Boolean(message.content.trim())
)

const ragRetrievalModeLabel = (message: ChatMessage) => {
  const mode = message.rag?.runtime.retrievalMode
  if (mode === 'metadata') {
    return message.rag?.runtime.retrievalStrategy === 'chapter_index_exact'
      ? '章节直达'
      : '资料直达'
  }
  if (mode === 'vector') return '向量检索'
  if (mode === 'lexical_fallback') return '词法降级'
  if (mode === 'empty') return '无命中'
  if (mode === 'lexical') return '词法检索'
  return typeof mode === 'string' && mode.trim() ? mode.trim() : '资料检索'
}

const ragSourceTypeLabel = (sourceType: string) => {
  if (sourceType === 'project') return '项目'
  if (sourceType === 'novel') return '小说'
  if (sourceType === 'chapter') return '章节'
  if (sourceType === 'art_style') return '视觉'
  if (sourceType === 'director_manual') return '导演'
  return sourceType || '资料'
}

const ragScoreLabel = (score: number) => (
  Number.isFinite(score) ? score.toFixed(2) : '0.00'
)

const visibleRagHits = (message: ChatMessage): ScreenwritingRagHit[] => (
  message.rag?.hits.slice(0, 3) ?? []
)

const hasRagFailure = (message: ChatMessage) => (
  Boolean(message.rag?.runtime.failureReason)
)

const hasAssistantDiagnostics = (message: ChatMessage) => (
  Boolean(message.rag || message.serverTimings)
)

const isAssistantDiagnosticsCollapsed = (message: ChatMessage) => (
  collapsedDiagnosticsMessageIds.value.has(message.id)
)

const toggleAssistantDiagnostics = (message: ChatMessage) => {
  const nextIds = new Set(collapsedDiagnosticsMessageIds.value)
  if (nextIds.has(message.id)) {
    nextIds.delete(message.id)
  } else {
    nextIds.add(message.id)
  }
  collapsedDiagnosticsMessageIds.value = nextIds
}

// 执行过程面板默认折叠，展开状态按消息 id 记录。
const expandedProcessMessageIds = ref<Set<number>>(new Set())

const isProcessCollapsed = (message: ChatMessage) => (
  !expandedProcessMessageIds.value.has(message.id)
)

const toggleProcess = (message: ChatMessage) => {
  const nextIds = new Set(expandedProcessMessageIds.value)
  if (nextIds.has(message.id)) {
    nextIds.delete(message.id)
  } else {
    nextIds.add(message.id)
  }
  expandedProcessMessageIds.value = nextIds
}

const latestActionMessage = (message: ChatMessage) => {
  const actions = message.actions ?? []
  return actions[actions.length - 1]?.message ?? '执行过程'
}

const isServerTimingStage = (
  stage: ScreenwritingServerTimingStage | undefined,
): stage is ScreenwritingServerTimingStage => Boolean(stage)

const visibleServerTimingStages = (message: ChatMessage): ScreenwritingServerTimingStage[] => {
  const stages = message.serverTimings?.stages ?? []
  return SERVER_TIMING_STAGE_ORDER
    .map((stageName) => stages.find((stage) => stage.name === stageName))
    .filter(isServerTimingStage)
}

const serverTimingStageLabel = (stageName: string) => (
  SERVER_TIMING_STAGE_LABELS[stageName] ?? stageName
)

const shouldShowClientToServerTiming = (message: ChatMessage) => (
  typeof message.serverTimings?.clientToServerMs === 'number'
)

const formatDurationMs = (durationMs: number | null | undefined) => {
  const safeMs = Math.max(0, Math.floor(durationMs ?? 0))
  if (safeMs < 1000) return `${safeMs}ms`
  if (safeMs < 10000) return `${(safeMs / 1000).toFixed(1)}s`
  return `${Math.round(safeMs / 1000)}s`
}

const shouldShowThinkingElapsed = (message: ChatMessage) => (
  message.role === 'assistant'
  && typeof message.thinkingElapsedMs === 'number'
  && message.thinkingElapsedMs >= 0
)

const formatThinkingElapsed = (elapsedMs: number | undefined) => {
  const safeMs = Math.max(0, Math.floor(elapsedMs ?? 0))
  const totalSeconds = Math.floor(safeMs / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
}

const waitForAssistantLayoutFrame = () => (
  new Promise<void>((resolve) => {
    window.requestAnimationFrame(() => resolve())
  })
)

const isAssistantThreadAtBottom = () => {
  const el = assistantThreadRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= 24
}

const updateAssistantScrollState = () => {
  const el = assistantThreadRef.value
  if (!el) {
    showAssistantScrollBottom.value = false
    return
  }
  showAssistantScrollBottom.value = el.scrollHeight > el.clientHeight && !isAssistantThreadAtBottom()
}

const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
  const el = assistantThreadRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior })
  showAssistantScrollBottom.value = false
}

const followOutput = async () => {
  await nextTick()
  await waitForAssistantLayoutFrame()
  if (assistantAutoScrollEnabled.value) {
    scrollToBottom('smooth')
  } else {
    updateAssistantScrollState()
  }
}

const pauseAssistantAutoScroll = () => {
  assistantAutoScrollEnabled.value = false
  updateAssistantScrollState()
}

const onAssistantThreadPointerDown = (event: PointerEvent) => {
  const el = assistantThreadRef.value
  if (!el) return

  const rect = el.getBoundingClientRect()
  const scrollbarHitWidth = Math.max(12, el.offsetWidth - el.clientWidth + 2)
  if (event.clientX >= rect.right - scrollbarHitWidth) {
    pauseAssistantAutoScroll()
  }
}

const resumeAssistantAutoScroll = () => {
  assistantAutoScrollEnabled.value = true
  scrollToBottom()
}

const onAssistantThreadScroll = () => {
  updateAssistantScrollState()
}

const resetAutoScroll = () => {
  assistantAutoScrollEnabled.value = true
}

defineExpose({
  followOutput,
  resetAutoScroll,
  scrollToBottom,
})
</script>

<style scoped>
.assistant-thread-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  background: rgba(4, 8, 14, 0.24);
}

.assistant-thread {
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 12px 16px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.assistant-thread::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.assistant-thread::-webkit-scrollbar-track {
  background: transparent;
}

.assistant-thread::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.assistant-thread::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.assistant-scroll-bottom-btn {
  position: absolute;
  right: 16px;
  bottom: 14px;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(96, 165, 250, 0.38);
  border-radius: 50%;
  color: #dbeafe;
  background: rgba(13, 18, 27, 0.92);
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.34);
  cursor: pointer;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.assistant-scroll-bottom-btn :deep(.el-icon) {
  font-size: 18px;
}

.assistant-scroll-bottom-btn:hover,
.assistant-scroll-bottom-btn:focus {
  color: #ffffff;
  border-color: rgba(96, 165, 250, 0.65);
  background: rgba(37, 99, 235, 0.72);
  transform: translateY(-1px);
}

.assistant-scroll-bottom-btn:active {
  transform: translateY(0);
}

.assistant-message {
  display: flex;
  align-items: flex-start;
}

.assistant-message.is-streaming .assistant-bubble {
  border-color: rgba(96, 165, 250, 0.24);
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.08);
}

.assistant-message--user {
  justify-content: flex-end;
}

.assistant-message--user .assistant-bubble {
  max-width: 86%;
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(30, 64, 175, 0.36);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.assistant-bubble {
  min-width: 0;
  max-width: 92%;
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
  background: rgba(15, 22, 32, 0.72);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.assistant-bubble__time {
  justify-self: end;
  color: #7e8893;
  font-size: 11px;
  line-height: 1;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.assistant-bubble__thinking-time {
  justify-self: end;
  color: #9fb4cc;
  font-size: 11px;
  line-height: 1;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.assistant-diagnostics {
  min-width: 0;
  display: grid;
  gap: 6px;
  padding-top: 7px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.assistant-diagnostics__toggle {
  justify-self: start;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #8da2ba;
  font-size: 11px;
  line-height: 1.3;
  cursor: pointer;
}

.assistant-diagnostics__toggle:hover {
  color: #cbd5e1;
}

.assistant-diagnostics__toggle-icon {
  flex-shrink: 0;
  font-size: 12px;
  transition: transform 0.16s ease;
}

.assistant-diagnostics.is-collapsed .assistant-diagnostics__toggle-icon {
  transform: rotate(-90deg);
}

.assistant-diagnostics__details {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.assistant-rag {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.assistant-rag__summary {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 8px;
  color: #9aa7b5;
  font-size: 11px;
  line-height: 1.35;
}

.assistant-rag__summary span {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.06);
}

.assistant-diagnostics.has-failure .assistant-rag__summary span:last-child {
  color: #fcd34d;
  border-color: rgba(245, 158, 11, 0.22);
  background: rgba(245, 158, 11, 0.08);
}

.assistant-rag__hits {
  min-width: 0;
  display: grid;
  gap: 3px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.assistant-rag__hits li {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 7px;
  color: #8b949e;
  font-size: 11px;
  line-height: 1.45;
}

.assistant-rag__hit-title {
  min-width: 0;
  overflow: hidden;
  color: #b8c2cc;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-rag__hit-type,
.assistant-rag__hit-score {
  flex-shrink: 0;
  color: #7e8893;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.assistant-server-timings {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
  color: #8b95a1;
  font-size: 11px;
  line-height: 1.35;
}

.assistant-server-timings span {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 1px 6px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.13);
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.05);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-streaming-text {
  min-width: 0;
  max-width: 100%;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.68;
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-type-caret {
  display: inline-block;
  width: 1px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.12em;
  background: rgba(147, 197, 253, 0.9);
  animation: assistant-caret-blink 0.9s steps(2, start) infinite;
}

@keyframes assistant-caret-blink {
  0%,
  48% {
    opacity: 1;
  }

  49%,
  100% {
    opacity: 0;
  }
}

.assistant-markdown-preview {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  color: #cbd5e1;
  background: transparent;
  font-size: 13px;
  line-height: 1.68;
}

.assistant-markdown-preview :deep(.md-editor-preview-wrapper),
.assistant-markdown-preview :deep(.md-editor-preview) {
  padding: 0;
  background: transparent;
  color: #cbd5e1;
}

.assistant-markdown-preview :deep(.md-editor-preview) {
  font-size: 13px;
  line-height: 1.68;
  word-break: break-word;
}

.assistant-markdown-preview :deep(p) {
  margin: 0 0 8px;
  color: #cbd5e1;
  line-height: 1.68;
  white-space: normal;
}

.assistant-markdown-preview :deep(p:last-child) {
  margin-bottom: 0;
}

.assistant-markdown-preview :deep(h1),
.assistant-markdown-preview :deep(h2),
.assistant-markdown-preview :deep(h3),
.assistant-markdown-preview :deep(h4),
.assistant-markdown-preview :deep(h5),
.assistant-markdown-preview :deep(h6) {
  margin: 12px 0 6px;
  color: #f2f4f8;
  line-height: 1.35;
  font-weight: 750;
}

.assistant-markdown-preview :deep(h1:first-child),
.assistant-markdown-preview :deep(h2:first-child),
.assistant-markdown-preview :deep(h3:first-child),
.assistant-markdown-preview :deep(h4:first-child),
.assistant-markdown-preview :deep(h5:first-child),
.assistant-markdown-preview :deep(h6:first-child) {
  margin-top: 0;
}

.assistant-markdown-preview :deep(h1) {
  font-size: 18px;
}

.assistant-markdown-preview :deep(h2) {
  font-size: 16px;
}

.assistant-markdown-preview :deep(h3),
.assistant-markdown-preview :deep(h4),
.assistant-markdown-preview :deep(h5),
.assistant-markdown-preview :deep(h6) {
  font-size: 14px;
}

.assistant-markdown-preview :deep(ul),
.assistant-markdown-preview :deep(ol) {
  margin: 6px 0 10px;
  padding-left: 20px;
  color: #cbd5e1;
  line-height: 1.65;
}

.assistant-markdown-preview :deep(li) {
  margin: 2px 0;
  padding-left: 2px;
}

.assistant-markdown-preview :deep(blockquote) {
  margin: 8px 0;
  padding: 7px 10px;
  border-left: 3px solid rgba(96, 165, 250, 0.56);
  border-radius: 6px;
  color: #b8c2cc;
  background: rgba(96, 165, 250, 0.08);
}

.assistant-markdown-preview :deep(code) {
  border-radius: 5px;
  padding: 1px 5px;
  color: #dbeafe;
  background: rgba(15, 23, 42, 0.88);
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px;
}

.assistant-markdown-preview :deep(pre) {
  max-width: 100%;
  margin: 8px 0;
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: #0d1117;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.32) transparent;
}

.assistant-markdown-preview :deep(pre code) {
  display: block;
  padding: 10px 12px;
  color: #d6dde7;
  background: transparent;
  line-height: 1.55;
  white-space: pre;
}

.assistant-markdown-preview :deep(pre::-webkit-scrollbar) {
  height: 8px;
}

.assistant-markdown-preview :deep(pre::-webkit-scrollbar-track) {
  background: transparent;
}

.assistant-markdown-preview :deep(pre::-webkit-scrollbar-thumb) {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.32);
}

.assistant-markdown-preview :deep(table) {
  display: block;
  max-width: 100%;
  margin: 8px 0;
  overflow-x: auto;
  border-collapse: collapse;
  font-size: 12px;
}

.assistant-markdown-preview :deep(th),
.assistant-markdown-preview :deep(td) {
  padding: 6px 8px;
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.assistant-markdown-preview :deep(a) {
  color: #93c5fd;
  text-decoration: none;
}

.assistant-markdown-preview :deep(a:hover) {
  color: #bfdbfe;
  text-decoration: underline;
}

.assistant-markdown-preview :deep(hr) {
  margin: 12px 0;
  border: none;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
}

.assistant-thinking {
  min-width: 44px;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.assistant-thinking span {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: #93c5fd;
  opacity: 0.38;
  animation: assistant-thinking-pulse 1s ease-in-out infinite;
}

.assistant-thinking span:nth-child(2) {
  animation-delay: 0.16s;
}

.assistant-thinking span:nth-child(3) {
  animation-delay: 0.32s;
}

@keyframes assistant-thinking-pulse {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.38;
  }

  40% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

.assistant-process {
  margin-bottom: 8px;
  border: 1px solid rgba(96, 165, 250, 0.18);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.55);
  overflow: hidden;
}

.assistant-process__toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: none;
  background: transparent;
  color: #9fb3c8;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.assistant-process__toggle:hover {
  color: #dbeafe;
  background: rgba(37, 99, 235, 0.1);
}

.assistant-process__toggle-icon {
  flex: 0 0 auto;
  font-size: 12px;
  color: #60a5fa;
  transition: transform 0.18s ease;
}

.assistant-process.is-collapsed .assistant-process__toggle-icon {
  transform: rotate(-90deg);
}

.assistant-process__latest {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #c3d4e6;
}

.assistant-process__count {
  flex: 0 0 auto;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid rgba(96, 165, 250, 0.24);
  color: #93c5fd;
  font-size: 11px;
}

.assistant-process__list {
  margin: 0;
  padding: 4px 10px 8px;
  list-style: none;
  display: grid;
  gap: 6px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.assistant-process__row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.assistant-process__row code {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(37, 99, 235, 0.14);
  color: #93c5fd;
  font-size: 11px;
}

.assistant-process__row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #cbd5e1;
  font-size: 12px;
}

.assistant-process__detail {
  margin: 2px 0 0;
  padding-left: 2px;
  color: #8b949e;
  font-size: 11px;
  line-height: 1.5;
  word-break: break-word;
}
</style>