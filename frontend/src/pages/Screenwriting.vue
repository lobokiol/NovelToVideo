<template>
  <main class="screenwriting-page">
    <div class="app-shell">
      <ScreenwritingSidebar
        @project="goProject"
        @novel="goNovel"
        @tasks="goTasks"
        @documents="showComingSoon"
        @settings="settingsVisible = true"
        @repository="showComingSoon"
        @production="goProduction"
      />

      <section class="main-panel">
        <ScreenwritingPageHeader
          @back-novel="goNovel"
          @script-manage="goScriptManage"
        />

        <section class="workspace">
          <ScreenwritingAssistantPanel
            ref="assistantPanelRef"
            v-model="chatInput"
            :messages="chatMessages"
            :connected-model-id="connectedModelId"
            :is-sending="isSendingChat"
            :streaming-message-id="streamingAssistantMessageId"
            :rag-warmup="ragWarmup"
            @send="sendChatMessage"
            @new-conversation="startNewConversation"
            @open-history="historyDialogVisible = true"
            @insert-stage-prompt="insertStagePrompt"
            @quote-events="showComingSoon"
            :config-drawer-visible="configDrawerVisible"
            :config-initial="configInitial"
            :config-submitting="isSubmittingConfig"
            @open-config="configDrawerVisible = true"
            @submit-config="submitConfigDraft"
            @update:config-drawer-visible="configDrawerVisible = $event"
            @clear-composer="clearComposer"
          />

          <ScreenwritingStageTabs
            ref="stageTabsRef"
            v-model:active-tab="activeTab"
            :tabs="screenwritingTabs"
            :workspace="workspace"
            :saving="isSavingWorkspace"
            :assessing-tab="assessingTab"
            :assessment-ready-tab="assessmentReadyTab"
            :syncing="isSyncingScript"
            @start="startWithPrompt"
            @save="saveWorkspace"
            @assess="assessStage"
            @sync-script="syncToScriptManage"
          />
        </section>
      </section>
    </div>

    <ScreenwritingHistoryDialog
      v-model="historyDialogVisible"
      :history-entries="historyEntries"
      :tab-label="screenwritingTabLabel"
      :restoring="isRestoringHistory"
      :deleting-history-id="deletingHistoryId"
      :busy="isSendingChat || isResettingConversation"
      @restore="restoreHistory"
      @delete-history="deleteHistory"
    />

    <ScreenwritingAssessmentDialog
      v-model="assessmentDialogVisible"
      :stage-label="screenwritingTabLabel(assessmentStage)"
      :report="assessmentReport"
      :scores="assessmentScores"
      :improvement-prompt="assessmentImprovementPrompt"
      :streaming="!!assessingTab"
      :error="assessmentError"
      :regenerating="isSendingChat"
      @confirm-improve="confirmAssessmentImprove"
    />

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { AxiosError } from 'axios'
import {
  Document,
  MagicStick,
  Tickets,
} from '@element-plus/icons-vue'
import {
  assessScreenwritingStreamUrl,
  chatScreenwritingStreamUrl,
  deleteScreenwritingHistoryApi,
  getScreenwritingStateApi,
  resetScreenwritingStateApi,
  restoreScreenwritingHistoryApi,
  setScreenwritingConfigDraftApi,
  updateScreenwritingWorkspaceApi,
  warmupScreenwritingRagIndexApi,
  type ScreenwritingActiveTab,
  type ScreenwritingAssessmentScores,
  type ScreenwritingConfigDraft,
  type ScreenwritingHistoryEntry,
  type ScreenwritingState,
  type ScreenwritingStreamEvent,
  type ScreenwritingWorkspace,
} from '@/api/screenwriting'
import { syncScriptPlanApi } from '@/api/script'
import { fetchWithAuthRetry } from '@/request'
import { readNdjsonStream } from '@/utils/ndjsonStream'
import ScreenwritingAssessmentDialog from '@/components/screenwriting/ScreenwritingAssessmentDialog.vue'
import ScreenwritingAssistantPanel from '@/components/screenwriting/ScreenwritingAssistantPanel.vue'
import ScreenwritingHistoryDialog from '@/components/screenwriting/ScreenwritingHistoryDialog.vue'
import ScreenwritingPageHeader from '@/components/screenwriting/ScreenwritingPageHeader.vue'
import ScreenwritingSidebar from '@/components/screenwriting/ScreenwritingSidebar.vue'
import ScreenwritingStageTabs from '@/components/screenwriting/ScreenwritingStageTabs.vue'
import type { AgentActionEntry, ChatMessage, ScreenwritingRagWarmupViewState, ScreenwritingTab } from '@/components/screenwriting/types'
import Settings from '../components/Settings.vue'

interface AssistantPanelExpose {
  focusComposer: () => void
  followOutput: () => Promise<void>
  resetAutoScroll: () => void
  scrollToBottom: (behavior?: ScrollBehavior) => void
}

interface StageTabsExpose {
  finishEdit: () => void
  scrollTabToBottom: (tab: ScreenwritingActiveTab) => void
}

const router = useRouter()
const route = useRoute()

const projectPublicId = ref('')
const settingsVisible = ref(false)
const activeTab = ref<ScreenwritingActiveTab>('skeleton')

const chatInput = ref('')
const assistantPanelRef = ref<AssistantPanelExpose | null>(null)
const stageTabsRef = ref<StageTabsExpose | null>(null)
const isSendingChat = ref(false)
const isSavingWorkspace = ref(false)
const isResettingConversation = ref(false)
const conversationId = ref('')
const connectedModelId = ref('')
const streamingAssistantMessageId = ref<number | null>(null)
const ragWarmup = ref<ScreenwritingRagWarmupViewState>({ status: 'idle', label: '' })
const workspace = ref<ScreenwritingWorkspace>({ skeleton: '', strategy: '', script: '' })
const workflow = ref<Record<string, unknown>>({})
const configDrawerVisible = ref(false)
const isSubmittingConfig = ref(false)
const historyEntries = ref<ScreenwritingHistoryEntry[]>([])
const historyDialogVisible = ref(false)
const isRestoringHistory = ref(false)
const deletingHistoryId = ref('')
let chatSeq = 2
let chatStreamController: AbortController | null = null
let ragWarmupPollTimer: number | null = null

const ASSISTANT_REVEAL_CHUNK_SIZE = 1
const ASSISTANT_REVEAL_INTERVAL_MS = 18
const RAG_WARMUP_POLL_INTERVAL_MS = 1400

const screenwritingTabs: ScreenwritingTab[] = [
  {
    name: 'skeleton',
    label: '故事骨架',
    icon: Tickets,
    desc: '基于已清洗的小说事件，梳理主线脉络、关键人物与核心冲突结构。',
    action: '生成故事骨架',
    title: '故事骨架尚未生成',
    hint: '在左侧与 AI Agent 对话，从已提取的小说事件中提炼主线、人物关系与章节脉络。',
    starter: '请基于本项目已提取的小说事件，梳理主线故事骨架，包含关键人物、核心冲突与章节脉络。',
  },
  {
    name: 'strategy',
    label: '改编策略',
    icon: MagicStick,
    desc: '明确改编基调、节奏取舍与表现重点，为剧本创作建立统一依据。',
    action: '制定改编策略',
    title: '改编策略待制定',
    hint: '结合故事骨架，确定整体基调、节奏安排与取舍重点，作为后续剧本创作的依据。',
    starter: '请结合故事骨架，提出本项目的改编策略，包括整体基调、节奏安排与情节取舍重点。',
  },
  {
    name: 'script',
    label: '剧本',
    icon: Document,
    desc: '在故事骨架与改编策略确认后，于此逐场景生成并打磨剧本内容。',
    action: '开始创作剧本',
    title: '剧本尚未开始',
    hint: '确认故事骨架与改编策略后，在左侧 Agent 协助下逐场景生成并编辑剧本初稿。',
    starter: '请根据故事骨架与改编策略，开始逐场景创作剧本初稿。',
  },
]

const ASSISTANT_GREETING =
  '你好，我是剧本创作助理。我会基于本项目已提取的小说事件，协助你完成故事骨架、改编策略与剧本。可以从右侧选择一个阶段，或直接告诉我你的创作目标。'

const chatMessages = ref<ChatMessage[]>([
  {
    id: 1,
    role: 'assistant',
    content: ASSISTANT_GREETING,
    time: '09:30',
  },
])

const resolveProjectPublicId = () => {
  const id = route.query.id
  if (Array.isArray(id)) return id[0] || ''
  return typeof id === 'string' ? id : ''
}

const formatChatTime = (date = new Date()) =>
  date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

const startWithPrompt = (tab: ScreenwritingTab) => {
  chatInput.value = tab.starter
  nextTick(() => assistantPanelRef.value?.focusComposer())
}

const insertStagePrompt = () => {
  const tab = screenwritingTabs.find((item) => item.name === activeTab.value) ?? screenwritingTabs[0]
  startWithPrompt(tab)
}

const clearComposer = () => {
  chatInput.value = ''
  nextTick(() => assistantPanelRef.value?.focusComposer())
}

const applyServerState = (state: ScreenwritingState) => {
  conversationId.value = state.conversationId
  if (state.modelId) {
    connectedModelId.value = state.modelId
  }
  activeTab.value = state.activeTab
  workspace.value = { ...state.workspace }
  workflow.value = (state.workflow ?? {}) as Record<string, unknown>
  historyEntries.value = [...state.history]
  const messages = state.messages.filter((turn) => turn.content.trim())
  chatSeq = 1
  chatMessages.value = messages.length
    ? messages.map((turn) => ({
        id: chatSeq++,
        role: turn.role,
        content: turn.content,
        time: turn.time,
      }))
    : [
        {
          id: chatSeq++,
          role: 'assistant',
          content: ASSISTANT_GREETING,
          time: formatChatTime(),
        },
      ]
}

const KNOWN_CONFIG_PLACEHOLDER = ['可指定', '故事骨架']

// 从已存配置（草案或已锁定）解析出抽屉初值；草案占位文案不回填，避免误导。
const parseConfigInitial = (): ScreenwritingConfigDraft => {
  const config = (workflow.value?.projectConfig ?? {}) as Record<string, string>
  const matchNumber = (text: string | undefined, pattern: RegExp): number | null => {
    const matched = (text ?? '').match(pattern)
    return matched ? Number(matched[1]) : null
  }
  const rangeMatch = (config.sourceRange ?? '').match(/第?\s*(\d+)\s*[-—到至]\s*(\d+)\s*章/)
  const platform = config.platformSpec ?? ''
  const resolvePlatform = (): string | null => {
    if (platform.includes('可改')) return null
    if (platform.includes('9:16') || platform.includes('竖屏')) return '9:16竖屏短剧优先'
    if (platform.includes('16:9') || platform.includes('横屏')) return '16:9横屏'
    return null
  }
  // 从项目当前配置提取风格；草案占位文案不回填，让用户自定义。
  const styleText = config.style ?? ''
  const style = KNOWN_CONFIG_PLACEHOLDER.some((token) => styleText.includes(token))
    ? null
    : (styleText || null)
  const paywall = config.paywall ?? ''
  return {
    totalEpisodes: matchNumber(config.totalEpisodes, /(\d+)\s*集/),
    episodeDuration: matchNumber(config.episodeDuration, /(\d+)\s*分钟/),
    sourceStart: rangeMatch ? Number(rangeMatch[1]) : null,
    sourceEnd: rangeMatch ? Number(rangeMatch[2]) : null,
    platformSpec: resolvePlatform(),
    style,
    paywall: paywall && !paywall.includes('可按') ? paywall : null,
  }
}

const configInitial = computed<ScreenwritingConfigDraft>(() => parseConfigInitial())

// 仅在新建对话且配置尚未锁定时自动上拉一次，引导用户结构化设置。
const maybeAutoOpenConfigDrawer = () => {
  if (workflow.value?.basicInfoConfirmed === true) return
  nextTick(() => {
    configDrawerVisible.value = true
  })
}

const submitConfigDraft = async (draft: ScreenwritingConfigDraft) => {
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  if (isSubmittingConfig.value) return
  isSubmittingConfig.value = true
  try {
    const { data: state } = await setScreenwritingConfigDraftApi(projectPublicId.value, draft)
    applyServerState(state)
    configDrawerVisible.value = false
    ElMessage.success('创作配置已保存并锁定，AI 将严格遵循该配置')
  } catch (error) {
    ElMessage.error(`保存创作配置失败：${getErrorMessage(error)}`)
  } finally {
    isSubmittingConfig.value = false
  }
}

const loadScreenwritingState = async () => {
  if (!projectPublicId.value) return
  try {
    const { data: state } = await getScreenwritingStateApi(projectPublicId.value)
    applyServerState(state)
    nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
  } catch (error) {
    ElMessage.error(`加载创作会话失败：${getErrorMessage(error)}`)
  }
}

const startNewConversation = async () => {
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  if (isResettingConversation.value) return
  stopChatStream()
  isResettingConversation.value = true
  try {
    const { data: state } = await resetScreenwritingStateApi(projectPublicId.value)
    assistantPanelRef.value?.resetAutoScroll()
    applyServerState(state)
    chatInput.value = ''
    maybeAutoOpenConfigDrawer()
    nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
    ElMessage.success('已开始新的对话')
  } catch (error) {
    ElMessage.error(`开始新对话失败：${getErrorMessage(error)}`)
  } finally {
    isResettingConversation.value = false
  }
}

const screenwritingTabLabel = (tab: ScreenwritingActiveTab) =>
  screenwritingTabs.find((item) => item.name === tab)?.label ?? '故事骨架'

const restoreHistory = async (historyId: string) => {
  if (!projectPublicId.value || isRestoringHistory.value) return
  isRestoringHistory.value = true
  try {
    const { data: state } = await restoreScreenwritingHistoryApi(projectPublicId.value, historyId)
    assistantPanelRef.value?.resetAutoScroll()
    applyServerState(state)
    historyDialogVisible.value = false
    nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
    ElMessage.success('已恢复创作历史')
  } catch (error) {
    ElMessage.error(`恢复创作历史失败：${getErrorMessage(error)}`)
  } finally {
    isRestoringHistory.value = false
  }
}

const deleteHistory = async (historyId: string) => {
  if (!projectPublicId.value || deletingHistoryId.value) return
  deletingHistoryId.value = historyId
  try {
    const { data: state } = await deleteScreenwritingHistoryApi(projectPublicId.value, historyId)
    historyEntries.value = [...state.history]
    ElMessage.success('已删除创作历史')
  } catch (error) {
    ElMessage.error(`删除创作历史失败：${getErrorMessage(error)}`)
  } finally {
    deletingHistoryId.value = ''
  }
}

const assessingTab = ref<ScreenwritingActiveTab | ''>('')
const assessmentReadyTab = ref<ScreenwritingActiveTab | ''>('')
const assessmentDialogVisible = ref(false)
const assessmentStage = ref<ScreenwritingActiveTab>('skeleton')
const assessmentReport = ref('')
const assessmentScores = ref<ScreenwritingAssessmentScores>({})
const assessmentImprovementPrompt = ref('')
const assessmentError = ref('')
let assessmentController: AbortController | null = null

const isSyncingScript = ref(false)

const syncToScriptManage = async () => {
  if (isSyncingScript.value || !projectPublicId.value) return
  if (!workspace.value.script.trim()) {
    ElMessage.warning('当前还没有剧本草案可同步')
    return
  }
  isSyncingScript.value = true
  try {
    const { data } = await syncScriptPlanApi(projectPublicId.value)
    ElMessage.success(`已同步到剧本管理：${data.episodes.length} 集`)
    router.push({ path: '/script', query: { projectId: projectPublicId.value, planId: data.publicId } })
  } catch (error) {
    ElMessage.error(`同步到剧本管理失败：${getErrorMessage(error)}`)
  } finally {
    isSyncingScript.value = false
  }
}

const assessStage = async (tab: ScreenwritingActiveTab) => {
  if (!assessingTab.value && assessmentReadyTab.value === tab && (assessmentReport.value || assessmentError.value)) {
    assessmentDialogVisible.value = true
    return
  }
  if (assessingTab.value || !projectPublicId.value) return
  assessmentStage.value = tab
  assessmentReadyTab.value = ''
  assessmentReport.value = ''
  assessmentScores.value = {}
  assessmentImprovementPrompt.value = ''
  assessmentError.value = ''
  assessingTab.value = tab
  const controller = new AbortController()
  assessmentController = controller
  try {
    const response = await fetchWithAuthRetry(assessScreenwritingStreamUrl(projectPublicId.value), {
      method: 'POST',
      headers: {
        Accept: 'application/x-ndjson',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ activeTab: tab }),
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new Error(await readFetchError(response))
    }
    if (!response.body) {
      throw new Error('当前浏览器不支持读取评估流')
    }
    await readNdjsonStream<ScreenwritingStreamEvent>(response.body, async (event) => {
      if (event.type === 'error') {
        throw new Error(readStreamError(event))
      }
      if (event.type === 'message.delta' && event.content) {
        assessmentReport.value += event.content
      }
      if (event.type === 'done') {
        const report = event.data?.report
        if (typeof report === 'string' && report.trim()) {
          assessmentReport.value = report
        }
        assessmentScores.value = isRecord(event.data?.scores)
          ? (event.data?.scores as ScreenwritingAssessmentScores)
          : {}
        const improvementPrompt = event.data?.improvementPrompt
        assessmentImprovementPrompt.value = typeof improvementPrompt === 'string' ? improvementPrompt : ''
        assessmentReadyTab.value = tab
      }
    })
    if (assessmentReport.value) {
      ElMessage.success('评估完成，可点击「查看评估」查看报告')
    }
  } catch (error) {
    if (!isAbortError(error)) {
      assessmentError.value = getErrorMessage(error)
      assessmentReadyTab.value = tab
      ElMessage.error(`评估失败：${assessmentError.value}`)
    }
  } finally {
    if (assessmentController === controller) {
      assessmentController = null
    }
    assessingTab.value = ''
  }
}

// 关闭评估弹窗即中断评估流，避免后台继续消耗模型输出。
watch(assessmentDialogVisible, (visible) => {
  if (!visible) {
    assessmentController?.abort()
  }
})

const confirmAssessmentImprove = async (prompt: string) => {
  if (isSendingChat.value) {
    ElMessage.warning('当前正在生成中，请等待完成后再重新生成')
    return
  }
  assessmentDialogVisible.value = false
  chatInput.value = prompt
  await sendChatMessage()
}

const saveWorkspace = async (tab: ScreenwritingActiveTab, content: string) => {
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  if (isSavingWorkspace.value) return
  isSavingWorkspace.value = true
  try {
    const { data: state } = await updateScreenwritingWorkspaceApi(projectPublicId.value, {
      activeTab: tab,
      content,
    })
    workspace.value = { ...state.workspace }
    activeTab.value = state.activeTab
    stageTabsRef.value?.finishEdit()
    ElMessage.success('工作区内容已保存')
  } catch (error) {
    ElMessage.error(`保存工作区失败：${getErrorMessage(error)}`)
  } finally {
    isSavingWorkspace.value = false
  }
}

const waitForAssistantRevealFrame = () => (
  new Promise<void>((resolve) => {
    window.setTimeout(resolve, ASSISTANT_REVEAL_INTERVAL_MS)
  })
)

const getMissingAssistantContent = (currentContent: string, incomingContent: string) => {
  if (!incomingContent) return ''
  if (!currentContent) return incomingContent
  if (incomingContent.startsWith(currentContent)) {
    return incomingContent.slice(currentContent.length)
  }
  if (currentContent.includes(incomingContent)) {
    return ''
  }
  return incomingContent
}

const readAssistantFinalContent = (event: ScreenwritingStreamEvent) => {
  if (event.content?.trim()) return event.content
  const assistantMessage = event.data?.assistantMessage
  if (typeof assistantMessage === 'string' && assistantMessage.trim()) {
    return assistantMessage
  }
  const messages = event.data?.messages
  if (Array.isArray(messages)) {
    const finalAssistantMessage = [...messages]
      .reverse()
      .find((message) => message.role === 'assistant' && message.content.trim())
    return finalAssistantMessage?.content ?? ''
  }
  return ''
}

const normalizeWorkspaceTab = (value: unknown): ScreenwritingActiveTab | null => {
  const tab = String(value ?? '').trim()
  return tab === 'skeleton' || tab === 'strategy' || tab === 'script'
    ? (tab as ScreenwritingActiveTab)
    : null
}

const readWorkspacePayload = (value: unknown): ScreenwritingWorkspace | null => {
  if (!isRecord(value)) return null
  return {
    skeleton: String(value.skeleton ?? ''),
    strategy: String(value.strategy ?? ''),
    script: String(value.script ?? ''),
  }
}

const sendChatMessage = async () => {
  const content = chatInput.value.trim()
  if (!content) {
    ElMessage.warning('请输入对话内容')
    return
  }
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  if (isSendingChat.value) {
    ElMessage.warning('上一轮对话仍在生成中')
    return
  }

  const thinkingStartedAt = performance.now()
  const clientRequestStartedAtMs = Date.now()
  assistantPanelRef.value?.resetAutoScroll()
  chatMessages.value.push({
    id: chatSeq++,
    role: 'user',
    content,
    time: formatChatTime(),
  })
  chatInput.value = ''

  const assistantMessageId = chatSeq++
  chatMessages.value.push({
    id: assistantMessageId,
    role: 'assistant',
    content: '',
    time: formatChatTime(),
    thinkingElapsedMs: 0,
  })
  const getAssistantMessage = () => (
    chatMessages.value.find((message) => message.id === assistantMessageId)
  )
  const updateAssistantMessage = (updater: (message: ChatMessage) => void) => {
    const message = getAssistantMessage()
    if (message) updater(message)
  }
  streamingAssistantMessageId.value = assistantMessageId
  await nextTick()
  assistantPanelRef.value?.scrollToBottom()

  const controller = new AbortController()
  chatStreamController = controller
  isSendingChat.value = true
  let receivedContent = false
  let targetAssistantContent = ''
  let assistantRevealCanceled = false
  let assistantRevealQueue: string[] = []
  let assistantRevealTask: Promise<void> | null = null

  const updateThinkingElapsed = (serverElapsedMs?: number) => {
    const localElapsedMs = Math.max(0, Math.floor(performance.now() - thinkingStartedAt))
    const normalizedServerElapsedMs = Number.isFinite(serverElapsedMs)
      ? Math.max(0, Math.floor(serverElapsedMs ?? 0))
      : 0
    updateAssistantMessage((message) => {
      message.thinkingElapsedMs = Math.max(
        message.thinkingElapsedMs ?? 0,
        localElapsedMs,
        normalizedServerElapsedMs,
      )
    })
  }

  const thinkingTimer = window.setInterval(() => {
    updateThinkingElapsed()
  }, 250)

  const revealQueuedAssistantContent = async () => {
    while (!assistantRevealCanceled && !controller.signal.aborted && assistantRevealQueue.length) {
      const chunk = assistantRevealQueue.splice(0, ASSISTANT_REVEAL_CHUNK_SIZE).join('')
      updateAssistantMessage((message) => {
        message.content += chunk
      })
      await assistantPanelRef.value?.followOutput()
      await waitForAssistantRevealFrame()
    }
  }

  const ensureAssistantRevealTask = () => {
    if (!assistantRevealTask) {
      assistantRevealTask = revealQueuedAssistantContent().finally(() => {
        assistantRevealTask = null
        if (!assistantRevealCanceled && !controller.signal.aborted && assistantRevealQueue.length) {
          ensureAssistantRevealTask()
        }
      })
    }
  }

  const waitForAssistantReveal = async () => {
    while (assistantRevealTask) {
      await assistantRevealTask
    }
  }

  const enqueueAssistantContent = (incomingContent: string, mode: 'delta' | 'final') => {
    const chunk = mode === 'final'
      ? getMissingAssistantContent(targetAssistantContent, incomingContent)
      : incomingContent
    if (!chunk) return

    targetAssistantContent += chunk
    receivedContent = true
    assistantRevealQueue.push(...Array.from(chunk))
    ensureAssistantRevealTask()
  }

  try {
    const response = await fetchWithAuthRetry(chatScreenwritingStreamUrl(projectPublicId.value), {
      method: 'POST',
      headers: {
        Accept: 'application/x-ndjson',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        activeTab: activeTab.value,
        message: content,
        clientRequestStartedAtMs,
      }),
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(await readFetchError(response))
    }
    if (!response.body) {
      throw new Error('当前浏览器不支持读取 AI 对话流')
    }

    await readNdjsonStream<ScreenwritingStreamEvent>(response.body, async (event) => {
      updateThinkingElapsed(event.data?.thinkingElapsedMs)
      if (event.conversationId) {
        conversationId.value = event.conversationId
      }
      if (event.modelId) {
        connectedModelId.value = event.modelId
      }
      if (event.data?.rag) {
        updateAssistantMessage((message) => {
          message.rag = event.data?.rag
        })
      }
      if (event.data?.serverTimings) {
        updateAssistantMessage((message) => {
          message.serverTimings = event.data?.serverTimings
        })
      }
      if (event.type === 'error') {
        throw new Error(readStreamError(event))
      }
      if (event.type === 'agent.action') {
        const entry: AgentActionEntry = {
          phase: String(event.data?.phase ?? ''),
          message: String(event.data?.message ?? ''),
          detail: typeof event.data?.detail === 'string' ? event.data.detail : undefined,
          targetTab: typeof event.data?.targetTab === 'string' ? event.data.targetTab : undefined,
        }
        if (entry.message) {
          updateAssistantMessage((message) => {
            message.actions = [...(message.actions ?? []), entry]
          })
          await assistantPanelRef.value?.followOutput()
        }
        return
      }
      if (event.type === 'workspace.delta') {
        const targetTab = normalizeWorkspaceTab(event.data?.targetTab)
        if (targetTab) {
          const fullWorkspace = readWorkspacePayload(event.data?.workspace)
          if (fullWorkspace) {
            workspace.value = fullWorkspace
          } else {
            workspace.value = {
              ...workspace.value,
              [targetTab]: String(event.data?.workspaceContent ?? ''),
            }
          }
          if (activeTab.value !== targetTab) {
            activeTab.value = targetTab
          }
          stageTabsRef.value?.scrollTabToBottom(targetTab)
        }
        return
      }
      if (event.type === 'message.delta' && event.content) {
        enqueueAssistantContent(event.content, 'delta')
      }
      if (event.type === 'done') {
        const doneWorkspace = readWorkspacePayload(event.data?.workspace)
        if (doneWorkspace) {
          workspace.value = doneWorkspace
        }
        const doneStage = normalizeWorkspaceTab(event.data?.stage)
        if (doneStage) {
          activeTab.value = doneStage
        }
        const finalContent = readAssistantFinalContent(event)
        if (finalContent) {
          enqueueAssistantContent(finalContent, 'final')
        }
      }
    })
    await waitForAssistantReveal()

    if (!receivedContent && !getAssistantMessage()?.content.trim()) {
      updateAssistantMessage((message) => {
        message.content = '本轮没有返回可展示内容，请稍后重试。'
      })
      await assistantPanelRef.value?.followOutput()
    }
  } catch (error) {
    if (isAbortError(error)) return
    assistantRevealCanceled = true
    assistantRevealQueue = []
    const errorMessage = `对话失败：${getErrorMessage(error)}`
    updateAssistantMessage((message) => {
      message.content = errorMessage
    })
    ElMessage.error(errorMessage)
  } finally {
    window.clearInterval(thinkingTimer)
    updateThinkingElapsed()
    assistantRevealCanceled = true
    if (chatStreamController === controller) {
      chatStreamController = null
    }
    isSendingChat.value = false
    streamingAssistantMessageId.value = null
    await assistantPanelRef.value?.followOutput()
  }
}

const readStreamError = (event: ScreenwritingStreamEvent) => {
  const detail = event.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  return event.content || 'AI 对话流返回错误'
}

const readFetchError = async (response: Response) => {
  const text = await response.text()
  try {
    const payload = JSON.parse(text)
    if (typeof payload?.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim()
    }
  } catch {
    // 非 JSON 错误响应继续读取纯文本。
  }
  return text.trim() || `请求失败：HTTP ${response.status}`
}

const getErrorMessage = (error: unknown) => {
  const axiosError = isRecord(error) ? (error as unknown as AxiosError<{ detail?: unknown; message?: unknown }>) : null
  const responseMessage =
    formatErrorDetail(axiosError?.response?.data?.detail) ||
    formatErrorDetail(axiosError?.response?.data?.message)
  if (responseMessage) return responseMessage
  if (axiosError?.response?.status) {
    const statusText = axiosError.response.statusText ? ` ${axiosError.response.statusText}` : ''
    return `请求失败：HTTP ${axiosError.response.status}${statusText}`
  }
  if (axiosError?.code === 'ECONNABORTED') return '请求超时'
  if (error instanceof Error) return error.message
  return formatErrorDetail(error) || '未知错误'
}

const formatErrorDetail = (detail: unknown): string => {
  if (!detail) return ''
  if (typeof detail === 'string') return detail.trim()
  if (Array.isArray(detail)) {
    return detail.map(formatErrorDetail).filter(Boolean).join('；')
  }
  if (isRecord(detail)) {
    const message =
      formatErrorDetail(detail.msg) ||
      formatErrorDetail(detail.message) ||
      formatErrorDetail(detail.detail)
    const location = Array.isArray(detail.loc) ? detail.loc.map(String).join('.') : ''
    if (message) return location ? `${location}: ${message}` : message
    try {
      return JSON.stringify(detail)
    } catch {
      return String(detail)
    }
  }
  return String(detail)
}

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null
)

const isAbortError = (error: unknown) => (
  error instanceof DOMException && error.name === 'AbortError'
)

const stopChatStream = () => {
  chatStreamController?.abort()
  chatStreamController = null
  isSendingChat.value = false
  streamingAssistantMessageId.value = null
}

const goProject = () => {
  router.push('/project')
}

const goNovel = () => {
  router.push({
    path: '/novel',
    query: projectPublicId.value ? { id: projectPublicId.value } : {},
  })
}

const goScriptManage = () => {
  router.push({
    path: '/script',
    query: projectPublicId.value ? { id: projectPublicId.value } : {},
  })
}

// 进入制作工作台（携带项目，制作流程总览与各阶段操作在工作台内进行）。
const goProduction = () => {
  if (!projectPublicId.value) {
    ElMessage.warning('缺少项目信息，无法进入制作工作台')
    return
  }
  router.push({ path: '/production', query: { id: projectPublicId.value } })
}

const goTasks = () => {
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  router.push({
    path: '/tasks',
    query: {
      id: projectPublicId.value,
      type: 'novel',
      from: route.fullPath,
    },
  })
}

const showComingSoon = () => {
  ElMessage.info('功能开发中')
}

const clearRagWarmupPoll = () => {
  if (ragWarmupPollTimer === null) return
  window.clearTimeout(ragWarmupPollTimer)
  ragWarmupPollTimer = null
}

const scheduleRagWarmupPoll = () => {
  clearRagWarmupPoll()
  ragWarmupPollTimer = window.setTimeout(() => {
    void warmupRagIndex({ silent: true })
  }, RAG_WARMUP_POLL_INTERVAL_MS)
}

const warmupRagIndex = async (options: { silent?: boolean } = {}) => {
  if (!projectPublicId.value) return
  if (!options.silent) {
    clearRagWarmupPoll()
    ragWarmup.value = {
      status: 'starting',
      label: '正在启动资料索引预热',
      detail: '首次进入当前项目时开始构建 RAG 检索索引。',
    }
  }
  try {
    const { data: result } = await warmupScreenwritingRagIndexApi(projectPublicId.value)
    if (result.status === 'ready') {
      clearRagWarmupPoll()
      ragWarmup.value = {
        status: 'ready',
        label: '资料索引预热完成',
        detail: '现在可以使用章节、项目与小说资料进行检索。',
      }
      return
    }
    ragWarmup.value = {
      status: 'running',
      label: result.status === 'started' ? '资料索引预热已开始' : '资料索引预热进行中',
      detail: result.status === 'running'
        ? '同项目已有构建任务在运行，正在等待完成。'
        : '正在异步构建当前项目的向量索引。',
    }
    scheduleRagWarmupPoll()
  } catch (error) {
    clearRagWarmupPoll()
    const errorMessage = getErrorMessage(error)
    ragWarmup.value = {
      status: 'failed',
      label: '资料索引预热失败',
      detail: `错误：${errorMessage}。仍可继续对话，系统会在问答时尝试检索。`,
    }
    console.warn('Screenwriting RAG warmup failed', {
      projectPublicId: projectPublicId.value,
      errorMessage,
      error,
    })
  }
}

onMounted(() => {
  projectPublicId.value = resolveProjectPublicId()
  void loadScreenwritingState()
  nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
})

onBeforeUnmount(() => {
  clearRagWarmupPoll()
  stopChatStream()
})
</script>

<style scoped>
.screenwriting-page {
  box-sizing: border-box;
  height: 100vh;
  height: 100dvh;
  min-height: 760px;
  overflow: hidden;
  padding: 16px;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  background:
    radial-gradient(circle at top, rgba(100, 116, 139, 0.18) 0%, rgba(11, 13, 16, 0) 32%),
    linear-gradient(180deg, #0d1117 0%, #0b0d10 100%);
}

.app-shell {
  height: calc(100vh - 32px);
  height: calc(100dvh - 32px);
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 16px;
}

.main-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 24px 28px 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: clamp(368px, 24vw, 432px) minmax(0, 1fr);
  gap: 8px;
  overflow: hidden;
}

@media (max-width: 1180px) {
  .workspace {
    grid-template-columns: minmax(320px, 0.8fr) minmax(0, 1fr);
  }
}

@media (max-width: 920px) {
  .screenwriting-page {
    min-height: 920px;
  }

  .app-shell {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .workspace {
    grid-template-columns: 1fr;
    overflow-y: auto;
    align-content: start;
  }
}
</style>
