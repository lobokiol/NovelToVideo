<template>
  <el-select
    :model-value="modelValue"
    class="model-group-select"
    popper-class="model-group-select-popper"
    :clearable="clearable"
    filterable
    :loading="loading"
    :placeholder="placeholder"
    @update:model-value="onUpdate"
    @change="onChange"
  >
    <el-option v-if="groups.length === 0" disabled :label="emptyLabel" value="" />
    <el-option-group
      v-for="group in groups"
      :key="group.key"
      :label="group.platform"
    >
      <el-option
        v-for="item in group.models"
        :key="`${group.key}:${item.value}`"
        :label="item.label"
        :value="item.value"
      >
        <span class="model-option">
          <span class="model-option__main">
            <img v-if="group.icon" class="model-option__icon" :src="group.icon" :alt="group.platform" />
            <span v-else class="model-option__fallback">{{ group.platform.slice(0, 1).toUpperCase() }}</span>
            <span class="model-option__name">{{ item.label }}</span>
          </span>
          <span class="model-option__category">{{ item.category }}</span>
        </span>
      </el-option>
    </el-option-group>
  </el-select>
</template>

<script setup lang="ts">
import type { ProviderModelGroup } from '@/composables/useProviderModels'

withDefaults(defineProps<{
  modelValue: string
  groups: ProviderModelGroup[]
  loading?: boolean
  clearable?: boolean
  placeholder?: string
  emptyLabel?: string
}>(), {
  loading: false,
  clearable: false,
  placeholder: '选择模型',
  emptyLabel: '暂无可用模型',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
}>()

const toModelId = (value: unknown) => (typeof value === 'string' ? value : '')

const onUpdate = (value: unknown) => {
  emit('update:modelValue', toModelId(value))
}

const onChange = (value: unknown) => {
  emit('change', toModelId(value))
}
</script>

<!-- 下拉面板挂载于 body，样式需全局生效 -->
<style>
.model-group-select-popper.el-popper {
  background-color: #14181f;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #e6edf3;
}

.model-group-select-popper .el-select-group__title {
  color: #8b949e;
}

.model-group-select-popper .el-select-dropdown__item {
  height: 38px;
  line-height: 38px;
  padding: 0 12px;
  color: #c5cdd6;
}

.model-group-select-popper .el-select-dropdown__item.is-hovering,
.model-group-select-popper .el-select-dropdown__item:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.06);
}

.model-group-select-popper .el-select-dropdown__item.is-selected {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.16);
}

.model-group-select-popper .el-popper__arrow::before {
  background: #14181f;
  border-color: rgba(255, 255, 255, 0.08);
}

.model-group-select-popper .model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.model-group-select-popper .model-option__main {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.model-group-select-popper .model-option__icon {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.18);
}

.model-group-select-popper .model-option__fallback {
  width: 24px;
  height: 24px;
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  border-radius: 8px;
  color: #dbeafe;
  font-size: 11px;
  font-weight: 700;
  background: rgba(37, 99, 235, 0.18);
  border: 1px solid rgba(147, 197, 253, 0.28);
}

.model-group-select-popper .model-option__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: inherit;
}

.model-group-select-popper .model-option__category {
  margin-left: auto;
  text-align: right;
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.14);
  border: 1px solid rgba(37, 99, 235, 0.3);
  line-height: 1.6;
}
</style>
