<template>
  <aside class="sidebar">
    <div class="side-top">
      <div class="brand" @click="emit('project')">AF</div>

      <el-tooltip content="项目" placement="right">
        <button class="nav-btn" aria-label="项目" @click="emit('project')">
          <el-icon><Folder /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="小说" placement="right">
        <button class="nav-btn" aria-label="小说" @click="emit('novel')">
          <el-icon><Reading /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="剧本创作" placement="right">
        <button class="nav-btn active" aria-label="剧本创作">
          <el-icon><EditPen /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="任务" placement="right">
        <button class="nav-btn" aria-label="任务" @click="emit('tasks')">
          <el-icon><List /></el-icon>
        </button>
      </el-tooltip>
    </div>

    <div class="side-bottom">
      <el-tooltip content="文档" placement="right">
        <button class="nav-btn" aria-label="文档" @click="emit('documents')">
          <el-icon><Document /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="设置" placement="right">
        <button class="nav-btn" aria-label="设置" @click="emit('settings')">
          <el-icon><Setting /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="代码仓库" placement="right">
        <button class="nav-btn" aria-label="代码仓库" @click="emit('repository')">
          <el-icon><Connection /></el-icon>
        </button>
      </el-tooltip>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {
  Connection,
  Document,
  EditPen,
  Folder,
  List,
  Reading,
  Setting,
} from '@element-plus/icons-vue'

const emit = defineEmits<{
  project: []
  novel: []
  tasks: []
  documents: []
  settings: []
  repository: []
}>()
</script>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.side-top,
.side-bottom {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.brand {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: #0a0a0a;
  font-size: 20px;
  font-weight: 800;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, #f3d96b, #c4b5fd);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 6px 18px rgba(243, 217, 107, 0.18);
  transition: transform 0.2s ease;
}

.brand:hover {
  transform: translateY(-1px);
}

.nav-btn {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 16px;
  color: #8b949e;
  background: transparent;
  cursor: pointer;
  font-size: 22px;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.nav-btn :deep(.el-icon) {
  font-size: 22px;
}

.nav-btn:hover {
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.05);
  transform: translateY(-1px);
}

.nav-btn.active {
  color: #dbeafe;
  border-color: rgba(37, 99, 235, 0.32);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.22), rgba(37, 99, 235, 0.12));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

@media (max-width: 920px) {
  .sidebar {
    flex-direction: row;
    padding: 12px 14px;
  }

  .side-top,
  .side-bottom {
    width: auto;
    flex-direction: row;
    gap: 10px;
  }
}
</style>
