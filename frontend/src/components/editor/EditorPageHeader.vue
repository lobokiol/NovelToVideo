<template>
  <header class="page-header">
    <div class="page-header__left">
      <h1 class="title">在线剪辑台</h1>
      <p class="desc">
        <template v-if="projectName">项目「{{ projectName }}」多轨粗剪与浏览器合成导出</template>
        <template v-else>正在加载项目信息…</template>
        <span v-if="saveStateLabel" class="save-state">{{ saveStateLabel }}</span>
      </p>
    </div>

    <div class="page-header__right">
      <el-button class="header-action" size="large" @click="emit('back')">
        <el-icon><Back /></el-icon>
        返回制作
      </el-button>
      <el-button class="header-action" size="large" :loading="libraryLoading" @click="emit('refresh')">
        <el-icon><Refresh /></el-icon>
        刷新素材
      </el-button>
      <el-button class="header-action" size="large" :loading="saving" @click="emit('save')">
        <el-icon><Check /></el-icon>
        保存工程
      </el-button>
      <el-dropdown
        split-button
        type="primary"
        size="large"
        class="export-button"
        popper-class="editor-dark-popper"
        :disabled="exporting || !canExport"
        @click="emit('export-full')"
        @command="onExportCommand"
      >
        {{ exporting ? `导出中 ${exportProgress}` : '导出完整视频' }}
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="selection" :disabled="!canExportSelection">
              导出选中片段
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Back, Check, Refresh } from '@element-plus/icons-vue'

defineProps<{
  projectName: string
  saveStateLabel: string
  libraryLoading: boolean
  saving: boolean
  exporting: boolean
  exportProgress: string
  canExport: boolean
  canExportSelection: boolean
}>()

const emit = defineEmits<{
  (e: 'back'): void
  (e: 'refresh'): void
  (e: 'save'): void
  (e: 'export-full'): void
  (e: 'export-selection'): void
}>()

const onExportCommand = (command: string | number | object) => {
  if (String(command) === 'selection') emit('export-selection')
}
</script>

<style scoped>
/* 页头视觉与制作工作台等页面的 page-header 规范保持一致。 */
.page-header {
  display: flex;
  flex-shrink: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.page-header__left {
  min-width: 0;
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

.save-state {
  margin-left: 10px;
  color: #6e7681;
}

.header-action {
  height: 38px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 10px;
  color: #c5cdd6;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 14px;
  font-weight: 500;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.header-action :deep(.el-icon) {
  font-size: 16px;
}

.header-action:hover,
.header-action:focus {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  transform: translateY(-1px);
}

.header-action:active {
  transform: translateY(0);
}

.export-button :deep(.el-button) {
  border: none;
  height: 38px;
}

.export-button :deep(.el-button.is-disabled) {
  background: rgba(37, 99, 235, 0.32);
  color: rgba(230, 237, 243, 0.55);
}
</style>