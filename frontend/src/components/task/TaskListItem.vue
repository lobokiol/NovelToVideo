<template>
  <div class="item" :class="{ active }">
    <div class="row1">
      <span class="name" :title="job.name">{{ job.name }}</span>
      <TaskStatusTag :status="job.status" />
    </div>
    <div class="queue" :title="queueName">
      <span class="queue-label">队列</span>
      <span class="queue-name">{{ queueName }}</span>
    </div>
    <div class="progress" :title="`${percent}%`">
      <div class="bar" :style="{ width: percent + '%' }" />
    </div>
    <div class="row3">
      <span class="count">{{ doneCount }}/{{ job.totalCount }}</span>
      <span class="meta">{{ relativeTime }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TaskJobResponse } from '@/api/task'
import TaskStatusTag from './TaskStatusTag.vue'

const props = defineProps<{ job: TaskJobResponse; active: boolean }>()

const doneCount = computed(
  () => props.job.succeededCount + props.job.failedCount + props.job.canceledCount,
)

const percent = computed(() => {
  if (!props.job.totalCount) return 0
  return Math.min(100, Math.round((doneCount.value / props.job.totalCount) * 100))
})

const queueName = computed(() => props.job.providerKey?.trim() || '—')

const relativeTime = computed(() => {
  const raw = props.job.updatedAt
  if (!raw) return ''
  const t = new Date(raw).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Math.max(0, Math.floor((Date.now() - t) / 1000))
  if (diff < 60) return `${diff} 秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
})
</script>

<style scoped>
.item {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.item:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.16);
  transform: translateY(-1px);
}

.item.active {
  border-color: rgba(96, 165, 250, 0.85);
  background: rgba(37, 99, 235, 0.08);
  box-shadow:
    0 0 0 1px rgba(96, 165, 250, 0.5),
    0 0 0 4px rgba(37, 99, 235, 0.18),
    0 22px 44px rgba(37, 99, 235, 0.32);
}

.row1 {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.name {
  color: #e6edf3;
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex: 1;
}

.queue {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: #93c5fd;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 11px;
}

.queue-label {
  flex: 0 0 auto;
  color: #6e7681;
}

.queue-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress {
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: hidden;
}

.bar {
  height: 100%;
  background: linear-gradient(90deg, #2563eb, #60a5fa);
  transition: width 0.3s ease;
}

.row3 {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
}

.count {
  color: #cbd5e1;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.meta {
  color: #8b949e;
}
</style>
