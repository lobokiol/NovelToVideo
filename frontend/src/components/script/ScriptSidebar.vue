<template>
  <aside class="sidebar">
    <div class="side-top">
      <div class="brand" @click="emit('project')">AF</div>

      <el-tooltip content="项目" placement="right">
        <button class="nav-btn" aria-label="项目" @click="emit('project')">
          <el-icon><Folder /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="剧本" placement="right">
        <button class="nav-btn active" aria-label="剧本">
          <el-icon><Tickets /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="制作" placement="right">
        <button class="nav-btn" aria-label="制作" @click="emit('production')">
          <el-icon><Film /></el-icon>
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
        <button class="nav-btn" aria-label="文档" @click="emit('coming-soon')">
          <el-icon><Document /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="设置" placement="right">
        <button class="nav-btn" aria-label="设置" @click="emit('settings')">
          <el-icon><Setting /></el-icon>
        </button>
      </el-tooltip>

      <el-tooltip content="代码仓库" placement="right">
        <button class="nav-btn" aria-label="代码仓库" @click="emit('coming-soon')">
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
  Film,
  Folder,
  List,
  Setting,
  Tickets,
} from '@element-plus/icons-vue'

const emit = defineEmits<{
  (e: 'project'): void
  (e: 'production'): void
  (e: 'tasks'): void
  (e: 'settings'): void
  (e: 'coming-soon'): void
}>()
</script>