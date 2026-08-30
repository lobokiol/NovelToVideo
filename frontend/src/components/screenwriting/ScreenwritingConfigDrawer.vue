<template>
  <transition name="config-drawer-slide">
    <section v-if="modelValue" class="config-drawer" aria-label="初始化创作配置">
      <header class="config-drawer__header">
        <div class="config-drawer__title">
          <strong>创作配置设置</strong>
        </div>
        <button type="button" class="config-drawer__close" aria-label="收起" @click="close">
          <el-icon><ArrowDownBold /></el-icon>
        </button>
      </header>

      <p class="config-drawer__tip">
        填写本次创作的基础设定，保存后立即生效并锁定；之后 AI 只读不写、严格遵循，需修改可在此重新保存。
      </p>

      <div class="config-drawer__grid">
        <label class="config-field">
          <span class="config-field__label">总集数</span>
          <el-input-number
            v-model="form.totalEpisodes"
            :min="1"
            :max="999"
            controls-position="right"
            class="config-field__control"
          />
        </label>
        <label class="config-field">
          <span class="config-field__label">单集时长（分钟）</span>
          <el-input-number
            v-model="form.episodeDuration"
            :min="1"
            :max="180"
            controls-position="right"
            class="config-field__control"
          />
        </label>
        <div class="config-field config-field--full">
          <span class="config-field__label">原著范围（章）</span>
          <div class="config-range">
            <el-input-number v-model="form.sourceStart" :min="1" controls-position="right" placeholder="起始章" />
            <span class="config-range__sep">—</span>
            <el-input-number v-model="form.sourceEnd" :min="1" controls-position="right" placeholder="结束章" />
          </div>
        </div>
        <label class="config-field config-field--full">
          <span class="config-field__label">平台规格</span>
          <el-select
            v-model="form.platformSpec"
            placeholder="选择平台规格"
            class="config-field__control"
            popper-class="config-select-dropdown"
          >
            <el-option v-for="option in PLATFORM_OPTIONS" :key="option" :label="option" :value="option" />
          </el-select>
        </label>
        <label class="config-field config-field--full">
          <span class="config-field__label">风格定位</span>
          <el-input
            v-model="form.style"
            placeholder="从项目提取或自定义，例如：复仇爽剧、古装甜宠"
            class="config-field__control"
          />
        </label>
        <label class="config-field config-field--full">
          <span class="config-field__label">付费策略</span>
          <el-input
            v-model="form.paywall"
            placeholder="例如：前3集免费，第4集起设置付费点"
            class="config-field__control"
          />
        </label>
      </div>

      <footer class="config-drawer__footer">
        <span class="config-drawer__hint">保存后立即生效并锁定，AI 将严格遵循</span>
        <div class="config-drawer__actions">
          <el-button class="config-btn--ghost" @click="close">取消</el-button>
          <el-button
            class="config-btn--primary"
            type="primary"
            :loading="submitting"
            @click="submit"
          >
            保存创作设置
          </el-button>
        </div>
      </footer>
    </section>
  </transition>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { ArrowDownBold } from '@element-plus/icons-vue'
import type { ScreenwritingConfigDraft } from '@/api/screenwriting'

const props = defineProps<{
  modelValue: boolean
  initial?: ScreenwritingConfigDraft
  submitting?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [draft: ScreenwritingConfigDraft]
}>()

const PLATFORM_OPTIONS = ['9:16竖屏短剧优先', '16:9横屏', '其他']
// 风格定位、付费策略的默认建议值：新建时预填，用户可直接删除或重写。
const DEFAULT_STYLE = '由故事骨架阶段结合小说事件细化，可指定爽剧、甜宠、复仇等方向'
const DEFAULT_PAYWALL = '前3集免费，第4集起设置付费点，可按平台策略调整'

const form = reactive<{
  totalEpisodes: number | undefined
  episodeDuration: number | undefined
  sourceStart: number | undefined
  sourceEnd: number | undefined
  platformSpec: string
  style: string
  paywall: string
}>({
  totalEpisodes: undefined,
  episodeDuration: undefined,
  sourceStart: undefined,
  sourceEnd: undefined,
  platformSpec: '',
  style: '',
  paywall: '',
})

const applyInitial = (initial?: ScreenwritingConfigDraft) => {
  form.totalEpisodes = initial?.totalEpisodes ?? undefined
  form.episodeDuration = initial?.episodeDuration ?? undefined
  form.sourceStart = initial?.sourceStart ?? undefined
  form.sourceEnd = initial?.sourceEnd ?? undefined
  form.platformSpec = initial?.platformSpec ?? ''
  // 已设过的项目配置优先回填；为空时用默认建议值，用户可删除重写。
  form.style = initial?.style ?? DEFAULT_STYLE
  form.paywall = initial?.paywall ?? DEFAULT_PAYWALL
}

// 每次打开时用最新初值回填（自动上拉或手动展开都生效）。
watch(
  () => props.modelValue,
  (visible) => {
    if (visible) applyInitial(props.initial)
  },
  { immediate: true },
)

const close = () => emit('update:modelValue', false)

const submit = () => {
  emit('submit', {
    totalEpisodes: form.totalEpisodes ?? null,
    episodeDuration: form.episodeDuration ?? null,
    sourceStart: form.sourceStart ?? null,
    sourceEnd: form.sourceEnd ?? null,
    platformSpec: form.platformSpec || null,
    style: form.style || null,
    paywall: form.paywall || null,
  })
}
</script>

<style scoped>
.config-drawer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 6;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 82%;
  overflow-y: auto;
  padding: 14px 16px 16px;
  border-top: 1px solid rgba(96, 165, 250, 0.28);
  border-radius: 16px 16px 18px 18px;
  background:
    radial-gradient(circle at 18% 0%, rgba(37, 99, 235, 0.16), transparent 36%),
    linear-gradient(180deg, rgba(15, 22, 32, 0.98), rgba(8, 12, 18, 0.99));
  box-shadow: 0 -18px 44px rgba(0, 0, 0, 0.5);
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.3) transparent;
}

.config-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.config-drawer__title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #f2f4f8;
  font-size: 15px;
  font-weight: 750;
}

.config-drawer__badge {
  padding: 1px 8px;
  border-radius: 999px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.18);
  font-size: 11px;
  font-weight: 700;
}

.config-drawer__close {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #9fb3c8;
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
}

.config-drawer__close:hover {
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.4);
  background: rgba(37, 99, 235, 0.14);
}

.config-drawer__tip {
  margin: 0;
  color: #9fb3c8;
  font-size: 12px;
  line-height: 1.6;
}

.config-drawer__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 14px;
}

.config-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.config-field--full {
  grid-column: 1 / -1;
}

.config-field__label {
  color: #c9d1d9;
  font-size: 12px;
  font-weight: 650;
}

.config-field__control {
  width: 100%;
}

.config-range {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-range__sep {
  color: #6e7681;
}

.config-drawer__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 2px;
}

.config-drawer__hint {
  color: #6e7681;
  font-size: 12px;
}

.config-drawer__actions {
  display: flex;
  gap: 10px;
}

.config-btn--ghost.el-button {
  height: 34px;
  padding: 0 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #c9d1d9;
  background: rgba(255, 255, 255, 0.04);
  box-shadow: none;
}

.config-btn--ghost.el-button:hover {
  color: #f2f4f8;
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.1);
}

.config-btn--primary.el-button {
  height: 34px;
  padding: 0 18px;
  border: none;
  border-radius: 10px;
  font-weight: 700;
  background: #2563eb;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
}

.config-btn--primary.el-button:hover {
  background: #1d4ed8;
}

.config-drawer :deep(.el-input__wrapper) {
  background-color: rgba(8, 12, 18, 0.6);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
}

.config-drawer :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.2) inset;
}

.config-drawer :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.55) inset;
}

.config-drawer :deep(.el-input__inner) {
  color: #e6edf3;
}

.config-drawer :deep(.el-input__inner::placeholder) {
  color: #6e7681;
}

.config-drawer :deep(.el-input-number) {
  width: 100%;
}

.config-drawer :deep(.el-input-number__decrease),
.config-drawer :deep(.el-input-number__increase) {
  background-color: rgba(255, 255, 255, 0.04);
  color: #9fb3c8;
  border-color: rgba(255, 255, 255, 0.1);
}

.config-drawer :deep(.el-input-number__decrease:hover),
.config-drawer :deep(.el-input-number__increase:hover) {
  color: #dbeafe;
}

.config-drawer :deep(.el-select__wrapper) {
  background-color: rgba(8, 12, 18, 0.6);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
}

.config-drawer :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.2) inset;
}

.config-drawer :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.55) inset;
}

.config-drawer :deep(.el-select__placeholder) {
  color: #6e7681;
}

.config-drawer :deep(.el-select__selected-item) {
  color: #e6edf3;
}

.config-drawer-slide-enter-active,
.config-drawer-slide-leave-active {
  transition: transform 0.26s ease, opacity 0.26s ease;
}

.config-drawer-slide-enter-from,
.config-drawer-slide-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>

<style>
/* 平台规格下拉 teleport 到 body，需全局选择器覆盖为暗色，与抽屉风格一致。 */
.config-select-dropdown.el-select-dropdown {
  background: #0c1015;
  border-color: rgba(255, 255, 255, 0.1);
}

.config-select-dropdown .el-select-dropdown__item {
  color: #c9d1d9;
}

.config-select-dropdown .el-select-dropdown__item.is-hovering,
.config-select-dropdown .el-select-dropdown__item:hover {
  background: rgba(37, 99, 235, 0.18);
  color: #dbeafe;
}

.config-select-dropdown .el-select-dropdown__item.is-selected {
  color: #93c5fd;
  font-weight: 700;
}

.config-select-dropdown .el-popper__arrow::before {
  background: #0c1015 !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
}
</style>