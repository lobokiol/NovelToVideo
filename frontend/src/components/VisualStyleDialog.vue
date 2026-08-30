<template>
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="1120px"
    destroy-on-close
    class="visual-style-dialog"
  >
    <el-form
      ref="styleFormRef"
      :model="styleForm"
      :rules="styleRules"
      class="visual-style-form"
      label-position="top"
    >
      <div class="style-form-grid">
        <el-form-item label="风格目录标识" prop="style_path">
          <el-input
            v-model="styleForm.style_path"
            :disabled="mode === 'edit'"
            maxlength="120"
            placeholder="例如 cinematic_realism"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="展示名称" prop="name">
          <el-input
            v-model="styleForm.name"
            maxlength="120"
            placeholder="例如 电影级写实"
            show-word-limit
          />
        </el-form-item>
      </div>
    </el-form>

    <section class="style-image-section">
      <header class="dialog-section-head">
        <h3>风格图片</h3>
        封面图必须叫：scene_character_in_landscape.png，否则客户端无法显示
        <span>{{ styleImages.length }} 张</span>
      </header>

      <div class="style-image-strip">
        <div
          v-for="(image, index) in styleImages"
          :key="image.id"
          class="style-image-tile"
          role="button"
          tabindex="0"
          :aria-label="`预览图片：${image.filename}`"
          @click="openImagePreview(index)"
          @keydown.enter.prevent="openImagePreview(index)"
          @keydown.space.prevent="openImagePreview(index)"
        >
          <img :src="image.url" :alt="image.filename" />
          <span class="style-image-name">{{ image.filename }}</span>
          <button
            type="button"
            class="style-image-delete"
            aria-label="删除图片"
            title="删除图片"
            @click.stop="removeStyleImage(image.id)"
          >
            <el-icon><Close /></el-icon>
          </button>
        </div>

        <button
          type="button"
          class="style-image-add"
          aria-label="上传风格图片"
          title="上传风格图片"
          @click="pickImageFiles"
        >
          <el-icon><Plus /></el-icon>
        </button>
      </div>

      <input
        ref="imageInputRef"
        type="file"
        accept=".png,.jpg,.jpeg,.webp,.gif,image/png,image/jpeg,image/webp,image/gif"
        multiple
        hidden
        @change="onImageFilesSelected"
      />
    </section>

    <section class="style-file-section">
      <header class="dialog-section-head">
        <h3>Markdown 文件</h3>
        <el-button size="small" @click="addStyleFile">
          <el-icon><Plus /></el-icon>
          添加文件
        </el-button>
      </header>

      <el-empty
        v-if="styleFiles.length === 0"
        class="style-file-empty"
        description="暂无 Markdown 文件"
      />

      <el-tabs
        v-else
        v-model="activeFileId"
        type="card"
        closable
        class="style-file-tabs"
        @tab-remove="removeStyleFileById"
      >
        <el-tab-pane
          v-for="file in styleFiles"
          :key="file.id"
          :name="file.id"
          :label="file.path || '未命名文件'"
        >
          <div class="style-file-meta">
            <el-input
              v-model="file.path"
              class="style-file-path"
              placeholder="文件名，例如 README.md"
              @blur="file.path = normalizeMarkdownPath(file.path)"
            />
            <el-button
              class="style-file-remove"
              type="danger"
              @click="removeStyleFile(file.id)"
            >
              <el-icon><Delete /></el-icon>
              删除文件
            </el-button>
          </div>

          <MarkdownEditor v-model="file.content" />
        </el-tab-pane>
      </el-tabs>
    </section>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitStyle">
        保存视觉风格
      </el-button>
    </template>

    <el-image-viewer
      v-if="previewVisible"
      :url-list="previewUrls"
      :initial-index="previewIndex"
      hide-on-click-modal
      teleported
      @close="previewVisible = false"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { AxiosError } from 'axios'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import {
  Close,
  Delete,
  Plus,
} from '@element-plus/icons-vue'
import MarkdownEditor from '@/components/MarkdownEditor.vue'
import {
  createVisualStyleApi,
  deleteVisualStyleFileApi,
  deleteVisualStyleImageApi,
  getVisualStyleApi,
  writeVisualStyleFileApi,
  writeVisualStyleImageApi,
  type VisualStyleFilePayload,
  type VisualStyleImagePayload,
  type VisualStyleRecord,
} from '@/api/project'

type VisualStyleDialogMode = 'create' | 'edit'

interface VisualStyleFormState {
  style_path: string
  name: string
}

interface StyleFileDraft {
  id: string
  originalPath: string
  path: string
  content: string
}

interface StyleImageDraft {
  id: string
  originalFilename: string
  filename: string
  url: string
  data: string
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  mode: VisualStyleDialogMode
  style?: VisualStyleRecord | null
}>(), {
  style: null,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [style: VisualStyleRecord]
}>()

const STYLE_PATH_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$/
const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif']
const ALLOWED_IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.gif']
const MAX_STYLE_IMAGE_BYTES = 8 * 1024 * 1024

let draftCounter = 0

const styleFormRef = ref<FormInstance>()
const imageInputRef = ref<HTMLInputElement | null>(null)
const submitting = ref(false)
const activeFileId = ref('')
const styleFiles = ref<StyleFileDraft[]>([])
const styleImages = ref<StyleImageDraft[]>([])
const removedFilePaths = ref<string[]>([])
const removedImageFilenames = ref<string[]>([])

const previewVisible = ref(false)
const previewUrls = ref<string[]>([])
const previewIndex = ref(0)

const styleForm = reactive<VisualStyleFormState>({
  style_path: '',
  name: '',
})

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const mode = computed(() => props.mode)

const dialogTitle = computed(() => (props.mode === 'create' ? '添加视觉风格' : `编辑视觉风格：${styleForm.style_path}`))

const validateStylePath = (_rule: unknown, value: string, callback: (error?: Error) => void) => {
  const trimmed = value.trim()
  if (!trimmed) {
    callback(new Error('请输入风格目录标识'))
    return
  }
  if (!STYLE_PATH_PATTERN.test(trimmed) || /^\d+$/.test(trimmed)) {
    callback(new Error('仅支持字母、数字、下划线和短横线，且不能为纯数字'))
    return
  }
  callback()
}

const styleRules: FormRules<VisualStyleFormState> = {
  style_path: [{ validator: validateStylePath, trigger: 'blur' }],
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      resetDraft()
    }
  },
)

watch(
  () => props.style,
  () => {
    if (props.modelValue) {
      resetDraft()
    }
  },
)

const createDraftId = () => {
  draftCounter += 1
  return `style-draft-${Date.now()}-${draftCounter}`
}

const resetDraft = () => {
  submitting.value = false
  removedFilePaths.value = []
  removedImageFilenames.value = []
  previewVisible.value = false

  if (props.mode === 'edit' && props.style) {
    styleForm.style_path = props.style.style_path
    styleForm.name = props.style.name
    styleFiles.value = props.style.files.map((file) => ({
      id: createDraftId(),
      originalPath: file.path,
      path: file.path,
      content: file.content,
    }))
    styleImages.value = props.style.images.map((image) => ({
      id: createDraftId(),
      originalFilename: image.filename,
      filename: image.filename,
      url: image.url || image.path,
      data: '',
    }))
  } else {
    styleForm.style_path = ''
    styleForm.name = ''
    styleFiles.value = [createStyleFileDraft('README.md', '# 新视觉风格\n')]
    styleImages.value = []
  }

  activeFileId.value = styleFiles.value[0]?.id ?? ''
  styleFormRef.value?.clearValidate()
}

const createStyleFileDraft = (path: string, content = ''): StyleFileDraft => ({
  id: createDraftId(),
  originalPath: '',
  path,
  content,
})

const addStyleFile = () => {
  const nextPath = getUniqueMarkdownPath(styleFiles.value.length === 0 ? 'README.md' : 'style.md')
  const file = createStyleFileDraft(nextPath, `# ${styleForm.name || '视觉风格'}\n`)
  styleFiles.value.push(file)
  activeFileId.value = file.id
}

const removeStyleFileById = (targetName: string | number) => {
  removeStyleFile(String(targetName))
}

const removeStyleFile = (id: string) => {
  const index = styleFiles.value.findIndex((file) => file.id === id)
  if (index < 0) return

  const [removed] = styleFiles.value.splice(index, 1)
  if (removed.originalPath) {
    removedFilePaths.value.push(removed.originalPath)
  }

  if (activeFileId.value === id) {
    activeFileId.value = styleFiles.value[Math.max(0, index - 1)]?.id ?? styleFiles.value[0]?.id ?? ''
  }
}

const normalizeMarkdownPath = (value: string) => value.trim().replace(/\\/g, '/')

const getUniqueMarkdownPath = (basePath: string) => {
  const normalizedBase = normalizeMarkdownPath(basePath)
  const dotIndex = normalizedBase.toLowerCase().lastIndexOf('.md')
  const stem = dotIndex >= 0 ? normalizedBase.slice(0, dotIndex) : normalizedBase
  const existing = new Set(styleFiles.value.map((file) => normalizeMarkdownPath(file.path).toLowerCase()))
  let candidate = normalizedBase.toLowerCase().endsWith('.md') ? normalizedBase : `${normalizedBase}.md`
  let index = 2
  while (existing.has(candidate.toLowerCase())) {
    candidate = `${stem}-${index}.md`
    index += 1
  }
  return candidate
}

const pickImageFiles = () => {
  imageInputRef.value?.click()
}

const onImageFilesSelected = (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files ?? [])
  target.value = ''
  if (files.length === 0) return
  void importImageFiles(files)
}

const importImageFiles = async (files: File[]) => {
  for (const file of files) {
    const validationError = validateImageFile(file)
    if (validationError) {
      ElMessage.error(validationError)
      continue
    }

    try {
      const dataUrl = await readFileAsDataUrl(file)
      const filename = getUniqueImageFilename(file.name)
      styleImages.value.push({
        id: createDraftId(),
        originalFilename: '',
        filename,
        url: dataUrl,
        data: dataUrl,
      })
    } catch {
      ElMessage.error(`图片读取失败：${file.name}`)
    }
  }
}

const validateImageFile = (file: File) => {
  const extension = getFileExtension(file.name)
  if (!ALLOWED_IMAGE_TYPES.includes(file.type) || !ALLOWED_IMAGE_EXTENSIONS.includes(extension)) {
    return `仅支持 PNG/JPEG/WEBP/GIF 图片：${file.name}`
  }
  if (file.size > MAX_STYLE_IMAGE_BYTES) {
    return `图片不能超过 8MB：${file.name}`
  }
  return ''
}

const readFileAsDataUrl = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => {
    const result = typeof reader.result === 'string' ? reader.result : ''
    if (!result.startsWith('data:')) {
      reject(new Error('invalid data url'))
      return
    }
    resolve(result)
  }
  reader.onerror = () => reject(reader.error ?? new Error('read failed'))
  reader.readAsDataURL(file)
})

const getFileExtension = (filename: string) => {
  const dotIndex = filename.lastIndexOf('.')
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : ''
}

const getUniqueImageFilename = (filename: string) => {
  const extension = getFileExtension(filename)
  const rawStem = extension ? filename.slice(0, -extension.length) : filename
  const safeStem = rawStem
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 96) || 'style-image'
  const existing = new Set(styleImages.value.map((image) => image.filename.toLowerCase()))
  let candidate = `${safeStem}${extension}`.slice(0, 120)
  let index = 2
  while (existing.has(candidate.toLowerCase())) {
    candidate = `${safeStem}-${index}${extension}`.slice(0, 120)
    index += 1
  }
  return candidate
}

const removeStyleImage = (id: string) => {
  const index = styleImages.value.findIndex((image) => image.id === id)
  if (index < 0) return
  const [removed] = styleImages.value.splice(index, 1)
  if (removed.originalFilename) {
    removedImageFilenames.value.push(removed.originalFilename)
  }
}

const openImagePreview = (index: number) => {
  if (styleImages.value.length === 0) return
  previewUrls.value = styleImages.value.map((image) => image.url).filter(Boolean)
  previewIndex.value = index
  previewVisible.value = true
}

const submitStyle = async () => {
  if (!styleFormRef.value) return
  const valid = await styleFormRef.value.validate().catch(() => false)
  if (!valid) return

  syncReadmeTitleFromName()
  const normalizedFiles = getNormalizedFiles()
  const validationError = validateFileDrafts(normalizedFiles)
  if (validationError) {
    ElMessage.error(validationError)
    return
  }

  submitting.value = true
  try {
    const stylePath = styleForm.style_path.trim()
    if (props.mode === 'create') {
      const { data } = await createVisualStyleApi({
        style_path: stylePath,
        name: styleForm.name.trim(),
        files: normalizedFiles,
        images: getNewImagePayloads(),
      })
      ElMessage.success('视觉风格已创建')
      emit('saved', data)
    } else {
      await saveExistingStyle(stylePath, normalizedFiles)
      const { data } = await getVisualStyleApi(stylePath)
      ElMessage.success('视觉风格已保存')
      emit('saved', data)
    }
    dialogVisible.value = false
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    submitting.value = false
  }
}

const getNormalizedFiles = (): VisualStyleFilePayload[] => (
  styleFiles.value.map((file) => ({
    path: normalizeMarkdownPath(file.path),
    content: file.content,
  }))
)

const syncReadmeTitleFromName = () => {
  const name = styleForm.name.trim()
  if (!name) return

  const readme = styleFiles.value.find((file) => normalizeMarkdownPath(file.path).toLowerCase() === 'readme.md')
  if (!readme) {
    styleFiles.value.unshift(createStyleFileDraft('README.md', `# ${name}\n`))
    activeFileId.value = styleFiles.value[0]?.id ?? ''
    return
  }

  readme.content = replaceFirstMarkdownHeading(readme.content, name)
}

const replaceFirstMarkdownHeading = (content: string, heading: string) => {
  const lines = content.replace(/\r\n?/g, '\n').split('\n')
  const firstContentIndex = lines.findIndex((line) => line.trim())
  if (firstContentIndex >= 0 && /^#\s+/.test(lines[firstContentIndex].trim())) {
    lines[firstContentIndex] = `# ${heading}`
    return lines.join('\n')
  }
  return [`# ${heading}`, '', ...lines].join('\n')
}

const validateFileDrafts = (files: VisualStyleFilePayload[]) => {
  if (files.length === 0) return '至少需要保留一个 Markdown 文件'

  const seen = new Set<string>()
  for (const file of files) {
    const path = file.path
    if (!path) return '请输入 Markdown 文件名'
    const parts = path.split('/')
    if (
      path.startsWith('/') ||
      parts.some((part) => !part || part === '.' || part === '..') ||
      parts[0]?.toLowerCase() === 'images'
    ) {
      return `文件路径不合法：${path}`
    }
    if (!path.toLowerCase().endsWith('.md')) {
      return `文件必须使用 .md 后缀：${path}`
    }
    const dedupeKey = path.toLowerCase()
    if (seen.has(dedupeKey)) {
      return `文件名重复：${path}`
    }
    seen.add(dedupeKey)
  }
  return ''
}

const getNewImagePayloads = (): VisualStyleImagePayload[] => (
  styleImages.value
    .filter((image) => image.data)
    .map((image) => ({
      filename: image.filename,
      data: image.data,
    }))
)

const saveExistingStyle = async (stylePath: string, files: VisualStyleFilePayload[]) => {
  const finalPaths = new Set(files.map((file) => file.path.toLowerCase()))
  const renamedOriginalPaths = styleFiles.value
    .filter((file) => file.originalPath && normalizeMarkdownPath(file.originalPath).toLowerCase() !== normalizeMarkdownPath(file.path).toLowerCase())
    .map((file) => file.originalPath)
  const fileDeletePaths = uniqueValues([...removedFilePaths.value, ...renamedOriginalPaths])
    .filter((filePath) => !finalPaths.has(normalizeMarkdownPath(filePath).toLowerCase()))

  await Promise.all(files.map((file) => writeVisualStyleFileApi(stylePath, file.path, file)))
  await Promise.all(fileDeletePaths.map((filePath) => deleteVisualStyleFileApi(stylePath, filePath)))

  const newImages = getNewImagePayloads()
  const newImageNames = new Set(newImages.map((image) => image.filename.toLowerCase()))
  const imageDeleteNames = uniqueValues(removedImageFilenames.value)
    .filter((filename) => !newImageNames.has(filename.toLowerCase()))

  await Promise.all(imageDeleteNames.map((filename) => deleteVisualStyleImageApi(stylePath, filename)))
  await Promise.all(newImages.map((image) => writeVisualStyleImageApi(stylePath, image.filename, image)))
}

const uniqueValues = (values: string[]) => Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)))

const getErrorMessage = (error: unknown) => {
  const axiosError = error as AxiosError<{ detail?: string }>
  return axiosError.response?.data?.detail || axiosError.message || '请求失败'
}

</script>

<style scoped>
.style-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}

.style-image-section,
.style-file-section {
  margin-top: 18px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.022), rgba(255, 255, 255, 0.012));
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  padding: 16px;
}

.dialog-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.dialog-section-head h3 {
  margin: 0;
  color: #f2f4f8;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0;
}

.dialog-section-head span {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.12);
  border: 1px solid rgba(37, 99, 235, 0.32);
}

.style-image-strip {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.32) transparent;
}

.style-image-tile,
.style-image-add {
  flex: 0 0 auto;
  position: relative;
  width: 144px;
  height: 100px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: #1a1f29;
  color: #e6edf3;
  cursor: pointer;
  overflow: hidden;
  font-family: inherit;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.style-image-tile::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 1;
  background:
    linear-gradient(180deg, rgba(7, 10, 16, 0) 36%, rgba(7, 10, 16, 0.55) 72%, rgba(7, 10, 16, 0.94) 100%),
    radial-gradient(120% 80% at 50% 0%, rgba(255, 255, 255, 0.08) 0%, transparent 60%);
  pointer-events: none;
}

.style-image-tile:hover,
.style-image-add:hover {
  border-color: rgba(255, 255, 255, 0.22);
  box-shadow: 0 18px 36px rgba(0, 0, 0, 0.34);
  transform: translateY(-2px);
}

.style-image-tile:focus-visible,
.style-image-add:focus-visible {
  outline: none;
  border-color: rgba(147, 197, 253, 0.7);
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55),
    0 0 0 4px rgba(37, 99, 235, 0.18);
}

.style-image-tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.style-image-name {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 7px;
  z-index: 2;
  color: #ffffff;
  font-size: 11px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.72);
}

.style-image-delete {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 3;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 1.5px solid rgba(255, 255, 255, 0.55);
  border-radius: 999px;
  color: #ffffff;
  background: rgba(15, 20, 28, 0.62);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.style-image-delete:hover,
.style-image-delete:focus-visible {
  outline: none;
  background: rgba(220, 38, 38, 0.88);
  border-color: rgba(254, 202, 202, 0.9);
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.22);
}

.style-image-add {
  display: grid;
  place-items: center;
  color: #bfdbfe;
  font-size: 22px;
  border-style: dashed;
  background: rgba(37, 99, 235, 0.08);
}

.style-file-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
  border-bottom-color: rgba(255, 255, 255, 0.08);
}

.style-file-tabs :deep(.el-tabs__nav) {
  border-color: rgba(255, 255, 255, 0.08);
}

.style-file-tabs :deep(.el-tabs__item) {
  color: #aab4bf;
  border-color: rgba(255, 255, 255, 0.08);
  font-weight: 600;
}

.style-file-tabs :deep(.el-tabs__item.is-active) {
  color: #ffffff;
  background: rgba(37, 99, 235, 0.16);
}

.style-file-empty {
  padding: 16px 0;
}

.style-file-meta {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}

.style-file-path {
  flex: 1;
}

.style-file-remove {
  flex: 0 0 auto;
}

.markdown-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.markdown-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.markdown-textarea :deep(.el-textarea__inner) {
  min-height: 420px !important;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.65;
}

.markdown-preview {
  min-height: 420px;
  max-height: 560px;
  overflow: auto;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: #0c1015;
  color: #d7dee8;
  line-height: 1.7;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.32) transparent;
}

.markdown-preview :deep(h1),
.markdown-preview :deep(h2),
.markdown-preview :deep(h3),
.markdown-preview :deep(h4),
.markdown-preview :deep(h5),
.markdown-preview :deep(h6) {
  margin: 0 0 12px;
  color: #f8fafc;
  line-height: 1.35;
}

.markdown-preview :deep(p) {
  margin: 0 0 10px;
}

.markdown-preview :deep(blockquote) {
  margin: 0 0 12px;
  padding: 8px 12px;
  border-left: 3px solid rgba(96, 165, 250, 0.82);
  border-radius: 8px;
  background: rgba(37, 99, 235, 0.12);
  color: #dbeafe;
}

.markdown-preview :deep(ul),
.markdown-preview :deep(ol) {
  margin: 0 0 12px;
  padding-left: 22px;
}

.markdown-preview :deep(code) {
  border-radius: 5px;
  padding: 1px 5px;
  background: rgba(148, 163, 184, 0.18);
  color: #bfdbfe;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.markdown-preview :deep(pre) {
  overflow: auto;
  margin: 0 0 12px;
  padding: 12px;
  border-radius: 10px;
  background: #0b1020;
}

.markdown-preview :deep(pre code) {
  padding: 0;
  background: transparent;
}

@media (max-width: 960px) {
  .style-form-grid,
  .markdown-workspace {
    grid-template-columns: minmax(0, 1fr);
  }

  .style-file-meta {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>

<style>
.visual-style-dialog {
  width: min(1120px, calc(100vw - 32px)) !important;
  overflow: hidden;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  color: #e6edf3;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  font-family: "Microsoft YaHei", "PingFang SC", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
  font-feature-settings: "ss01", "ss02", "cv11";
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.visual-style-dialog .el-dialog__header {
  margin: 0;
  padding: 24px 30px 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: transparent;
}

.visual-style-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 0;
}

.visual-style-dialog .el-dialog__headerbtn {
  top: 18px;
  right: 22px;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.visual-style-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
  font-size: 20px;
  font-weight: 400;
}

.visual-style-dialog .el-dialog__headerbtn:hover,
.visual-style-dialog .el-dialog__headerbtn:focus {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.18);
}

.visual-style-dialog .el-dialog__headerbtn:hover .el-dialog__close,
.visual-style-dialog .el-dialog__headerbtn:focus .el-dialog__close {
  color: #ffffff;
}

.visual-style-dialog .el-dialog__body {
  max-height: min(78vh, 780px);
  overflow-y: auto;
  padding: 22px 30px 8px;
  color: #b8c2cc;
  background: transparent;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.visual-style-dialog .el-dialog__body::-webkit-scrollbar,
.visual-style-dialog .el-textarea__inner::-webkit-scrollbar,
.visual-style-dialog .markdown-preview::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.visual-style-dialog .el-dialog__body::-webkit-scrollbar-track,
.visual-style-dialog .el-textarea__inner::-webkit-scrollbar-track,
.visual-style-dialog .markdown-preview::-webkit-scrollbar-track {
  background: transparent;
}

.visual-style-dialog .el-dialog__body::-webkit-scrollbar-thumb,
.visual-style-dialog .el-textarea__inner::-webkit-scrollbar-thumb,
.visual-style-dialog .markdown-preview::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.visual-style-dialog .el-dialog__body::-webkit-scrollbar-thumb:hover,
.visual-style-dialog .el-textarea__inner::-webkit-scrollbar-thumb:hover,
.visual-style-dialog .markdown-preview::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.visual-style-dialog .el-dialog__footer {
  padding: 18px 30px 24px;
  background: transparent;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.visual-style-dialog .el-form-item {
  margin-bottom: 18px;
}

.visual-style-dialog .el-form-item__label {
  color: #d5dce4;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  padding: 0 0 8px;
}

.visual-style-dialog .el-form-item.is-error .el-form-item__error {
  color: #fca5a5;
  padding-top: 4px;
}

.visual-style-dialog .el-input__wrapper {
  min-height: 46px;
  padding: 0 14px;
}

.visual-style-dialog .el-input__wrapper,
.visual-style-dialog .el-textarea__inner {
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border: none;
  border-radius: 12px;
  color: #e6edf3;
  font-size: 14px;
  font-family: inherit;
  transition: box-shadow 0.18s ease, background-color 0.18s ease;
}

.visual-style-dialog .el-textarea__inner {
  padding: 12px 14px;
  resize: vertical;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.visual-style-dialog .el-input__wrapper:hover,
.visual-style-dialog .el-textarea__inner:hover {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.visual-style-dialog .el-input__wrapper.is-focus,
.visual-style-dialog .el-textarea__inner:focus {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.visual-style-dialog .el-input.is-disabled .el-input__wrapper {
  background-color: rgba(255, 255, 255, 0.02);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.04) inset;
  color: #6e7681;
}

.visual-style-dialog .el-input.is-disabled .el-input__inner {
  color: #6e7681;
  -webkit-text-fill-color: #6e7681;
}

.visual-style-dialog .el-input__inner,
.visual-style-dialog .el-textarea__inner {
  color: #e6edf3;
}

.visual-style-dialog .el-input__inner::placeholder,
.visual-style-dialog .el-textarea__inner::placeholder {
  color: #7e8893;
}

.visual-style-dialog .el-input__count,
.visual-style-dialog .el-input__count-inner,
.visual-style-dialog .el-textarea .el-input__count,
.visual-style-dialog .el-input .el-input__count {
  color: #6e7681 !important;
  background: transparent !important;
  background-color: transparent !important;
  font-size: 12px;
}

.visual-style-dialog .el-button {
  min-height: 38px;
  border-radius: 10px;
  font-weight: 700;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.visual-style-dialog .el-dialog__footer .el-button {
  height: 42px;
  min-width: 88px;
  padding: 0 20px;
  border-radius: 12px;
  font-size: 14px;
}

.visual-style-dialog .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.12);
  color: #e6edf3;
}

.visual-style-dialog .el-button:not(.el-button--primary):not(.el-button--danger):hover,
.visual-style-dialog .el-button:not(.el-button--primary):not(.el-button--danger):focus {
  background-color: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
}

.visual-style-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):hover,
.visual-style-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):focus,
.visual-style-dialog .el-dialog__footer .el-button--primary:hover,
.visual-style-dialog .el-dialog__footer .el-button--primary:focus {
  transform: translateY(-1px);
}

.visual-style-dialog .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
}

.visual-style-dialog .el-button--primary:hover,
.visual-style-dialog .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
  box-shadow: 0 16px 30px rgba(37, 99, 235, 0.28);
}

.visual-style-dialog .el-button--danger {
  background-color: #dc2626;
  border-color: #dc2626;
  box-shadow: 0 8px 18px rgba(220, 38, 38, 0.22);
}

.visual-style-dialog .el-button--danger:hover,
.visual-style-dialog .el-button--danger:focus {
  background-color: #b91c1c;
  border-color: #b91c1c;
}

.visual-style-dialog .el-button:active {
  transform: translateY(0);
}
</style>