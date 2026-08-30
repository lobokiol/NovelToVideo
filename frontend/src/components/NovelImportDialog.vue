<template>
  <el-dialog
    :model-value="modelValue"
    title="全文导入"
    width="1230px"
    destroy-on-close
    class="novel-dark-dialog novel-import-dialog"
    @update:model-value="(val: boolean) => emit('update:modelValue', val)"
    @close="resetImportState"
  >
    <el-steps :active="importStep - 1" finish-status="success" align-center class="import-steps">
      <el-step title="输入内容" />
      <el-step title="预览章节" />
    </el-steps>

    <div v-show="importStep === 1" class="import-step">
      <el-upload
        class="import-uploader"
        drag
        :auto-upload="false"
        :show-file-list="false"
        :on-change="handleImportFile"
        accept=".txt,.docx,.pdf,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      >
        <el-icon class="import-uploader__icon"><UploadFilled /></el-icon>
        <div class="import-uploader__text">
          <strong>点击或拖拽文件到此处</strong>
          <span>支持 .txt（自动识别 UTF-8 / GBK） · .docx · .pdf，单文件 ≤ 10 MB</span>
        </div>
        <div v-if="importFileName" class="import-uploader__file">
          已选择：{{ importFileName }}
        </div>
      </el-upload>

      <el-divider class="import-divider">或直接粘贴小说全文</el-divider>

      <el-input
        v-model="importRaw"
        type="textarea"
        :rows="12"
        placeholder="粘贴小说全文。系统按 “第X章 / 第X回 / 第X节” 自动切分章节，按 “第X卷” 自动归类卷次。"
      />

      <div class="import-meta">
        <span>字符数：<strong>{{ importRaw.length }}</strong></span>
        <span>识别章节：<strong>{{ importParsed.length }}</strong></span>
        <span
          v-if="importRaw.length > 0 && importParsed.length === 0"
          class="import-meta__warn"
        >未识别到章节，请在下方调整切分规则</span>
      </div>

      <section class="import-split">
        <header class="import-split__head">
          <div>
            <h4 class="import-split__title">章节切分规则</h4>
            <p class="import-split__hint">选择预设后可直接修改下方正则与匹配方式；上方“识别章节”计数与下一步预览实时刷新。</p>
          </div>
          <el-button size="small" disabled>AI 分割（开发中）</el-button>
        </header>

        <div class="import-split__main">
          <el-select
            v-model="importSplitKey"
            class="import-split__select"
            :loading="importSplitRulesLoading"
            popper-class="novel-dark-select"
          >
            <el-option
              v-for="preset in importSplitPresets"
              :key="preset.key"
              :label="preset.label"
              :value="preset.key"
            >
              <div class="import-split__opt">
                <span class="import-split__opt-label">{{ preset.label }}</span>
                <span class="import-split__opt-desc">{{ preset.description }}</span>
              </div>
            </el-option>
          </el-select>

          <div class="import-split__editor">
            <div class="import-split__row">
              <label class="import-split__row-label">章节</label>
              <el-input
                v-model="currentSplitRule.chapterPattern"
                size="small"
                placeholder="章节正则（必填）"
                class="import-split__row-pattern"
              />
              <el-select
                v-model="currentSplitRule.chapterFlagsList"
                multiple
                collapse-tags
                collapse-tags-tooltip
                size="small"
                placeholder="匹配方式"
                popper-class="novel-dark-select"
                class="import-split__row-flags"
              >
                <el-option
                  v-for="opt in FLAG_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </div>

            <div class="import-split__row">
              <label class="import-split__row-label">卷次</label>
              <el-input
                v-model="currentSplitRule.reelPattern"
                size="small"
                placeholder="卷次正则（可选）"
                class="import-split__row-pattern"
              />
              <el-select
                v-model="currentSplitRule.reelFlagsList"
                multiple
                collapse-tags
                collapse-tags-tooltip
                size="small"
                placeholder="匹配方式"
                popper-class="novel-dark-select"
                class="import-split__row-flags"
              >
                <el-option
                  v-for="opt in FLAG_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </div>
          </div>
        </div>
      </section>

      <section class="import-filter">
        <header class="import-filter__head">
          <div>
            <h4 class="import-filter__title">内容过滤</h4>
            <p class="import-filter__hint">勾选规则后点击「应用过滤」，可叠加执行多次。「恢复原文」回到最近一次过滤前。</p>
          </div>
          <div class="import-filter__actions">
            <el-button size="small" disabled>AI 过滤（开发中）</el-button>
            <el-button size="small" @click="restoreImportOriginal">恢复原文</el-button>
            <el-button size="small" type="primary" @click="applyImportFilter">应用过滤</el-button>
          </div>
        </header>

        <ul class="import-filter__list">
          <li
            v-for="rule in importFilterRules"
            :key="rule.id"
            class="import-filter__item"
          >
            <el-checkbox v-model="rule.enabled" class="import-filter__check">
              <div class="import-filter__item-info">
                <span class="import-filter__item-name">{{ rule.name }}</span>
                <code
                  class="import-filter__item-regex"
                  :title="`/${rule.pattern}/${rule.flags}`"
                >/{{ rule.pattern }}/{{ rule.flags }}</code>
              </div>
            </el-checkbox>
            <el-tag v-if="rule.builtin" size="small" effect="plain" class="import-filter__badge">内置</el-tag>
            <el-button
              v-else
              link
              type="danger"
              size="small"
              @click="removeFilterRule(rule.id)"
            >移除</el-button>
          </li>
        </ul>

        <div class="import-filter__custom">
          <el-input
            v-model="customRuleName"
            size="small"
            placeholder="规则名称（可选）"
            class="import-filter__custom-input import-filter__custom-input--name"
          />
          <el-input
            v-model="customRulePattern"
            size="small"
            placeholder="匹配正则（必填）"
            class="import-filter__custom-input import-filter__custom-input--pattern"
          />
          <el-select
            v-model="customRuleFlagsList"
            multiple
            collapse-tags
            collapse-tags-tooltip
            size="small"
            placeholder="匹配方式"
            popper-class="novel-dark-select"
            class="import-filter__custom-input import-filter__custom-input--flags"
          >
            <el-option
              v-for="opt in FLAG_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-input
            v-model="customRuleReplacement"
            size="small"
            placeholder="替换为（默认空）"
            class="import-filter__custom-input import-filter__custom-input--repl"
          />
          <el-button size="small" type="primary" plain @click="addCustomFilterRule">
            <el-icon><Plus /></el-icon>
            添加自定义规则
          </el-button>
        </div>
      </section>
    </div>

    <div v-show="importStep === 2" class="import-step">
      <div class="import-preview__head">
        共识别 <strong>{{ importParsed.length }}</strong> 章，已选 <strong>{{ importSelectedRows.length }}</strong> 章入库
      </div>

      <el-table
        ref="importTableRef"
        :data="importParsed"
        class="novel-table import-preview__table"
        height="420"
        row-key="key"
        :tooltip-options="{ effect: 'dark', popperClass: 'novel-cell-tooltip' }"
        @selection-change="onImportSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="#" type="index" width="60" />
        <el-table-column prop="reel" label="卷次" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.reel">{{ row.reel }}</span>
            <span v-else class="text-muted">未分卷</span>
          </template>
        </el-table-column>
        <el-table-column prop="chapter" label="章节标题" min-width="200">
          <template #default="{ row }">
            <el-popover
              trigger="click"
              placement="top"
              popper-class="novel-chapter-preview-popper"
              :width="560"
              :teleported="true"
            >
              <template #reference>
                <button
                  type="button"
                  class="import-preview__chapter-title"
                  :class="{ 'is-warning': hasChapterLengthWarning(row) }"
                  :aria-label="getChapterPreviewAriaLabel(row)"
                  :title="getChapterLengthWarning(row) || undefined"
                >
                  <el-icon
                    v-if="hasChapterLengthWarning(row)"
                    class="import-preview__chapter-warning"
                    aria-hidden="true"
                  >
                    <WarningFilled />
                  </el-icon>
                  <span class="import-preview__chapter-text">{{ row.chapter }}</span>
                </button>
              </template>

              <article class="chapter-preview-tip">
                <header class="chapter-preview-tip__head">
                  <strong>{{ row.chapter }}</strong>
                  <span>{{ row.chapterData.length }} 字</span>
                </header>
                <div class="chapter-preview-tip__body">
                  {{ row.chapterData || '本章暂无正文' }}
                </div>
              </article>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column label="字数" width="100">
          <template #default="{ row }">
            <span class="row-count">{{ row.chapterData.length }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <template #footer>
      <el-button v-if="importStep === 2" @click="importStep = 1">上一步</el-button>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        v-if="importStep === 1"
        type="primary"
        @click="goImportNext"
      >下一步</el-button>
      <el-button
        v-if="importStep === 2"
        type="primary"
        :loading="importSubmitting"
        :disabled="importSelectedRows.length === 0"
        @click="submitImport"
      >确认导入 ({{ importSelectedRows.length }})</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, UploadFilled, WarningFilled } from '@element-plus/icons-vue'
import {
  listNovelImportSplitRulesApi,
  type NovelImportSplitRule,
} from '@/api/novel'

export interface ImportChapterDraft {
  key: number
  reel: string
  chapter: string
  chapterData: string
}

const props = defineProps<{
  modelValue: boolean
  projectPublicId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'submit', drafts: ImportChapterDraft[]): void
}>()

const importStep = ref<1 | 2>(1)
const importRaw = ref('')
const importFileName = ref('')
const importTableRef = ref()
const importSelectedRows = ref<ImportChapterDraft[]>([])
const importSubmitting = ref(false)
const CHAPTER_SHORT_WARNING_LENGTH = 1000
const CHAPTER_LONG_WARNING_LENGTH = 20000

// 预览解析辅助正则；内置切分规则由服务端返回。
const CJK_NUMBER_PATTERN = '0-9一二三四五六七八九十百千万零〇两'
const TITLE_NUMBER_PATTERN = `[${CJK_NUMBER_PATTERN}]+(?:\\s*[~～\\-—至]\\s*[${CJK_NUMBER_PATTERN}]+)?`
const REEL_PREFIX_PATTERN = `第\\s*[${CJK_NUMBER_PATTERN}]+\\s*[卷部集册]`
const INLINE_REEL_CHAPTER_REGEX = new RegExp(
  `^\\s*(${REEL_PREFIX_PATTERN})\\s*(第\\s*${TITLE_NUMBER_PATTERN}\\s*[章回节][^\\n\\r]*)$`,
)
const BARE_NUMBER_TITLE_REGEX = new RegExp(`^\\s*([${CJK_NUMBER_PATTERN}]+)\\s+([^\\n\\r]{1,80})\\s*$`)
const BARE_NUMBER_ONLY_REGEX = new RegExp(`^\\s*([${CJK_NUMBER_PATTERN}]+)\\s*$`)
const TITLE_END_PUNCTUATION_REGEX = /[。！？；，、.,;!?]$/

interface ImportSplitPreset {
  key: string
  label: string
  description: string
  chapterPattern: string
  chapterFlagsList: string[]
  reelPattern: string
  reelFlagsList: string[]
  builtin?: boolean
}

const CUSTOM_SPLIT_RULE_KEY = 'custom'
const CUSTOM_SPLIT_RULE_STORAGE_KEY = 'novel-import-custom-split-rule'

const createEmptyCustomSplitRule = (): ImportSplitPreset => ({
  key: CUSTOM_SPLIT_RULE_KEY,
  label: '自定义正则',
  description: '手动指定章节 / 卷次的匹配正则',
  chapterPattern: '',
  chapterFlagsList: [],
  reelPattern: '',
  reelFlagsList: [],
  builtin: false,
})

const hasSplitRuleContent = (rule: ImportSplitPreset) => (
  Boolean(rule.chapterPattern.trim() || rule.reelPattern.trim())
)

const normalizeFlags = (value: unknown) => (
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
)

const readCustomSplitRule = (): ImportSplitPreset => {
  const fallback = createEmptyCustomSplitRule()
  try {
    const raw = localStorage.getItem(CUSTOM_SPLIT_RULE_STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<ImportSplitPreset>
    return {
      ...fallback,
      label: parsed.label?.trim() || fallback.label,
      description: parsed.description?.trim() || fallback.description,
      chapterPattern: parsed.chapterPattern || '',
      chapterFlagsList: normalizeFlags(parsed.chapterFlagsList),
      reelPattern: parsed.reelPattern || '',
      reelFlagsList: normalizeFlags(parsed.reelFlagsList),
    }
  } catch {
    return fallback
  }
}

const writeCustomSplitRule = (rule: ImportSplitPreset) => {
  try {
    if (!hasSplitRuleContent(rule)) {
      localStorage.removeItem(CUSTOM_SPLIT_RULE_STORAGE_KEY)
      return
    }
    localStorage.setItem(
      CUSTOM_SPLIT_RULE_STORAGE_KEY,
      JSON.stringify({
        key: CUSTOM_SPLIT_RULE_KEY,
        label: rule.label,
        description: rule.description,
        chapterPattern: rule.chapterPattern,
        chapterFlagsList: rule.chapterFlagsList,
        reelPattern: rule.reelPattern,
        reelFlagsList: rule.reelFlagsList,
        builtin: false,
      }),
    )
  } catch {
    ElMessage.warning('自定义切分规则保存失败，请检查浏览器存储权限')
  }
}

const toImportSplitPreset = (rule: NovelImportSplitRule): ImportSplitPreset => ({
  key: rule.key,
  label: rule.label,
  description: rule.description,
  chapterPattern: rule.chapterPattern,
  chapterFlagsList: normalizeFlags(rule.chapterFlagsList),
  reelPattern: rule.reelPattern,
  reelFlagsList: normalizeFlags(rule.reelFlagsList),
  builtin: rule.builtin,
})

const appendCustomSplitRule = (rules: ImportSplitPreset[]) => [
  ...rules.filter((rule) => rule.key !== CUSTOM_SPLIT_RULE_KEY),
  readCustomSplitRule(),
]

const importSplitPresets = ref<ImportSplitPreset[]>(appendCustomSplitRule([]))

const importSplitKey = ref<string>(CUSTOM_SPLIT_RULE_KEY)
const importSplitRulesLoading = ref(false)

const currentSplitRule = computed<ImportSplitPreset>(() => {
  return (
    importSplitPresets.value.find((p) => p.key === importSplitKey.value) ||
    importSplitPresets.value[0] ||
    createEmptyCustomSplitRule()
  )
})

const requestErrorMessage = (error: unknown) => {
  const maybeError = error as { response?: { data?: { detail?: string } }; message?: string }
  return maybeError.response?.data?.detail || maybeError.message || '未知错误'
}

const fetchImportSplitRules = async () => {
  const projectPublicId = props.projectPublicId.trim()
  if (!projectPublicId) {
    importSplitPresets.value = appendCustomSplitRule([])
    importSplitKey.value = CUSTOM_SPLIT_RULE_KEY
    return
  }
  importSplitRulesLoading.value = true
  try {
    const { data } = await listNovelImportSplitRulesApi(projectPublicId)
    const nextRules = appendCustomSplitRule(data.map(toImportSplitPreset))
    importSplitPresets.value = nextRules
    const selectedRule = nextRules.find((rule) => rule.key === importSplitKey.value)
    if (
      !selectedRule ||
      (selectedRule.key === CUSTOM_SPLIT_RULE_KEY && !hasSplitRuleContent(selectedRule))
    ) {
      importSplitKey.value = nextRules.find((rule) => rule.key !== CUSTOM_SPLIT_RULE_KEY)?.key || CUSTOM_SPLIT_RULE_KEY
    }
  } catch (error) {
    importSplitPresets.value = appendCustomSplitRule([])
    importSplitKey.value = importSplitPresets.value[0]?.key || CUSTOM_SPLIT_RULE_KEY
    ElMessage.error(`读取章节切分规则失败：${requestErrorMessage(error)}`)
  } finally {
    importSplitRulesLoading.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) void fetchImportSplitRules()
  },
)

watch(
  () => props.projectPublicId,
  () => {
    if (props.modelValue) void fetchImportSplitRules()
  },
)

watch(
  importSplitPresets,
  (rules) => {
    const customRule = rules.find((rule) => rule.key === CUSTOM_SPLIT_RULE_KEY)
    if (customRule) writeCustomSplitRule(customRule)
  },
  { deep: true },
)

const testRegex = (regex: RegExp, line: string) => {
  regex.lastIndex = 0
  return regex.test(line)
}

const normalizeHeading = (value: string) => value.replace(/\s+/g, ' ').trim()

const looksLikeHeadingMetadata = (line: string) => (
  line.length <= 100 &&
  line.includes('作者') &&
  line.includes('第') &&
  /[章节回]/.test(line)
)

const looksLikeShortTitle = (line: string) => (
  line.length > 0 &&
  line.length <= 80 &&
  !TITLE_END_PUNCTUATION_REGEX.test(line)
)

const splitInlineReelChapter = (line: string) => {
  INLINE_REEL_CHAPTER_REGEX.lastIndex = 0
  const match = INLINE_REEL_CHAPTER_REGEX.exec(line)
  if (!match) return null
  return {
    reel: normalizeHeading(match[1]),
    chapter: normalizeHeading(match[2]),
  }
}

const splitBareNumberChapter = (
  line: string,
  nextLine: string | undefined,
  chapterRegex: RegExp,
  reelRegex: RegExp | null,
) => {
  BARE_NUMBER_TITLE_REGEX.lastIndex = 0
  const inlineMatch = BARE_NUMBER_TITLE_REGEX.exec(line)
  if (inlineMatch) {
    const title = inlineMatch[2].trim()
    if (looksLikeShortTitle(title)) {
      return { chapter: normalizeHeading(`${inlineMatch[1]} ${title}`), consumed: 1 }
    }
  }

  BARE_NUMBER_ONLY_REGEX.lastIndex = 0
  const numberMatch = BARE_NUMBER_ONLY_REGEX.exec(line)
  if (!numberMatch || !nextLine) return null
  const title = nextLine.trim()
  if (!looksLikeShortTitle(title)) return null
  BARE_NUMBER_ONLY_REGEX.lastIndex = 0
  if (
    BARE_NUMBER_ONLY_REGEX.test(title) ||
    looksLikeHeadingMetadata(title) ||
    splitInlineReelChapter(title) ||
    testRegex(chapterRegex, title) ||
    (reelRegex && testRegex(reelRegex, title))
  ) {
    return null
  }
  return { chapter: normalizeHeading(`${numberMatch[1]} ${title}`), consumed: 2 }
}

const parseNovelText = (raw: string, rule: ImportSplitPreset): ImportChapterDraft[] => {
  if (!raw || !rule.chapterPattern) return []
  let chapterRegex: RegExp
  let reelRegex: RegExp | null = null
  try {
    chapterRegex = new RegExp(rule.chapterPattern, rule.chapterFlagsList.join(''))
    if (rule.reelPattern) {
      reelRegex = new RegExp(rule.reelPattern, rule.reelFlagsList.join(''))
    }
  } catch {
    return []
  }
  const lines = raw.split(/\r?\n/)
  const drafts: ImportChapterDraft[] = []
  let currentReel = ''
  let currentChapter = ''
  let currentBody: string[] = []

  const flush = () => {
    const chapterData = currentBody.join('\n').trim()
    if (currentChapter && chapterData) {
      drafts.push({
        key: drafts.length + 1,
        reel: currentReel,
        chapter: currentChapter,
        chapterData,
      })
    }
    currentChapter = ''
    currentBody = []
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    const nextLine = lines[index + 1]
    const inlineHeading = splitInlineReelChapter(line)
    if (inlineHeading) {
      flush()
      currentReel = inlineHeading.reel
      currentChapter = inlineHeading.chapter
      continue
    }
    const bareHeading = splitBareNumberChapter(line, nextLine, chapterRegex, reelRegex)
    if (bareHeading) {
      flush()
      currentChapter = bareHeading.chapter
      index += bareHeading.consumed - 1
    } else if (reelRegex && testRegex(reelRegex, line)) {
      flush()
      currentReel = line.trim()
      currentChapter = ''
    } else if (testRegex(chapterRegex, line)) {
      flush()
      currentChapter = line.trim()
    } else if (currentChapter) {
      if (looksLikeHeadingMetadata(line.trim())) continue
      currentBody.push(line)
    }
  }
  flush()
  return drafts
}

const importParsed = computed(() => parseNovelText(importRaw.value, currentSplitRule.value))

const getChapterLengthWarning = (draft: ImportChapterDraft) => {
  const length = draft.chapterData.length
  if (length < CHAPTER_SHORT_WARNING_LENGTH) {
    return `本章字数 ${length}，低于 ${CHAPTER_SHORT_WARNING_LENGTH}字`
  }
  if (length > CHAPTER_LONG_WARNING_LENGTH) {
    return `本章字数 ${length}，高于 ${CHAPTER_LONG_WARNING_LENGTH}字`
  }
  return ''
}

const hasChapterLengthWarning = (draft: ImportChapterDraft) => Boolean(getChapterLengthWarning(draft))

const getChapterPreviewAriaLabel = (draft: ImportChapterDraft) => {
  const warning = getChapterLengthWarning(draft)
  return warning ? `预览章节正文：${draft.chapter}，${warning}` : `预览章节正文：${draft.chapter}`
}

interface ImportFilterRule {
  id: string
  name: string
  pattern: string
  flags: string
  replacement: string
  enabled: boolean
  builtin: boolean
}

const importOriginalRaw = ref('')
const importFilterRules = ref<ImportFilterRule[]>([
  {
    id: 'f-url',
    name: '移除 http(s) 网址',
    pattern: 'https?:\\/\\/[^\\s\\u4e00-\\u9fa5]+',
    flags: 'gi',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'f-www',
    name: '移除 www.xxx 域名',
    pattern: 'www\\.[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}',
    flags: 'gi',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'f-ads',
    name: '移除常见广告 / 水印行',
    pattern: '^.*(笔趣阁|起点中文|纵横中文|17K小说|顶点小说|百度搜索|本站|本书首发|手打|更新最快|VIP章节|微信公众号|加群|本作品).*$',
    flags: 'gm',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'f-email',
    name: '移除邮箱',
    pattern: '[\\w.+-]+@[\\w-]+\\.[\\w.-]+',
    flags: 'gi',
    replacement: '',
    enabled: false,
    builtin: true,
  },
  {
    id: 'f-garbled',
    name: '移除乱码字符（�、控制符）',
    pattern: '[\\uFFFD\\u0000-\\u0008\\u000B-\\u001F]',
    flags: 'g',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'f-empty',
    name: '合并多余空行（≥3 行 → 1 行）',
    pattern: '\\n{3,}',
    flags: 'g',
    replacement: '\\n\\n',
    enabled: true,
    builtin: true,
  },
  {
    id: 'cf-unicode',
    name: '移除ubicode特殊符号',
    pattern: '[¤§©®™°±×÷•·※★☆♠♣♥♦¤⊕♟◇●c♜◆•Θ★mó◇ Θī♜]',
    flags: 'g',
    replacement: '',
    enabled: true,
    builtin: true,
  },
])

const customRuleName = ref('')
const customRulePattern = ref('')
const customRuleFlagsList = ref<string[]>(['g'])
const customRuleReplacement = ref('')

const FLAG_OPTIONS = [
  { value: 'g', label: '全局匹配（所有出现处都替换）' },
  { value: 'i', label: '忽略大小写' },
  { value: 'm', label: '多行模式（^ $ 匹配每一行）' },
  { value: 's', label: '点号匹配换行' },
]

const unescapeReplacement = (str: string) =>
  str.replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\r/g, '\r')

const addCustomFilterRule = () => {
  if (!customRulePattern.value.trim()) {
    ElMessage.warning('请输入匹配规则')
    return
  }
  const flags = customRuleFlagsList.value.join('') || 'g'
  try {
    new RegExp(customRulePattern.value, flags)
  } catch (e) {
    ElMessage.error(`正则无效：${(e as Error).message}`)
    return
  }
  importFilterRules.value.push({
    id: `f-${Date.now()}`,
    name: customRuleName.value || `自定义规则 #${importFilterRules.value.length + 1}`,
    pattern: customRulePattern.value,
    flags,
    replacement: customRuleReplacement.value,
    enabled: true,
    builtin: false,
  })
  customRuleName.value = ''
  customRulePattern.value = ''
  customRuleFlagsList.value = ['g']
  customRuleReplacement.value = ''
  ElMessage.success('已添加自定义规则')
}

const removeFilterRule = (id: string) => {
  importFilterRules.value = importFilterRules.value.filter((r) => r.id !== id)
}

const applyImportFilter = () => {
  if (!importRaw.value) {
    ElMessage.warning('暂无内容可过滤')
    return
  }
  if (!importOriginalRaw.value) {
    importOriginalRaw.value = importRaw.value
  }
  const before = importRaw.value.length
  let result = importRaw.value
  for (const rule of importFilterRules.value) {
    if (!rule.enabled) continue
    try {
      const regex = new RegExp(rule.pattern, rule.flags)
      const replacement = unescapeReplacement(rule.replacement)
      result = result.replace(regex, (match) => {
        if (rule.id === 'cf-unicode' && match === ' ') return match
        return replacement
      })
    } catch (e) {
      ElMessage.error(`规则「${rule.name}」执行失败：${(e as Error).message}`)
      return
    }
  }
  importRaw.value = result
  ElMessage.success(`已应用过滤：${before} → ${result.length}（净减 ${before - result.length} 字符）`)
}

const restoreImportOriginal = () => {
  if (!importOriginalRaw.value) {
    ElMessage.info('暂无可恢复的原始内容')
    return
  }
  importRaw.value = importOriginalRaw.value
  importOriginalRaw.value = ''
  ElMessage.success('已恢复至原始内容')
}

const resetImportState = () => {
  importStep.value = 1
  importRaw.value = ''
  importFileName.value = ''
  importOriginalRaw.value = ''
  importSelectedRows.value = []
  importSubmitting.value = false
}

// 编码自动识别：UTF-8 BOM / 严格 UTF-8 解码失败时回退 GBK
const detectEncoding = (buffer: ArrayBuffer): 'utf-8' | 'gbk' => {
  const bytes = new Uint8Array(buffer)
  // UTF-8 BOM：EF BB BF
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return 'utf-8'
  }
  // UTF-16 BOM 暂当作 UTF-8 处理（TextDecoder 能自动处理）
  if (bytes.length >= 2 && ((bytes[0] === 0xff && bytes[1] === 0xfe) || (bytes[0] === 0xfe && bytes[1] === 0xff))) {
    return 'utf-8'
  }
  // 严格 UTF-8 解码：非法字节抛错就回退 GBK
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(buffer)
    return 'utf-8'
  } catch {
    return 'gbk'
  }
}

const readFileAsArrayBuffer = (file: File): Promise<ArrayBuffer> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const buffer = e.target?.result as ArrayBuffer | null
      if (!buffer) reject(new Error('文件内容为空'))
      else resolve(buffer)
    }
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.readAsArrayBuffer(file)
  })

const extractTextFromTxt = async (buffer: ArrayBuffer): Promise<{ text: string; detail: string }> => {
  const encoding = detectEncoding(buffer)
  const decoder = new TextDecoder(encoding)
  return { text: decoder.decode(buffer), detail: `${encoding.toUpperCase()} 编码` }
}

const extractTextFromDocx = async (buffer: ArrayBuffer): Promise<{ text: string; detail: string }> => {
  const mammoth = await import('mammoth/mammoth.browser')
  const result = await mammoth.extractRawText({ arrayBuffer: buffer })
  return { text: result.value || '', detail: 'DOCX 文档' }
}

const extractTextFromPdf = async (buffer: ArrayBuffer): Promise<{ text: string; detail: string }> => {
  const pdfjsLib: any = await import('pdfjs-dist')
  const workerModule = await import('pdfjs-dist/build/pdf.worker.min.mjs?url')
  pdfjsLib.GlobalWorkerOptions.workerSrc = workerModule.default
  const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(buffer) })
  const pdf = await loadingTask.promise
  const pages: string[] = []
  for (let i = 1; i <= pdf.numPages; i += 1) {
    const page = await pdf.getPage(i)
    const content = await page.getTextContent()
    const lines: string[] = []
    let currentLine = ''
    let lastY: number | null = null
    for (const item of content.items as Array<{ str: string; transform?: number[]; hasEOL?: boolean }>) {
      const y = item.transform?.[5] ?? null
      if (lastY !== null && y !== null && Math.abs(y - lastY) > 2) {
        if (currentLine.trim()) lines.push(currentLine.trim())
        currentLine = ''
      }
      currentLine += item.str
      if (item.hasEOL) {
        if (currentLine.trim()) lines.push(currentLine.trim())
        currentLine = ''
      }
      lastY = y
    }
    if (currentLine.trim()) lines.push(currentLine.trim())
    pages.push(lines.join('\n'))
  }
  return { text: pages.join('\n\n'), detail: `PDF ${pdf.numPages} 页` }
}

const handleImportFile = async (uploadFile: { raw?: File; name: string }) => {
  const rawFile = uploadFile?.raw
  if (!rawFile) {
    ElMessage.error('文件读取失败，请重新选择')
    return
  }
  if (/\.doc$/i.test(rawFile.name)) {
    ElMessage.error('暂不支持旧版 .doc（二进制 Word 97-2003）；请用 Word/WPS 另存为 .docx 后再上传')
    return
  }
  if (!/\.(txt|docx|pdf)$/i.test(rawFile.name)) {
    ElMessage.error('仅支持 .txt / .docx / .pdf')
    return
  }
  if (rawFile.size > 10 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 10MB')
    return
  }
  const loading = ElMessage({ message: `正在解析 ${rawFile.name}…`, duration: 0, type: 'info' })
  try {
    const buffer = await readFileAsArrayBuffer(rawFile)
    let result: { text: string; detail: string }
    if (/\.docx$/i.test(rawFile.name)) {
      result = await extractTextFromDocx(buffer)
    } else if (/\.pdf$/i.test(rawFile.name)) {
      result = await extractTextFromPdf(buffer)
    } else {
      result = await extractTextFromTxt(buffer)
    }
    importRaw.value = result.text
    importOriginalRaw.value = ''
    importFileName.value = rawFile.name
    ElMessage.success(
      `已读取 ${rawFile.name}（${result.detail}），共 ${importRaw.value.length} 字符`,
    )
  } catch (err) {
    ElMessage.error(`解析失败：${(err as Error).message}`)
  } finally {
    loading.close()
  }
}

const onImportSelectionChange = (rows: ImportChapterDraft[]) => {
  importSelectedRows.value = rows
}

const goImportNext = () => {
  if (!importRaw.value.trim()) {
    ElMessage.warning('请先上传文件或粘贴小说全文')
    return
  }
  importStep.value = 2
  nextTick(() => {
    importTableRef.value?.clearSelection?.()
    importTableRef.value?.toggleAllSelection?.()
  })
}

const submitImport = async () => {
  if (importSelectedRows.value.length === 0) {
    ElMessage.warning('请选择要导入的章节')
    return
  }
  importSubmitting.value = true
  await new Promise((resolve) => setTimeout(resolve, 200))
  emit('submit', [...importSelectedRows.value])
  emit('update:modelValue', false)
  importSubmitting.value = false
}
</script>

<style>
/* 全文导入对话框（element-plus teleport 到 body，需置于非 scoped 块） */
.novel-import-dialog .import-steps {
  padding: 4px 12px 18px;
}

.novel-import-dialog .import-steps .el-step__title {
  color: #8b949e;
  font-size: 13px;
  font-weight: 500;
}

.novel-import-dialog .import-steps .el-step__head.is-process .el-step__icon,
.novel-import-dialog .import-steps .el-step__head.is-finish .el-step__icon {
  background-color: rgba(37, 99, 235, 0.18);
  border-color: rgba(37, 99, 235, 0.55);
  color: #93c5fd;
}

.novel-import-dialog .import-steps .el-step__head.is-success .el-step__icon {
  background-color: rgba(34, 197, 94, 0.16);
  border-color: rgba(34, 197, 94, 0.55);
  color: #86efac;
}

.novel-import-dialog .import-steps .el-step__title.is-process,
.novel-import-dialog .import-steps .el-step__title.is-success {
  color: #e6edf3;
  font-weight: 600;
}

.novel-import-dialog .import-steps .el-step__line {
  background-color: rgba(255, 255, 255, 0.08);
}

.novel-import-dialog .import-step {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.novel-import-dialog .import-uploader .el-upload-dragger {
  padding: 5px 24px;
  background-color: #0c1015;
  border: 1.5px dashed rgba(255, 255, 255, 0.18);
  border-radius: 14px;
  transition: background-color 0.18s ease, border-color 0.18s ease;
}

.novel-import-dialog .import-uploader .el-upload-dragger:hover,
.novel-import-dialog .import-uploader .el-upload-dragger.is-dragover {
  background-color: rgba(37, 99, 235, 0.06);
  border-color: rgba(96, 165, 250, 0.55);
}

.novel-import-dialog .import-uploader__icon {
  font-size: 38px;
  color: #93c5fd;
}

.novel-import-dialog .import-uploader__text {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #c5cdd6;
}

.novel-import-dialog .import-uploader__text strong {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.novel-import-dialog .import-uploader__text span {
  font-size: 12px;
  color: #6e7681;
}

.novel-import-dialog .import-uploader__file {
  margin-top: 10px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  background: rgba(37, 99, 235, 0.12);
  border: 1px solid rgba(37, 99, 235, 0.32);
  color: #93c5fd;
  display: inline-block;
}

.novel-import-dialog .import-divider {
  margin: 4px 0;
  background-color: transparent;
}

.novel-import-dialog .import-divider .el-divider__text {
  color: #6e7681;
  font-size: 12px;
  background-color: transparent;
  padding: 0 12px;
}

.novel-import-dialog .import-divider.el-divider--horizontal {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  height: 1px;
}

.novel-import-dialog .import-meta {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  padding: 10px 0 0;
  color: #8b949e;
  font-size: 12px;
}

.novel-import-dialog .import-meta strong {
  color: #e6edf3;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-weight: 600;
  margin: 0 2px;
}

.novel-import-dialog .import-meta__warn {
  color: #fca5a5;
}

.novel-import-dialog .import-preview__head {
  color: #c5cdd6;
  font-size: 13px;
  padding: 4px 4px 8px;
}

.novel-import-dialog .import-preview__head strong {
  color: #93c5fd;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  margin: 0 2px;
}

.novel-import-dialog .import-preview__table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-row-hover-bg-color: rgba(37, 99, 235, 0.08);
  --el-table-border-color: rgba(255, 255, 255, 0.06);
  --el-table-header-text-color: #c5cdd6;
  --el-table-text-color: #e6edf3;
  --el-table-fixed-box-shadow: none;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background-color: #0c1015;
  overflow: hidden;
}

.novel-import-dialog .import-preview__table,
.novel-import-dialog .import-preview__table tr,
.novel-import-dialog .import-preview__table th.el-table__cell,
.novel-import-dialog .import-preview__table td.el-table__cell {
  background-color: transparent;
  color: #e6edf3;
  border-color: rgba(255, 255, 255, 0.06);
}

.novel-import-dialog .import-preview__table thead th.el-table__cell {
  background-color: rgba(255, 255, 255, 0.04);
  color: #c5cdd6;
  font-size: 12px;
  font-weight: 600;
}

.novel-import-dialog .import-preview__table tbody tr:hover > td.el-table__cell {
  background-color: rgba(37, 99, 235, 0.08);
}

.novel-import-dialog .import-preview__table .el-table__inner-wrapper::before {
  display: none;
}

.novel-import-dialog .import-preview__table .el-table__body-wrapper,
.novel-import-dialog .import-preview__table .el-table__header-wrapper,
.novel-import-dialog .import-preview__table .el-table__inner-wrapper,
.novel-import-dialog .import-preview__table .el-table__empty-block {
  background-color: transparent;
}

.novel-import-dialog .import-preview__table .el-table__empty-text {
  color: #6e7681;
}

.novel-import-dialog .import-preview__chapter-title {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: #dbeafe;
  cursor: pointer;
  font: inherit;
  line-height: 1.5;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.18s ease;
}

.novel-import-dialog .import-preview__chapter-title:hover {
  color: #93c5fd;
}

.novel-import-dialog .import-preview__chapter-title:focus-visible {
  color: #93c5fd;
  outline: 2px solid rgba(96, 165, 250, 0.55);
  outline-offset: 2px;
}

.novel-import-dialog .import-preview__chapter-title.is-warning {
  color: #f87171;
  font-weight: 600;
}

.novel-import-dialog .import-preview__chapter-title.is-warning:hover,
.novel-import-dialog .import-preview__chapter-title.is-warning:focus-visible {
  color: #fca5a5;
}

.novel-import-dialog .import-preview__chapter-warning {
  flex-shrink: 0;
  color: currentColor;
  font-size: 14px;
}

.novel-import-dialog .import-preview__chapter-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-chapter-preview-popper.el-popper {
  max-width: min(560px, calc(100vw - 32px));
  padding: 0;
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
  overflow: hidden;
}

.novel-chapter-preview-popper.el-popper .el-popper__arrow::before {
  background-color: #14181f;
  border-color: rgba(255, 255, 255, 0.12);
}

.novel-chapter-preview-popper .chapter-preview-tip {
  display: flex;
  flex-direction: column;
  max-height: min(420px, calc(100vh - 96px));
  min-width: 0;
}

.novel-chapter-preview-popper .chapter-preview-tip__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.035);
}

.novel-chapter-preview-popper .chapter-preview-tip__head strong {
  min-width: 0;
  color: #f2f4f8;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-chapter-preview-popper .chapter-preview-tip__head span {
  flex-shrink: 0;
  color: #93c5fd;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px;
  font-weight: 600;
}

.novel-chapter-preview-popper .chapter-preview-tip__body {
  max-height: 320px;
  overflow-y: auto;
  padding: 14px 16px 16px;
  color: #d5dce4;
  font-size: 13px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.novel-chapter-preview-popper .chapter-preview-tip__body::-webkit-scrollbar {
  width: 8px;
}

.novel-chapter-preview-popper .chapter-preview-tip__body::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.04);
}

.novel-chapter-preview-popper .chapter-preview-tip__body::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.38);
  border-radius: 999px;
}

.novel-chapter-preview-popper .chapter-preview-tip__body::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.55);
}

.novel-import-dialog .text-muted {
  color: #6e7681;
  font-size: 12px;
}

.novel-import-dialog .el-dialog__header {
  padding: 18px 28px 12px;
}

.novel-import-dialog .el-dialog__title {
  font-size: 19px;
}

.novel-import-dialog .el-dialog__headerbtn {
  top: 12px;
}

.novel-import-dialog .import-uploader .el-upload-dragger {
  padding: 4px 24px;
}

.novel-import-dialog .import-uploader__icon {
  font-size: 30px;
}

.novel-import-dialog .import-uploader__text {
  margin-top: 6px;
}

/* 内容过滤区 */
.novel-import-dialog .import-filter {
  margin-top: 4px;
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.novel-import-dialog .import-filter__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}

.novel-import-dialog .import-filter__title {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 700;
  color: #f2f4f8;
}

.novel-import-dialog .import-filter__hint {
  margin: 0;
  font-size: 12px;
  color: #6e7681;
  line-height: 1.5;
}

.novel-import-dialog .import-filter__actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.novel-import-dialog .import-filter__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.novel-import-dialog .import-filter__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  min-width: 0;
}

.novel-import-dialog .import-filter__check {
  flex: 1;
  min-width: 0;
}

.novel-import-dialog .import-filter__check .el-checkbox__label {
  width: 100%;
  min-width: 0;
  padding-left: 8px;
  line-height: 1.4;
}

.novel-import-dialog .import-filter__item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  width: 100%;
}

.novel-import-dialog .import-filter__item-name {
  font-size: 13px;
  font-weight: 600;
  color: #d5dce4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-import-dialog .import-filter__item-regex {
  display: block;
  font-size: 11px;
  color: #6e7681;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  cursor: help;
}

.novel-import-dialog .import-filter__badge {
  flex-shrink: 0;
  color: #93c5fd;
  background-color: rgba(37, 99, 235, 0.12);
  border-color: rgba(37, 99, 235, 0.3);
  font-size: 11px;
  padding: 0 6px;
  height: 20px;
  line-height: 18px;
}

.novel-import-dialog .import-filter__custom {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-import-dialog .import-filter__custom-input {
  flex-shrink: 0;
}

.novel-import-dialog .import-filter__custom-input--name {
  width: 160px;
}

.novel-import-dialog .import-filter__custom-input--pattern {
  flex: 1;
  min-width: 220px;
}

.novel-import-dialog .import-filter__custom-input--flags {
  width: 180px;
}

.novel-import-dialog .import-filter__custom-input--repl {
  width: 160px;
}

/* 全文导入对话框内部按钮统一为黑雅风格（footer 已另行覆盖，这里只覆盖正文区） */
.novel-import-dialog .el-dialog__body .el-button {
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
  color: #c5cdd6;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.novel-import-dialog .el-dialog__body .el-button:hover,
.novel-import-dialog .el-dialog__body .el-button:focus {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
  transform: translateY(-1px);
}

.novel-import-dialog .el-dialog__body .el-button:active {
  transform: translateY(0);
}

.novel-import-dialog .el-dialog__body .el-button.is-disabled,
.novel-import-dialog .el-dialog__body .el-button.is-disabled:hover,
.novel-import-dialog .el-dialog__body .el-button.is-disabled:focus {
  background-color: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.06);
  color: #4d5560;
  transform: none;
  cursor: not-allowed;
}

.novel-import-dialog .el-dialog__body .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.22);
}

.novel-import-dialog .el-dialog__body .el-button--primary:hover,
.novel-import-dialog .el-dialog__body .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
  color: #ffffff;
}

.novel-import-dialog .el-dialog__body .el-button--primary.is-plain {
  background-color: rgba(37, 99, 235, 0.1);
  border-color: rgba(37, 99, 235, 0.45);
  color: #93c5fd;
  box-shadow: none;
}

.novel-import-dialog .el-dialog__body .el-button--primary.is-plain:hover,
.novel-import-dialog .el-dialog__body .el-button--primary.is-plain:focus {
  background-color: rgba(37, 99, 235, 0.2);
  border-color: rgba(37, 99, 235, 0.65);
  color: #ffffff;
}

.novel-import-dialog .el-dialog__body .el-button.is-link {
  height: auto;
  padding: 2px 4px;
  background: transparent;
  border: none;
  box-shadow: none;
}

.novel-import-dialog .el-dialog__body .el-button.is-link.el-button--danger {
  color: #fca5a5;
}

.novel-import-dialog .el-dialog__body .el-button.is-link.el-button--danger:hover {
  color: #fecaca;
  background: transparent;
  transform: none;
}

.novel-import-dialog .el-dialog__body .el-button .el-icon {
  margin-right: 2px;
}

/* 切分规则区 */
.novel-import-dialog .import-split {
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 14px;
}

.novel-import-dialog .import-split__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}

.novel-import-dialog .import-split__title {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 700;
  color: #f2f4f8;
}

.novel-import-dialog .import-split__hint {
  margin: 0;
  font-size: 12px;
  color: #6e7681;
  line-height: 1.5;
}

.novel-import-dialog .import-split__main {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.novel-import-dialog .import-split__select {
  width: 280px;
}

.novel-import-dialog .import-split__opt {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.novel-import-dialog .import-split__opt-label {
  color: inherit;
  font-size: 13px;
  font-weight: 600;
}

.novel-import-dialog .import-split__opt-desc {
  color: #6e7681;
  font-size: 11px;
}

.novel-import-dialog .import-split__custom {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.novel-import-dialog .import-split__custom-pattern {
  flex: 1;
  min-width: 240px;
}

.novel-import-dialog .import-split__custom-flags {
  width: 80px;
}

.novel-import-dialog .import-split__editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.novel-import-dialog .import-split__row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.novel-import-dialog .import-split__row-label {
  flex-shrink: 0;
  width: 48px;
  font-size: 12px;
  font-weight: 600;
  color: #c5cdd6;
  text-align: right;
}

.novel-import-dialog .import-split__row-pattern {
  flex: 1;
  min-width: 240px;
}

.novel-import-dialog .import-split__row-flags {
  width: 200px;
  flex-shrink: 0;
}

.novel-import-dialog .import-split__regex-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: #8b949e;
}

.novel-import-dialog .import-split__regex-preview code {
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  overflow-x: auto;
  white-space: nowrap;
}
</style>
