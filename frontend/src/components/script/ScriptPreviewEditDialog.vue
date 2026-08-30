<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑剧本"
    width="min(1080px, calc(100vw - 32px))"
    destroy-on-close
    append-to-body
    class="script-dark-dialog script-preview-edit-dialog"
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <el-form
      :model="draft"
      class="script-form"
      label-position="top"
    >
      <el-form-item label="剧本名称">
        <el-input
          v-model="draft.name"
          placeholder="剧本名称"
          maxlength="120"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="剧本正文">
        <MarkdownEditor
          v-model="draft.content"
          placeholder="支持 Markdown 语法，可粘贴完整分集剧本结构"
          height="520px"
        />
      </el-form-item>

      <div v-if="draft.detail" class="preview-edit__meta">
        来源：{{ draft.detail }} · 字数 {{ draft.content.length }}
      </div>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="emit('save')">保存修改</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import MarkdownEditor from '@/components/MarkdownEditor.vue'
import type { PreviewEditDraft } from './types'

defineProps<{
  modelValue: boolean
  draft: PreviewEditDraft
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'save'): void
}>()
</script>
