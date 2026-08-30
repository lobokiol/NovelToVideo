<template>
  <section class="toolbar">
    <el-input
      :model-value="searchKeyword"
      class="search-input"
      clearable
      placeholder="按剧本名称搜索"
      @update:model-value="onSearchInput"
      @clear="emit('update:searchKeyword', '')"
    >
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
    </el-input>

    <el-dropdown
      trigger="click"
      placement="bottom-start"
      popper-class="script-sort-dropdown"
      @command="onSortCommand"
    >
      <el-button class="sort-trigger">
        <el-icon><Sort /></el-icon>
        &nbsp;排序：{{ currentSortLabel }}
        <el-icon class="sort-direction-icon">
          <CaretTop v-if="sortOrder === 'asc'" />
          <CaretBottom v-else />
        </el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="opt in sortOptions"
            :key="opt.value"
            :command="opt.value"
            :class="{ 'is-active': sortField === opt.value }"
          >
            <span class="sort-option-label">{{ opt.label }}</span>
            <el-icon v-if="sortField === opt.value" class="sort-option-arrow">
              <CaretTop v-if="sortOrder === 'asc'" />
              <CaretBottom v-else />
            </el-icon>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <div class="toolbar-spacer"></div>

    <el-button :disabled="scriptsCount === 0" @click="emit('toggle-select-all')">
      <el-icon><Select /></el-icon>
      &nbsp;{{ isAllSelected ? '取消全选' : '全选' }}
    </el-button>

    <el-button
      type="primary"
      :loading="extracting"
      :icon="MagicStick"
      @click="emit('extract')"
    >
      批量提取资产
    </el-button>

    <el-button
      :disabled="selectedCount === 0"
      :loading="exporting"
      @click="emit('export')"
    >
      <el-icon><Download /></el-icon>
      &nbsp;导出剧本{{ selectedCount ? ` (${selectedCount})` : '' }}
    </el-button>

    <el-button
      :disabled="selectedCount === 0"
      type="danger"
      @click="emit('batch-delete')"
    >
      <el-icon><Delete /></el-icon>
      &nbsp;批量删除{{ selectedCount ? ` (${selectedCount})` : '' }}
    </el-button>
  </section>
</template>

<script setup lang="ts">
import {
  CaretBottom,
  CaretTop,
  Delete,
  Download,
  MagicStick,
  Search,
  Select,
  Sort,
} from '@element-plus/icons-vue'
import type { SortField, SortOption, SortOrder } from './types'

defineProps<{
  searchKeyword: string
  scriptsCount: number
  selectedCount: number
  isAllSelected: boolean
  extracting: boolean
  exporting: boolean
  sortOptions: SortOption[]
  sortField: SortField
  sortOrder: SortOrder
  currentSortLabel: string
}>()

const emit = defineEmits<{
  (e: 'update:searchKeyword', value: string): void
  (e: 'sort', value: SortField): void
  (e: 'toggle-select-all'): void
  (e: 'extract'): void
  (e: 'export'): void
  (e: 'batch-delete'): void
}>()

const onSearchInput = (value: string | number) => {
  emit('update:searchKeyword', String(value))
}

const onSortCommand = (command: string | number | object) => {
  if (typeof command === 'string') {
    emit('sort', command as SortField)
  }
}
</script>