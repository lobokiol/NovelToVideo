<template>
  <header class="assistant-header">
    <div class="assistant-heading">
      <span class="assistant-status-dot"></span>
      <div>
        <h2>剧本创作助理</h2>
        <p>{{ connectedModelId }}</p>
      </div>
    </div>
    <span class="assistant-message-count">{{ messageCount }} 条</span>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  connectedModelId: string
  messageCount: number
}>()
</script>

<style scoped>
.assistant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 50px;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.01)),
    rgba(9, 14, 22, 0.86);
}

.assistant-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.assistant-status-dot {
  position: relative;
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow:
    0 0 0 4px rgba(34, 197, 94, 0.12),
    0 0 18px rgba(34, 197, 94, 0.32);
}

.assistant-heading h2 {
  margin: 0;
  color: #f2f4f8;
  font-size: 16px;
  line-height: 1.25;
  font-weight: 750;
}

.assistant-heading p {
  margin: 3px 0 0;
  color: #7e8893;
  font-size: 12px;
  line-height: 1.35;
}

.assistant-message-count {
  flex-shrink: 0;
  min-width: 54px;
  padding: 5px 9px;
  border-radius: 999px;
  color: #93c5fd;
  border: 1px solid rgba(96, 165, 250, 0.22);
  background: rgba(37, 99, 235, 0.12);
  text-align: center;
  font-size: 12px;
  font-weight: 700;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}
</style>
