<template>
  <el-dialog
    v-model="visibleModel"
    title="创作历史"
    width="min(980px, calc(100vw - 32px))"
    append-to-body
    destroy-on-close
    class="settings-dark-dialog screenwriting-history-dialog"
  >
    <div v-if="!historyEntries.length" class="history-empty">
      <el-icon><Clock /></el-icon>
      <strong>暂无创作历史</strong>
      <p>点击"新对话"后，当前工作区和对话会归档到这里，可随时恢复。</p>
    </div>
    <div v-else class="history-layout">
      <aside class="history-list" aria-label="创作历史列表">
        <div
          v-for="entry in historyEntries"
          :key="entry.id"
          class="history-item"
          :class="{ 'is-active': selectedHistoryId === entry.id }"
          role="button"
          tabindex="0"
          @click="selectedHistoryId = entry.id"
          @keydown.enter.prevent="selectedHistoryId = entry.id"
          @keydown.space.prevent="selectedHistoryId = entry.id"
        >
          <div class="history-item__content">
            <strong>{{ entry.title }}</strong>
            <span>{{ tabLabel(entry.activeTab) }} · {{ formatHistoryTime(entry.createdAt) }}</span>
          </div>
          <el-button
            class="history-item__delete"
            circle
            type="danger"
            :loading="deletingHistoryId === entry.id"
            :disabled="busy || (!!deletingHistoryId && deletingHistoryId !== entry.id)"
            :aria-label="`删除创作历史：${entry.title}`"
            title="删除创作历史"
            @click.stop="emit('delete-history', entry.id)"
          >
            <el-icon v-if="deletingHistoryId !== entry.id"><DeleteIcon /></el-icon>
          </el-button>
        </div>
      </aside>
      <section class="history-preview">
        <MdPreview
          v-if="selectedHistoryPreview"
          id="screenwriting-history-preview"
          class="history-preview__markdown"
          :model-value="selectedHistoryPreview"
          theme="dark"
          preview-theme="github"
          code-theme="github"
        />
        <div v-else class="history-empty history-empty--compact">
          <strong>请选择一条历史记录</strong>
        </div>
      </section>
    </div>
    <template #footer>
      <el-button class="history-footer__close" @click="visibleModel = false">关闭</el-button>
      <el-button
        class="history-footer__restore"
        type="primary"
        :loading="restoring"
        :disabled="!selectedHistoryId || busy"
        @click="emitRestore"
      >
        恢复到当前会话
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Clock, Delete as DeleteIcon } from '@element-plus/icons-vue'
import { MdPreview } from 'md-editor-v3'
import type { ScreenwritingActiveTab, ScreenwritingHistoryEntry } from '@/api/screenwriting'

const props = defineProps<{
  modelValue: boolean
  historyEntries: ScreenwritingHistoryEntry[]
  tabLabel: (tab: ScreenwritingActiveTab) => string
  restoring?: boolean
  deletingHistoryId?: string
  busy?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  restore: [historyId: string]
  'delete-history': [historyId: string]
}>()

const selectedHistoryId = ref('')

const visibleModel = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

// 历史列表变化（删除/刷新）时保持选中项有效，默认选中第一条。
watch(
  () => props.historyEntries,
  (entries) => {
    if (!entries.some((entry) => entry.id === selectedHistoryId.value)) {
      selectedHistoryId.value = entries[0]?.id ?? ''
    }
  },
  { immediate: true, deep: true },
)

watch(visibleModel, (visible) => {
  if (visible && !selectedHistoryId.value) {
    selectedHistoryId.value = props.historyEntries[0]?.id ?? ''
  }
})

const selectedEntry = computed(() =>
  props.historyEntries.find((entry) => entry.id === selectedHistoryId.value) ?? null,
)

const selectedHistoryPreview = computed(() => {
  const entry = selectedEntry.value
  if (!entry) return ''
  const sections: string[] = []
  const ordered: ScreenwritingActiveTab[] = [entry.activeTab, 'skeleton', 'strategy', 'script']
  const seen = new Set<string>()
  for (const tab of ordered) {
    if (seen.has(tab)) continue
    seen.add(tab)
    const content = (entry.workspace[tab] ?? '').trim()
    if (content) {
      sections.push(`## ${tabLabelText(tab)}\n\n${content}`)
    }
  }
  if (!sections.length && entry.messages.length) {
    const recent = entry.messages.slice(-6)
    sections.push(
      `## 对话片段\n\n${recent
        .map((turn) => `- **${turn.role === 'user' ? '我' : '助理'}**：${turn.content}`)
        .join('\n')}`,
    )
  }
  return sections.join('\n\n---\n\n')
})

const tabLabelText = (tab: ScreenwritingActiveTab) => props.tabLabel(tab)

const formatHistoryTime = (value: string) => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

const emitRestore = () => {
  if (selectedHistoryId.value) {
    emit('restore', selectedHistoryId.value)
  }
}
</script>

<style scoped>
.history-layout {
  height: min(62vh, 620px);
  min-height: 360px;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 14px;
}

.history-list,
.history-preview {
  min-height: 0;
  overflow: auto;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(8, 12, 18, 0.58);
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.32) transparent;
}

.history-list::-webkit-scrollbar,
.history-preview::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.history-list::-webkit-scrollbar-thumb,
.history-preview::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background-color: rgba(148, 163, 184, 0.3);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 10px;
}

.history-item {
  box-sizing: border-box;
  width: 100%;
  min-height: 64px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 10px;
  color: #cbd5e1;
  background: rgba(15, 23, 42, 0.48);
  text-align: left;
  cursor: pointer;
}

.history-item__content {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.history-item__content strong,
.history-item__content span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-item__content strong {
  color: #e6edf3;
  font-size: 13px;
}

.history-item__content span {
  color: #8b949e;
  font-size: 12px;
}

.history-item:hover,
.history-item:focus,
.history-item.is-active {
  color: #ffffff;
  border-color: rgba(96, 165, 250, 0.38);
  background: rgba(37, 99, 235, 0.16);
}

.history-item :deep(.history-item__delete.el-button) {
  width: 32px;
  min-width: 32px;
  height: 32px;
  min-height: 32px;
  padding: 0;
  justify-self: end;
  color: #fca5a5;
  border-color: rgba(248, 113, 113, 0.2);
  background-color: rgba(127, 29, 29, 0.14);
  box-shadow: none;
}

.history-item :deep(.history-item__delete.el-button:hover),
.history-item :deep(.history-item__delete.el-button:focus) {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.38);
  background-color: rgba(153, 27, 27, 0.28);
}

.history-preview {
  padding: 18px;
}

.history-preview__markdown {
  color: #cbd5e1;
  background: transparent;
}

.history-preview__markdown :deep(.md-editor-preview-wrapper),
.history-preview__markdown :deep(.md-editor-preview) {
  padding: 0;
  color: #cbd5e1;
  background: transparent;
  font-size: 13px;
  line-height: 1.72;
}

.history-empty {
  min-height: 300px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 10px;
  color: #8b949e;
  text-align: center;
}

.history-empty--compact {
  min-height: 160px;
}

.history-empty :deep(.el-icon) {
  color: #93c5fd;
  font-size: 32px;
}

.history-empty strong {
  color: #e6edf3;
  font-size: 15px;
}

.history-empty p {
  margin: 0;
  max-width: 420px;
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 920px) {
  .history-layout {
    grid-template-columns: 1fr;
  }
}

.history-footer__close.el-button {
  height: 36px;
  padding: 0 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #c9d1d9;
  background: rgba(255, 255, 255, 0.04);
  box-shadow: none;
}

.history-footer__close.el-button:hover,
.history-footer__close.el-button:focus {
  color: #f2f4f8;
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.1);
}

.history-footer__restore.el-button {
  height: 36px;
  padding: 0 18px;
  border: none;
  border-radius: 10px;
  font-weight: 700;
  background: #2563eb;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
}

.history-footer__restore.el-button:hover,
.history-footer__restore.el-button:focus {
  background: #1d4ed8;
}

.history-footer__restore.el-button.is-disabled,
.history-footer__restore.el-button.is-disabled:hover {
  color: #4d5560;
  background: rgba(255, 255, 255, 0.05);
  box-shadow: none;
}
</style>
