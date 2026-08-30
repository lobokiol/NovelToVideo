<template>
  <header class="page-header">
    <div class="page-header__left">
      <h1 class="title">剧本创作</h1>
      <p class="desc">基于小说事件，与 AI Agent 协作完成故事骨架、改编策略与剧本</p>
    </div>

    <div class="page-header__right">
      <el-button class="header-action" size="large" @click="emit('back-novel')">
        <el-icon><Reading /></el-icon>
        &nbsp;返回小说
      </el-button>

      <el-button class="header-action stage-button" size="large" @click="emit('script-manage')">
        <el-icon><Document /></el-icon>
        &nbsp;剧本管理
      </el-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Document, Reading } from '@element-plus/icons-vue'

const emit = defineEmits<{
  'back-novel': []
  'script-manage': []
}>()
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
  flex-shrink: 0;
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

.header-action {
  height: 38px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #c5cdd6;
  background-color: rgba(255, 255, 255, 0.04);
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.header-action :deep(.el-icon) {
  margin-right: 0;
  font-size: 16px;
}

.header-action:hover,
.header-action:focus {
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.18);
  background-color: rgba(255, 255, 255, 0.08);
  transform: translateY(-1px);
}

.stage-button {
  border-color: rgba(96, 165, 250, 0.28);
  color: #bfdbfe;
  background-color: rgba(37, 99, 235, 0.12);
}

.stage-button:hover,
.stage-button:focus {
  color: #ffffff;
  border-color: rgba(147, 197, 253, 0.42);
  background-color: rgba(37, 99, 235, 0.2);
}

@media (max-width: 920px) {
  .page-header,
  .page-header__right {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
