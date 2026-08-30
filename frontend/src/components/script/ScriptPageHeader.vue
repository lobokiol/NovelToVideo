<template>
  <header class="page-header">
    <div class="page-header__left">
      <h1 class="title">我的剧本</h1>
      <p class="desc">管理项目剧本素材库、关联资产与短剧分镜原型</p>
    </div>

    <div class="page-header__right">
      <el-button class="header-action" size="large" @click="emit('back-screenwriting')">
        <el-icon><Back /></el-icon>
        &nbsp;返回剧本创作
      </el-button>

      <el-button class="header-action" size="large" @click="emit('import')">
        <el-icon><Upload /></el-icon>
        &nbsp;导入剧本
      </el-button>

      <el-button class="primary-button" type="primary" size="large" @click="emit('create')">
        <el-icon><Plus /></el-icon>
        &nbsp;新建剧本
      </el-button>

      <el-button class="header-action" size="large" @click="emit('assets')">
        <el-icon><Collection /></el-icon>
        &nbsp;资产管理
      </el-button>

      <el-button class="header-action" size="large" @click="emit('production')">
        <el-icon><Film /></el-icon>
        &nbsp;进入生产工作台
      </el-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Back, Collection, Film, Plus, Upload } from '@element-plus/icons-vue'

const emit = defineEmits<{
  (e: 'back-screenwriting'): void
  (e: 'import'): void
  (e: 'create'): void
  (e: 'production'): void
  (e: 'assets'): void
}>()
</script>