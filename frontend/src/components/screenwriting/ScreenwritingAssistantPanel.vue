<template>
  <aside class="ai-chat-panel">
    <section class="assistant-shell">
      <ScreenwritingAssistantHeader
        :connected-model-id="connectedModelId"
        :message-count="messages.length"
      />

      <section
        v-if="ragWarmup.status !== 'idle'"
        class="rag-warmup"
        :class="`rag-warmup--${ragWarmup.status}`"
        aria-live="polite"
      >
        <div class="rag-warmup__meta">
          <span class="rag-warmup__dot"></span>
          <span class="rag-warmup__label">{{ ragWarmup.label }}</span>
          <span
            v-if="ragWarmup.detail"
            class="rag-warmup__detail"
            :title="ragWarmup.detail"
          >
            {{ ragWarmup.detail }}
          </span>
        </div>
        <div
          class="rag-warmup__track"
          role="progressbar"
          :aria-label="ragWarmup.label"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="ragWarmup.status === 'ready' || ragWarmup.status === 'failed' ? 100 : undefined"
        >
          <span class="rag-warmup__bar"></span>
        </div>
      </section>

      <ScreenwritingAssistantThread
        ref="threadRef"
        :messages="messages"
        :streaming-message-id="streamingMessageId"
      />

      <ScreenwritingAssistantComposer
        ref="composerRef"
        :model-value="modelValue"
        :is-sending="isSending"
        :input-limit="inputLimit"
        @update:model-value="emit('update:modelValue', $event)"
        @send="emit('send')"
        @new-conversation="emit('new-conversation')"
        @open-history="emit('open-history')"
        @insert-stage-prompt="emit('insert-stage-prompt')"
        @quote-events="emit('quote-events')"
        @open-config="emit('open-config')"
        @clear-composer="emit('clear-composer')"
      />

      <ScreenwritingConfigDrawer
        :model-value="configDrawerVisible"
        :initial="configInitial"
        :submitting="configSubmitting"
        @update:model-value="emit('update:configDrawerVisible', $event)"
        @submit="emit('submit-config', $event)"
      />
    </section>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ScreenwritingAssistantComposer from './ScreenwritingAssistantComposer.vue'
import ScreenwritingAssistantHeader from './ScreenwritingAssistantHeader.vue'
import ScreenwritingAssistantThread from './ScreenwritingAssistantThread.vue'
import ScreenwritingConfigDrawer from './ScreenwritingConfigDrawer.vue'
import type { ChatMessage, ScreenwritingRagWarmupViewState } from './types'
import type { ScreenwritingConfigDraft } from '@/api/screenwriting'

interface AssistantThreadExpose {
  followOutput: () => Promise<void>
  resetAutoScroll: () => void
  scrollToBottom: (behavior?: ScrollBehavior) => void
}

interface AssistantComposerExpose {
  focusComposer: () => void
}

withDefaults(defineProps<{
  modelValue: string
  messages: ChatMessage[]
  connectedModelId: string
  isSending: boolean
  streamingMessageId: number | null
  ragWarmup?: ScreenwritingRagWarmupViewState
  inputLimit?: number
  configDrawerVisible?: boolean
  configInitial?: ScreenwritingConfigDraft
  configSubmitting?: boolean
}>(), {
  ragWarmup: () => ({ status: 'idle', label: '' }),
  inputLimit: 2000,
  configDrawerVisible: false,
  configInitial: undefined,
  configSubmitting: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  'new-conversation': []
  'open-history': []
  'insert-stage-prompt': []
  'quote-events': []
  'open-config': []
  'submit-config': [draft: ScreenwritingConfigDraft]
  'update:configDrawerVisible': [value: boolean]
  'clear-composer': []
}>()

const threadRef = ref<AssistantThreadExpose | null>(null)
const composerRef = ref<AssistantComposerExpose | null>(null)

const focusComposer = () => {
  composerRef.value?.focusComposer()
}

const followOutput = async () => {
  await threadRef.value?.followOutput()
}

const resetAutoScroll = () => {
  threadRef.value?.resetAutoScroll()
}

const scrollToBottom = (behavior?: ScrollBehavior) => {
  threadRef.value?.scrollToBottom(behavior)
}

defineExpose({
  focusComposer,
  followOutput,
  resetAutoScroll,
  scrollToBottom,
})
</script>

<style scoped>
.ai-chat-panel {
  min-height: 0;
  overflow: hidden;
}

.assistant-shell {
  min-height: 0;
  height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background:
    radial-gradient(circle at 20% 0%, rgba(37, 99, 235, 0.14), transparent 34%),
    linear-gradient(180deg, rgba(15, 22, 32, 0.92), rgba(7, 11, 17, 0.96));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 22px 52px rgba(0, 0, 0, 0.42);
  overflow: hidden;
}

.rag-warmup {
  display: grid;
  gap: 7px;
  padding: 9px 14px 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  background: rgba(15, 23, 42, 0.42);
}

.rag-warmup__meta {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #cbd5e1;
  font-size: 12px;
  line-height: 1.35;
}

.rag-warmup__dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #60a5fa;
  box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.12);
}

.rag-warmup__label {
  flex: 0 0 auto;
  font-weight: 650;
}

.rag-warmup__detail {
  min-width: 0;
  overflow: hidden;
  color: #93a4b8;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rag-warmup__track {
  position: relative;
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
}

.rag-warmup__bar {
  position: absolute;
  inset: 0 auto 0 0;
  width: 38%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60a5fa, #22d3ee);
}

.rag-warmup--starting .rag-warmup__bar,
.rag-warmup--running .rag-warmup__bar {
  animation: rag-warmup-progress 1.15s ease-in-out infinite;
}

.rag-warmup--ready .rag-warmup__dot {
  background: #22c55e;
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.12);
}

.rag-warmup--ready .rag-warmup__bar {
  width: 100%;
  background: linear-gradient(90deg, #22c55e, #86efac);
}

.rag-warmup--failed .rag-warmup__dot {
  background: #f59e0b;
  box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.12);
}

.rag-warmup--failed .rag-warmup__bar {
  width: 100%;
  background: linear-gradient(90deg, #f59e0b, #f97316);
}

@keyframes rag-warmup-progress {
  0% {
    transform: translateX(-110%);
  }

  50% {
    transform: translateX(55%);
  }

  100% {
    transform: translateX(270%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .rag-warmup--starting .rag-warmup__bar,
  .rag-warmup--running .rag-warmup__bar {
    animation: none;
    width: 68%;
  }
}

@media (max-width: 920px) {
  .ai-chat-panel {
    overflow: visible;
  }

  .assistant-shell {
    min-height: 560px;
  }
}
</style>