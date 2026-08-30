<template>
  <div class="asset-prompt-wrap">
    <div
      ref="editorEl"
      class="asset-prompt-editor"
      contenteditable="true"
      :data-placeholder="placeholder"
      spellcheck="false"
      @input="onInput"
      @blur="onBlur"
      @keydown="onKeydown"
      @paste.prevent="onPaste"
      @click="updateMentionState"
    ></div>

    <!-- @ 触发的资产选择弹层：跟随光标位置，↑↓ 选择、Enter 确认、Esc 关闭。 -->
    <div
      v-if="mention.open && filteredAssets.length > 0"
      class="mention-menu"
      :style="{ left: `${mention.left}px`, top: `${mention.top}px` }"
    >
      <button
        v-for="(asset, index) in filteredAssets"
        :key="asset.publicId"
        type="button"
        class="mention-menu__item"
        :class="{ 'is-active': index === mention.activeIndex }"
        @mousedown.prevent="pickAsset(asset)"
        @mousemove="mention.activeIndex = index"
      >
        <img v-if="asset.thumbnailUrl" :src="asset.thumbnailUrl" alt="" draggable="false" />
        <span v-else class="mention-menu__thumb-empty">无图</span>
        <span class="mention-menu__name">{{ asset.name }}</span>
      </button>
    </div>

    <!-- 悬停芯片时的大图预览。 -->
    <div
      v-if="hoverPreview.url"
      class="chip-hover-preview"
      :style="{ left: `${hoverPreview.left}px`, top: `${hoverPreview.top}px` }"
    >
      <img :src="hoverPreview.url" alt="" draggable="false" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

export interface AssetPromptAsset {
  publicId: string
  name: string
  thumbnailUrl: string
}

const props = defineProps<{
  modelValue: string
  /** 可引用资产名单：文本中的 @资产名 命中后渲染为内嵌图片芯片。 */
  assets: AssetPromptAsset[]
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const editorEl = ref<HTMLElement | null>(null)
/** 最近一次由本组件 emit 的值：watch 时据此区分外部赋值与内部输入回流。 */
let lastEmitted: string | null = null

const assetByName = computed(() => {
  const map = new Map<string, AssetPromptAsset>()
  for (const asset of props.assets) {
    const name = asset.name.trim()
    if (name) map.set(name, asset)
  }
  return map
})

// 与后端 _MENTION_RE 保持一致：@资产名 到空白或常见标点为止。
const MENTION_RE = /@([^\s@，。；、！？…,;.!?()（）【】[\]{}<>：:"'`]{1,60})/g
/** mention 查询词的终止字符集（与 MENTION_RE 排除集一致）。 */
const MENTION_STOP_RE = /[\s@，。；、！？…,;.!?()（）【】[\]{}<>：:"'`]/

// ---------------------------------------------------------------------------
// 悬停大图预览
// ---------------------------------------------------------------------------

const hoverPreview = reactive({ url: '', left: 0, top: 0 })

const showChipPreview = (chip: HTMLElement) => {
  const url = chip.dataset.previewUrl || ''
  const wrap = editorEl.value?.parentElement
  if (!url || !wrap) return
  const wrapRect = wrap.getBoundingClientRect()
  const chipRect = chip.getBoundingClientRect()
  hoverPreview.url = url
  hoverPreview.left = chipRect.left - wrapRect.left
  hoverPreview.top = chipRect.top - wrapRect.top - 128
}

const hideChipPreview = () => {
  hoverPreview.url = ''
}

// ---------------------------------------------------------------------------
// 渲染与序列化：@资产名 ↔ 内嵌芯片
// ---------------------------------------------------------------------------

/** 构造资产芯片（不可编辑原子块：缩略图 + 名称；悬停显示大图，Backspace 整块删除）。 */
const buildChip = (asset: AssetPromptAsset): HTMLElement => {
  const chip = document.createElement('span')
  chip.className = 'asset-prompt-chip'
  chip.contentEditable = 'false'
  chip.dataset.assetName = asset.name
  chip.dataset.previewUrl = asset.thumbnailUrl
  if (asset.thumbnailUrl) {
    const img = document.createElement('img')
    img.src = asset.thumbnailUrl
    img.alt = ''
    img.draggable = false
    chip.appendChild(img)
  }
  const label = document.createElement('span')
  label.className = 'asset-prompt-chip__name'
  label.textContent = asset.name
  chip.appendChild(label)
  chip.addEventListener('mouseenter', () => showChipPreview(chip))
  chip.addEventListener('mouseleave', hideChipPreview)
  return chip
}

/** 把提示词文本渲染进编辑器：命中资产名单的 @名 转为芯片，其余保持纯文本。 */
const render = (text: string) => {
  const el = editorEl.value
  if (!el) return
  el.textContent = ''
  const pattern = new RegExp(MENTION_RE.source, 'g')
  let cursor = 0
  let match = pattern.exec(text)
  while (match) {
    const asset = assetByName.value.get(match[1].trim())
    if (asset) {
      if (match.index > cursor) el.appendChild(document.createTextNode(text.slice(cursor, match.index)))
      el.appendChild(buildChip(asset))
      cursor = match.index + match[0].length
    }
    match = pattern.exec(text)
  }
  if (cursor < text.length) el.appendChild(document.createTextNode(text.slice(cursor)))
}

/** DOM → 提示词文本：芯片序列化回 @资产名，与后端提示词协议一致。 */
const serialize = (): string => {
  const el = editorEl.value
  if (!el) return ''
  let result = ''
  el.childNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      result += node.textContent ?? ''
      return
    }
    if (node instanceof HTMLElement && node.classList.contains('asset-prompt-chip')) {
      result += `@${node.dataset.assetName ?? ''}`
      return
    }
    // 粘贴/输入法偶发包裹元素时兜底取纯文本。
    result += node.textContent ?? ''
  })
  return result
}

const emitCurrent = () => {
  const value = serialize()
  lastEmitted = value
  emit('update:modelValue', value)
}

// ---------------------------------------------------------------------------
// @ 触发的 mention 弹层
// ---------------------------------------------------------------------------

interface MentionState {
  open: boolean
  query: string
  activeIndex: number
  left: number
  top: number
  /** 正在输入 mention 的文本节点与 @ 起始位置、光标位置。 */
  node: Text | null
  atOffset: number
  caretOffset: number
}

const mention = reactive<MentionState>({
  open: false,
  query: '',
  activeIndex: 0,
  left: 0,
  top: 0,
  node: null,
  atOffset: 0,
  caretOffset: 0,
})

const closeMention = () => {
  mention.open = false
  mention.node = null
  mention.query = ''
}

const filteredAssets = computed(() => {
  const query = mention.query.trim().toLowerCase()
  const list = props.assets.filter((asset) => asset.name)
  const matched = query
    ? list.filter((asset) => asset.name.toLowerCase().includes(query))
    : list
  return matched.slice(0, 8)
})

/** 检测光标是否处于「@查询词」输入中：命中则打开弹层并定位到光标处。 */
const updateMentionState = () => {
  const el = editorEl.value
  const selection = window.getSelection()
  if (!el || !selection || selection.rangeCount === 0 || !selection.isCollapsed) {
    closeMention()
    return
  }
  const range = selection.getRangeAt(0)
  const node = range.startContainer
  if (!(node instanceof Text) || !el.contains(node)) {
    closeMention()
    return
  }
  const textBefore = (node.textContent ?? '').slice(0, range.startOffset)
  const atIndex = textBefore.lastIndexOf('@')
  if (atIndex === -1) {
    closeMention()
    return
  }
  const query = textBefore.slice(atIndex + 1)
  if (query.length > 30 || MENTION_STOP_RE.test(query)) {
    closeMention()
    return
  }
  const wrap = el.parentElement
  if (!wrap) return
  const caretRect = range.getBoundingClientRect()
  const wrapRect = wrap.getBoundingClientRect()
  mention.open = true
  mention.query = query
  mention.activeIndex = 0
  mention.left = Math.max(0, Math.min(caretRect.left - wrapRect.left, wrapRect.width - 240))
  mention.top = caretRect.bottom - wrapRect.top + 4
  mention.node = node
  mention.atOffset = atIndex
  mention.caretOffset = range.startOffset
}

/** 选定资产：删除「@查询词」，在原位插入芯片与后随空格，光标落在空格后。 */
const pickAsset = (asset: AssetPromptAsset) => {
  const node = mention.node
  const el = editorEl.value
  if (!node || !el) {
    closeMention()
    return
  }
  const range = document.createRange()
  range.setStart(node, mention.atOffset)
  range.setEnd(node, Math.min(mention.caretOffset, node.length))
  range.deleteContents()
  const chip = buildChip(asset)
  range.insertNode(chip)
  const space = document.createTextNode(' ')
  chip.after(space)
  const selection = window.getSelection()
  if (selection) {
    const caret = document.createRange()
    caret.setStart(space, 1)
    caret.collapse(true)
    selection.removeAllRanges()
    selection.addRange(caret)
  }
  closeMention()
  emitCurrent()
}

// ---------------------------------------------------------------------------
// 事件
// ---------------------------------------------------------------------------

const onInput = () => {
  emitCurrent()
  updateMentionState()
}

const onKeydown = (event: KeyboardEvent) => {
  if (mention.open && filteredAssets.value.length > 0) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      mention.activeIndex = (mention.activeIndex + 1) % filteredAssets.value.length
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      mention.activeIndex =
        (mention.activeIndex - 1 + filteredAssets.value.length) % filteredAssets.value.length
      return
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault()
      pickAsset(filteredAssets.value[mention.activeIndex])
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      closeMention()
      return
    }
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    document.execCommand('insertText', false, '\n')
  }
}

/** 失焦时把手动键入的完整 @资产名 收敛为芯片（此刻无光标，安全重渲染）。 */
const onBlur = () => {
  // 延迟关闭，保证弹层 mousedown 选择先于 blur 生效。
  window.setTimeout(closeMention, 120)
  const value = serialize()
  render(value)
  lastEmitted = value
  emit('update:modelValue', value)
}

const onPaste = (event: ClipboardEvent) => {
  const text = event.clipboardData?.getData('text/plain') ?? ''
  if (text) document.execCommand('insertText', false, text)
}

watch(
  () => props.modelValue,
  (value) => {
    if (value === lastEmitted) return
    render(value)
    lastEmitted = value
  },
)

// 资产名单异步加载完成后重渲染，让已有 @名 立即芯片化。
watch(assetByName, () => {
  render(props.modelValue)
  lastEmitted = props.modelValue
})

onMounted(() => {
  render(props.modelValue)
  lastEmitted = props.modelValue
})
</script>

<style scoped>
.asset-prompt-wrap {
  position: relative;
}

.asset-prompt-editor {
  min-height: 200px;
  max-height: 340px;
  overflow-y: auto;
  padding: 8px 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: rgba(13, 17, 23, 0.8);
  color: #e6edf3;
  font-size: 13px;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-word;
  outline: none;
  transition: border-color 0.15s ease;
}

.asset-prompt-editor:focus {
  border-color: rgba(96, 165, 250, 0.6);
}

.asset-prompt-editor:empty::before {
  content: attr(data-placeholder);
  color: #6e7681;
  pointer-events: none;
}

/* 芯片为动态注入节点，scoped 需 :deep 命中。 */
.asset-prompt-editor :deep(.asset-prompt-chip) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0 2px;
  padding: 1px 7px 1px 2px;
  border: 1px solid rgba(52, 211, 153, 0.45);
  border-radius: 6px;
  background: rgba(16, 185, 129, 0.16);
  color: #6ee7b7;
  font-size: 12px;
  line-height: 20px;
  vertical-align: middle;
  user-select: none;
  white-space: nowrap;
  cursor: default;
}

.asset-prompt-editor :deep(.asset-prompt-chip img) {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  object-fit: cover;
}

.mention-menu {
  position: absolute;
  z-index: 30;
  min-width: 200px;
  max-width: 260px;
  padding: 4px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: #161b22;
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.5);
}

.mention-menu__item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #e6edf3;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.mention-menu__item.is-active {
  background: rgba(37, 99, 235, 0.25);
}

.mention-menu__item img,
.mention-menu__thumb-empty {
  width: 26px;
  height: 26px;
  border-radius: 5px;
  object-fit: cover;
  flex-shrink: 0;
}

.mention-menu__thumb-empty {
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.06);
  color: #6e7681;
  font-size: 10px;
}

.mention-menu__name {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chip-hover-preview {
  position: absolute;
  z-index: 31;
  pointer-events: none;
  padding: 4px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: #0d1117;
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.55);
}

.chip-hover-preview img {
  display: block;
  width: 116px;
  height: 116px;
  border-radius: 6px;
  object-fit: cover;
}
</style>