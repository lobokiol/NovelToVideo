<template>
  <section class="detail">
    <header class="detail-head">
      <div class="head-left">
        <h2 class="head-title" :title="job?.name || ''">{{ job?.name || '任务详情' }}</h2>
        <TaskStatusTag :status="job?.status || 'pending'" />
      </div>
      <div class="head-actions">
        <el-button
          v-if="visibility.pause"
          class="action-btn"
          size="default"
          :loading="actionLoading"
          @click="onPause"
        >
          <el-icon><VideoPause /></el-icon>
          暂停
        </el-button>
        <el-button
          v-if="visibility.resume"
          class="action-btn primary"
          size="default"
          :loading="actionLoading"
          @click="onResume"
        >
          <el-icon><VideoPlay /></el-icon>
          恢复
        </el-button>
        <el-button
          v-if="visibility.cancel"
          class="action-btn warning"
          size="default"
          :loading="actionLoading"
          @click="onCancel"
        >
          <el-icon><Close /></el-icon>
          取消
        </el-button>
        <el-button
          v-if="visibility.retry"
          class="action-btn primary"
          size="default"
          :loading="actionLoading"
          @click="onRetry"
        >
          <el-icon><RefreshRight /></el-icon>
          重试失败
        </el-button>
        <el-button
          v-if="visibility.remove"
          class="action-btn danger"
          size="default"
          :loading="actionLoading"
          @click="onRemove"
        >
          <el-icon><Delete /></el-icon>
          删除
        </el-button>
      </div>
    </header>

    <div class="info-bar">
      <div class="info-item">
        <label>任务类型</label>
        <span>{{ job ? (TASK_TYPE_LABEL[job.taskType] ?? job.taskType) : '—' }}</span>
      </div>
      <div class="info-item">
        <label>模型</label>
        <span class="mono">{{ job?.modelId || '—' }}</span>
      </div>
      <div class="info-item">
        <label>队列</label>
        <span class="mono">{{ job?.providerKey || '—' }}</span>
      </div>
      <div class="info-item">
        <label>创建</label>
        <span>{{ formatTime(job?.createdAt) }}</span>
      </div>
      <div class="info-item">
        <label>开始</label>
        <span>{{ formatTime(job?.startedAt) }}</span>
      </div>
      <div class="info-item">
        <label>结束</label>
        <span>{{ formatTime(job?.finishedAt) }}</span>
      </div>
    </div>

    <div class="progress-block">
      <div class="progress-summary">
        <span class="summary-text">
          已完成 <strong>{{ doneCount }}</strong> / {{ job?.totalCount ?? 0 }}
        </span>
        <span class="summary-percent">{{ percent }}%</span>
      </div>
      <div class="total-bar">
        <div class="bar succeeded" :style="{ width: succeededPercent + '%' }" />
        <div class="bar failed" :style="{ width: failedPercent + '%', left: succeededPercent + '%' }" />
        <div class="bar canceled" :style="{ width: canceledPercent + '%', left: (succeededPercent + failedPercent) + '%' }" />
      </div>
      <div class="count-grid">
        <div class="count-card pending">
          <span class="num">{{ job?.pendingCount ?? 0 }}</span>
          <span class="lbl">排队中</span>
        </div>
        <div class="count-card running">
          <span class="num">{{ job?.runningCount ?? 0 }}</span>
          <span class="lbl">运行中</span>
        </div>
        <div class="count-card paused">
          <span class="num">{{ job?.pausedCount ?? 0 }}</span>
          <span class="lbl">已暂停</span>
        </div>
        <div class="count-card succeeded">
          <span class="num">{{ job?.succeededCount ?? 0 }}</span>
          <span class="lbl">已完成</span>
        </div>
        <div class="count-card failed">
          <span class="num">{{ job?.failedCount ?? 0 }}</span>
          <span class="lbl">失败</span>
        </div>
        <div class="count-card canceled">
          <span class="num">{{ job?.canceledCount ?? 0 }}</span>
          <span class="lbl">已取消</span>
        </div>
      </div>
    </div>

    <TaskItemTable
      class="items-region"
      :project-public-id="projectPublicId"
      :job-public-id="jobPublicId"
      @open-item="onOpenItem"
      @mutated="onItemMutated"
    />

    <TaskItemDetailDialog
      v-model="itemDialogVisible"
      :project-public-id="projectPublicId"
      :job-public-id="jobPublicId"
      :job-task-type="job?.taskType || ''"
      :item-public-id="openItemId"
      :initial-item="openItem"
    />
  </section>

</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElButton, ElIcon, ElMessage, ElMessageBox } from 'element-plus'
import {
  Close,
  Delete,
  RefreshRight,
  VideoPause,
  VideoPlay,
} from '@element-plus/icons-vue'
import {
  cancelTaskJobApi,
  deleteTaskJobApi,
  getTaskJobApi,
  listTaskItemsApi,
  pauseTaskJobApi,
  resumeTaskJobApi,
  retryTaskJobApi,
  type AgentTaskType,
  type TaskItemResponse,
  type TaskJobResponse,
} from '@/api/task'
import { useAdaptivePolling } from '@/composables/useAdaptivePolling'
import { getErrorMessage, usePollErrorNotice } from '@/composables/usePollErrorNotice'
import TaskStatusTag from './TaskStatusTag.vue'
import TaskItemTable from './TaskItemTable.vue'
import TaskItemDetailDialog from './TaskItemDetailDialog.vue'

const props = defineProps<{
  projectPublicId: string
  jobPublicId: string
  job?: TaskJobResponse
}>()

const emit = defineEmits<{
  (e: 'mutated'): void
  (e: 'cleared'): void
}>()

const POLL_ACTIVE_INTERVAL_MS = 2000
const POLL_IDLE_INTERVAL_MS = 10000
const ACTIVE_STATUSES = new Set(['pending', 'running', 'paused'])

const TASK_TYPE_LABEL: Record<AgentTaskType, string> = {
  script_creation: '剧本创作',
  chapter_event_extraction: '章节事件抽取',
  asset_prompt_generation: '资产提示词生成',
  asset_image_generation: '资产图像生成',
  storyboard_script: '分镜剧本',
  'storyboard.generate': '分镜表生成',
  'novel.chapter.clean_event': '章节事件清洗',
}

const job = ref<TaskJobResponse | null>(props.job ?? null)
const loading = ref(false)
const actionLoading = ref(false)
const {
  clearError: clearDetailLoadError,
  notifyError: notifyDetailLoadError,
} = usePollErrorNotice('加载任务详情失败')

const itemDialogVisible = ref(false)
const openItemId = ref<string | null>(null)
const openItem = ref<TaskItemResponse | null>(null)

const onOpenItem = (item: TaskItemResponse) => {
  openItem.value = item
  openItemId.value = item.publicId
  itemDialogVisible.value = true
}

const doneCount = computed(() => {
  if (!job.value) return 0
  return job.value.succeededCount + job.value.failedCount + job.value.canceledCount
})

const percent = computed(() => {
  if (!job.value || !job.value.totalCount) return 0
  return Math.min(100, Math.round((doneCount.value / job.value.totalCount) * 100))
})

const succeededPercent = computed(() => {
  if (!job.value || !job.value.totalCount) return 0
  return Math.min(100, (job.value.succeededCount / job.value.totalCount) * 100)
})

const failedPercent = computed(() => {
  if (!job.value || !job.value.totalCount) return 0
  return Math.min(100, (job.value.failedCount / job.value.totalCount) * 100)
})

const canceledPercent = computed(() => {
  if (!job.value || !job.value.totalCount) return 0
  return Math.min(100, (job.value.canceledCount / job.value.totalCount) * 100)
})

const visibility = computed(() => {
  const status = job.value?.status
  return {
    pause: status === 'pending' || status === 'running',
    resume: status === 'paused',
    cancel: status === 'pending' || status === 'running' || status === 'paused',
    retry: status === 'failed' || status === 'partial_failed',
    remove:
      status === 'succeeded' ||
      status === 'partial_failed' ||
      status === 'failed' ||
      status === 'canceled',
  }
})

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

const isCancelError = (error: unknown) => error === 'cancel' || error === 'close'

const loadJob = async () => {
  if (!props.projectPublicId || !props.jobPublicId) return
  if (!job.value) loading.value = true
  try {
    const { data } = await getTaskJobApi(props.projectPublicId, props.jobPublicId)
    job.value = data
    clearDetailLoadError()
  } catch (error) {
    const message = getErrorMessage(error, '加载任务详情失败')
    if (message.includes('不存在') || message.includes('已被删除')) {
      if (notifyDetailLoadError(error, { fallback: '该批次不存在或已被删除', type: 'warning' })) {
        console.error('加载任务详情失败', error)
      }
      emit('cleared')
    } else {
      if (notifyDetailLoadError(error)) {
        console.error('加载任务详情失败', error)
      }
    }
  } finally {
    loading.value = false
  }
}

const detailPoll = useAdaptivePolling({
  task: loadJob,
  interval: () => {
    const status = job.value?.status
    if (!status) return POLL_ACTIVE_INTERVAL_MS
    return ACTIVE_STATUSES.has(status) ? POLL_ACTIVE_INTERVAL_MS : POLL_IDLE_INTERVAL_MS
  },
  enabled: () => Boolean(props.projectPublicId && props.jobPublicId),
})

const onItemMutated = () => {
  emit('mutated')
  void detailPoll.refreshNow()
}

const withAction = async <T>(fn: () => Promise<T>, errorFallback: string): Promise<T | null> => {
  if (actionLoading.value) return null
  actionLoading.value = true
  try {
    return await fn()
  } catch (error) {
    if (isCancelError(error)) return null
    console.error(errorFallback, error)
    ElMessage.error(getErrorMessage(error, errorFallback))
    return null
  } finally {
    actionLoading.value = false
  }
}

const onPause = () =>
  withAction(async () => {
    const { data } = await pauseTaskJobApi(props.projectPublicId, props.jobPublicId)
    ElMessage.success(`已暂停 ${data?.pausedCount ?? 0} 个条目`)
    emit('mutated')
    await detailPoll.refreshNow()
  }, '暂停失败')

const onResume = () =>
  withAction(async () => {
    const { data } = await resumeTaskJobApi(props.projectPublicId, props.jobPublicId)
    ElMessage.success(`已恢复 ${data?.resumedCount ?? 0} 个条目`)
    emit('mutated')
    await detailPoll.refreshNow()
  }, '恢复失败')

const onCancel = () =>
  withAction(async () => {
    await ElMessageBox.confirm('确定取消该批次？未完成的条目将被取消。', '取消批次', {
      confirmButtonText: '确认取消',
      cancelButtonText: '返回',
      type: 'warning',
      customClass: 'task-dark-messagebox',
    })
    const { data } = await cancelTaskJobApi(props.projectPublicId, props.jobPublicId)
    ElMessage.success(`已取消 ${data?.canceledCount ?? 0} 个条目`)
    emit('mutated')
    await detailPoll.refreshNow()
  }, '取消失败')

const onRetry = () =>
  withAction(async () => {
    const { data: itemsData } = await listTaskItemsApi(
      props.projectPublicId,
      props.jobPublicId,
      { status: 'failed', page: 1, pageSize: 200 },
    )
    const failedIds = (itemsData?.items ?? []).map((item) => item.publicId)
    if (failedIds.length === 0) {
      ElMessage.info('当前没有可重试的失败条目')
      return
    }
    const { data } = await retryTaskJobApi(props.projectPublicId, props.jobPublicId, {
      itemPublicIds: failedIds,
    })
    const newCount = data?.newItemPublicIds?.length ?? 0
    ElMessage.success(`已为 ${newCount} 个失败条目重新排队`)
    emit('mutated')
    await detailPoll.refreshNow()
  }, '重试失败')

const onRemove = () =>
  withAction(async () => {
    await ElMessageBox.confirm('确定删除该批次？此操作不可撤销。', '删除批次', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'task-dark-messagebox',
    })
    await deleteTaskJobApi(props.projectPublicId, props.jobPublicId)
    ElMessage.success('批次已删除')
    emit('mutated')
    emit('cleared')
  }, '删除失败')

watch(
  () => props.job,
  (nextJob) => {
    if (!nextJob) return
    if (!job.value || job.value.publicId !== nextJob.publicId) {
      job.value = nextJob
      clearDetailLoadError()
    }
  },
  { immediate: true },
)

onMounted(() => {
  detailPoll.start()
})
</script>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  padding: 14px 18px;
  min-height: 0;
  height: 100%;
  /* 允许整体面板纵向滚动作为兜底；条目列表区域会优先占据剩余空间并启用自身滚动 */
  overflow-y: auto;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.35);
}

.detail.loading {
  align-items: center;
  justify-content: center;
  color: #8b949e;
  font-size: 13px;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}

.head-title {
  margin: 0;
  color: #f2f4f8;
  font-size: 18px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.action-btn {
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12px;
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.action-btn :deep(.el-icon) {
  font-size: 15px;
}

.action-btn:hover,
.action-btn:focus {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
}

.action-btn.primary {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.16);
  border-color: rgba(37, 99, 235, 0.32);
}

.action-btn.primary:hover,
.action-btn.primary:focus {
  background: rgba(37, 99, 235, 0.24);
  border-color: rgba(37, 99, 235, 0.45);
  color: #dbeafe;
}

.action-btn.warning {
  color: #fcd34d;
  background: rgba(234, 179, 8, 0.14);
  border-color: rgba(234, 179, 8, 0.3);
}

.action-btn.warning:hover,
.action-btn.warning:focus {
  background: rgba(234, 179, 8, 0.22);
  border-color: rgba(234, 179, 8, 0.45);
  color: #fde68a;
}

.action-btn.danger {
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.14);
  border-color: rgba(248, 113, 113, 0.3);
}

.action-btn.danger:hover,
.action-btn.danger:focus {
  background: rgba(248, 113, 113, 0.22);
  border-color: rgba(248, 113, 113, 0.45);
  color: #fecaca;
}

.info-bar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 4px 14px;
  padding: 6px 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  flex-shrink: 0;
}

.info-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.info-item label {
  color: #6e7681;
  font-size: 11px;
  letter-spacing: 0.3px;
  flex-shrink: 0;
}

.info-item span {
  color: #e6edf3;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.info-item .mono {
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px;
}

.progress-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 14px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  flex-shrink: 0;
}

.progress-summary {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  color: #cbd5e1;
  font-size: 12px;
}

.progress-summary strong {
  color: #ffffff;
  font-size: 14px;
  font-weight: 700;
}

.summary-percent {
  font-family: "JetBrains Mono", monospace;
  color: #93c5fd;
  font-size: 14px;
  font-weight: 700;
}

.total-bar {
  position: relative;
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: hidden;
}

.total-bar .bar {
  position: absolute;
  top: 0;
  height: 100%;
  transition: width 0.3s ease;
}

.total-bar .bar.succeeded {
  left: 0;
  background: linear-gradient(90deg, #2563eb, #60a5fa);
}

.total-bar .bar.failed {
  background: linear-gradient(90deg, #f87171, #fca5a5);
}

.total-bar .bar.canceled {
  background: linear-gradient(90deg, #6b7280, #9ca3af);
}

.count-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(86px, 1fr));
  gap: 6px;
}

.count-card {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.025);
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}

.count-card .num {
  font-family: "JetBrains Mono", monospace;
  font-size: 15px;
  font-weight: 700;
  color: #e6edf3;
}

.count-card .lbl {
  color: #8b949e;
  font-size: 11px;
}

.count-card.pending .num { color: #fcd34d; }
.count-card.running .num { color: #86efac; }
.count-card.paused .num { color: #c4b5fd; }
.count-card.succeeded .num { color: #93c5fd; }
.count-card.failed .num { color: #fca5a5; }
.count-card.canceled .num { color: #9ca3af; }

.items-region {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px dashed rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.015);
  flex: 1 0 auto;
  /* 保证小屏下条目列表也有足够的可视高度，至少可显示 8-10 条 */
  min-height: 560px;
  overflow: hidden;
}

/* 窄屏断点下适度放宽最小高度，避免在低分辨率窗口出现外层滚动条 */
@media (max-height: 720px) {
  .items-region {
    min-height: 420px;
  }
}

.items-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.items-head h3 {
  margin: 0;
  color: #e6edf3;
  font-size: 14px;
  font-weight: 600;
}

.items-hint {
  color: #6e7681;
  font-size: 11px;
}

.items-body {
  flex: 1;
  display: grid;
  place-items: center;
  color: #6e7681;
  font-size: 12px;
}
</style>

<style>
/* 批次操作确认框挂载在 body，需在组件内补齐暗色样式，避免依赖项目页全局样式。 */
.el-overlay-message-box {
  background-color: rgba(0, 0, 0, 0.72);
  backdrop-filter: blur(2px);
}

.task-dark-messagebox.el-message-box {
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.task-dark-messagebox .el-message-box__header {
  padding: 18px 24px 8px;
}

.task-dark-messagebox .el-message-box__title {
  color: #e6edf3;
  font-size: 17px;
  font-weight: 700;
}

.task-dark-messagebox .el-message-box__headerbtn .el-message-box__close {
  color: #8b949e;
}

.task-dark-messagebox .el-message-box__headerbtn:hover .el-message-box__close,
.task-dark-messagebox .el-message-box__headerbtn:focus .el-message-box__close {
  color: #ffffff;
}

.task-dark-messagebox .el-message-box__content {
  padding: 8px 24px 18px;
  color: #b8c2cc;
}

.task-dark-messagebox .el-message-box__container {
  align-items: flex-start;
}

.task-dark-messagebox .el-message-box__status.el-icon {
  margin-top: 1px;
}

.task-dark-messagebox .el-message-box__status.el-message-box-icon--warning {
  color: #fcd34d;
}

.task-dark-messagebox .el-message-box__message p {
  color: #b8c2cc;
  line-height: 1.6;
}

.task-dark-messagebox .el-message-box__btns {
  padding: 12px 24px 18px;
  background: rgba(255, 255, 255, 0.015);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.task-dark-messagebox .el-message-box__btns .el-button {
  min-width: 76px;
  height: 34px;
  border-radius: 8px;
  font-weight: 600;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.task-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
}

.task-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger):hover,
.task-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger):focus {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
  transform: translateY(-1px);
}

.task-dark-messagebox .el-message-box__btns .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.22);
}

.task-dark-messagebox .el-message-box__btns .el-button--primary:hover,
.task-dark-messagebox .el-message-box__btns .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.28);
  transform: translateY(-1px);
}

.task-dark-messagebox .el-message-box__btns .el-button--danger {
  background-color: #dc2626;
  border-color: #dc2626;
  color: #ffffff;
  box-shadow: 0 10px 22px rgba(220, 38, 38, 0.22);
}

.task-dark-messagebox .el-message-box__btns .el-button--danger:hover,
.task-dark-messagebox .el-message-box__btns .el-button--danger:focus {
  background-color: #b91c1c;
  border-color: #b91c1c;
  box-shadow: 0 14px 28px rgba(220, 38, 38, 0.28);
  transform: translateY(-1px);
}

.task-dark-messagebox .el-message-box__btns .el-button:active {
  transform: translateY(0);
}
</style>