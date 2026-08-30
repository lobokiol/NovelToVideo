<template>
  <section
    v-loading="loading"
    class="script-grid"
    element-loading-background="rgba(13, 17, 23, 0.55)"
  >
    <el-empty
      v-if="!loading && filteredCount === 0"
      class="empty-state"
      description="该项目暂无剧本，点击右上角新建"
    />

    <article
      v-for="script in scripts"
      :key="script.id"
      class="script-card"
      :class="{ 'is-selected': selectedIds.includes(script.id) }"
      @click="emit('open-edit', script)"
    >
      <header class="card-header">
        <div class="card-title-wrap">
          <h3 class="card-title" :title="script.name">{{ script.name }}</h3>
          <el-icon
            v-if="script.isLocked"
            class="card-lock-badge"
            title="已锁定：从创作工作台同步时不会覆盖本集"
          >
            <Lock />
          </el-icon>
        </div>
        <el-checkbox
          :model-value="selectedIds.includes(script.id)"
          class="card-checkbox"
          @click.stop
          @change="(value: unknown) => emit('toggle-select', script.id, !!value)"
        />
      </header>

      <p class="card-preview" :title="script.intro">{{ script.intro }}</p>

      <div class="card-assets">
        <span
          v-for="asset in script.relatedAssets"
          :key="asset.publicId"
          class="asset-chip"
          :class="`asset-chip--${asset.assetType}`"
          :title="asset.summary"
        >
          <span class="asset-chip__name">{{ asset.name }}</span>
        </span>
        <span v-if="script.relatedAssets.length === 0" class="asset-empty">
          尚未提取资产
        </span>
      </div>

      <footer class="card-footer">
        <span
          class="status-chip"
          :class="statusClass(script.extractState)"
          :title="script.extractState === -1 && script.errorReason ? script.errorReason : ''"
        >
          <span class="status-dot"></span>
          {{ statusText(script.extractState) }}
        </span>
        <div class="card-actions" @click.stop>
          <button
            class="card-action-btn"
            :class="{ 'is-locked': script.isLocked }"
            :aria-label="script.isLocked ? '解锁本集' : '锁定本集'"
            :title="script.isLocked ? '解锁本集' : '锁定本集（同步时不覆盖本集）'"
            @click.stop="emit('toggle-lock', script)"
          >
            <el-icon>
              <Lock v-if="script.isLocked" />
              <Unlock v-else />
            </el-icon>
          </button>
          <el-button
            class="card-action-btn"
            link
            :loading="extractingSingle[script.id]"
            :icon="MagicStick"
            :title="extractingSingle[script.id] ? '资产抽取中...' : '从本集剧本抽取资产'"
            @click.stop="emit('extract-single', script)"
          />
          <el-dropdown
            trigger="click"
            placement="bottom-end"
            popper-class="script-card-menu"
            @command="(cmd: string | number) => emit('card-command', String(cmd), script)"
          >
            <button class="card-action-btn" aria-label="更多操作" @click.stop>
              <el-icon><MoreFilled /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">
                  <el-icon><EditPen /></el-icon>编辑本集
                </el-dropdown-item>
                <el-dropdown-item command="delete">
                  <el-icon><Delete /></el-icon>删除本集
                </el-dropdown-item>
                <el-dropdown-item command="rename-plan" divided>
                  <el-icon><EditPen /></el-icon>重命名所属剧本
                </el-dropdown-item>
                <el-dropdown-item command="delete-plan">
                  <el-icon><Delete /></el-icon>删除整部剧本
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </footer>
    </article>
  </section>

  <div v-if="filteredCount > 0" class="pagination-wrap">
    <el-pagination
      :current-page="currentPage"
      :page-size="pageSize"
      :total="filteredCount"
      layout="prev, pager, next, total"
      background
      @update:current-page="(value: number) => emit('update:currentPage', value)"
    />
  </div>
</template>

<script setup lang="ts">
import {
  Delete,
  EditPen,
  Lock,
  MagicStick,
  MoreFilled,
  Unlock,
} from '@element-plus/icons-vue'
import type { ExtractState, ScriptRecord } from './types'

defineProps<{
  loading: boolean
  filteredCount: number
  scripts: ScriptRecord[]
  selectedIds: string[]
  currentPage: number
  pageSize: number
  extractingSingle: Record<string, boolean>
}>()

const emit = defineEmits<{
  (e: 'open-edit', script: ScriptRecord): void
  (e: 'toggle-select', id: string, checked: boolean): void
  (e: 'toggle-lock', script: ScriptRecord): void
  (e: 'extract-single', script: ScriptRecord): void
  (e: 'card-command', command: string, script: ScriptRecord): void
  (e: 'update:currentPage', value: number): void
}>()

const STATUS_LABELS: Record<ExtractState, string> = {
  [-1]: '提取失败',
  0: '待提取',
  1: '提取中',
  2: '已提取',
}

const STATUS_CLASS: Record<ExtractState, string> = {
  [-1]: 'is-failed',
  0: 'is-pending',
  1: 'is-extracting',
  2: 'is-completed',
}

const statusText = (state: ExtractState) => STATUS_LABELS[state]
const statusClass = (state: ExtractState) => STATUS_CLASS[state]
</script>
