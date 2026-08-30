<template>
  <span class="tag" :class="status">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TaskJobStatus, TaskItemStatus } from '@/api/task'

const props = defineProps<{ status: TaskJobStatus | TaskItemStatus }>()

const LABELS: Record<string, string> = {
  pending: '排队中',
  running: '运行中',
  paused: '已暂停',
  succeeded: '已完成',
  partial_failed: '部分失败',
  failed: '失败',
  canceled: '已取消',
}

const label = computed(() => LABELS[props.status] ?? props.status)
</script>

<style scoped>
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.14);
  border: 1px solid rgba(37, 99, 235, 0.3);
  white-space: nowrap;
}

.tag.running {
  color: #86efac;
  background: rgba(34, 197, 94, 0.14);
  border-color: rgba(34, 197, 94, 0.3);
}

.tag.succeeded {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.14);
  border-color: rgba(37, 99, 235, 0.3);
}

.tag.failed,
.tag.partial_failed {
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.14);
  border-color: rgba(248, 113, 113, 0.3);
}

.tag.canceled {
  color: #9ca3af;
  background: rgba(148, 163, 184, 0.14);
  border-color: rgba(148, 163, 184, 0.3);
}

.tag.pending {
  color: #fcd34d;
  background: rgba(234, 179, 8, 0.14);
  border-color: rgba(234, 179, 8, 0.3);
}

.tag.paused {
  color: #c4b5fd;
  background: rgba(139, 92, 246, 0.14);
  border-color: rgba(139, 92, 246, 0.3);
}
</style>
