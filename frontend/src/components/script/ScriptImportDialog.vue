<template>
  <el-dialog
    :model-value="modelValue"
    title="导入剧本"
    width="min(1180px, calc(100vw - 48px))"
    destroy-on-close
    append-to-body
    class="script-dark-dialog script-import-dialog"
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
    @close="emit('close')"
  >
    <el-steps :active="importStep - 1" finish-status="success" align-center class="import-steps">
      <el-step title="输入内容" />
      <el-step title="预览剧本" />
    </el-steps>

    <div v-show="importStep === 1" class="import-step">
      <el-radio-group
        :model-value="importMode"
        class="import-mode"
        @update:model-value="(value: string | number | boolean) => emit('update:importMode', value === 'split' ? 'split' : 'bulk')"
      >
        <el-radio-button value="bulk">按文件批量导入</el-radio-button>
        <el-radio-button value="split">单文件 / 粘贴 + 切分规则</el-radio-button>
      </el-radio-group>
      <p class="import-mode__hint">
        <span v-if="importMode === 'bulk'">每个上传的文件视为一份剧本，文件名作为剧本名</span>
        <span v-else>从单份文件或粘贴内容中按标题正则切分多份剧本</span>
      </p>

      <template v-if="importMode === 'bulk'">
        <el-upload
          class="import-uploader"
          drag
          multiple
          :auto-upload="false"
          :show-file-list="false"
          :on-change="(file: UploadFile) => emit('bulk-file-change', file)"
          accept=".txt,.md,.markdown,.docx,.pdf"
        >
          <el-icon class="import-uploader__icon"><UploadFilled /></el-icon>
          <div class="import-uploader__text">
            <strong>点击或拖拽多份剧本文件到此处</strong>
            <span>支持 .md / .txt（自动识别 UTF-8 / GBK） · .docx · .pdf，单文件 ≤ 10 MB</span>
          </div>
        </el-upload>

        <div v-if="bulkParsed.length > 0" class="import-bulk">
          <header class="import-bulk__head">
            <h4 class="import-bulk__title">已就绪的剧本</h4>
            <span class="import-bulk__count">共 {{ bulkParsed.length }} 份 · 拖拽调整顺序</span>
          </header>
          <ul class="import-bulk__list">
            <li
              v-for="(item, idx) in bulkParsed"
              :key="item.key"
              class="import-bulk__item"
              :class="{
                'is-dragging': bulkDragIndex === idx,
                'is-drop-before': bulkDropIndex === idx && bulkDropPosition === 'before',
                'is-drop-after': bulkDropIndex === idx && bulkDropPosition === 'after',
              }"
              draggable="true"
              @dragstart="(event: DragEvent) => emit('bulk-drag-start', event, idx)"
              @dragover.prevent="(event: DragEvent) => emit('bulk-drag-over', event, idx)"
              @dragleave="emit('bulk-drag-leave', idx)"
              @drop.prevent="emit('bulk-drop', idx)"
              @dragend="emit('bulk-drag-end')"
            >
              <div class="import-bulk__main">
                <span class="import-bulk__handle" aria-label="拖拽排序">
                  <el-icon><Rank /></el-icon>
                </span>
                <span class="import-bulk__seq">{{ idx + 1 }}</span>
                <div class="import-bulk__info">
                  <span class="import-bulk__name" :title="item.name">{{ item.name }}</span>
                  <span class="import-bulk__meta">{{ item.detail }} · {{ item.content.length }} 字符</span>
                </div>
              </div>
              <el-button link type="danger" size="small" @click="emit('remove-bulk-item', idx)">移除</el-button>
            </li>
          </ul>
        </div>
      </template>

      <template v-if="importMode === 'split'">
        <el-upload
          class="import-uploader"
          drag
          :auto-upload="false"
          :show-file-list="false"
          :on-change="(file: UploadFile) => emit('split-file-change', file)"
          accept=".txt,.md,.markdown,.docx,.pdf"
        >
          <el-icon class="import-uploader__icon"><UploadFilled /></el-icon>
          <div class="import-uploader__text">
            <strong>点击或拖拽单份文件到此处</strong>
            <span>支持 .md / .txt（自动识别 UTF-8 / GBK） · .docx · .pdf，单文件 ≤ 10 MB</span>
          </div>
          <div v-if="importFileName" class="import-uploader__file">
            已选择：{{ importFileName }}
          </div>
        </el-upload>

        <el-divider class="import-divider">或直接粘贴剧本内容</el-divider>

        <el-input
          :model-value="importRaw"
          type="textarea"
          :rows="10"
          placeholder="粘贴剧本全文。系统按预设规则识别一级 / 二级标题、EP 编号、第 N 集等切分多份剧本。"
          @update:model-value="(value: string | number) => emit('update:importRaw', String(value))"
        />

        <div class="import-meta">
          <span>字符数：<strong>{{ importRaw.length }}</strong></span>
          <span>识别剧本：<strong>{{ splitParsed.length }}</strong></span>
          <span
            v-if="importRaw.length > 0 && splitParsed.length === 0"
            class="import-meta__warn"
          >未识别到剧本，请在下方调整切分规则</span>
        </div>

        <section class="import-split">
          <header class="import-split__head">
            <div>
              <h4 class="import-split__title">剧本切分规则</h4>
              <p class="import-split__hint">选择预设后可直接修改下方正则与匹配方式；上方"识别剧本"计数与下一步预览实时刷新。</p>
            </div>
          </header>

          <div class="import-split__main">
            <el-select
              :model-value="splitPresetKey"
              class="import-split__select"
              popper-class="script-dark-select"
              @update:model-value="(value: string | number | boolean) => emit('update:splitPresetKey', String(value))"
            >
              <el-option
                v-for="preset in splitPresets"
                :key="preset.key"
                :label="preset.label"
                :value="preset.key"
              >
                <div class="import-split__opt">
                  <span class="import-split__opt-label">{{ preset.label }}</span>
                  <span class="import-split__opt-desc">{{ preset.description }}</span>
                </div>
              </el-option>
            </el-select>

            <div class="import-split__editor">
              <div class="import-split__row">
                <label class="import-split__row-label">剧本</label>
                <el-input
                  :model-value="currentSplitRule.titlePattern"
                  size="small"
                  placeholder="剧本标题正则（必填）"
                  class="import-split__row-pattern"
                  @update:model-value="(value: string | number) => emit('update-title-pattern', String(value))"
                />
                <el-select
                  :model-value="currentSplitRule.titleFlagsList"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  size="small"
                  placeholder="匹配方式"
                  popper-class="script-dark-select"
                  class="import-split__row-flags"
                  @update:model-value="(value: string[]) => emit('update-title-flags', value)"
                >
                  <el-option
                    v-for="opt in flagOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </div>
            </div>
          </div>
        </section>
      </template>
    </div>

    <div v-show="importStep === 2" class="import-step">
      <div class="import-preview__head">
        共识别 <strong>{{ importParsed.length }}</strong> 份剧本，已选
        <strong>{{ importSelectedCount }}</strong> 份入库
      </div>

      <el-table
        ref="importTableRef"
        :data="importParsed"
        class="script-import-table"
        height="420"
        row-key="key"
        :tooltip-options="{ effect: 'dark', popperClass: 'script-cell-tooltip' }"
        @selection-change="(rows: ImportScriptDraft[]) => emit('selection-change', rows)"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="#" type="index" width="60" />
        <el-table-column prop="name" label="剧本名称" min-width="280" show-overflow-tooltip />
        <el-table-column prop="detail" label="来源" width="180" show-overflow-tooltip />
        <el-table-column label="字数" width="100">
          <template #default="{ row }">
            <span class="row-count">{{ row.content.length }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="96" align="center">
          <template #default="{ row, $index }">
            <el-button
              link
              type="primary"
              class="row-edit-btn"
              @click="emit('preview-edit', row, $index)"
            >
              <el-icon><EditPen /></el-icon>
              <span>编辑</span>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <template #footer>
      <el-button v-if="importStep === 2" @click="emit('update:importStep', 1)">上一步</el-button>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        v-if="importStep === 1"
        type="primary"
        @click="emit('next')"
      >下一步</el-button>
      <el-button
        v-if="importStep === 2"
        type="primary"
        :loading="importSubmitting"
        :disabled="importSelectedCount === 0"
        @click="emit('submit')"
      >确认导入 ({{ importSelectedCount }})</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { EditPen, Rank, UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import type { ImportScriptDraft, ImportSplitPreset } from './types'

defineProps<{
  modelValue: boolean
  importStep: 1 | 2
  importMode: 'bulk' | 'split'
  importRaw: string
  importFileName: string
  bulkParsed: ImportScriptDraft[]
  bulkDragIndex: number | null
  bulkDropIndex: number | null
  bulkDropPosition: 'before' | 'after' | null
  splitParsed: ImportScriptDraft[]
  splitPresets: ImportSplitPreset[]
  splitPresetKey: string
  currentSplitRule: ImportSplitPreset
  flagOptions: { value: string; label: string }[]
  importParsed: ImportScriptDraft[]
  importSelectedCount: number
  importSubmitting: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'update:importStep', value: 1 | 2): void
  (e: 'update:importMode', value: 'bulk' | 'split'): void
  (e: 'update:importRaw', value: string): void
  (e: 'update:splitPresetKey', value: string): void
  (e: 'update-title-pattern', value: string): void
  (e: 'update-title-flags', value: string[]): void
  (e: 'bulk-file-change', file: UploadFile): void
  (e: 'split-file-change', file: UploadFile): void
  (e: 'bulk-drag-start', event: DragEvent, index: number): void
  (e: 'bulk-drag-over', event: DragEvent, index: number): void
  (e: 'bulk-drag-leave', index: number): void
  (e: 'bulk-drop', index: number): void
  (e: 'bulk-drag-end'): void
  (e: 'remove-bulk-item', index: number): void
  (e: 'selection-change', rows: ImportScriptDraft[]): void
  (e: 'preview-edit', row: ImportScriptDraft, index: number): void
  (e: 'next'): void
  (e: 'submit'): void
  (e: 'close'): void
}>()

const importTableRef = ref()

const toggleAllSelection = () => {
  importTableRef.value?.toggleAllSelection?.()
}

const toggleRowSelection = (row: ImportScriptDraft, selected = true) => {
  importTableRef.value?.toggleRowSelection?.(row, selected)
}

defineExpose({ toggleAllSelection, toggleRowSelection })
</script>
