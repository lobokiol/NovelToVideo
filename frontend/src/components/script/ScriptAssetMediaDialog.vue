<template>
  <el-dialog
    :model-value="modelValue"
    :title="asset ? `配图 · ${asset.name}` : '资产配图'"
    width="min(980px, 96vw)"
    append-to-body
    class="script-asset-dialog script-asset-media-dialog"
    @update:model-value="onVisibleChange"
    @open="onOpen"
  >
    <section class="gen-config">
      <div class="gen-block">
        <div class="gen-label-row">
          <label class="gen-label">提示词</label>
          <el-button link size="small" :loading="prompting" @click="synthesizePrompt">
            <el-icon><MagicStick /></el-icon>&nbsp;生成专业提示词
          </el-button>
        </div>
        <el-input
          v-model="form.prompt"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="留空时会先调用项目绑定文本模型生成专业提示词，再提交给项目绑定图像模型"
        />
      </div>

      <div v-if="isDerivativeAsset" class="gen-block reference-block">
        <div class="gen-label-row">
          <label class="gen-label">参考图</label>
          <div class="reference-tools">
            <span v-if="referenceCandidates.length" class="reference-count">
              已选择 {{ referenceMediaPublicIds.length }} / {{ referenceCandidates.length }} 张
            </span>
            <el-button link size="small" :loading="uploadingReference" @click="triggerReferenceUpload">
              <el-icon><Upload /></el-icon>&nbsp;上传参考图
            </el-button>
            <el-button
              v-if="referenceCandidates.length"
              link
              size="small"
              @click="selectAllReferenceMedia"
            >
              全选
            </el-button>
            <el-button
              v-if="referenceCandidates.length"
              link
              size="small"
              :disabled="referenceMediaPublicIds.length === 0"
              @click="clearReferenceMediaSelection"
            >
              清空
            </el-button>
          </div>
        </div>
        <input
          ref="referenceUploadInput"
          class="reference-upload-input"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          @change="onReferenceFilesChange"
        />
        <div v-if="referenceCandidates.length" class="reference-strip">
          <div
            v-for="media in referenceCandidates"
            :key="`ref-${media.publicId}`"
            role="button"
            tabindex="0"
            class="reference-tile"
            :class="{ 'is-selected': isReferenceSelected(media.publicId) }"
            :aria-pressed="isReferenceSelected(media.publicId)"
            title="点击切换这张图是否作为参考"
            @click="toggleReferenceMedia(media.publicId)"
            @keydown.enter.prevent="toggleReferenceMedia(media.publicId)"
            @keydown.space.prevent="toggleReferenceMedia(media.publicId)"
          >
            <img :src="media.url" :alt="referenceAsset?.name || '参考图'" loading="lazy" />
            <span class="reference-role">{{ mediaRoleLabel(media) }}</span>
            <span class="reference-state">{{ isReferenceSelected(media.publicId) ? '已选' : '未选' }}</span>
            <button
              v-if="media.mediaRole === 'reference'"
              type="button"
              class="reference-remove"
              title="删除这张上传参考图"
              aria-label="删除这张上传参考图"
              @click.stop="removeReferenceMedia(media)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </div>
        <p v-else class="reference-empty">
          衍生资产基于参考图出图：可先为主资产生成配图，或直接上传本地参考图。
        </p>
      </div>

      <div class="gen-grid">
        <div class="gen-block gen-block--select">
          <label class="gen-label">画面比例</label>
          <el-select
            v-model="form.aspectRatio"
            class="script-asset-media-select"
            popper-class="script-asset-media-select-popper"
          >
            <el-option
              v-for="ratio in ratioOptions"
              :key="ratio.value"
              :label="ratio.value"
              :value="ratio.value"
            >
              <span class="media-select-option">
                <span class="ratio-box" :style="ratioBoxStyle(ratio)"></span>
                <span>{{ ratio.value }}</span>
              </span>
            </el-option>
          </el-select>
        </div>
        <div class="gen-block gen-block--select">
          <label class="gen-label">分辨率</label>
          <el-select
            v-model="form.imageSize"
            class="script-asset-media-select script-asset-media-select--small"
            popper-class="script-asset-media-select-popper"
          >
            <el-option v-for="size in SIZES" :key="size" :label="size" :value="size" />
          </el-select>
        </div>
        <div class="gen-block gen-block--select">
          <label class="gen-label">数量</label>
          <el-select
            v-model="form.count"
            class="script-asset-media-select script-asset-media-select--small"
            popper-class="script-asset-media-select-popper"
          >
            <el-option v-for="n in COUNTS" :key="n" :label="String(n)" :value="n" />
          </el-select>
        </div>
        <div class="gen-block gen-block--actions">
          <el-button class="media-refresh-button" :loading="loading" @click="() => loadMedia()">
            <el-icon><Refresh /></el-icon>&nbsp;刷新
          </el-button>
          <el-button type="primary" :loading="generating" @click="generate">
            <el-icon><MagicStick /></el-icon>&nbsp;{{ isDerivativeAsset ? '生成衍生图' : '生成主资产图' }}
          </el-button>
        </div>
      </div>
    </section>

    <section class="media-gallery">
      <template v-if="loading && galleryMedias.length === 0 && pendingCount === 0">
        <div
          v-for="n in 4"
          :key="`sk${n}`"
          class="media-card media-card--skeleton"
          :style="{ aspectRatio: cardAspect }"
        />
      </template>
      <template v-else>
        <div
          v-for="n in pendingCount"
          :key="`pd${n}`"
          class="media-card media-card--pending"
          :style="{ aspectRatio: cardAspect }"
        >
          <el-icon class="pending-spin"><Loading /></el-icon>
          <span>生成中…</span>
        </div>

        <el-empty
          v-if="galleryMedias.length === 0 && pendingCount === 0"
          class="media-empty"
          :image-size="80"
          description="暂无配图，调整参数后点击「生成配图」"
        />

        <figure
          v-for="(media, idx) in galleryMedias"
          :key="media.publicId"
          class="media-card"
          :class="{
            'is-cover': media.mediaRole === 'final',
            'is-detail-open': expandedMediaPublicId === media.publicId,
          }"
        >
          <div class="media-image-frame">
            <img
              :src="media.url"
              :alt="asset?.name || ''"
              :width="media.width || undefined"
              :height="media.height || undefined"
              loading="lazy"
              @load="updateMediaNaturalSize(media.publicId, $event)"
              @click="openPreview(idx)"
            />
            <span v-if="media.mediaRole === 'final'" class="cover-ribbon">封面</span>
            <div class="media-overlay">
              <el-button
                class="media-detail-button"
                circle
                size="small"
                :aria-expanded="expandedMediaPublicId === media.publicId"
                :aria-label="expandedMediaPublicId === media.publicId ? '收起图片详情' : '查看图片详情'"
                :title="expandedMediaPublicId === media.publicId ? '收起图片详情' : '查看图片详情'"
                @click.stop="toggleMediaDetails(media.publicId)"
              >
                <el-icon><Picture /></el-icon>
              </el-button>
              <el-button circle size="small" title="放大预览" @click.stop="openPreview(idx)">
                <el-icon><ZoomIn /></el-icon>
              </el-button>
              <el-button
                circle
                size="small"
                :disabled="media.mediaRole === 'final'"
                title="设为封面"
                @click.stop="setCover(media)"
              >
                <el-icon><Star /></el-icon>
              </el-button>
              <el-button
                circle
                size="small"
                title="复用当前图片参数"
                @click.stop="reuseMediaSettings(media)"
              >
                <el-icon><RefreshRight /></el-icon>
              </el-button>
              <el-button circle size="small" type="danger" title="删除" @click.stop="remove(media)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          <div class="media-meta-panel" @click.stop>
            <dl class="media-meta-grid">
              <div>
                <dt>比例</dt>
                <dd>{{ mediaRatioLabel(media) }}</dd>
              </div>
              <div>
                <dt>尺寸</dt>
                <dd>{{ mediaSizeLabel(media) }}</dd>
              </div>
              <div>
                <dt>类型</dt>
                <dd>{{ mediaTypeLabel(media) }}</dd>
              </div>
            </dl>
            <p class="media-prompt-text">{{ mediaPromptLabel(media) }}</p>
          </div>
        </figure>
      </template>
    </section>
  </el-dialog>

  <el-image-viewer
    v-if="previewVisible"
    :url-list="previewUrls"
    :initial-index="previewIndex"
    hide-on-click-modal
    teleported
    @close="previewVisible = false"
  />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Delete, Loading, MagicStick, Picture, Refresh, RefreshRight, Star, Upload, ZoomIn } from '@element-plus/icons-vue'
import {
  deleteAssetMediaApi,
  generateAssetImagesApi,
  listAssetMediaApi,
  setAssetMediaCoverApi,
  synthesizeAssetImagePromptApi,
  uploadAssetReferenceImageApi,
  type AssetManageItem,
  type AssetMediaItem,
} from '@/api/asset'
import { getTaskJobApi, type TaskJobResponse } from '@/api/task'

const props = defineProps<{
  modelValue: boolean
  projectPublicId: string
  asset: AssetManageItem | null
  referenceAsset?: AssetManageItem | null
  textModelId?: string
  imageModelId?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'changed'): void
}>()

interface RatioOption {
  value: string
  w: number
  h: number
}

const RATIOS: RatioOption[] = [
  { value: '1:1', w: 1, h: 1 },
  { value: '4:3', w: 4, h: 3 },
  { value: '3:4', w: 3, h: 4 },
  { value: '16:9', w: 16, h: 9 },
  { value: '9:16', w: 9, h: 16 },
  { value: '3:2', w: 3, h: 2 },
  { value: '2:3', w: 2, h: 3 },
  { value: '5:4', w: 5, h: 4 },
  { value: '4:5', w: 4, h: 5 },
  { value: '21:9', w: 21, h: 9 },
]
const SIZES = ['1K', '2K', '4K']
const COUNTS = [1, 2, 3, 4]
const PROMPT_POLL_INTERVAL_MS = 3000
const PROMPT_MAX_POLL_ATTEMPTS = 100
const MEDIA_POLL_INTERVAL_MS = 4000
const MEDIA_MAX_POLL_ATTEMPTS = 120
const REFERENCE_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
const REFERENCE_UPLOAD_MIME_TYPES = new Set(['image/png', 'image/jpeg', 'image/jpg', 'image/webp'])

const form = reactive({
  prompt: '',
  aspectRatio: '3:4',
  imageSize: '2K',
  count: 1,
})

const loading = ref(false)
const generatingAssets = reactive<Record<string, boolean>>({})
const promptingAssets = reactive<Record<string, boolean>>({})
const medias = ref<AssetMediaItem[]>([])
const referenceMedias = ref<AssetMediaItem[]>([])
const selectedReferenceMediaPublicIds = ref<string[]>([])
const pendingCount = ref(0)
const expandedMediaPublicId = ref('')
const mediaNaturalSizes = reactive<Record<string, { width: number; height: number }>>({})

const currentAssetPublicId = computed(() => props.asset?.publicId || '')
const generating = computed(
  () => currentAssetPublicId.value !== '' && !!generatingAssets[currentAssetPublicId.value],
)
const prompting = computed(
  () => currentAssetPublicId.value !== '' && !!promptingAssets[currentAssetPublicId.value],
)
const cardAspect = computed(() => form.aspectRatio.replace(':', ' / '))
// 衍生判定与后端一致：以是否传入父资产（child_of 绑定）为准，
// main_asset 标记缺失的普通资产不能被误判成衍生而无法生图。
const isDerivativeAsset = computed(() => (
  props.asset ? !props.asset.mainAsset && !!props.referenceAsset?.publicId : false
))
const galleryMedias = computed(() => medias.value.filter((media) => media.mediaRole !== 'reference'))
// 参考图候选 = 当前资产上传的本地参考图 + 父资产的生成图/封面。
const uploadedReferenceMedias = computed(() => medias.value.filter((media) => (
  media.mediaType === 'image' &&
  media.mediaRole === 'reference' &&
  !!media.url
)))
const parentReferenceMedias = computed(() => referenceMedias.value.filter((media) => (
  media.mediaType === 'image' &&
  media.mediaRole !== 'reference' &&
  !!media.url
)))
const referenceCandidates = computed(() => [
  ...uploadedReferenceMedias.value,
  ...parentReferenceMedias.value,
])
const referenceCandidatePublicIds = computed(() => referenceCandidates.value.map((media) => media.publicId))
const referenceMediaPublicIds = computed(() => {
  const candidates = new Set(referenceCandidatePublicIds.value)
  return selectedReferenceMediaPublicIds.value.filter((publicId) => candidates.has(publicId))
})

const selectAllReferenceMedia = () => {
  selectedReferenceMediaPublicIds.value = [...referenceCandidatePublicIds.value]
}

const clearReferenceMediaSelection = () => {
  selectedReferenceMediaPublicIds.value = []
}

const isReferenceSelected = (mediaPublicId: string) => (
  referenceMediaPublicIds.value.includes(mediaPublicId)
)

const toggleReferenceMedia = (mediaPublicId: string) => {
  const selected = new Set(referenceMediaPublicIds.value)
  if (selected.has(mediaPublicId)) selected.delete(mediaPublicId)
  else selected.add(mediaPublicId)
  selectedReferenceMediaPublicIds.value = referenceCandidatePublicIds.value.filter((publicId) => selected.has(publicId))
}

const uploadingReference = ref(false)
const referenceUploadInput = ref<HTMLInputElement | null>(null)

const triggerReferenceUpload = () => {
  referenceUploadInput.value?.click()
}

const onReferenceFilesChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  const assetPublicId = currentAssetPublicId.value
  if (!files.length || !assetPublicId) return
  const valid: File[] = []
  for (const file of files) {
    if (!REFERENCE_UPLOAD_MIME_TYPES.has((file.type || '').toLowerCase())) {
      ElMessage.warning(`「${file.name}」不是 PNG/JPEG/WebP 图片，已跳过`)
      continue
    }
    if (file.size > REFERENCE_UPLOAD_MAX_BYTES) {
      ElMessage.warning(`「${file.name}」超过 20MB 上限，已跳过`)
      continue
    }
    valid.push(file)
  }
  if (!valid.length) return
  uploadingReference.value = true
  try {
    const uploadedPublicIds: string[] = []
    for (const file of valid) {
      const { data } = await uploadAssetReferenceImageApi(props.projectPublicId, assetPublicId, file)
      uploadedPublicIds.push(data.publicId)
    }
    if (currentAssetPublicId.value !== assetPublicId) return
    await loadMedia({ silent: true })
    selectedReferenceMediaPublicIds.value = [
      ...new Set([...selectedReferenceMediaPublicIds.value, ...uploadedPublicIds]),
    ]
    ElMessage.success(`已上传 ${uploadedPublicIds.length} 张参考图`)
  } catch (error) {
    ElMessage.error((error as Error)?.message || '上传参考图失败')
    if (currentAssetPublicId.value === assetPublicId) await loadMedia({ silent: true })
  } finally {
    uploadingReference.value = false
  }
}

const removeReferenceMedia = async (media: AssetMediaItem) => {
  try {
    await ElMessageBox.confirm('确认删除这张上传的参考图？', '删除参考图', {
      type: 'warning',
      customClass: 'script-asset-messagebox',
    })
  } catch {
    return
  }
  try {
    await deleteAssetMediaApi(props.projectPublicId, media.publicId)
    selectedReferenceMediaPublicIds.value = selectedReferenceMediaPublicIds.value.filter(
      (publicId) => publicId !== media.publicId,
    )
    await loadMedia({ silent: true })
    ElMessage.success('已删除参考图')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '删除参考图失败')
  }
}

const ratioOptionFromValue = (value: string): RatioOption | null => {
  const match = value.trim().match(/^(\d+):(\d+)$/)
  if (!match) return null
  const w = Number(match[1])
  const h = Number(match[2])
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null
  return { value: `${w}:${h}`, w, h }
}

const ratioOptions = computed(() => {
  const current = ratioOptionFromValue(form.aspectRatio)
  if (!current || RATIOS.some((ratio) => ratio.value === current.value)) return RATIOS
  return [...RATIOS, current]
})

const ratioBoxStyle = (ratio: RatioOption) => {
  const max = 16
  const longSide = Math.max(ratio.w, ratio.h)
  return {
    width: `${(ratio.w / longSide) * max}px`,
    height: `${(ratio.h / longSide) * max}px`,
  }
}

const greatestCommonDivisor = (a: number, b: number): number => {
  let x = Math.abs(Math.trunc(a))
  let y = Math.abs(Math.trunc(b))
  while (y !== 0) {
    const next = x % y
    x = y
    y = next
  }
  return x || 1
}

const normalizeMediaDimension = (value: number) => Math.max(0, Math.trunc(value || 0))

const mediaDisplaySize = (media: AssetMediaItem) => {
  const width = normalizeMediaDimension(media.width)
  const height = normalizeMediaDimension(media.height)
  if (width > 0 && height > 0) return { width, height }
  const natural = mediaNaturalSizes[media.publicId]
  if (!natural) return { width: 0, height: 0 }
  return {
    width: normalizeMediaDimension(natural.width),
    height: normalizeMediaDimension(natural.height),
  }
}

const mediaRatioLabel = (media: AssetMediaItem) => {
  const { width, height } = mediaDisplaySize(media)
  if (width <= 0 || height <= 0) return '读取中'
  const divisor = greatestCommonDivisor(width, height)
  return `${Math.trunc(width / divisor)}:${Math.trunc(height / divisor)}`
}

const mediaRatioValue = (media: AssetMediaItem) => {
  const { width, height } = mediaDisplaySize(media)
  if (width <= 0 || height <= 0) return ''
  const divisor = greatestCommonDivisor(width, height)
  return `${Math.trunc(width / divisor)}:${Math.trunc(height / divisor)}`
}

const mediaSizeLabel = (media: AssetMediaItem) => {
  const { width, height } = mediaDisplaySize(media)
  return width > 0 && height > 0 ? `${width} x ${height}` : '读取中'
}

const mediaReuseImageSize = (media: AssetMediaItem) => {
  const { width, height } = mediaDisplaySize(media)
  const longSide = Math.max(width, height)
  if (longSide <= 0) return form.imageSize
  if (longSide <= 1536) return '1K'
  if (longSide <= 3072) return '2K'
  return '4K'
}

const mediaTypeLabel = (media: AssetMediaItem) => {
  const mime = (media.mimeType || '').split('/').pop()?.trim().toUpperCase()
  return mime || media.mediaType || '未知'
}

const mediaPromptLabel = (media: AssetMediaItem) => {
  const prompt = (media.prompt || '').trim()
  return prompt || '暂无提示词'
}

const mediaRoleLabel = (media: AssetMediaItem) => {
  if (media.mediaRole === 'final') return '封面'
  if (media.mediaRole === 'reference') return '参考'
  return '配图'
}

const toggleMediaDetails = (mediaPublicId: string) => {
  expandedMediaPublicId.value = expandedMediaPublicId.value === mediaPublicId ? '' : mediaPublicId
}

const reuseMediaSettings = (media: AssetMediaItem) => {
  const ratio = mediaRatioValue(media)
  form.prompt = (media.prompt || '').trim()
  form.imageSize = mediaReuseImageSize(media)
  if (!ratio) {
    ElMessage.warning('图片尺寸尚未读取完成，已复用提示词')
    return
  }
  form.aspectRatio = ratio
  ElMessage.success('已复用当前图片的比例、分辨率和提示词')
}

const updateMediaNaturalSize = (mediaPublicId: string, event: Event) => {
  const image = event.target
  if (!(image instanceof HTMLImageElement)) return
  const width = normalizeMediaDimension(image.naturalWidth)
  const height = normalizeMediaDimension(image.naturalHeight)
  if (width <= 0 || height <= 0) return
  mediaNaturalSizes[mediaPublicId] = { width, height }
}

const pruneMediaNaturalSizes = (mediaItems: AssetMediaItem[]) => {
  const activePublicIds = new Set(mediaItems.map((media) => media.publicId))
  for (const mediaPublicId of Object.keys(mediaNaturalSizes)) {
    if (!activePublicIds.has(mediaPublicId)) delete mediaNaturalSizes[mediaPublicId]
  }
}

const loadMedia = async (options: { silent?: boolean } = {}) => {
  const assetPublicId = currentAssetPublicId.value
  if (!assetPublicId) return
  if (!options.silent) loading.value = true
  try {
    const { data } = await listAssetMediaApi(props.projectPublicId, assetPublicId)
    if (currentAssetPublicId.value === assetPublicId) {
      medias.value = data
      pruneMediaNaturalSizes([...galleryMedias.value, ...referenceCandidates.value])
      if (
        expandedMediaPublicId.value &&
        !data.some((media) => media.publicId === expandedMediaPublicId.value)
      ) {
        expandedMediaPublicId.value = ''
      }
    }
  } catch (error) {
    if (!options.silent) {
      ElMessage.error((error as Error)?.message || '加载配图失败')
    }
  } finally {
    if (!options.silent) loading.value = false
  }
}

const loadReferenceMedia = async () => {
  const referenceAssetPublicId = props.referenceAsset?.publicId || ''
  if (!isDerivativeAsset.value || !referenceAssetPublicId) {
    referenceMedias.value = []
    return
  }
  try {
    const { data } = await listAssetMediaApi(props.projectPublicId, referenceAssetPublicId)
    if ((props.referenceAsset?.publicId || '') === referenceAssetPublicId) {
      referenceMedias.value = data
      selectAllReferenceMedia()
      pruneMediaNaturalSizes([...galleryMedias.value, ...referenceCandidates.value])
    }
  } catch (error) {
    referenceMedias.value = []
    selectedReferenceMediaPublicIds.value = []
    ElMessage.error((error as Error)?.message || '加载主资产参考图失败')
  }
}

let promptPollTimer: ReturnType<typeof setTimeout> | undefined
let promptPollTries = 0
let promptPollingJobPublicId = ''
let promptPollingAssetPublicId = ''
let promptPollingResolve: ((prompt: string) => void) | undefined

const promptFromJob = (job: TaskJobResponse) => {
  for (const item of job.items ?? []) {
    if (item.status !== 'succeeded') continue
    const prompt = (item.outputText || item.finalPrompt || item.composedPrompt || '').trim()
    if (prompt) return prompt
  }
  return ''
}

const activeJobCount = (job: TaskJobResponse) => (
  job.pendingCount + job.runningCount + job.pausedCount
)

const stopPromptPolling = (prompt = '') => {
  if (promptPollTimer) clearTimeout(promptPollTimer)
  const resolve = promptPollingResolve
  promptPollTimer = undefined
  promptPollTries = 0
  promptPollingJobPublicId = ''
  promptPollingAssetPublicId = ''
  promptPollingResolve = undefined
  if (resolve) resolve(prompt)
}

const startPromptPolling = (jobPublicId: string, assetPublicId: string) => {
  stopPromptPolling()
  promptPollingJobPublicId = jobPublicId
  promptPollingAssetPublicId = assetPublicId
  return new Promise<string>((resolve) => {
    promptPollingResolve = resolve
    const tick = async () => {
      if (!promptPollingJobPublicId) return
      if (promptPollingAssetPublicId !== currentAssetPublicId.value) {
        stopPromptPolling()
        return
      }
      promptPollTries += 1
      try {
        const { data: job } = await getTaskJobApi(props.projectPublicId, jobPublicId)
        const prompt = promptFromJob(job)
        if (prompt) {
          if (currentAssetPublicId.value === assetPublicId) {
            form.prompt = prompt
          }
          stopPromptPolling(prompt)
          return
        }
        if (job.succeededCount > 0 || activeJobCount(job) === 0 || isTerminalJob(job)) {
          stopPromptPolling()
          if (currentAssetPublicId.value === assetPublicId) {
            ElMessage.warning('专业提示词任务已结束，但未返回可用提示词，可在任务中心查看详情')
          }
          return
        }
      } catch (error) {
        stopPromptPolling()
        if (currentAssetPublicId.value === assetPublicId) {
          ElMessage.error((error as Error)?.message || '读取专业提示词任务状态失败')
        }
        return
      }
      // 有上限的轮询：任务长期无进展时结束等待并释放生成按钮，避免 UI 被永久锁死。
      if (promptPollTries >= PROMPT_MAX_POLL_ATTEMPTS) {
        stopPromptPolling()
        if (currentAssetPublicId.value === assetPublicId) {
          ElMessage.warning('专业提示词任务耗时过长，已停止等待，可稍后在任务中心查看结果')
        }
        return
      }
      promptPollTimer = setTimeout(tick, PROMPT_POLL_INTERVAL_MS)
    }
    void tick()
  })
}

const synthesizePrompt = async () => {
  const assetPublicId = currentAssetPublicId.value
  if (!assetPublicId) return ''
  if (!(props.textModelId || '').trim()) {
    ElMessage.warning('请先在项目设置中选择文本模型，再生成专业提示词')
    return ''
  }
  if (!(props.imageModelId || '').trim()) {
    ElMessage.warning('请先在项目设置中选择图像模型，再生成专业提示词')
    return ''
  }
  promptingAssets[assetPublicId] = true
  try {
    const { data: job } = await synthesizeAssetImagePromptApi(props.projectPublicId, assetPublicId)
    if (currentAssetPublicId.value !== assetPublicId) return ''
    const prompt = await startPromptPolling(job.publicId, assetPublicId)
    if (prompt && currentAssetPublicId.value === assetPublicId) {
      form.prompt = prompt
    }
    return prompt
  } catch (error) {
    ElMessage.error((error as Error)?.message || '生成专业提示词失败')
    return ''
  } finally {
    delete promptingAssets[assetPublicId]
  }
}

// 异步生成可见化：提交后插入占位卡，按任务状态轮询，并在终态刷新媒体列表。
let pollTimer: ReturnType<typeof setTimeout> | undefined
let pollTries = 0
let pollingJobPublicId = ''
let pollingAssetPublicId = ''

const stopPolling = () => {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = undefined
  pollingJobPublicId = ''
  pollingAssetPublicId = ''
}

const stopAllPolling = () => {
  stopPromptPolling()
  stopPolling()
}

const isTerminalJob = (job: TaskJobResponse) => (
  job.status === 'succeeded' ||
  job.status === 'partial_failed' ||
  job.status === 'failed' ||
  job.status === 'canceled'
)

const pendingFromJob = (job: TaskJobResponse, expected: number) => {
  const active = job.pendingCount + job.runningCount + job.pausedCount
  const unfinished = Math.max(
    0,
    job.totalCount - job.succeededCount - job.failedCount - job.canceledCount,
  )
  return Math.min(expected, Math.max(active, unfinished))
}

const startPolling = (jobPublicId: string, expected: number, assetPublicId: string) => {
  if (currentAssetPublicId.value !== assetPublicId) return
  stopPolling()
  const baseline = galleryMedias.value.length
  pendingCount.value = expected
  pollTries = 0
  pollingJobPublicId = jobPublicId
  pollingAssetPublicId = assetPublicId
  const tick = async () => {
    if (!pollingJobPublicId) return
    if (pollingAssetPublicId !== currentAssetPublicId.value) {
      pendingCount.value = 0
      stopPolling()
      return
    }
    pollTries += 1
    try {
      const { data: job } = await getTaskJobApi(props.projectPublicId, jobPublicId)
      await loadMedia({ silent: true })
      pendingCount.value = pendingFromJob(job, expected)
      if (galleryMedias.value.length > baseline || job.succeededCount > 0) emit('changed')
      if (isTerminalJob(job)) {
        pendingCount.value = 0
        stopPolling()
        if (job.failedCount > 0 || job.canceledCount > 0) {
          ElMessage.warning('配图任务已结束，部分图片未生成成功，可在任务中心查看详情')
        }
        return
      }
    } catch {
      await loadMedia({ silent: true })
      const produced = Math.max(0, galleryMedias.value.length - baseline)
      pendingCount.value = Math.max(0, expected - produced)
      if (produced >= expected) {
        emit('changed')
        pendingCount.value = 0
        stopPolling()
        return
      }
    }
    if (pollTries >= MEDIA_MAX_POLL_ATTEMPTS) {
      stopPolling()
      pendingCount.value = 0
      await loadMedia({ silent: true })
      ElMessage.warning('配图任务仍在后台执行，可稍后手动刷新查看结果')
      return
    }
    pollTimer = setTimeout(tick, MEDIA_POLL_INTERVAL_MS)
  }
  pollTimer = setTimeout(tick, MEDIA_POLL_INTERVAL_MS)
}

const generate = async () => {
  const assetPublicId = currentAssetPublicId.value
  if (!assetPublicId) return
  const modelId = (props.imageModelId || '').trim()
  if (!modelId) {
    ElMessage.warning('请先在项目设置中选择图像模型，再生成配图')
    return
  }
  const aspectRatio = form.aspectRatio
  const imageSize = form.imageSize
  const count = form.count
  const referenceIds = isDerivativeAsset.value ? referenceMediaPublicIds.value : []
  if (isDerivativeAsset.value && referenceIds.length === 0) {
    ElMessage.warning('请先勾选参考图：可为主资产生成配图，或直接上传本地参考图')
    return
  }
  generatingAssets[assetPublicId] = true
  try {
    let prompt = form.prompt.trim()
    if (!prompt) {
      const synthesized = await synthesizePrompt()
      if (currentAssetPublicId.value !== assetPublicId) return
      prompt = synthesized.trim()
      if (!prompt) return
    }
    const { data: job } = await generateAssetImagesApi(props.projectPublicId, {
      modelId,
      assetPublicIds: [assetPublicId],
      prompt,
      aspectRatio,
      imageSize,
      referenceMediaPublicIds: referenceIds,
      count,
    })
    ElMessage.success(isDerivativeAsset.value ? '已提交衍生图生成任务，正在等待出图…' : '已提交主资产图生成任务，正在等待出图…')
    startPolling(job.publicId, count, assetPublicId)
  } catch (error) {
    ElMessage.error((error as Error)?.message || '提交配图任务失败')
  } finally {
    delete generatingAssets[assetPublicId]
  }
}

const setCover = async (media: AssetMediaItem) => {
  try {
    await setAssetMediaCoverApi(props.projectPublicId, media.publicId)
    ElMessage.success('已设为封面')
    await loadMedia()
    emit('changed')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '设置封面失败')
  }
}

const remove = async (media: AssetMediaItem) => {
  try {
    await ElMessageBox.confirm('确认删除这张配图？', '删除配图', {
      type: 'warning',
      customClass: 'script-asset-messagebox',
    })
  } catch {
    return
  }
  try {
    await deleteAssetMediaApi(props.projectPublicId, media.publicId)
    if (expandedMediaPublicId.value === media.publicId) {
      expandedMediaPublicId.value = ''
    }
    ElMessage.success('已删除')
    await loadMedia()
    emit('changed')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '删除失败')
  }
}

const previewVisible = ref(false)
const previewUrls = ref<string[]>([])
const previewIndex = ref(0)
const openPreview = (index: number) => {
  previewUrls.value = galleryMedias.value.map((media) => media.url).filter(Boolean)
  previewIndex.value = index
  previewVisible.value = true
}

const resetForCurrentAsset = () => {
  stopAllPolling()
  form.prompt = ''
  medias.value = []
  referenceMedias.value = []
  selectedReferenceMediaPublicIds.value = []
  pruneMediaNaturalSizes([])
  expandedMediaPublicId.value = ''
  pendingCount.value = 0
  void loadMedia()
  void loadReferenceMedia()
}

const onOpen = () => {
  resetForCurrentAsset()
}

const onVisibleChange = (value: boolean) => {
  if (!value) {
    stopAllPolling()
    pendingCount.value = 0
    pruneMediaNaturalSizes([])
    expandedMediaPublicId.value = ''
  }
  emit('update:modelValue', value)
}

watch(
  () => currentAssetPublicId.value,
  () => {
    if (props.modelValue) resetForCurrentAsset()
  },
)

watch(
  () => props.referenceAsset?.publicId || '',
  () => {
    if (!props.modelValue) return
    referenceMedias.value = []
    selectedReferenceMediaPublicIds.value = []
    void loadReferenceMedia()
  },
)

onBeforeUnmount(stopAllPolling)
</script>

<style>
/* 资产配图弹窗：深色，复用 .script-asset-dialog 暗色外壳；以唯一类前缀避免泄漏。 */
.script-asset-media-dialog .gen-config {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px 16px;
  margin-bottom: 16px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.07);
}
.script-asset-media-dialog .gen-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.script-asset-media-dialog .gen-block--select {
  min-width: 128px;
}
.script-asset-media-dialog .gen-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.script-asset-media-dialog .gen-label {
  font-size: 12px;
  font-weight: 600;
  color: #8b949e;
  letter-spacing: 0.02em;
}
.script-asset-media-dialog .reference-block {
  gap: 10px;
}
.script-asset-media-dialog .reference-count {
  color: #7aa2f7;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.script-asset-media-dialog .reference-tools {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.script-asset-media-dialog .reference-tools .el-button {
  height: auto;
  padding: 0;
  font-size: 12px;
}
.script-asset-media-dialog .reference-strip {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 2px 2px 6px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.16) transparent;
}
.script-asset-media-dialog .reference-tile {
  position: relative;
  flex: 0 0 auto;
  width: 72px;
  height: 72px;
  padding: 0;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: #0c1015;
  color: inherit;
  appearance: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, opacity 0.16s ease;
}
.script-asset-media-dialog .reference-tile:not(.is-selected) {
  opacity: 0.48;
}
.script-asset-media-dialog .reference-tile.is-selected {
  border-color: rgba(37, 99, 235, 0.9);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.28);
}
.script-asset-media-dialog .reference-tile:focus-visible {
  outline: 2px solid rgba(147, 197, 253, 0.88);
  outline-offset: 2px;
}
.script-asset-media-dialog .reference-tile img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.script-asset-media-dialog .reference-role,
.script-asset-media-dialog .reference-state {
  position: absolute;
  max-width: calc(100% - 10px);
  padding: 1px 6px;
  color: #ffffff;
  background: rgba(6, 9, 13, 0.78);
  border-radius: 999px;
  font-size: 10px;
  line-height: 1.4;
  white-space: nowrap;
}
.script-asset-media-dialog .reference-role {
  left: 5px;
  bottom: 5px;
}
.script-asset-media-dialog .reference-state {
  top: 5px;
  right: 5px;
}
.script-asset-media-dialog .reference-tile.is-selected .reference-state {
  background: rgba(37, 99, 235, 0.9);
}
.script-asset-media-dialog .reference-upload-input {
  display: none;
}
.script-asset-media-dialog .reference-remove {
  position: absolute;
  top: 5px;
  left: 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  color: #ffffff;
  background: rgba(220, 38, 38, 0.82);
  border: none;
  border-radius: 999px;
  cursor: pointer;
  font-size: 11px;
}
.script-asset-media-dialog .reference-remove:hover,
.script-asset-media-dialog .reference-remove:focus-visible {
  background: #dc2626;
}
.script-asset-media-dialog .reference-empty {
  margin: 0;
  color: #7d8590;
  font-size: 12px;
  line-height: 1.5;
}
.script-asset-media-dialog .gen-grid {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 18px;
}
.script-asset-media-dialog .gen-block--actions {
  margin-left: auto;
  flex-direction: row;
  gap: 8px;
}
.script-asset-media-dialog .script-asset-media-select {
  width: 142px;
}
.script-asset-media-dialog .script-asset-media-select--small {
  width: 96px;
}
.script-asset-media-dialog .script-asset-media-select .el-select__wrapper {
  min-height: 40px;
  background: #0c1015;
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: none;
  border-radius: 8px;
}
.script-asset-media-dialog .script-asset-media-select .el-select__wrapper:hover {
  background: #111820;
  border-color: rgba(255, 255, 255, 0.24);
}
.script-asset-media-dialog .script-asset-media-select .el-select__wrapper.is-focused {
  border-color: rgba(37, 99, 235, 0.7);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14);
}
.script-asset-media-dialog .script-asset-media-select .el-select__selected-item,
.script-asset-media-dialog .script-asset-media-select .el-select__placeholder {
  color: #e6edf3;
}
.script-asset-media-dialog .script-asset-media-select .el-select__caret {
  color: #8b949e;
}
.script-asset-media-dialog .media-refresh-button {
  min-height: 40px;
  color: #c5cdd6;
  background: #0c1015;
  border-color: rgba(255, 255, 255, 0.14);
  box-shadow: none;
}
.script-asset-media-dialog .media-refresh-button:hover,
.script-asset-media-dialog .media-refresh-button:focus {
  color: #ffffff;
  background: #111820;
  border-color: rgba(255, 255, 255, 0.28);
}
.script-asset-media-dialog .el-textarea__inner {
  background: #0c1015;
  color: #e6edf3;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border-radius: 8px;
}
.script-asset-media-dialog .el-textarea__inner::placeholder {
  color: #6e7681;
}
.script-asset-media-dialog .el-textarea__inner:focus {
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.55) inset, 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.script-asset-media-dialog .ratio-box {
  display: inline-block;
  border-radius: 2px;
  background: currentColor;
  opacity: 0.85;
}

.script-asset-media-dialog .media-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  align-items: start;
  gap: 12px;
  min-height: 180px;
  max-height: 52vh;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}
.script-asset-media-dialog .media-empty {
  grid-column: 1 / -1;
}
.script-asset-media-dialog .media-card {
  position: relative;
  margin: 0;
  align-self: start;
  border-radius: 10px;
  overflow: hidden;
  background: #0c1015;
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}
.script-asset-media-dialog .media-card:hover {
  border-color: rgba(255, 255, 255, 0.2);
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
}
.script-asset-media-dialog .media-card.is-cover {
  border-color: rgba(37, 99, 235, 0.7);
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.4);
}
.script-asset-media-dialog .media-image-frame {
  position: relative;
}
.script-asset-media-dialog .media-card img {
  width: 100%;
  height: auto;
  display: block;
  cursor: zoom-in;
}
.script-asset-media-dialog .media-detail-button {
  color: #e6edf3;
  background: rgba(6, 9, 13, 0.72);
  border-color: rgba(255, 255, 255, 0.24);
}
.script-asset-media-dialog .media-detail-button:hover,
.script-asset-media-dialog .media-detail-button:focus {
  color: #ffffff;
  background: rgba(37, 99, 235, 0.86);
  border-color: rgba(147, 197, 253, 0.72);
}
.script-asset-media-dialog .media-card.is-detail-open .media-detail-button {
  color: #ffffff;
  background: #2563eb;
  border-color: rgba(147, 197, 253, 0.72);
}
.script-asset-media-dialog .media-meta-panel {
  display: grid;
  gap: 8px;
  max-height: 0;
  padding: 0 10px;
  overflow: hidden;
  color: #c5cdd6;
  background: #0f141b;
  border-top: 1px solid transparent;
  opacity: 0;
  transform: translateY(-6px);
  transition:
    max-height 0.2s ease,
    padding 0.2s ease,
    border-color 0.2s ease,
    opacity 0.18s ease,
    transform 0.18s ease;
}
.script-asset-media-dialog .media-card.is-detail-open .media-meta-panel {
  max-height: none;
  padding: 10px;
  border-color: rgba(255, 255, 255, 0.08);
  opacity: 1;
  transform: translateY(0);
}
.script-asset-media-dialog .media-meta-grid {
  display: grid;
  grid-template-columns: minmax(46px, 0.7fr) minmax(96px, 1.4fr) minmax(46px, 0.7fr);
  gap: 8px;
  margin: 0;
}
.script-asset-media-dialog .media-meta-grid div {
  min-width: 0;
}
.script-asset-media-dialog .media-meta-grid dt {
  margin: 0 0 2px;
  font-size: 10px;
  line-height: 1.2;
  color: #7d8590;
}
.script-asset-media-dialog .media-meta-grid dd {
  margin: 0;
  color: #e6edf3;
  font-size: 11px;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.script-asset-media-dialog .media-prompt-text {
  margin: 0;
  color: #9da7b3;
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.script-asset-media-dialog .cover-ribbon {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 2;
  font-size: 11px;
  padding: 1px 9px;
  border-radius: 999px;
  color: #fff;
  background: #2563eb;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}
.script-asset-media-dialog .media-overlay {
  position: absolute;
  inset: auto 0 0 0;
  display: flex;
  justify-content: center;
  gap: 5px;
  padding: 7px;
  background: linear-gradient(to top, rgba(6, 9, 13, 0.86), rgba(6, 9, 13, 0));
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.script-asset-media-dialog .media-overlay .el-button {
  width: 26px;
  height: 26px;
  min-width: 26px;
  margin-left: 0;
}
.script-asset-media-dialog .media-card:hover .media-overlay,
.script-asset-media-dialog .media-card:focus-within .media-overlay {
  opacity: 1;
  transform: translateY(0);
}
.script-asset-media-dialog .media-card--skeleton {
  background: linear-gradient(100deg, #0c1015 30%, #161b22 50%, #0c1015 70%);
  background-size: 200% 100%;
  animation: media-shimmer 1.3s ease-in-out infinite;
}
.script-asset-media-dialog .media-card--pending {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #8b949e;
  font-size: 12px;
  border-style: dashed;
}
.script-asset-media-dialog .pending-spin {
  font-size: 22px;
  color: #2563eb;
  animation: media-spin 1s linear infinite;
}
@keyframes media-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}
@keyframes media-spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .script-asset-media-dialog .media-card,
  .script-asset-media-dialog .media-meta-panel,
  .script-asset-media-dialog .media-overlay,
  .script-asset-media-dialog .media-card--skeleton,
  .script-asset-media-dialog .pending-spin {
    transition: none;
    animation: none;
  }
}
</style>

<style>
/* 下拉浮层会 teleport 到 body，需使用全局类保持配图弹窗的暗色控件一致性。 */
.script-asset-media-select-popper.el-popper {
  background: #111820 !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}
.script-asset-media-select-popper .el-select-dropdown {
  background: #111820;
  border: none;
}
.script-asset-media-select-popper .el-select-dropdown__wrap,
.script-asset-media-select-popper .el-scrollbar,
.script-asset-media-select-popper .el-scrollbar__wrap,
.script-asset-media-select-popper .el-scrollbar__view {
  background: #111820;
}
.script-asset-media-select-popper .el-select-dropdown__list {
  padding: 6px 4px;
}
.script-asset-media-select-popper .el-select-dropdown__item {
  margin: 2px 4px;
  border-radius: 8px;
  color: #c5cdd6;
  transition: background-color 0.18s ease, color 0.18s ease;
}
.script-asset-media-select-popper .el-select-dropdown__item:hover,
.script-asset-media-select-popper .el-select-dropdown__item.hover,
.script-asset-media-select-popper .el-select-dropdown__item.is-hovering {
  background: rgba(255, 255, 255, 0.06);
  color: #ffffff;
}
.script-asset-media-select-popper .el-select-dropdown__item.selected,
.script-asset-media-select-popper .el-select-dropdown__item.is-selected {
  color: #7aa2f7;
  background: rgba(37, 99, 235, 0.16);
  font-weight: 600;
}
.script-asset-media-select-popper .el-select-dropdown__item.is-disabled {
  color: #4d5560;
  background: transparent;
}
.script-asset-media-select-popper .el-select-dropdown__wrap::-webkit-scrollbar {
  width: 6px;
}
.script-asset-media-select-popper .el-select-dropdown__wrap::-webkit-scrollbar-track {
  background: transparent;
}
.script-asset-media-select-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.3);
  border-radius: 999px;
}
.script-asset-media-select-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}
.script-asset-media-select-popper .el-popper__arrow::before {
  background: #111820 !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
}
.script-asset-media-select-popper .media-select-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-variant-numeric: tabular-nums;
}
</style>
