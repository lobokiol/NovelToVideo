<template>
  <div class="item-table">
    <header class="table-head">
      <div class="head-left">
        <h3>条目明细</h3>
        <span class="total-hint">共 {{ total }} 条</span>
      </div>
      <div class="head-right">
        <el-select
          v-model="statusFilter"
          class="status-select"
          size="small"
          placeholder="全部状态"
          popper-class="task-items-dark-popper"
          :disabled="isActionLocked"
          @change="onFilterChange"
        >
          <el-option
            v-for="opt in STATUS_OPTIONS"
            :key="opt.value || 'all'"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
    </header>

    <div v-if="selectedCount > 0" class="bulk-bar">
      <span class="bulk-summary">
        已选 <strong>{{ selectedCount }}</strong> 项
      </span>
      <div class="bulk-actions">
        <el-button
          class="bulk-btn"
          size="small"
          :disabled="isActionLocked || selectedPausableCount === 0"
          :loading="bulkActionLoading === 'pause'"
          @click="onBulkPause"
        >
          <el-icon><VideoPause /></el-icon>
          暂停 {{ selectedPausableCount }}
        </el-button>
        <el-button
          class="bulk-btn primary"
          size="small"
          :disabled="isActionLocked || selectedResumableCount === 0"
          :loading="bulkActionLoading === 'resume'"
          @click="onBulkResume"
        >
          <el-icon><VideoPlay /></el-icon>
          恢复 {{ selectedResumableCount }}
        </el-button>
        <el-button
          class="bulk-btn warning"
          size="small"
          :disabled="isActionLocked || selectedCancellableCount === 0"
          :loading="bulkActionLoading === 'cancel'"
          @click="onBulkCancel"
        >
          <el-icon><Close /></el-icon>
          取消 {{ selectedCancellableCount }}
        </el-button>
        <el-button
          class="bulk-btn primary"
          size="small"
          :disabled="isActionLocked || selectedRetryableCount === 0"
          :loading="bulkActionLoading === 'retry'"
          @click="onBulkRetry"
        >
          <el-icon><RefreshRight /></el-icon>
          重试 {{ selectedRetryableCount }}
        </el-button>
        <button class="bulk-clear" type="button" :disabled="isActionLocked" @click="clearSelection">清空</button>
      </div>
    </div>

    <div class="table-body">
      <div v-if="loading && items.length === 0" class="state-empty">加载中…</div>
      <div v-else-if="items.length === 0" class="state-empty">暂无条目</div>
      <table v-else class="rows">
        <thead>
          <tr>
            <th class="col-check">
              <el-checkbox
                class="row-check"
                :model-value="allCurrentPageSelected"
                :indeterminate="someCurrentPageSelected"
                :disabled="isActionLocked"
                aria-label="选择当前页全部条目"
                @change="onTogglePageSelection"
              />
            </th>
            <th class="col-seq">#</th>
            <th class="col-status">状态</th>
            <th class="col-duration">耗时</th>
            <th class="col-error">错误摘要</th>
            <th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.publicId"
            class="row"
            @click="emit('open-item', item)"
          >
            <td class="col-check" @click.stop>
              <el-checkbox
                class="row-check"
                :model-value="selectedIdSet.has(item.publicId)"
                :disabled="isActionLocked"
                :aria-label="`选择条目 #${item.seq}`"
                @change="(value) => onToggleItemSelection(item.publicId, value)"
              />
            </td>
            <td class="col-seq">#{{ item.seq }}</td>
            <td class="col-status">
              <TaskStatusTag :status="item.status" />
            </td>
            <td class="col-duration mono">{{ formatDuration(item) }}</td>
            <td class="col-error">
              <span v-if="item.errorMessage" class="err" :title="item.errorMessage">
                {{ truncate(item.errorMessage, 80) }}
              </span>
              <span v-else class="dim">—</span>
            </td>
            <td class="col-actions" @click.stop>
              <el-button
                v-if="isRetryable(item)"
                class="row-btn primary"
                size="small"
                :disabled="isActionLocked"
                :loading="actionRowId === item.publicId"
                @click="onRetryItem(item)"
              >
                <el-icon><RefreshRight /></el-icon>
                重试
              </el-button>
              <el-button
                v-if="isCancellable(item)"
                class="row-btn warning"
                size="small"
                :disabled="isActionLocked"
                :loading="actionRowId === item.publicId"
                @click="onCancelItem(item)"
              >
                <el-icon><Close /></el-icon>
                取消
              </el-button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer v-if="total > pageSize" class="table-foot">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, jumper, total"
        small
        background
        :disabled="isActionLocked"
        popper-class="task-items-dark-popper"
        @current-change="onPageChange"
      />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElButton, ElCheckbox, ElIcon, ElMessage, ElMessageBox, ElOption, ElPagination, ElSelect } from 'element-plus'
import { Close, RefreshRight, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import {
  cancelTaskJobApi,
  listTaskItemsApi,
  pauseTaskJobApi,
  resumeTaskJobApi,
  retryTaskJobApi,
  type TaskItemResponse,
  type TaskItemStatus,
} from '@/api/task'
import { useAdaptivePolling } from '@/composables/useAdaptivePolling'
import { getErrorMessage, usePollErrorNotice } from '@/composables/usePollErrorNotice'
import TaskStatusTag from './TaskStatusTag.vue'

type FilterValue = TaskItemStatus | ''

const props = defineProps<{
  projectPublicId: string
  jobPublicId: string
}>()

const emit = defineEmits<{
  (e: 'open-item', item: TaskItemResponse): void
  (e: 'mutated'): void
}>()

const POLL_ACTIVE_INTERVAL_MS = 3000
const POLL_IDLE_INTERVAL_MS = 15000
const ACTIVE_ITEM_STATUSES = new Set<TaskItemStatus>(['pending', 'running', 'paused'])

const STATUS_OPTIONS: Array<{ label: string; value: FilterValue }> = [
  { label: '全部状态', value: '' },
  { label: '排队中', value: 'pending' },
  { label: '运行中', value: 'running' },
  { label: '已暂停', value: 'paused' },
  { label: '已完成', value: 'succeeded' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'canceled' },
]

const items = ref<TaskItemResponse[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const statusFilter = ref<FilterValue>('')
const loading = ref(false)
const actionRowId = ref<string | null>(null)
const selectedIds = ref<string[]>([])
const bulkActionLoading = ref<'pause' | 'resume' | 'cancel' | 'retry' | null>(null)
const {
  clearError: clearItemLoadError,
  notifyError: notifyItemLoadError,
} = usePollErrorNotice('加载条目列表失败')

const isPausable = (item: TaskItemResponse) => item.status === 'pending'
const isResumable = (item: TaskItemResponse) => item.status === 'paused'
const isCancellable = (item: TaskItemResponse) => item.status === 'pending' || item.status === 'paused'
const isRetryable = (item: TaskItemResponse) => item.status === 'failed' || item.status === 'canceled'

const isActionLocked = computed(() => Boolean(actionRowId.value || bulkActionLoading.value))
const selectedIdSet = computed(() => new Set(selectedIds.value))
const currentPageIds = computed(() => items.value.map((item) => item.publicId))
const selectedItems = computed(() => items.value.filter((item) => selectedIdSet.value.has(item.publicId)))
const selectedCount = computed(() => selectedIds.value.length)
const selectedPausableCount = computed(() => selectedItems.value.filter(isPausable).length)
const selectedResumableCount = computed(() => selectedItems.value.filter(isResumable).length)
const selectedCancellableCount = computed(() => selectedItems.value.filter(isCancellable).length)
const selectedRetryableCount = computed(() => selectedItems.value.filter(isRetryable).length)
const allCurrentPageSelected = computed(() => (
  currentPageIds.value.length > 0 && currentPageIds.value.every((id) => selectedIdSet.value.has(id))
))
const someCurrentPageSelected = computed(() => (
  currentPageIds.value.some((id) => selectedIdSet.value.has(id)) && !allCurrentPageSelected.value
))

const truncate = (text: string, max: number) => {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max)}…` : text
}

const formatDuration = (item: TaskItemResponse) => {
  const raw = item.diagnostics?.durationMs
  if (typeof raw === 'number' && raw >= 0) {
    if (raw < 1000) return `${raw} ms`
    return `${(raw / 1000).toFixed(2)} s`
  }
  // 回退口径与 diagnostics.durationMs 一致：创建→完成的总耗时（含排队）。
  if (item.createdAt && item.finishedAt) {
    const dt = new Date(item.finishedAt).getTime() - new Date(item.createdAt).getTime()
    if (Number.isFinite(dt) && dt >= 0) {
      if (dt < 1000) return `${dt} ms`
      return `${(dt / 1000).toFixed(2)} s`
    }
  }
  return '—'
}

const loadItems = async () => {
  if (!props.projectPublicId || !props.jobPublicId) return
  if (items.value.length === 0) loading.value = true
  try {
    const { data } = await listTaskItemsApi(props.projectPublicId, props.jobPublicId, {
      status: statusFilter.value || null,
      page: page.value,
      pageSize: pageSize.value,
    })
    items.value = data?.items ?? []
    total.value = data?.total ?? 0
    if (total.value > 0 && page.value > 1 && items.value.length === 0) {
      page.value = Math.max(1, Math.ceil(total.value / pageSize.value))
      await loadItems()
      return
    }
    pruneSelection()
    clearItemLoadError()
  } catch (error) {
    if (notifyItemLoadError(error)) {
      console.error('加载条目列表失败', error)
    }
  } finally {
    loading.value = false
  }
}

const hasActiveItem = () => items.value.some((item) => ACTIVE_ITEM_STATUSES.has(item.status))

const itemPoll = useAdaptivePolling({
  task: loadItems,
  interval: () => (hasActiveItem() ? POLL_ACTIVE_INTERVAL_MS : POLL_IDLE_INTERVAL_MS),
  enabled: () => Boolean(props.projectPublicId && props.jobPublicId),
})

const clearSelection = () => {
  selectedIds.value = []
}

const pruneSelection = () => {
  const validIds = new Set(currentPageIds.value)
  selectedIds.value = selectedIds.value.filter((id) => validIds.has(id))
}

const onTogglePageSelection = (value: string | number | boolean) => {
  selectedIds.value = value ? [...currentPageIds.value] : []
}

const onToggleItemSelection = (itemPublicId: string, value: string | number | boolean) => {
  const next = new Set(selectedIds.value)
  if (value) {
    next.add(itemPublicId)
  } else {
    next.delete(itemPublicId)
  }
  selectedIds.value = currentPageIds.value.filter((id) => next.has(id))
}

const withRowAction = async (itemPublicId: string, fn: () => Promise<void>, errorFallback: string) => {
  if (actionRowId.value || bulkActionLoading.value) return
  actionRowId.value = itemPublicId
  try {
    await fn()
  } catch (error) {
    console.error(errorFallback, error)
    ElMessage.error(getErrorMessage(error, errorFallback))
  } finally {
    actionRowId.value = null
  }
}

const isCancelError = (error: unknown) => error === 'cancel' || error === 'close'

const selectedIdsBy = (predicate: (item: TaskItemResponse) => boolean) => (
  selectedItems.value.filter(predicate).map((item) => item.publicId)
)

const withBulkAction = async (
  action: NonNullable<typeof bulkActionLoading.value>,
  itemIds: string[],
  fn: () => Promise<void>,
  errorFallback: string,
) => {
  if (bulkActionLoading.value || actionRowId.value || itemIds.length === 0) return
  bulkActionLoading.value = action
  try {
    await fn()
    clearSelection()
    emit('mutated')
    await itemPoll.refreshNow()
  } catch (error) {
    if (isCancelError(error)) return
    console.error(errorFallback, error)
    ElMessage.error(getErrorMessage(error, errorFallback))
  } finally {
    bulkActionLoading.value = null
  }
}

const onRetryItem = (item: TaskItemResponse) =>
  withRowAction(
    item.publicId,
    async () => {
      const { data } = await retryTaskJobApi(props.projectPublicId, props.jobPublicId, {
        itemPublicIds: [item.publicId],
      })
      const newCount = data?.newItemPublicIds?.length ?? 0
      ElMessage.success(`已为条目 #${item.seq} 创建 ${newCount} 个重试`)
      emit('mutated')
      await itemPoll.refreshNow()
    },
    `重试条目 #${item.seq} 失败`,
  )

const onCancelItem = (item: TaskItemResponse) =>
  withRowAction(
    item.publicId,
    async () => {
      const { data } = await cancelTaskJobApi(props.projectPublicId, props.jobPublicId, {
        itemPublicIds: [item.publicId],
      })
      const canceledCount = data?.canceledCount ?? 0
      ElMessage.success(`已取消 ${canceledCount} 个条目`)
      emit('mutated')
      await itemPoll.refreshNow()
    },
    `取消条目 #${item.seq} 失败`,
  )

const onBulkPause = () => {
  const itemIds = selectedIdsBy(isPausable)
  void withBulkAction(
    'pause',
    itemIds,
    async () => {
      const { data } = await pauseTaskJobApi(props.projectPublicId, props.jobPublicId, { itemPublicIds: itemIds })
      ElMessage.success(`已暂停 ${data?.pausedCount ?? 0} 个条目`)
    },
    '批量暂停失败',
  )
}

const onBulkResume = () => {
  const itemIds = selectedIdsBy(isResumable)
  void withBulkAction(
    'resume',
    itemIds,
    async () => {
      const { data } = await resumeTaskJobApi(props.projectPublicId, props.jobPublicId, { itemPublicIds: itemIds })
      ElMessage.success(`已恢复 ${data?.resumedCount ?? 0} 个条目`)
    },
    '批量恢复失败',
  )
}

const onBulkCancel = () => {
  const itemIds = selectedIdsBy(isCancellable)
  void withBulkAction(
    'cancel',
    itemIds,
    async () => {
      await ElMessageBox.confirm(`确定取消选中的 ${itemIds.length} 个可取消条目吗？`, '批量取消条目', {
        confirmButtonText: '确认取消',
        cancelButtonText: '返回',
        type: 'warning',
        customClass: 'task-dark-messagebox',
      })
      const { data } = await cancelTaskJobApi(props.projectPublicId, props.jobPublicId, { itemPublicIds: itemIds })
      ElMessage.success(`已取消 ${data?.canceledCount ?? 0} 个条目`)
    },
    '批量取消失败',
  )
}

const onBulkRetry = () => {
  const itemIds = selectedIdsBy(isRetryable)
  void withBulkAction(
    'retry',
    itemIds,
    async () => {
      const { data } = await retryTaskJobApi(props.projectPublicId, props.jobPublicId, { itemPublicIds: itemIds })
      const newCount = data?.newItemPublicIds?.length ?? 0
      ElMessage.success(`已创建 ${newCount} 个重试条目`)
    },
    '批量重试失败',
  )
}

const onFilterChange = () => {
  page.value = 1
  clearSelection()
  void itemPoll.refreshNow()
}

const onPageChange = (next: number) => {
  page.value = next
  clearSelection()
  void itemPoll.refreshNow()
}

const refresh = () => {
  if (itemPoll.running.value) {
    void itemPoll.refreshNow()
  }
}

watch(
  () => props.jobPublicId,
  () => {
    items.value = []
    total.value = 0
    page.value = 1
    statusFilter.value = ''
    clearSelection()
    clearItemLoadError()
    if (itemPoll.running.value) {
      void itemPoll.refreshNow()
    }
  },
)

onMounted(() => {
  itemPoll.start()
})

defineExpose({ refresh })
</script>

<style scoped>
.item-table {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 0;
}

.table-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.head-left h3 {
  margin: 0;
  color: #e6edf3;
  font-size: 14px;
  font-weight: 600;
}

.total-hint {
  color: #6e7681;
  font-size: 12px;
}

.status-select {
  width: 140px;
}

.status-select :deep(.el-select__wrapper) {
  min-height: 30px;
  border-radius: 8px;
  background-color: rgba(255, 255, 255, 0.04);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
  transition: background-color 0.18s ease, box-shadow 0.18s ease;
}

.status-select :deep(.el-select__wrapper.is-hovering) {
  background-color: rgba(255, 255, 255, 0.06);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset;
}

.status-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px rgba(122, 162, 247, 0.7) inset;
}

.status-select :deep(.el-select__wrapper.is-disabled) {
  background-color: rgba(255, 255, 255, 0.02);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.05) inset;
  cursor: not-allowed;
}

.status-select :deep(.el-select__placeholder),
.status-select :deep(.el-select__selected-item) {
  color: #e6edf3;
  font-size: 12px;
}

.status-select :deep(.el-select__caret) {
  color: #8b949e;
}

.status-select :deep(.el-select__wrapper.is-disabled .el-select__placeholder),
.status-select :deep(.el-select__wrapper.is-disabled .el-select__selected-item),
.status-select :deep(.el-select__wrapper.is-disabled .el-select__caret) {
  color: rgba(203, 213, 225, 0.38);
}

.bulk-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid rgba(122, 162, 247, 0.22);
  border-radius: 10px;
  background: rgba(37, 99, 235, 0.1);
}

.bulk-summary {
  flex: 0 0 auto;
  color: #9fb0c7;
  font-size: 12px;
  white-space: nowrap;
}

.bulk-summary strong {
  color: #dbeafe;
  font-weight: 700;
}

.bulk-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
  flex-wrap: wrap;
}

.bulk-btn {
  height: 26px;
  padding: 0 9px;
  border-radius: 7px;
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.bulk-btn :deep(.el-icon) {
  font-size: 12px;
}

.bulk-btn:hover,
.bulk-btn:focus {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

.bulk-btn.primary {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.16);
  border-color: rgba(37, 99, 235, 0.32);
}

.bulk-btn.primary:hover,
.bulk-btn.primary:focus {
  color: #dbeafe;
  background: rgba(37, 99, 235, 0.24);
  border-color: rgba(37, 99, 235, 0.45);
}

.bulk-btn.warning {
  color: #fcd34d;
  background: rgba(234, 179, 8, 0.14);
  border-color: rgba(234, 179, 8, 0.3);
}

.bulk-btn.warning:hover,
.bulk-btn.warning:focus {
  color: #fde68a;
  background: rgba(234, 179, 8, 0.22);
  border-color: rgba(234, 179, 8, 0.45);
}

.bulk-btn.is-disabled,
.bulk-btn.is-disabled:hover,
.bulk-btn.is-disabled:focus {
  color: rgba(203, 213, 225, 0.38);
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.06);
  cursor: not-allowed;
}

.bulk-clear {
  height: 26px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  color: #8b949e;
  background: transparent;
  font-size: 11px;
  cursor: pointer;
  transition: color 0.18s ease, background 0.18s ease;
}

.bulk-clear:hover,
.bulk-clear:focus {
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.06);
}

.bulk-clear:disabled,
.bulk-clear:disabled:hover,
.bulk-clear:disabled:focus {
  color: rgba(203, 213, 225, 0.35);
  background: transparent;
  cursor: not-allowed;
}

.table-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.state-empty {
  display: grid;
  place-items: center;
  height: 100%;
  min-height: 120px;
  color: #6e7681;
  font-size: 12px;
}

.rows {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.rows thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 10px 12px;
  text-align: left;
  background: rgba(255, 255, 255, 0.04);
  color: #c5cdd6;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.rows tbody td {
  padding: 9px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
  vertical-align: middle;
}

.rows tbody .row {
  cursor: pointer;
  transition: background 0.15s ease;
}

.rows tbody .row:hover td {
  background: rgba(255, 255, 255, 0.04);
}

.rows .col-check {
  width: 56px;
  min-width: 56px;
  max-width: 56px;
  padding-right: 0;
  padding-left: 0;
  text-align: center;
}

.row-check {
  display: grid;
  place-items: center;
  width: 100%;
  min-height: 24px;
  line-height: 1;
}

.row-check :deep(.el-checkbox__input) {
  display: inline-grid;
  place-items: center;
}

.row-check :deep(.el-checkbox__inner) {
  width: 14px;
  height: 14px;
  border-color: rgba(148, 163, 184, 0.4);
  background: rgba(255, 255, 255, 0.04);
}

.row-check :deep(.el-checkbox__input.is-checked .el-checkbox__inner),
.row-check :deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner) {
  border-color: #7aa2f7;
  background: #2563eb;
}

.row-check :deep(.el-checkbox__input.is-focus .el-checkbox__inner) {
  border-color: rgba(122, 162, 247, 0.8);
  box-shadow: 0 0 0 2px rgba(122, 162, 247, 0.2);
}

.row-check :deep(.el-checkbox__input.is-disabled .el-checkbox__inner) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.02);
}

.col-seq {
  width: 60px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  color: #93c5fd;
}

.col-status {
  width: 90px;
}

.col-duration {
  width: 90px;
}

.col-error {
  min-width: 0;
}

.col-error .err {
  color: #fca5a5;
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

.col-error .dim {
  color: #6e7681;
}

.col-actions {
  width: 110px;
  text-align: right;
  white-space: nowrap;
}

.mono {
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.row-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: 7px;
  font-size: 11px;
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.12);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.row-btn :deep(.el-icon) {
  font-size: 12px;
}

.row-btn:hover,
.row-btn:focus {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.22);
}

.row-btn.primary {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.16);
  border-color: rgba(37, 99, 235, 0.32);
}

.row-btn.primary:hover,
.row-btn.primary:focus {
  background: rgba(37, 99, 235, 0.24);
  border-color: rgba(37, 99, 235, 0.45);
  color: #dbeafe;
}

.row-btn.warning {
  color: #fcd34d;
  background: rgba(234, 179, 8, 0.14);
  border-color: rgba(234, 179, 8, 0.3);
}

.row-btn.warning:hover,
.row-btn.warning:focus {
  background: rgba(234, 179, 8, 0.22);
  border-color: rgba(234, 179, 8, 0.45);
  color: #fde68a;
}

.row-btn.is-disabled,
.row-btn.is-disabled:hover,
.row-btn.is-disabled:focus {
  color: rgba(203, 213, 225, 0.38);
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.06);
  cursor: not-allowed;
}

.table-foot {
  display: flex;
  justify-content: flex-end;
}

/* 分页容器：透明背景，文字浅色 */
.table-foot :deep(.el-pagination) {
  --el-pagination-bg-color: transparent;
  --el-pagination-text-color: #e6edf3;
  --el-pagination-button-color: #e6edf3;
  --el-pagination-button-bg-color: rgba(255, 255, 255, 0.04);
  --el-pagination-button-disabled-color: rgba(230, 237, 243, 0.4);
  --el-pagination-button-disabled-bg-color: rgba(255, 255, 255, 0.02);
  --el-pagination-hover-color: #7aa2f7;
  background: transparent;
  color: #e6edf3;
}

/* 翻页箭头按钮 */
.table-foot :deep(.el-pagination button),
.table-foot :deep(.el-pagination .btn-prev),
.table-foot :deep(.el-pagination .btn-next) {
  background: rgba(255, 255, 255, 0.04);
  color: #e6edf3;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.table-foot :deep(.el-pagination button:disabled),
.table-foot :deep(.el-pagination .btn-prev:disabled),
.table-foot :deep(.el-pagination .btn-next:disabled) {
  background: rgba(255, 255, 255, 0.02);
  color: rgba(230, 237, 243, 0.4);
  opacity: 0.4;
}

.table-foot :deep(.el-pagination button:not(:disabled):hover),
.table-foot :deep(.el-pagination .btn-prev:not(:disabled):hover),
.table-foot :deep(.el-pagination .btn-next:not(:disabled):hover) {
  background: rgba(255, 255, 255, 0.08);
  color: #7aa2f7;
}

/* 页码列表 */
.table-foot :deep(.el-pager li) {
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.table-foot :deep(.el-pager li:hover) {
  background: rgba(255, 255, 255, 0.08);
  color: #e6edf3;
}

.table-foot :deep(.el-pager li.more) {
  background: rgba(255, 255, 255, 0.02);
  color: #8b949e;
}

.table-foot :deep(.el-pager li.is-disabled),
.table-foot :deep(.el-pager li.is-disabled:hover) {
  background: rgba(255, 255, 255, 0.02);
  color: rgba(230, 237, 243, 0.35);
  border-color: rgba(255, 255, 255, 0.05);
}

.table-foot :deep(.el-pager li.is-active),
.table-foot :deep(.el-pager li.is-active:hover) {
  background: rgba(122, 162, 247, 0.18);
  color: #7aa2f7;
  border-color: rgba(122, 162, 247, 0.4);
}

/* 总数与跳转标签文字 */
.table-foot :deep(.el-pagination__total),
.table-foot :deep(.el-pagination__jump),
.table-foot :deep(.el-pagination__goto),
.table-foot :deep(.el-pagination__classifier) {
  color: #8b949e;
}

/* 跳转输入框 */
.table-foot :deep(.el-pagination__editor.el-input .el-input__wrapper) {
  background: rgba(255, 255, 255, 0.04);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
  border-radius: 4px;
}

.table-foot :deep(.el-pagination__editor.el-input .el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(122, 162, 247, 0.4) inset;
}

.table-foot :deep(.el-pagination__editor.el-input .el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #7aa2f7 inset;
}

.table-foot :deep(.el-pagination__editor.el-input .el-input__inner) {
  color: #e6edf3;
  background: transparent;
}

.table-foot :deep(.el-pagination__editor.el-input .el-input__inner::placeholder) {
  color: rgba(230, 237, 243, 0.45);
}

.table-body::-webkit-scrollbar {
  width: 6px;
}

.table-body::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
}

@media (max-width: 980px) {
  .bulk-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .bulk-actions {
    justify-content: flex-start;
  }
}
</style>

<style>
/* 暗黑主题弹层：覆盖状态筛选下拉与分页跳转下拉，因弹层挂载至 body，需放在非 scoped 样式中 */
.task-items-dark-popper.el-popper {
  background: #1a1d23 !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}

.task-items-dark-popper .el-select-dropdown {
  background: #1a1d23;
  border: none;
}

.task-items-dark-popper .el-select-dropdown__wrap,
.task-items-dark-popper .el-scrollbar,
.task-items-dark-popper .el-scrollbar__wrap,
.task-items-dark-popper .el-scrollbar__view {
  background: #1a1d23;
}

.task-items-dark-popper .el-select-dropdown__list {
  padding: 6px 4px;
}

.task-items-dark-popper .el-select-dropdown__item {
  color: #c5cdd6;
  background: transparent;
  border-radius: 8px;
  margin: 2px 4px;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.task-items-dark-popper .el-select-dropdown__item:hover,
.task-items-dark-popper .el-select-dropdown__item.hover,
.task-items-dark-popper .el-select-dropdown__item.is-hovering {
  background: rgba(255, 255, 255, 0.04);
  color: #ffffff;
}

.task-items-dark-popper .el-select-dropdown__item.is-selected,
.task-items-dark-popper .el-select-dropdown__item.selected {
  color: #7aa2f7;
  background: rgba(122, 162, 247, 0.12);
  font-weight: 600;
}

.task-items-dark-popper .el-select-dropdown__item.is-disabled {
  color: #4d5560;
  background: transparent;
}

.task-items-dark-popper .el-select-dropdown__wrap::-webkit-scrollbar {
  width: 6px;
}

.task-items-dark-popper .el-select-dropdown__wrap::-webkit-scrollbar-track {
  background: transparent;
}

.task-items-dark-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.3);
  border-radius: 999px;
}

.task-items-dark-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}

.task-items-dark-popper .el-popper__arrow::before {
  background: #1a1d23 !important;
  border-color: rgba(255, 255, 255, 0.08) !important;
}
</style>
