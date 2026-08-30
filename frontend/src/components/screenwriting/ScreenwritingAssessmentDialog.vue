<template>
  <el-dialog
    v-model="visibleModel"
    :title="`阶段质量评估 - ${stageLabel}`"
    width="min(1100px, calc(100vw - 24px))"
    append-to-body
    class="settings-dark-dialog screenwriting-assessment-dialog"
    :close-on-click-modal="!streaming"
  >
    <template v-if="view === 'report'">
      <div v-if="scoreEntries.length" class="assessment-scores" aria-label="评估评分">
        <span
          v-for="entry in scoreEntries"
          :key="entry.name"
          class="assessment-score"
          :class="{ 'is-overall': entry.isOverall }"
        >
          {{ entry.name }} {{ entry.value }}/10
        </span>
      </div>
      <div ref="reportBodyRef" class="assessment-report">
        <MdPreview
          v-if="report"
          id="screenwriting-assessment-report"
          class="assessment-report__markdown"
          :model-value="report"
          theme="dark"
          preview-theme="github"
          code-theme="github"
        />
        <div v-else class="assessment-empty">
          <span v-if="streaming" class="assessment-empty__loading">评估中，报告将实时显示…</span>
          <span v-else>{{ error || '暂无评估报告' }}</span>
        </div>
        <p v-if="streaming && report" class="assessment-streaming-hint">评估输出中…</p>
      </div>
    </template>

    <template v-else>
      <p class="assessment-confirm-tip">
        以下改进提示词由评估报告生成，可直接编辑；确认后将作为新的创作指令发送，
        由阶段助理重新生成「{{ stageLabel }}」（当前工作区内容会被覆盖）。
      </p>
      <MdEditor
        v-model="promptDraft"
        class="assessment-prompt-editor"
        theme="dark"
        preview-theme="github"
        code-theme="github"
        :toolbars="[]"
        :footers="[]"
        no-upload-img
        placeholder="改进提示词"
      />
    </template>

    <template #footer>
      <template v-if="view === 'report'">
        <el-button class="assessment-btn--ghost" @click="visibleModel = false">关闭</el-button>
        <el-button
          class="assessment-btn--primary"
          type="primary"
          :disabled="streaming || !improvementPrompt"
          @click="openConfirmView"
        >
          按评估改进并重新生成
        </el-button>
      </template>
      <template v-else>
        <el-button class="assessment-btn--ghost" @click="view = 'report'">返回报告</el-button>
        <el-button
          class="assessment-btn--primary"
          type="primary"
          :disabled="!promptDraft.trim() || regenerating"
          :loading="regenerating"
          @click="emit('confirm-improve', promptDraft.trim())"
        >
          确认重新生成
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { MdEditor, MdPreview } from 'md-editor-v3'
import type { ScreenwritingAssessmentScores } from '@/api/screenwriting'

const props = defineProps<{
  modelValue: boolean
  stageLabel: string
  report: string
  scores: ScreenwritingAssessmentScores
  improvementPrompt: string
  streaming: boolean
  error?: string
  regenerating?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'confirm-improve': [prompt: string]
}>()

const view = ref<'report' | 'confirm'>('report')
const promptDraft = ref('')
const reportBodyRef = ref<HTMLElement | null>(null)

const visibleModel = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const scoreEntries = computed(() =>
  Object.entries(props.scores).map(([name, value]) => ({
    name,
    value,
    isOverall: name.includes('综合'),
  })),
)

// 重新打开弹窗时回到报告视图。
watch(visibleModel, (visible) => {
  if (visible) {
    view.value = 'report'
  }
})

// 流式输出期间跟随滚动到底部。
watch(
  () => props.report,
  () => {
    if (!props.streaming) return
    nextTick(() => {
      const el = reportBodyRef.value
      if (el) {
        el.scrollTop = el.scrollHeight
      }
    })
  },
)

const openConfirmView = () => {
  promptDraft.value = props.improvementPrompt
  view.value = 'confirm'
}
</script>

<style scoped>
.assessment-scores {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.assessment-score {
  padding: 3px 12px;
  border: 1px solid rgba(96, 165, 250, 0.24);
  border-radius: 999px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.12);
  font-size: 12px;
  font-weight: 700;
}

.assessment-score.is-overall {
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.5);
  background: rgba(37, 99, 235, 0.28);
}

.assessment-report {
  height: min(70vh, 780px);
  min-height: 320px;
  overflow: auto;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(8, 12, 18, 0.58);
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.32) transparent;
}

.assessment-report::-webkit-scrollbar {
  width: 6px;
}

.assessment-report::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background-color: rgba(148, 163, 184, 0.3);
}

.assessment-report__markdown {
  color: #cbd5e1;
  background: transparent;
}

.assessment-report__markdown :deep(.md-editor-preview-wrapper),
.assessment-report__markdown :deep(.md-editor-preview) {
  padding: 0;
  color: #cbd5e1;
  background: transparent;
  font-size: 13px;
  line-height: 1.72;
}

.assessment-empty {
  min-height: 260px;
  display: grid;
  place-items: center;
  color: #8b949e;
  font-size: 13px;
}

.assessment-empty__loading {
  color: #93c5fd;
}

.assessment-streaming-hint {
  margin: 10px 0 0;
  color: #60a5fa;
  font-size: 12px;
}

.assessment-confirm-tip {
  margin: 0 0 8px;
  color: #9fb3c8;
  font-size: 13px;
  line-height: 1.7;
}

.assessment-prompt-editor {
  height: min(62vh, 680px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  overflow: hidden;
  --md-bk-color: rgba(8, 12, 18, 0.58);
}

.assessment-btn--ghost.el-button {
  height: 36px;
  padding: 0 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #c9d1d9;
  background: rgba(255, 255, 255, 0.04);
  box-shadow: none;
}

.assessment-btn--ghost.el-button:hover,
.assessment-btn--ghost.el-button:focus {
  color: #f2f4f8;
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.1);
}

.assessment-btn--primary.el-button {
  height: 36px;
  padding: 0 18px;
  border: none;
  border-radius: 10px;
  font-weight: 700;
  background: #2563eb;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
}

.assessment-btn--primary.el-button:hover,
.assessment-btn--primary.el-button:focus {
  background: #1d4ed8;
}

.assessment-btn--primary.el-button.is-disabled,
.assessment-btn--primary.el-button.is-disabled:hover {
  color: #4d5560;
  background: rgba(255, 255, 255, 0.05);
  box-shadow: none;
}
</style>

<style>
/* 评估弹窗边距压缩（teleport 到 body，需全局选择器覆盖暗黑弹窗默认内边距）。 */
.screenwriting-assessment-dialog .el-dialog__header {
  padding: 10px 16px 6px;
}

.screenwriting-assessment-dialog .el-dialog__title {
  font-size: 16px;
}

.screenwriting-assessment-dialog .el-dialog__headerbtn {
  top: 6px;
  right: 10px;
}

.screenwriting-assessment-dialog .el-dialog__body {
  padding: 6px 12px 8px;
  max-height: none;
}

.screenwriting-assessment-dialog .el-dialog__footer {
  padding: 6px 12px 10px;
}
</style>