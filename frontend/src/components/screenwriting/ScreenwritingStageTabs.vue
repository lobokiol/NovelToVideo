<template>
  <section class="workspace-main">
    <el-tabs v-model="tabValue" class="screenwriting-tabs">
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.name"
        :name="tab.name"
        :label="tab.label"
      >
        <div class="tab-panel">
          <div class="tab-panel__toolbar">
            <div class="tab-panel__heading">
              <h3>{{ tab.label }}</h3>
              <p>{{ tab.desc }}</p>
            </div>
            <div class="tab-panel__actions">
              <template v-if="editingTab === tab.name">
                <el-button
                  class="tab-action tab-action--ghost"
                  :disabled="saving"
                  @click="cancelEdit"
                >
                  取消
                </el-button>
                <el-button
                  class="tab-action"
                  type="primary"
                  :loading="saving"
                  @click="saveEdit(tab.name)"
                >
                  保存
                </el-button>
              </template>
              <template v-else>
                <el-button
                  class="tab-action tab-action--ghost"
                  @click="startEdit(tab.name)"
                >
                  <el-icon><EditPen /></el-icon>
                  &nbsp;{{ workspaceContent(tab.name) ? '编辑' : '手动撰写' }}
                </el-button>
                <el-button
                  class="tab-action tab-action--ghost"
                  :loading="assessingTab === tab.name"
                  :disabled="!workspaceContent(tab.name) || (!!assessingTab && assessingTab !== tab.name)"
                  @click="emit('assess', tab.name)"
                >
                  <el-icon v-if="assessingTab !== tab.name"><DataAnalysis /></el-icon>
                  &nbsp;{{ assessmentReadyTab === tab.name ? '查看评估' : '评估' }}
                </el-button>
                <el-button
                  v-if="tab.name === 'script' && scriptEpisodeCards.length"
                  class="tab-action tab-action--ghost"
                  :loading="syncing"
                  @click="emit('sync-script')"
                >
                  <el-icon v-if="!syncing"><FolderChecked /></el-icon>
                  &nbsp;同步到剧本管理
                </el-button>
                <el-button class="tab-action" type="primary" @click="emit('start', tab)">
                  <el-icon><MagicStick /></el-icon>
                  &nbsp;{{ tab.action }}
                </el-button>
              </template>
            </div>
          </div>

          <div
            :ref="(el) => setBodyRef(tab.name, el)"
            class="tab-panel__body"
            :class="{ 'tab-panel__body--filled': editingTab === tab.name || workspaceContent(tab.name) }"
          >
            <el-input
              v-if="editingTab === tab.name"
              v-model="draftContent"
              class="tab-editor"
              type="textarea"
              :autosize="false"
              resize="none"
              :placeholder="editingEpisode ? `编辑 EP${formatEpisodeNo(editingEpisode.episodeNo)} 剧本正文，支持 Markdown 格式` : `在此撰写${tab.label}内容，支持 Markdown 格式`"
            />
            <div
              v-else-if="tab.name === 'script' && scriptEpisodeCards.length"
              class="script-episode-board"
            >
              <article
                v-for="episode in scriptEpisodeCards"
                :key="episode.key"
                class="script-episode-card"
                :class="{ 'is-expanded': expandedEpisodeKey === episode.key }"
              >
                <header class="script-episode-card__header">
                  <button
                    type="button"
                    class="script-episode-card__summary"
                    @click="toggleEpisode(episode.key)"
                  >
                    <span class="script-episode-badge">EP{{ formatEpisodeNo(episode.episodeNo) }}</span>
                    <strong class="script-episode-card__title">{{ episode.title }}</strong>
                  </button>
                  <div class="script-episode-card__actions">
                    <button
                      type="button"
                      class="script-episode-icon-btn"
                      :title="`编辑 EP${formatEpisodeNo(episode.episodeNo)}`"
                      :disabled="saving"
                      @click.stop="startEditEpisode(episode)"
                    >
                      <el-icon><EditPen /></el-icon>
                    </button>
                    <button
                      type="button"
                      class="script-episode-icon-btn is-danger"
                      :title="`删除 EP${formatEpisodeNo(episode.episodeNo)}`"
                      :disabled="saving"
                      @click.stop="deleteEpisode(episode)"
                    >
                      <el-icon><Delete /></el-icon>
                    </button>
                    <button
                      type="button"
                      class="script-episode-expand"
                      :aria-expanded="expandedEpisodeKey === episode.key"
                      @click.stop="toggleEpisode(episode.key)"
                    >
                      <span>{{ expandedEpisodeKey === episode.key ? '收起' : '展开' }}</span>
                      <el-icon><CaretBottom /></el-icon>
                    </button>
                  </div>
                </header>

                <p
                  v-if="expandedEpisodeKey !== episode.key && episode.summary"
                  class="script-episode-card__summary-copy"
                  @click="toggleEpisode(episode.key)"
                >
                  {{ episode.summary }}
                </p>

                <div v-if="episode.meta.length" class="script-episode-card__meta">
                  <span v-for="item in episode.meta" :key="item">{{ item }}</span>
                </div>

                <div v-if="expandedEpisodeKey === episode.key" class="script-episode-card__body">
                  <p v-if="episode.synopsis" class="script-episode-synopsis">{{ episode.synopsis }}</p>
                  <div class="script-scene-list">
                    <section
                      v-for="scene in episode.scenes"
                      :key="scene.key"
                      class="script-scene"
                    >
                      <div class="script-scene__head">
                        <span>{{ scene.number }}</span>
                        <strong>{{ scene.title }}</strong>
                        <em v-if="scene.duration" class="script-scene__duration">{{ scene.duration }}</em>
                      </div>
                      <p v-if="scene.people" class="script-scene__people">人物：{{ scene.people }}</p>
                      <template v-for="(line, lineIndex) in scene.lines">
                        <p v-if="line.type === 'action'" :key="`action-${lineIndex}`" class="script-scene__action">{{ line.text }}</p>
                        <p v-else-if="line.type === 'dialogue'" :key="`dialogue-${lineIndex}`" class="script-scene__dialogue">{{ line.text }}</p>
                        <span v-else-if="line.type === 'transition'" :key="`transition-${lineIndex}`" class="script-scene__transition">{{ line.text }}</span>
                        <p v-else :key="`text-${lineIndex}`" class="script-scene__text">{{ line.text }}</p>
                      </template>
                    </section>
                  </div>
                </div>
              </article>
            </div>
            <MdPreview
              v-else-if="workspaceContent(tab.name)"
              :id="`screenwriting-workspace-${tab.name}`"
              class="workspace-markdown-preview"
              :model-value="workspaceContent(tab.name)"
              theme="dark"
              preview-theme="github"
              code-theme="github"
            />
            <div v-else class="tab-empty">
              <el-icon class="tab-empty__icon"><component :is="tab.icon" /></el-icon>
              <strong>{{ tab.title }}</strong>
              <p>{{ tab.hint }}</p>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { ElMessageBox } from 'element-plus'
import { CaretBottom, DataAnalysis, Delete, EditPen, FolderChecked, MagicStick } from '@element-plus/icons-vue'
import { MdPreview } from 'md-editor-v3'
import type { ScreenwritingActiveTab, ScreenwritingWorkspace } from '@/api/screenwriting'
import type { ScreenwritingTab, ScriptEpisodeCard } from './types'
import {
  parseScriptEpisodes,
  removeScriptEpisode,
  replaceScriptEpisode,
} from '@/utils/screenwritingScript'

const props = defineProps<{
  activeTab: ScreenwritingActiveTab
  tabs: ScreenwritingTab[]
  workspace: ScreenwritingWorkspace
  saving?: boolean
  assessingTab?: ScreenwritingActiveTab | ''
  assessmentReadyTab?: ScreenwritingActiveTab | ''
  syncing?: boolean
}>()

const emit = defineEmits<{
  'update:activeTab': [value: ScreenwritingActiveTab]
  start: [tab: ScreenwritingTab]
  save: [tab: ScreenwritingActiveTab, content: string]
  assess: [tab: ScreenwritingActiveTab]
  'sync-script': []
}>()

const editingTab = ref<ScreenwritingActiveTab | null>(null)
const draftContent = ref('')
const editingEpisode = ref<ScriptEpisodeCard | null>(null)
const expandedEpisodeKey = ref('')

const tabValue = computed({
  get: () => props.activeTab,
  set: (value) => emit('update:activeTab', value as ScreenwritingActiveTab),
})

const workspaceContent = (tab: ScreenwritingActiveTab) => props.workspace[tab] ?? ''

const scriptEpisodeCards = computed<ScriptEpisodeCard[]>(() => parseScriptEpisodes(props.workspace.script))

// 全文变化（含流式追加）后清理失效的展开 key（key 含字符偏移）。
watch(scriptEpisodeCards, (episodes) => {
  if (expandedEpisodeKey.value && !episodes.some((episode) => episode.key === expandedEpisodeKey.value)) {
    expandedEpisodeKey.value = ''
  }
})

const formatEpisodeNo = (episodeNo: number) => String(episodeNo).padStart(2, '0')

const toggleEpisode = (episodeKey: string) => {
  expandedEpisodeKey.value = expandedEpisodeKey.value === episodeKey ? '' : episodeKey
}

const startEdit = (tab: ScreenwritingActiveTab) => {
  editingTab.value = tab
  editingEpisode.value = null
  draftContent.value = workspaceContent(tab)
}

const startEditEpisode = (episode: ScriptEpisodeCard) => {
  editingTab.value = 'script'
  editingEpisode.value = episode
  expandedEpisodeKey.value = episode.key
  draftContent.value = props.workspace.script.replace(/\r\n/g, '\n').trim().slice(episode.start, episode.end).trim()
}

const cancelEdit = () => {
  editingTab.value = null
  editingEpisode.value = null
  draftContent.value = ''
}

const saveEdit = (tab: ScreenwritingActiveTab) => {
  if (tab === 'script' && editingEpisode.value) {
    emit('save', 'script', replaceScriptEpisode(props.workspace.script, editingEpisode.value, draftContent.value))
    return
  }
  emit('save', tab, draftContent.value)
}

const deleteEpisode = async (episode: ScriptEpisodeCard) => {
  try {
    await ElMessageBox.confirm(
      `确定删除 EP${formatEpisodeNo(episode.episodeNo)}「${episode.title}」吗？删除后会同步保存到剧本工作区。`,
      '删除分集剧本',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'settings-dark-messagebox',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  emit('save', 'script', removeScriptEpisode(props.workspace.script, episode))
}

const bodyRefs = new Map<string, HTMLElement>()

const setBodyRef = (tab: ScreenwritingActiveTab, el: Element | ComponentPublicInstance | null) => {
  if (el instanceof HTMLElement) {
    bodyRefs.set(tab, el)
  } else {
    bodyRefs.delete(tab)
  }
}

const scrollTabToBottom = (tab: ScreenwritingActiveTab) => {
  nextTick(() => {
    const el = bodyRefs.get(tab)
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  })
}

defineExpose({
  /** 保存成功后由父组件调用以退出编辑态。 */
  finishEdit: cancelEdit,
  /** 流式写入工作区时由父组件调用以跟随滚动。 */
  scrollTabToBottom,
})
</script>

<style scoped>
.workspace-main {
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(8, 12, 18, 0.62);
  padding: 14px 16px 16px;
}

.screenwriting-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.screenwriting-tabs :deep(.el-tabs__header) {
  margin: 0 0 14px;
}

.screenwriting-tabs :deep(.el-tabs__nav-wrap)::after {
  height: 1px;
  background-color: rgba(255, 255, 255, 0.06);
}

.screenwriting-tabs :deep(.el-tabs__item) {
  height: 42px;
  padding: 0 18px;
  color: #8b949e;
  font-size: 14px;
  font-weight: 600;
}

.screenwriting-tabs :deep(.el-tabs__item:hover) {
  color: #e6edf3;
}

.screenwriting-tabs :deep(.el-tabs__item.is-active) {
  color: #dbeafe;
}

.screenwriting-tabs :deep(.el-tabs__active-bar) {
  height: 3px;
  border-radius: 3px;
  background: linear-gradient(90deg, #2563eb 0%, #60a5fa 100%);
}

.screenwriting-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
}

.screenwriting-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.tab-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.tab-panel__toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.tab-panel__heading h3 {
  margin: 0;
  color: #f2f4f8;
  font-size: 17px;
  font-weight: 750;
}

.tab-panel__heading p {
  margin: 5px 0 0;
  max-width: 540px;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.6;
}

.tab-panel__actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0;
}

.tab-action {
  flex-shrink: 0;
  height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  background: #2563eb;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
}

.tab-action :deep(.el-icon) {
  margin-right: 0;
  font-size: 15px;
}

.tab-action:hover,
.tab-action:focus {
  background: #1d4ed8;
  transform: translateY(-1px);
}

.tab-action--ghost {
  color: #c9d1d9;
  background: rgba(255, 255, 255, 0.06);
  box-shadow: none;
}

.tab-action--ghost:hover,
.tab-action--ghost:focus {
  color: #f2f4f8;
  background: rgba(255, 255, 255, 0.12);
}

.tab-panel__body {
  flex: 1;
  min-height: 0;
  display: flex;
  border: 1px dashed rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  background: rgba(4, 8, 14, 0.36);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.tab-panel__body--filled {
  border-style: solid;
  border-color: rgba(255, 255, 255, 0.08);
}

.tab-panel__body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.tab-panel__body::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.tab-editor {
  flex: 1;
  display: flex;
}

.tab-editor :deep(.el-textarea__inner) {
  height: 100%;
  min-height: 100%;
  padding: 16px 18px;
  color: #e6edf3;
  font-size: 13.5px;
  line-height: 1.8;
  font-family: "JetBrains Mono", Consolas, "PingFang SC", monospace;
  background: transparent;
  border: none;
  box-shadow: none;
}

.workspace-markdown-preview {
  flex: 1;
  min-width: 0;
  background: transparent;
}

.workspace-markdown-preview :deep(.md-editor-preview-wrapper),
.workspace-markdown-preview :deep(.md-editor-preview) {
  padding: 16px 18px;
  background: transparent;
  color: #dbe4ec;
}

.workspace-markdown-preview :deep(.md-editor-preview) {
  font-size: 13.5px;
  line-height: 1.85;
  word-break: break-word;
}

.tab-empty {
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 32px 24px;
  text-align: center;
}

.tab-empty__icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.12);
  font-size: 28px;
}

.tab-empty strong {
  color: #e6edf3;
  font-size: 15px;
  font-weight: 700;
}

.tab-empty p {
  max-width: 420px;
  margin: 0;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.7;
}

@media (max-width: 920px) {
  .workspace-main {
    overflow: visible;
    min-height: 520px;
  }
}
</style>

<style scoped>
/* 剧本分集折叠列表：单列堆叠，每集一个折叠框，与前两阶段的整页 Markdown 预览区分。 */
.script-episode-board {
  display: grid;
  grid-template-columns: 1fr;
  align-items: start;
  align-content: start;
  gap: 12px;
  padding: 2px;
}

.script-episode-card {
  min-width: 0;
  align-self: start;
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(8, 12, 18, 0.46);
}

.script-episode-card.is-expanded {
  border-color: rgba(96, 165, 250, 0.26);
  background: rgba(12, 18, 28, 0.72);
}

.script-episode-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.script-episode-card__summary {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.script-episode-badge {
  flex: 0 0 auto;
  min-width: 54px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #dbeafe;
  background: rgba(37, 99, 235, 0.16);
  font-weight: 800;
  font-size: 12px;
  font-family: "JetBrains Mono", Consolas, monospace;
}

.script-episode-card__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #e6edf3;
  font-size: 13px;
}

.script-episode-card__actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 6px;
}

.script-episode-icon-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #9fb3c8;
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
}

.script-episode-icon-btn:hover:not(:disabled) {
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.38);
  background: rgba(37, 99, 235, 0.14);
}

.script-episode-icon-btn:disabled {
  color: #4d5560;
  cursor: not-allowed;
}

.script-episode-icon-btn.is-danger {
  color: #fca5a5;
  border-color: rgba(248, 113, 113, 0.2);
  background: rgba(127, 29, 29, 0.12);
}

.script-episode-icon-btn.is-danger:hover:not(:disabled) {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.38);
  background: rgba(153, 27, 27, 0.28);
}

.script-episode-expand {
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  color: #9fb3c8;
  background: transparent;
  font-size: 12px;
  cursor: pointer;
}

.script-episode-expand:hover {
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.38);
}

.script-episode-card.is-expanded .script-episode-expand .el-icon {
  transform: rotate(180deg);
}

.script-episode-card__summary-copy {
  margin: 0;
  color: #8b949e;
  font-size: 12px;
  line-height: 1.65;
  cursor: pointer;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.script-episode-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.script-episode-card__meta span {
  padding: 2px 10px;
  border-radius: 999px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.12);
  font-size: 11px;
  font-weight: 700;
}

.script-episode-card__body {
  display: grid;
  gap: 10px;
}

.script-episode-synopsis {
  margin: 0;
  color: #dbeafe;
  font-size: 12px;
  line-height: 1.7;
}

.script-scene-list {
  display: grid;
  gap: 8px;
}

.script-scene {
  display: grid;
  gap: 6px;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.script-scene__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.script-scene__head span {
  flex: 0 0 auto;
  color: #60a5fa;
  font-family: "JetBrains Mono", Consolas, monospace;
  font-size: 12px;
  font-weight: 800;
}

.script-scene__head strong {
  min-width: 0;
  color: #e6edf3;
  font-size: 12px;
}

.script-scene__people {
  margin: 0;
  color: #8b949e;
  font-size: 11px;
}

.script-scene__action {
  margin: 0;
  color: #cbd5e1;
  font-size: 12px;
  line-height: 1.6;
}

.script-scene__dialogue {
  margin: 0;
  color: #e5e7eb;
  font-size: 12px;
  line-height: 1.6;
}

.script-scene__text {
  margin: 0;
  color: #9fb3c8;
  font-size: 12px;
  line-height: 1.6;
}

.script-scene__duration {
  flex: 0 0 auto;
  margin-left: auto;
  color: #93c5fd;
  font-style: normal;
  font-family: "JetBrains Mono", Consolas, monospace;
  font-size: 11px;
  font-weight: 700;
}

.script-scene__transition {
  justify-self: start;
  color: #fbbf24;
  font-family: "JetBrains Mono", Consolas, monospace;
  font-size: 11px;
  font-weight: 800;
}
</style>
