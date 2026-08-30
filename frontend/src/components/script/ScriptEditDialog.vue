<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="min(1080px, calc(100vw - 32px))"
    destroy-on-close
    append-to-body
    class="script-dark-dialog"
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      class="script-form"
      label-position="top"
    >
      <el-form-item label="剧本名称" prop="name">
        <el-input
          v-model="form.name"
          placeholder="如：青云 EP01：青云初入"
          maxlength="120"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="剧本正文" prop="content">
        <MarkdownEditor
          v-model="form.content"
          placeholder="支持 Markdown 语法，可粘贴完整分集剧本结构"
          height="520px"
        />
      </el-form-item>

      <el-form-item label="关联资产" prop="relatedAssetIds">
        <el-select
          v-model="form.relatedAssetIds"
          class="script-asset-select"
          multiple
          collapse-tags
          collapse-tags-tooltip
          filterable
          popper-class="script-dark-select"
          placeholder="选择关联的角色 / 场景 / 道具 / 镜头"
        >
          <el-option-group
            v-for="group in groupedAssetOptions"
            :key="group.type"
            :label="`${assetTypeLabel(group.type)}（${group.items.length}）`"
          >
            <el-option
              v-for="asset in group.items"
              :key="asset.publicId"
              :label="asset.name"
              :value="asset.publicId"
            >
              <div
                class="asset-option"
                :title="asset.summary ? `${asset.name}：${asset.summary}` : asset.name"
              >
                <span class="asset-option__name">{{ asset.name }}</span>
                <span v-if="asset.summary" class="asset-option__desc">{{ asset.summary }}</span>
              </div>
            </el-option>
          </el-option-group>
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import MarkdownEditor from '@/components/MarkdownEditor.vue'
import type { AssetType, ScriptAsset, ScriptEditForm } from './types'

const props = defineProps<{
  modelValue: boolean
  title: string
  form: ScriptEditForm
  rules: FormRules<ScriptEditForm>
  submitting: boolean
  groupedAssetOptions: { type: AssetType; items: ScriptAsset[] }[]
  assetTypeLabel: (type: AssetType) => string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'submit'): void
}>()

const formRef = ref<FormInstance>()

const onSubmit = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (valid) emit('submit')
}

const clearValidate = () => {
  formRef.value?.clearValidate()
}

defineExpose({ clearValidate })
</script>
