<template>
  <div class="panel">
    <header class="panel-head">
      <h2>
        批次列表
        <span class="badge">{{ total }}</span>
      </h2>
      <div class="status-filter">
        <el-select
          class="status-select"
          :model-value="activeFilter"
          size="small"
          placeholder="全部状态"
          popper-class="task-list-filter-popper"
          @change="onFilterChange"
        >
          <el-option
            v-for="opt in STATUS_FILTERS"
            :key="opt.value || 'all'"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
    </header>

    <div v-if="loading && items.length === 0" class="empty">加载中…</div>
    <div v-else-if="items.length === 0" class="empty">暂无批次</div>
    <div v-else class="list">
      <TaskListItem
        v-for="job in items"
        :key="job.publicId"
        :job="job"
        :active="job.publicId === selectedId"
        @click="emit('select', job.publicId)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElOption, ElSelect } from 'element-plus'
import type { TaskJobResponse, TaskJobStatus } from '@/api/task'
import TaskListItem from './TaskListItem.vue'

type FilterValue = TaskJobStatus | ''

const STATUS_FILTERS: Array<{ label: string; value: FilterValue }> = [
  { label: '全部', value: '' },
  { label: '排队中', value: 'pending' },
  { label: '运行中', value: 'running' },
  { label: '已暂停', value: 'paused' },
  { label: '失败', value: 'failed' },
  { label: '部分失败', value: 'partial_failed' },
  { label: '已完成', value: 'succeeded' },
  { label: '已取消', value: 'canceled' },
]

defineProps<{
  items: TaskJobResponse[]
  total: number
  loading: boolean
  selectedId: string | null
  activeFilter: FilterValue
}>()

const emit = defineEmits<{
  (e: 'select', jobPublicId: string): void
  (e: 'update:filter', value: FilterValue): void
}>()

const onFilterChange = (value: string | number | boolean) => {
  const nextValue = typeof value === 'string' ? value : ''
  if (STATUS_FILTERS.some((opt) => opt.value === nextValue)) {
    emit('update:filter', nextValue as FilterValue)
  }
}
</script>

<style scoped>
.panel {
  --batch-list-max-height: min(704px, calc(100dvh));

  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  padding: 16px;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.35);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.panel-head h2 {
  margin: 0;
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
}

.badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.18);
  color: #93c5fd;
  font-size: 11px;
  border: 1px solid rgba(37, 99, 235, 0.3);
  font-weight: 600;
  line-height: 1.5;
}

.status-filter {
  width: 132px;
  flex: 0 0 132px;
}

.status-select {
  width: 100%;
}

.status-select :deep(.el-select__wrapper) {
  min-height: 30px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  box-shadow: none;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}

.status-select :deep(.el-select__wrapper.is-hovering) {
  border-color: rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.06);
}

.status-select :deep(.el-select__wrapper.is-focused) {
  border-color: rgba(122, 162, 247, 0.7);
  box-shadow: 0 0 0 1px rgba(122, 162, 247, 0.32);
}

.status-select :deep(.el-select__placeholder),
.status-select :deep(.el-select__selected-item) {
  color: #e6edf3;
  font-size: 12px;
  font-weight: 500;
}

.status-select :deep(.el-select__caret) {
  color: #8b949e;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.38) transparent;
  flex: 0 1 auto;
  max-height: var(--batch-list-max-height);
  padding-right: 6px;
  min-height: 0;
}

.empty {
  color: #8b949e;
  font-size: 13px;
  text-align: center;
  padding: 60px 0;
  flex: 1;
  display: grid;
  place-items: center;
}

.list::-webkit-scrollbar {
  width: 8px;
}

.list::-webkit-scrollbar-track {
  background: transparent;
}

.list::-webkit-scrollbar-thumb {
  min-height: 44px;
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.32);
  background-clip: padding-box;
}

.list::-webkit-scrollbar-thumb:hover {
  background: rgba(203, 213, 225, 0.48);
  background-clip: padding-box;
}

.list::-webkit-scrollbar-corner {
  background: transparent;
}

@media (max-height: 720px) {
  .panel {
    --batch-list-max-height: min(560px, calc(100dvh - 260px));
  }
}
</style>

<style>
/* 批次列表筛选下拉浮层挂载到 body，需使用全局样式保持暗黑主题。 */
.task-list-filter-popper.el-popper {
  background: #1a1d23 !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}

.task-list-filter-popper .el-select-dropdown {
  background: #1a1d23;
  border: none;
}

.task-list-filter-popper .el-select-dropdown__wrap,
.task-list-filter-popper .el-scrollbar,
.task-list-filter-popper .el-scrollbar__wrap,
.task-list-filter-popper .el-scrollbar__view {
  background: #1a1d23;
}

.task-list-filter-popper .el-select-dropdown__list {
  padding: 6px 4px;
}

.task-list-filter-popper .el-select-dropdown__item {
  height: 32px;
  margin: 2px 4px;
  padding: 0 12px;
  border-radius: 8px;
  color: #c5cdd6;
  line-height: 32px;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.task-list-filter-popper .el-select-dropdown__item:hover,
.task-list-filter-popper .el-select-dropdown__item.hover,
.task-list-filter-popper .el-select-dropdown__item.is-hovering {
  background: rgba(255, 255, 255, 0.05);
  color: #ffffff;
}

.task-list-filter-popper .el-select-dropdown__item.selected,
.task-list-filter-popper .el-select-dropdown__item.is-selected {
  background: rgba(122, 162, 247, 0.12);
  color: #7aa2f7;
  font-weight: 600;
}

.task-list-filter-popper .el-select-dropdown__item.is-disabled {
  background: transparent;
  color: #4d5560;
}

.task-list-filter-popper .el-select-dropdown__wrap::-webkit-scrollbar {
  width: 6px;
}

.task-list-filter-popper .el-select-dropdown__wrap::-webkit-scrollbar-track {
  background: transparent;
}

.task-list-filter-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background-color: rgba(148, 163, 184, 0.3);
}

.task-list-filter-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}

.task-list-filter-popper .el-popper__arrow::before {
  background: #1a1d23 !important;
  border-color: rgba(255, 255, 255, 0.08) !important;
}
</style>