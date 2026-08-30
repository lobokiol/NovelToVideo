<template>
  <main class="tasks-page">
    <div class="app-shell">
      <aside class="sidebar">
        <div class="side-top">
          <div class="brand" @click="goProject">AF</div>

          <el-tooltip content="项目" placement="right">
            <button class="nav-btn" aria-label="项目" @click="goProject">
              <el-icon><Folder /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="任务" placement="right">
            <button class="nav-btn active" aria-label="任务">
              <el-icon><List /></el-icon>
            </button>
          </el-tooltip>
        </div>

        <div class="side-bottom">
          <el-tooltip content="文档" placement="right">
            <button class="nav-btn" aria-label="文档" @click="showComingSoon">
              <el-icon><Document /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="设置" placement="right">
            <button class="nav-btn" aria-label="设置" @click="settingsVisible = true">
              <el-icon><Setting /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="代码仓库" placement="right">
            <button class="nav-btn" aria-label="代码仓库" @click="showComingSoon">
              <el-icon><Connection /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </aside>

      <section class="main-panel">
        <header class="page-header">
          <div class="page-header__left">
            <h1 class="title">异步任务</h1>
            <p class="desc">
              <template v-if="projectName">查看项目「{{ projectName }}」的任务执行状态与进度控制</template>
              <template v-else>正在加载项目信息…</template>
            </p>
          </div>

          <div class="page-header__right">
            <el-button class="header-action" size="large" @click="goProject">
              <el-icon><Back /></el-icon>
              返回项目
            </el-button>
            <el-button
              class="header-action"
              size="large"
              :loading="reloading"
              @click="handleManualRefresh"
            >
              <el-icon><Refresh /></el-icon>
              立即刷新
            </el-button>
          </div>
        </header>

        <TaskMetricsBar v-if="projectPublicId" class="metrics-bar" :project-public-id="projectPublicId" />
        <section v-else class="metrics-bar placeholder-card">
          <el-icon class="placeholder-icon"><DataAnalysis /></el-icon>
          <div class="placeholder-text">
            <strong>指标快照</strong>
            <span>加载项目信息中…</span>
          </div>
        </section>

        <section v-if="listErrorMessage" class="task-error-banner">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ listErrorMessage }}</span>
        </section>

        <section class="content-grid">
          <TaskListPanel
            class="list-panel"
            :items="jobs"
            :total="jobTotal"
            :loading="listLoading"
            :selected-id="selectedJobId"
            :active-filter="statusFilter"
            @select="onSelectJob"
            @update:filter="onUpdateFilter"
          />

          <TaskDetailPanel
            v-if="selectedJobId"
            class="detail-panel"
            :project-public-id="projectPublicId"
            :job-public-id="selectedJobId"
            :job="selectedJob ?? undefined"
            @mutated="onDetailMutated"
            @cleared="onDetailCleared"
          />
          <div v-else class="detail-panel placeholder-card">
            <el-icon class="placeholder-icon"><Tickets /></el-icon>
            <div class="placeholder-text">
              <strong>任务详情</strong>
              <span>选择左侧批次后可查看条目明细与执行控制</span>
            </div>
          </div>
        </section>
      </section>
    </div>

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Back,
  Connection,
  DataAnalysis,
  Document,
  Folder,
  List,
  Refresh,
  Setting,
  Tickets,
  WarningFilled,
} from '@element-plus/icons-vue'
import {
  listTaskJobsApi,
  type TaskJobResponse,
  type TaskJobStatus,
} from '@/api/task'
import { listProjectsApi, type ProjectRecord } from '@/api/project'
import { useAdaptivePolling } from '@/composables/useAdaptivePolling'
import { usePollErrorNotice } from '@/composables/usePollErrorNotice'
import Settings from '../components/Settings.vue'
import TaskListPanel from '@/components/task/TaskListPanel.vue'
import TaskDetailPanel from '@/components/task/TaskDetailPanel.vue'
import TaskMetricsBar from '@/components/task/TaskMetricsBar.vue'

type FilterValue = TaskJobStatus | ''

const ACTIVE_JOB_STATUSES: TaskJobStatus[] = ['pending', 'running', 'paused']
const POLL_ACTIVE_INTERVAL_MS = 5000
const POLL_IDLE_INTERVAL_MS = 15000

const router = useRouter()
const route = useRoute()

const projectPublicId = ref('')
const projectName = ref('')
const projectType = ref('')
const reloading = ref(false)
const settingsVisible = ref(false)

const jobs = ref<TaskJobResponse[]>([])
const jobTotal = ref(0)
const listLoading = ref(false)
const selectedJobId = ref<string | null>(null)
const pendingRouteJobId = ref<string | null>(null)
const lastRouteJobId = ref<string | null>(null)
const allowDefaultJobSelection = ref(true)
const statusFilter = ref<FilterValue>('')
const {
  errorMessage: listErrorMessage,
  clearError: clearListError,
  notifyError: notifyListError,
} = usePollErrorNotice('加载任务列表失败')

const hasActiveJob = computed(() =>
  jobs.value.some((job) => ACTIVE_JOB_STATUSES.includes(job.status)),
)

const selectedJob = computed(() => (
  jobs.value.find((job) => job.publicId === selectedJobId.value) ?? null
))

const resolveProjectPublicId = () => {
  const id = route.query.id
  if (Array.isArray(id)) return id[0] || ''
  return typeof id === 'string' ? id : ''
}

const resolveQueryString = (value: unknown) => {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : ''
  return typeof value === 'string' ? value : ''
}

const resolveRouteJobPublicId = () => resolveQueryString(route.query.job).trim()

const resolveSourcePath = () => {
  const source = resolveQueryString(route.query.from).trim()
  if (!source.startsWith('/') || source.startsWith('/tasks')) return ''
  return source
}

const resolveRouteProjectType = () => resolveQueryString(route.query.type).trim()

const applyProjectMeta = (publicId: string, project: ProjectRecord | null) => {
  const explicitType = resolveRouteProjectType()
  projectName.value = project?.name || publicId
  projectType.value = explicitType || project?.project_type || ''
}

const loadProjectMeta = async (publicId: string) => {
  if (!publicId) {
    projectName.value = ''
    projectType.value = resolveRouteProjectType()
    return
  }
  try {
    const { data } = await listProjectsApi()
    if (projectPublicId.value !== publicId) return
    const project = (data ?? []).find((entry) => entry.public_id === publicId) ?? null
    applyProjectMeta(publicId, project)
  } catch (error) {
    if (projectPublicId.value !== publicId) return
    console.error('加载项目信息失败', error)
    applyProjectMeta(publicId, null)
  }
}

const applyPendingRouteJobSelection = (items: TaskJobResponse[]) => {
  const routeJobId = pendingRouteJobId.value
  if (!routeJobId) return false
  if (!items.some((job) => job.publicId === routeJobId)) return false
  selectedJobId.value = routeJobId
  pendingRouteJobId.value = null
  allowDefaultJobSelection.value = false
  return true
}

const loadJobs = async () => {
  const id = projectPublicId.value
  if (!id) return
  const requestedStatus = statusFilter.value || null
  listLoading.value = true
  try {
    const { data } = await listTaskJobsApi(id, {
      status: requestedStatus,
      page: 1,
      pageSize: 100,
    })
    if (requestedStatus !== (statusFilter.value || null)) {
      await loadJobs()
      return
    }
    const items = data?.items ?? []
    jobs.value = items
    jobTotal.value = data?.total ?? items.length
    if (applyPendingRouteJobSelection(items)) {
      clearListError()
      return
    }
    if (selectedJobId.value) {
      const matchedJob = items.find((job) => job.publicId === selectedJobId.value)
      if (matchedJob) {
        selectedJobId.value = matchedJob.publicId
        allowDefaultJobSelection.value = false
        clearListError()
        return
      }
      selectedJobId.value = null
      allowDefaultJobSelection.value = false
    }
    if (!selectedJobId.value && allowDefaultJobSelection.value && items.length > 0) {
      selectedJobId.value = items[0].publicId
      allowDefaultJobSelection.value = false
    }
    clearListError()
  } catch (error) {
    if (notifyListError(error)) {
      console.error('加载任务列表失败', error)
    }
  } finally {
    listLoading.value = false
  }
}

const listPoll = useAdaptivePolling({
  task: loadJobs,
  interval: () => (hasActiveJob.value ? POLL_ACTIVE_INTERVAL_MS : POLL_IDLE_INTERVAL_MS),
  enabled: () => Boolean(projectPublicId.value),
})

const loadRouteProject = () => {
  const id = resolveProjectPublicId().trim()
  const routeJobId = resolveRouteJobPublicId() || null
  const idChanged = projectPublicId.value !== id
  if (idChanged || lastRouteJobId.value !== routeJobId) {
    pendingRouteJobId.value = routeJobId
    lastRouteJobId.value = routeJobId
  }
  if (idChanged) {
    projectPublicId.value = id
    projectName.value = ''
    projectType.value = ''
    jobs.value = []
    jobTotal.value = 0
    selectedJobId.value = null
    allowDefaultJobSelection.value = true
    statusFilter.value = ''
    clearListError()
    if (listPoll.running.value) {
      void listPoll.refreshNow()
    }
  } else if (listPoll.running.value) {
    void listPoll.refreshNow()
  }
  void loadProjectMeta(id)
}

const handleManualRefresh = async () => {
  if (!projectPublicId.value) return
  reloading.value = true
  try {
    await loadProjectMeta(projectPublicId.value)
    await listPoll.refreshNow()
  } finally {
    reloading.value = false
  }
}

const onSelectJob = (jobPublicId: string) => {
  pendingRouteJobId.value = null
  allowDefaultJobSelection.value = false
  if (selectedJobId.value !== jobPublicId) {
    selectedJobId.value = jobPublicId
  }
}

const onUpdateFilter = (value: FilterValue) => {
  statusFilter.value = value
  pendingRouteJobId.value = null
  selectedJobId.value = null
  allowDefaultJobSelection.value = true
  void listPoll.refreshNow()
}

const onDetailMutated = () => {
  void listPoll.refreshNow()
}

const onDetailCleared = () => {
  pendingRouteJobId.value = null
  selectedJobId.value = null
  allowDefaultJobSelection.value = false
  void listPoll.refreshNow()
}

const goProject = () => {
  const sourcePath = resolveSourcePath()
  if (sourcePath) {
    router.push(sourcePath)
    return
  }
  const routeMap: Record<string, string> = {
    novel: '/novel',
    script: '/script',
    original: '/original',
  }
  const path = routeMap[projectType.value || resolveRouteProjectType()]
  if (path && projectPublicId.value) {
    router.push({ path, query: { id: projectPublicId.value } })
    return
  }
  if (projectPublicId.value) {
    ElMessage.info('项目信息加载中，请稍候')
    return
  }
  router.push('/project')
}

const showComingSoon = () => {
  ElMessage.info('功能开发中')
}

watch(() => [route.query.id, route.query.type, route.query.job] as const, loadRouteProject, { immediate: true })
watch(selectedJobId, (nextId, prevId) => {
  if (nextId === prevId) return
  pendingRouteJobId.value = null
})

onMounted(() => {
  listPoll.start()
})
</script>

<style scoped>
.tasks-page {
  box-sizing: border-box;
  height: 100vh;
  height: 100dvh;
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

.sidebar {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.side-top,
.side-bottom {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.brand {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: #0a0a0a;
  font-size: 20px;
  font-weight: 800;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, #f3d96b, #c4b5fd);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 6px 18px rgba(243, 217, 107, 0.18);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.brand:hover {
  transform: translateY(-1px);
}

.nav-btn {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 16px;
  color: #8b949e;
  background: transparent;
  cursor: pointer;
  font-size: 22px;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.nav-btn :deep(.el-icon) {
  font-size: 22px;
}

.nav-btn:hover {
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.05);
  transform: translateY(-1px);
}

.nav-btn.active {
  color: #dbeafe;
  border-color: rgba(37, 99, 235, 0.32);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.22), rgba(37, 99, 235, 0.12));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.main-panel {
  display: flex;
  flex-direction: column;
  /* 允许整页在指标条展开时纵向滚动，避免压缩底部批次/明细 */
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.34) transparent;
  padding: 24px 28px 20px;
  gap: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.main-panel::-webkit-scrollbar {
  width: 8px;
}

.main-panel::-webkit-scrollbar-track {
  background: transparent;
}

.main-panel::-webkit-scrollbar-thumb {
  min-height: 48px;
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.32);
  background-clip: padding-box;
}

.main-panel::-webkit-scrollbar-thumb:hover {
  background: rgba(203, 213, 225, 0.46);
  background-clip: padding-box;
}

.main-panel::-webkit-scrollbar-corner {
  background: transparent;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  flex-shrink: 0;
}

.page-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  margin: 0;
  font-size: 32px;
  line-height: 1.1;
  font-weight: 800;
  background: linear-gradient(180deg, #ffffff 0%, #93a1b3 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.desc {
  margin: 6px 0 0;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.4;
}

.header-action {
  height: 38px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 10px;
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 14px;
  font-weight: 500;
  transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.header-action :deep(.el-icon) {
  font-size: 16px;
}

.header-action:hover,
.header-action:focus {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  transform: translateY(-1px);
}

.metrics-bar {
  flex-shrink: 0;
  min-height: 76px;
}

.task-error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 10px 12px;
  border: 1px solid rgba(248, 113, 113, 0.25);
  border-radius: 10px;
  color: #fecaca;
  background: rgba(127, 29, 29, 0.18);
  font-size: 12px;
  line-height: 1.4;
}

.task-error-banner :deep(.el-icon) {
  flex: 0 0 auto;
  color: #f87171;
  font-size: 16px;
}

.content-grid {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: minmax(320px, 360px) 1fr;
  grid-template-rows: 1fr;
  gap: 16px;
  min-height: 560px;
  min-width: 0;
}

.content-grid > * {
  min-height: 0;
  min-width: 0;
}

.placeholder-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border: 1px dashed rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.02);
  color: #8b949e;
}

.list-panel {
  min-height: 0;
  height: 100%;
}

.detail-panel {
  height: 100%;
  min-height: 560px;
}

.detail-panel.placeholder-card {
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.placeholder-icon {
  font-size: 22px;
  color: #6e7681;
}

.placeholder-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.placeholder-text strong {
  color: #e6edf3;
  font-size: 15px;
  font-weight: 600;
}

.placeholder-text span {
  font-size: 12px;
  color: #6e7681;
}

.detail-panel .placeholder-text {
  align-items: center;
}

@media (max-height: 720px) {
  .content-grid {
    min-height: 480px;
  }

  .detail-panel {
    min-height: 480px;
  }
}
</style>