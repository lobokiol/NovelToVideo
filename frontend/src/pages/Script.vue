<template>
  <main class="script-page">
    <div class="app-shell">
      <ScriptSidebar
        @project="goProject"
        @production="goProduction"
        @tasks="goTasks"
        @settings="settingsVisible = true"
        @coming-soon="showComingSoon"
      />

      <section class="main-panel">
        <ScriptPageHeader
          @back-screenwriting="goScreenwriting"
          @import="openBatchImportDialog"
          @create="openCreateDialog"
          @production="goProduction"
          @assets="assetDrawerVisible = true"
        />

        <ScriptToolbar
          v-model:search-keyword="searchKeyword"
          :scripts-count="scripts.length"
          :selected-count="selectedIds.length"
          :is-all-selected="isAllSelected"
          :extracting="extracting"
          :exporting="exporting"
          :sort-options="SORT_OPTIONS"
          :sort-field="sortField"
          :sort-order="sortOrder"
          :current-sort-label="currentSortLabel"
          @sort="onSortCommand"
          @toggle-select-all="toggleSelectAll"
          @extract="batchExtractAssets"
          @export="batchExportZip"
          @batch-delete="batchDeleteSelected"
        />

        <ScriptCardGrid
          v-model:current-page="currentPage"
          :loading="loading"
          :filtered-count="filteredScripts.length"
          :scripts="paginatedScripts"
          :selected-ids="selectedIds"
          :page-size="pageSize"
          :extracting-single="extractingSingle"
          @open-edit="openEditDialog"
          @toggle-select="toggleSelect"
          @toggle-lock="toggleLock"
          @extract-single="extractSingleEpisode"
          @card-command="onCardCommand"
        />
      </section>
    </div>

    <Settings v-model="settingsVisible" />

    <ScriptAssetDrawer
      v-model="assetDrawerVisible"
      :project-public-id="projectPublicId"
      :text-model-id="currentTextModel"
      :image-model-id="currentImageModel"
      @changed="loadEpisodes"
    />

    <ScriptEditDialog
      ref="formRef"
      v-model="formDialogVisible"
      :title="formDialogTitle"
      :form="form"
      :rules="formRules"
      :submitting="submitting"
      :grouped-asset-options="groupedAssetOptions"
      :asset-type-label="assetTypeLabel"
      @submit="submitForm"
    />

    <ScriptImportDialog
      ref="importTableRef"
      v-model="importDialogVisible"
      v-model:import-step="importStep"
      v-model:import-mode="importMode"
      v-model:import-raw="importRaw"
      v-model:split-preset-key="splitPresetKey"
      :import-file-name="importFileName"
      :bulk-parsed="bulkParsed"
      :bulk-drag-index="bulkDragIndex"
      :bulk-drop-index="bulkDropIndex"
      :bulk-drop-position="bulkDropPosition"
      :split-parsed="splitParsed"
      :split-presets="splitPresets"
      :current-split-rule="currentSplitRule"
      :flag-options="FLAG_OPTIONS"
      :import-parsed="importParsed"
      :import-selected-count="importSelectedRows.length"
      :import-submitting="importSubmitting"
      @close="resetImportState"
      @bulk-file-change="handleBulkImportFile"
      @split-file-change="handleSplitImportFile"
      @bulk-drag-start="onBulkDragStart"
      @bulk-drag-over="onBulkDragOver"
      @bulk-drag-leave="onBulkDragLeave"
      @bulk-drop="onBulkDrop"
      @bulk-drag-end="onBulkDragEnd"
      @remove-bulk-item="removeBulkItem"
      @update-title-pattern="updateSplitRuleTitlePattern"
      @update-title-flags="updateSplitRuleTitleFlags"
      @selection-change="onImportSelectionChange"
      @preview-edit="openPreviewEdit"
      @next="goImportNext"
      @submit="submitImport"
    />

    <ScriptPreviewEditDialog
      v-model="previewEditVisible"
      :draft="previewEditDraft"
      @save="savePreviewEdit"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormRules } from 'element-plus'
import {
  createScriptPlanApi,
  deleteScriptEpisodeApi,
  deleteScriptPlanApi,
  exportScriptEpisodesApi,
  listProjectEpisodesApi,
  lockScriptEpisodeApi,
  unlockScriptEpisodeApi,
  updateScriptEpisodeApi,
  updateScriptPlanApi,
  type ScriptAsset as EpisodeAssetItem,
  type ScriptEpisodeListItem,
} from '@/api/script'
import {
  extractAssetsApi,
  listAssetsApi,
  setEpisodeAssetsApi,
  type AssetItem,
} from '@/api/asset'
import { listProjectsApi, type ProjectRecord } from '@/api/project'
import Settings from '../components/Settings.vue'
import ScriptCardGrid from '@/components/script/ScriptCardGrid.vue'
import ScriptEditDialog from '@/components/script/ScriptEditDialog.vue'
import ScriptImportDialog from '@/components/script/ScriptImportDialog.vue'
import ScriptPageHeader from '@/components/script/ScriptPageHeader.vue'
import ScriptAssetDrawer from '@/components/script/ScriptAssetDrawer.vue'
import ScriptPreviewEditDialog from '@/components/script/ScriptPreviewEditDialog.vue'
import ScriptSidebar from '@/components/script/ScriptSidebar.vue'
import ScriptToolbar from '@/components/script/ScriptToolbar.vue'
import '@/components/script/script.css'
import type {
  AssetType,
  ImportScriptDraft,
  ImportSplitPreset,
  PreviewEditDraft,
  ScriptAsset,
  ScriptEditForm,
  ScriptRecord,
  SortField,
  SortOrder,
} from '@/components/script/types'

const router = useRouter()
const route = useRoute()

// 当前项目公开 ID：常规从项目页进入为 ?id=，从创作工作台同步跳转为 ?projectId=。
const projectPublicId = ref(
  String(route.query.id ?? route.query.projectId ?? '').trim(),
)

// 从后端错误响应中提取可读的中文提示。
const errorDetail = (error: unknown, fallback: string): string => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (error instanceof Error && error.message) return error.message
  return fallback
}

const scripts = ref<ScriptRecord[]>([])
const allAssets = ref<ScriptAsset[]>([])
const currentProject = ref<ProjectRecord | null>(null)

const pad2 = (value: number) => String(value).padStart(2, '0')

const toScriptAsset = (asset: AssetItem): ScriptAsset => ({
  publicId: asset.publicId,
  name: asset.name,
  summary: asset.summary,
  description: asset.description,
  assetType: asset.assetType,
})

const assetsByPublicId = computed(() => new Map(allAssets.value.map((asset) => [asset.publicId, asset])))

const toScriptAssetFromEpisode = (asset: EpisodeAssetItem): ScriptAsset => {
  const fullAsset = assetsByPublicId.value.get(asset.publicId)
  return {
    publicId: asset.publicId,
    name: asset.name,
    summary: fullAsset?.summary || asset.summary,
    description: fullAsset?.description || asset.description,
    assetType: asset.assetType,
  }
}

const loadCurrentProject = async () => {
  if (!projectPublicId.value) {
    currentProject.value = null
    return
  }
  const { data } = await listProjectsApi()
  currentProject.value = data.find((item) => item.public_id === projectPublicId.value) ?? null
}

const assetDrawerVisible = ref(false)

const loadAssets = async () => {
  if (!projectPublicId.value) {
    allAssets.value = []
    return
  }
  const { data } = await listAssetsApi(projectPublicId.value)
  allAssets.value = data.map(toScriptAsset)
}

const currentTextModel = computed(() => currentProject.value?.text_model?.trim() || '')
const currentImageModel = computed(() => currentProject.value?.image_model?.trim() || '')

const ensureTextModel = () => {
  if (currentTextModel.value) return true
  ElMessage.warning('请先在项目设置中选择文本模型，再抽取资产')
  return false
}

// 把后端分集平铺项映射为列表卡片记录；关联资产由后端通过 AssetEpisode 返回。
const toRecord = (item: ScriptEpisodeListItem): ScriptRecord => {
  const episodeLabel = `EP${pad2(item.episodeIndex)}`
  const name = item.planTitle
    ? `${item.planTitle} ${episodeLabel}：${item.title}`
    : `${episodeLabel}：${item.title}`
  const relatedAssets = (item.assets ?? []).map(toScriptAssetFromEpisode)
  return {
    id: item.publicId,
    planPublicId: item.planPublicId,
    planTitle: item.planTitle,
    episodeIndex: item.episodeIndex,
    episodeTitle: item.title,
    name,
    intro: item.summary,
    content: item.body,
    extractState: relatedAssets.length > 0 ? 2 : 0,  // 有关联资产→已提取(2)，否则→待提取(0)
    errorReason: null,
    relatedAssets,
    isLocked: item.isLocked,
    version: item.version,
    createdAt: item.updatedAt,
  }
}

const loadEpisodes = async (options: { showLoading?: boolean } = {}) => {
  if (!projectPublicId.value) {
    scripts.value = []
    ElMessage.warning('未指定项目，请从项目列表进入剧本管理')
    return
  }
  const showLoading = options.showLoading !== false
  if (showLoading) loading.value = true
  try {
    await Promise.all([loadCurrentProject(), loadAssets()])
    const { data } = await listProjectEpisodesApi(projectPublicId.value)
    scripts.value = data.map(toRecord)
  } catch (error) {
    scripts.value = []
    ElMessage.error(errorDetail(error, '加载剧本列表失败'))
  } finally {
    if (showLoading) loading.value = false
  }
}

onMounted(() => {
  void loadEpisodes()
})

const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(6)
const loading = ref(false)
const extracting = ref(false)
const exporting = ref(false)
const extractingSingle = reactive<Record<string, boolean>>({})  // 单 EP 抽取 loading 状态

const selectedIds = ref<string[]>([])
const settingsVisible = ref(false)

const formDialogVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingId = ref<string | null>(null)
const submitting = ref(false)
const formRef = ref<InstanceType<typeof ScriptEditDialog>>()

const form = reactive<ScriptEditForm>({
  name: '',
  content: '',
  relatedAssetIds: [],
})

const formRules: FormRules<ScriptEditForm> = {
  name: [
    { required: true, message: '请输入剧本名称', trigger: 'blur' },
    { max: 120, message: '剧本名称不超过 120 个字符', trigger: 'blur' },
  ],
  content: [{ required: true, message: '请输入剧本正文', trigger: 'blur' }],
}

const formDialogTitle = computed(() => (formMode.value === 'create' ? '新建剧本' : '编辑剧本'))

const resetForm = () => {
  form.name = ''
  form.content = ''
  form.relatedAssetIds = []
  formRef.value?.clearValidate()
}

const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  role: '人物',
  faction: '势力',
  prop: '道具',
  scene: '场景',
}

const ASSET_TYPE_ORDER: AssetType[] = ['role', 'faction', 'prop', 'scene']

const assetTypeLabel = (type: AssetType) => ASSET_TYPE_LABELS[type]

const assetOptions = computed<ScriptAsset[]>(() => {
  return [...allAssets.value].sort((a, b) => {
    if (a.assetType !== b.assetType) {
      return ASSET_TYPE_ORDER.indexOf(a.assetType) - ASSET_TYPE_ORDER.indexOf(b.assetType)
    }
    return a.name.localeCompare(b.name, 'zh-CN')
  })
})

const groupedAssetOptions = computed<{ type: AssetType; items: ScriptAsset[] }[]>(() => {
  const groups: { type: AssetType; items: ScriptAsset[] }[] = []
  ASSET_TYPE_ORDER.forEach((type) => {
    const items = assetOptions.value.filter((asset) => asset.assetType === type)
    if (items.length > 0) groups.push({ type, items })
  })
  return groups
})

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: 'id', label: '集号' },
  { value: 'createdAt', label: '创建时间' },
  { value: 'name', label: '剧本名称' },
  { value: 'extractState', label: '提取状态' },
  { value: 'assetCount', label: '资产数量' },
]

const sortField = ref<SortField>('id')
const sortOrder = ref<SortOrder>('asc')

const currentSortLabel = computed(
  () => SORT_OPTIONS.find((opt) => opt.value === sortField.value)?.label ?? '创建时间',
)

const onSortCommand = (cmd: SortField) => {
  if (sortField.value === cmd) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = cmd
    sortOrder.value = 'desc'
  }
  currentPage.value = 1
}

const filteredScripts = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  const dir = sortOrder.value === 'asc' ? 1 : -1
  return scripts.value
    .filter((item) => (keyword ? item.name.toLowerCase().includes(keyword) : true))
    .sort((a, b) => {
      switch (sortField.value) {
        case 'id': {
          // 同一部剧的分集聚在一起，再按集号升序
          if (a.planPublicId !== b.planPublicId) {
            return a.planPublicId.localeCompare(b.planPublicId) * dir
          }
          return (a.episodeIndex - b.episodeIndex) * dir
        }
        case 'name':
          return a.name.localeCompare(b.name, 'zh-CN') * dir
        case 'extractState':
          return (a.extractState - b.extractState) * dir
        case 'assetCount':
          return (a.relatedAssets.length - b.relatedAssets.length) * dir
        case 'createdAt':
        default:
          return a.createdAt.localeCompare(b.createdAt) * dir
      }
    })
})

const paginatedScripts = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredScripts.value.slice(start, start + pageSize.value)
})

const isAllSelected = computed(
  () => filteredScripts.value.length > 0 && selectedIds.value.length === filteredScripts.value.length,
)

const toggleSelect = (id: string, checked: boolean) => {
  if (checked) {
    if (!selectedIds.value.includes(id)) {
      selectedIds.value = [...selectedIds.value, id]
    }
  } else {
    selectedIds.value = selectedIds.value.filter((sid) => sid !== id)
  }
}

const openEditDialog = (script: ScriptRecord) => {
  formMode.value = 'edit'
  editingId.value = script.id
  form.name = script.episodeTitle
  form.content = script.content
  form.relatedAssetIds = script.relatedAssets.map((asset) => asset.publicId)
  formDialogVisible.value = true
  nextTick(() => formRef.value?.clearValidate())
}

const deleteScript = async (script: ScriptRecord) => {
  try {
    await ElMessageBox.confirm(
      `确定删除本集「${script.name}」吗？删除后不可恢复。`,
      '删除本集',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        customClass: 'script-dark-messagebox',
      },
    )
    await deleteScriptEpisodeApi(projectPublicId.value, script.id)
    selectedIds.value = selectedIds.value.filter((sid) => sid !== script.id)
    ElMessage.success('本集已删除')
    await loadEpisodes()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorDetail(error, '删除失败'))
  }
}

// 锁定/解锁本集：锁定后从创作工作台同步时不会覆盖该集。
const toggleLock = async (script: ScriptRecord) => {
  if (!projectPublicId.value) return
  try {
    if (script.isLocked) {
      await unlockScriptEpisodeApi(projectPublicId.value, script.id)
      ElMessage.success('已解锁本集')
    } else {
      await lockScriptEpisodeApi(projectPublicId.value, script.id)
      ElMessage.success('已锁定本集')
    }
    await loadEpisodes()
  } catch (error) {
    ElMessage.error(errorDetail(error, '操作失败'))
  }
}

// 重命名分集所属的整部剧本（更新其下全部分集的归属剧名）。
const renameScriptPlan = async (script: ScriptRecord) => {
  if (!projectPublicId.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      '为这部剧本输入新的名称，将更新其下全部分集的归属剧名。',
      '重命名剧本',
      {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputValue: script.planTitle,
        inputPlaceholder: '请输入剧本名称',
        inputValidator: (v: string) => (v && v.trim() ? true : '剧本名称不能为空'),
        customClass: 'script-dark-messagebox',
      },
    )
    const title = value.trim()
    if (!title || title === script.planTitle) return
    await updateScriptPlanApi(projectPublicId.value, script.planPublicId, { title })
    ElMessage.success('剧本已重命名')
    await loadEpisodes()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorDetail(error, '重命名失败'))
  }
}

// 删除分集所属的整部剧本（含其全部分集）。
const deleteScriptPlan = async (script: ScriptRecord) => {
  if (!projectPublicId.value) return
  const planEpisodes = scripts.value.filter((item) => item.planPublicId === script.planPublicId)
  const planName = script.planTitle || '未命名剧本'
  try {
    await ElMessageBox.confirm(
      `确定删除整部剧本「${planName}」吗？将一并删除其 ${planEpisodes.length} 集，且不可恢复。`,
      '删除整部剧本',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        customClass: 'script-dark-messagebox',
      },
    )
    await deleteScriptPlanApi(projectPublicId.value, script.planPublicId)
    const removedIds = new Set(planEpisodes.map((item) => item.id))
    selectedIds.value = selectedIds.value.filter((sid) => !removedIds.has(sid))
    ElMessage.success('整部剧本已删除')
    await loadEpisodes()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorDetail(error, '删除失败'))
  }
}

// 卡片「更多」菜单分发。
const onCardCommand = (command: string, script: ScriptRecord) => {
  switch (command) {
    case 'edit':
      openEditDialog(script)
      break
    case 'delete':
      void deleteScript(script)
      break
    case 'rename-plan':
      void renameScriptPlan(script)
      break
    case 'delete-plan':
      void deleteScriptPlan(script)
      break
  }
}

const toggleSelectAll = () => {
  if (isAllSelected.value) {
    selectedIds.value = []
  } else {
    selectedIds.value = filteredScripts.value.map((item) => item.id)
  }
}

const openCreateDialog = () => {
  formMode.value = 'create'
  editingId.value = null
  resetForm()
  formDialogVisible.value = true
}

const submitForm = async () => {
  if (!projectPublicId.value) {
    ElMessage.warning('未指定项目，无法保存')
    return
  }

  submitting.value = true
  try {
    if (formMode.value === 'create') {
      await createScriptPlanApi(projectPublicId.value, {
        title: form.name.trim(),
        content: form.content,
      })
      ElMessage.success('剧本已新建')
    } else if (editingId.value) {
      await updateScriptEpisodeApi(projectPublicId.value, editingId.value, {
        title: form.name.trim(),
        body: form.content,
      })
      await setEpisodeAssetsApi(projectPublicId.value, {
        episodePublicId: editingId.value,
        assetPublicIds: form.relatedAssetIds,
      })
      ElMessage.success('剧本已更新')
    }
    formDialogVisible.value = false
    await loadEpisodes()
  } catch (error) {
    ElMessage.error(errorDetail(error, '保存失败'))
  } finally {
    submitting.value = false
  }
}

const openBatchImportDialog = () => {
  resetImportState()
  importDialogVisible.value = true
}

const goProduction = () => {
  if (!projectPublicId.value) {
    ElMessage.warning('缺少项目信息，无法进入制作工作台')
    return
  }
  router.push({ path: '/production', query: { id: projectPublicId.value } })
}

const batchExtractAssets = async () => {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先勾选要抽取资产的分集')
    return
  }
  if (!projectPublicId.value || !ensureTextModel()) return
  extracting.value = true
  try {
    await extractAssetsApi(projectPublicId.value, {
      modelId: currentTextModel.value,
      episodePublicIds: selectedIds.value,
    })
    ElMessage.success('资产抽取任务已提交')
    void loadEpisodes({ showLoading: false })
  } catch (error) {
    ElMessage.error(errorDetail(error, '资产抽取失败'))
  } finally {
    extracting.value = false
  }
}
const extractSingleEpisode = async (script: ScriptRecord) => {
  if (!projectPublicId.value || !ensureTextModel()) return
  extractingSingle[script.id] = true
  try {
    await extractAssetsApi(projectPublicId.value, {
      modelId: currentTextModel.value,
      episodePublicIds: [script.id],
    })
    ElMessage.success('资产抽取任务已提交')
    void loadEpisodes({ showLoading: false })
  } catch (error) {
    ElMessage.error(errorDetail(error, '资产抽取失败'))
  } finally {
    extractingSingle[script.id] = false
  }
}
const parseDownloadFilename = (contentDisposition = '') => {
  const encoded = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded)
    } catch {
      return encoded
    }
  }
  const plain = contentDisposition.match(/filename="?([^";]+)"?/i)?.[1]
  return plain || `scripts-${Date.now()}.zip`
}

const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

const batchExportZip = async () => {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先勾选要导出的剧本')
    return
  }
  if (!projectPublicId.value) {
    ElMessage.warning('未指定项目，无法导出')
    return
  }
  exporting.value = true
  try {
    const response = await exportScriptEpisodesApi(projectPublicId.value, {
      episodePublicIds: selectedIds.value,
    })
    const filename = parseDownloadFilename(response.headers['content-disposition'])
    downloadBlob(response.data, filename)
    const count = response.headers['x-script-episode-count'] || selectedIds.value.length
    ElMessage.success(`已导出 ${count} 集剧本`)
  } catch (error) {
    ElMessage.error(errorDetail(error, '导出剧本失败'))
  } finally {
    exporting.value = false
  }
}

const batchDeleteSelected = async () => {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedIds.value.length} 集吗？删除后不可恢复。`,
      '批量删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        customClass: 'script-dark-messagebox',
      },
    )
    const ids = [...selectedIds.value]
    await Promise.all(ids.map((id) => deleteScriptEpisodeApi(projectPublicId.value, id)))
    ElMessage.success(`已删除 ${ids.length} 集`)
    selectedIds.value = []
    await loadEpisodes()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorDetail(error, '批量删除失败'))
  }
}

const importDialogVisible = ref(false)
const importStep = ref<1 | 2>(1)
const importMode = ref<'bulk' | 'split'>('bulk')

const importRaw = ref('')
const importFileName = ref('')
const bulkParsed = ref<ImportScriptDraft[]>([])
const importTableRef = ref<InstanceType<typeof ScriptImportDialog>>()
const importSelectedRows = ref<ImportScriptDraft[]>([])
const importSubmitting = ref(false)

const bulkDragIndex = ref<number | null>(null)
const bulkDropIndex = ref<number | null>(null)
const bulkDropPosition = ref<'before' | 'after' | null>(null)

const onBulkDragStart = (event: DragEvent, index: number) => {
  bulkDragIndex.value = index
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(index))
  }
}

const onBulkDragOver = (event: DragEvent, index: number) => {
  if (bulkDragIndex.value === null) return
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const offset = event.clientY - rect.top
  bulkDropIndex.value = index
  bulkDropPosition.value = offset < rect.height / 2 ? 'before' : 'after'
}

const onBulkDragLeave = (index: number) => {
  if (bulkDropIndex.value === index) {
    bulkDropIndex.value = null
    bulkDropPosition.value = null
  }
}

const onBulkDrop = (index: number) => {
  const from = bulkDragIndex.value
  const position = bulkDropPosition.value
  bulkDragIndex.value = null
  bulkDropIndex.value = null
  bulkDropPosition.value = null
  if (from === null || from === index) return
  let to = index + (position === 'after' ? 1 : 0)
  if (from < to) to -= 1
  if (to === from) return
  const list = bulkParsed.value.slice()
  const [moved] = list.splice(from, 1)
  list.splice(to, 0, moved)
  bulkParsed.value = list
}

const onBulkDragEnd = () => {
  bulkDragIndex.value = null
  bulkDropIndex.value = null
  bulkDropPosition.value = null
}

const splitPresets = ref<ImportSplitPreset[]>([
  {
    key: 'md-h1',
    label: '一级标题（# ）',
    description: '识别 Markdown 一级标题作为剧本名，逐份切分',
    titlePattern: '^\\s*#\\s+[^\\n\\r]+$',
    titleFlagsList: ['m'],
  },
  {
    key: 'md-h2',
    label: '二级标题（## ）',
    description: '识别 Markdown 二级标题，常用于「## 第 01 集」',
    titlePattern: '^\\s*##\\s+[^\\n\\r]+$',
    titleFlagsList: ['m'],
  },
  {
    key: 'ep',
    label: 'EP 编号（EP01 / EP 1）',
    description: '识别 EP + 数字开头的标题行',
    titlePattern: '^\.\*\?EP\\s*\\d+\.\*?$',
    titleFlagsList: ['i', 'm'],
  },
  {
    key: 'cn-ep',
    label: '第 X 集',
    description: '识别「第一集 / 第 01 集 / 第 N 集」',
    titlePattern: '^\\s*第\\s*[0-9一二三四五六七八九十百千零〇两]+\\s*集[^\\n\\r]*$',
    titleFlagsList: ['m'],
  },
  {
    key: 'custom',
    label: '自定义正则',
    description: '手动指定剧本标题的匹配正则',
    titlePattern: '',
    titleFlagsList: ['m'],
  },
])

const splitPresetKey = ref<string>('md-h1')

const currentSplitRule = computed<ImportSplitPreset>(
  () =>
    splitPresets.value.find((p) => p.key === splitPresetKey.value) ||
    splitPresets.value[0],
)

const updateCurrentSplitRule = (patch: Partial<Pick<ImportSplitPreset, 'titlePattern' | 'titleFlagsList'>>) => {
  const index = splitPresets.value.findIndex((preset) => preset.key === currentSplitRule.value.key)
  if (index < 0) return
  splitPresets.value[index] = {
    ...splitPresets.value[index],
    ...patch,
  }
}

const updateSplitRuleTitlePattern = (value: string) => {
  updateCurrentSplitRule({ titlePattern: value })
}

const updateSplitRuleTitleFlags = (value: string[]) => {
  updateCurrentSplitRule({ titleFlagsList: value })
}

const parseScriptText = (
  raw: string,
  rule: ImportSplitPreset,
): ImportScriptDraft[] => {
  if (!raw || !rule.titlePattern) return []
  const flags = rule.titleFlagsList.includes('m')
    ? rule.titleFlagsList.join('')
    : `${rule.titleFlagsList.join('')}m`
  let titleRegex: RegExp
  try {
    titleRegex = new RegExp(rule.titlePattern, flags)
  } catch {
    return []
  }
  const lines = raw.split(/\r?\n/)
  const drafts: ImportScriptDraft[] = []
  let currentTitle = ''
  let currentBody: string[] = []

  const lineRegex = (() => {
    const lineFlags = rule.titleFlagsList.filter((f) => f !== 'm').join('')
    try {
      return new RegExp(rule.titlePattern, lineFlags)
    } catch {
      return null
    }
  })()
  if (!lineRegex) return []

  const flush = () => {
    if (currentTitle) {
      const name = currentTitle.replace(/^\s*#+\s*/, '').trim() || currentTitle.trim()
      drafts.push({
        key: drafts.length + 1,
        name,
        detail: '文本切分',
        content: [currentTitle, ...currentBody].join('\n').trim(),
      })
    }
    currentBody = []
  }

  for (const line of lines) {
    if (lineRegex.test(line)) {
      flush()
      currentTitle = line
    } else if (currentTitle) {
      currentBody.push(line)
    }
  }
  flush()
  // 确保至少匹配过：若 titleRegex 全文未命中，drafts 为空
  if (drafts.length === 0 && !titleRegex.test(raw)) return []
  return drafts
}

const splitParsed = computed(() =>
  parseScriptText(importRaw.value, currentSplitRule.value),
)

const importParsed = ref<ImportScriptDraft[]>([])

const snapshotImportParsed = () => {
  const source = importMode.value === 'bulk' ? bulkParsed.value : splitParsed.value
  importParsed.value = source.map((item) => ({ ...item }))
}

const previewEditVisible = ref(false)
const previewEditIndex = ref<number>(-1)
const previewEditDraft = reactive<PreviewEditDraft>({ name: '', content: '', detail: '' })

const openPreviewEdit = (row: ImportScriptDraft, index: number) => {
  previewEditIndex.value = index
  previewEditDraft.name = row.name
  previewEditDraft.content = row.content
  previewEditDraft.detail = row.detail
  previewEditVisible.value = true
}

const savePreviewEdit = () => {
  if (previewEditIndex.value < 0) return
  const trimmedName = previewEditDraft.name.trim()
  if (!trimmedName) {
    ElMessage.warning('剧本名称不能为空')
    return
  }
  const target = importParsed.value[previewEditIndex.value]
  if (!target) {
    previewEditVisible.value = false
    return
  }
  const wasSelected = importSelectedRows.value.some((row) => row.key === target.key)
  const updated: ImportScriptDraft = {
    ...target,
    name: trimmedName,
    content: previewEditDraft.content,
  }
  importParsed.value.splice(previewEditIndex.value, 1, updated)
  previewEditVisible.value = false
  if (wasSelected) {
    nextTick(() => {
      importTableRef.value?.toggleRowSelection?.(updated, true)
    })
  }
  ElMessage.success('已更新该集剧本')
}

const FLAG_OPTIONS = [
  { value: 'g', label: '全局匹配（所有出现处都替换）' },
  { value: 'i', label: '忽略大小写' },
  { value: 'm', label: '多行模式（^ $ 匹配每一行）' },
  { value: 's', label: '点号匹配换行' },
]

const detectEncoding = (buffer: ArrayBuffer): 'utf-8' | 'gbk' => {
  const bytes = new Uint8Array(buffer)
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return 'utf-8'
  }
  if (
    bytes.length >= 2 &&
    ((bytes[0] === 0xff && bytes[1] === 0xfe) ||
      (bytes[0] === 0xfe && bytes[1] === 0xff))
  ) {
    return 'utf-8'
  }
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

const extractTextFromTxt = async (
  buffer: ArrayBuffer,
): Promise<{ text: string; detail: string }> => {
  const encoding = detectEncoding(buffer)
  const decoder = new TextDecoder(encoding)
  return { text: decoder.decode(buffer), detail: `${encoding.toUpperCase()} 编码` }
}

const extractTextFromDocx = async (
  buffer: ArrayBuffer,
): Promise<{ text: string; detail: string }> => {
  const mammoth = await import('mammoth/mammoth.browser')
  const result = await mammoth.extractRawText({ arrayBuffer: buffer })
  return { text: result.value || '', detail: 'DOCX 文档' }
}

const extractTextFromPdf = async (
  buffer: ArrayBuffer,
): Promise<{ text: string; detail: string }> => {
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
    for (const item of content.items as Array<{
      str: string
      transform?: number[]
      hasEOL?: boolean
    }>) {
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

const validateImportFile = (file: File): boolean => {
  if (/\.doc$/i.test(file.name)) {
    ElMessage.error('暂不支持旧版 .doc（二进制 Word 97-2003），请另存为 .docx 后再上传')
    return false
  }
  if (!/\.(txt|md|markdown|docx|pdf)$/i.test(file.name)) {
    ElMessage.error('仅支持 .md / .txt / .docx / .pdf')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error(`「${file.name}」超过 10 MB 限制`)
    return false
  }
  return true
}

const extractFileText = async (
  file: File,
): Promise<{ text: string; detail: string }> => {
  const buffer = await readFileAsArrayBuffer(file)
  if (/\.docx$/i.test(file.name)) return extractTextFromDocx(buffer)
  if (/\.pdf$/i.test(file.name)) return extractTextFromPdf(buffer)
  return extractTextFromTxt(buffer)
}

const fileNameToScriptName = (fname: string) =>
  fname.replace(/\.[^.]+$/, '').trim() || fname

const handleSplitImportFile = async (uploadFile: { raw?: File; name: string }) => {
  const rawFile = uploadFile?.raw
  if (!rawFile) {
    ElMessage.error('文件读取失败，请重新选择')
    return
  }
  if (!validateImportFile(rawFile)) return
  const loading = ElMessage({
    message: `正在解析 ${rawFile.name}…`,
    duration: 0,
    type: 'info',
  })
  try {
    const result = await extractFileText(rawFile)
    importRaw.value = result.text
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

let bulkSeq = 0
const handleBulkImportFile = async (uploadFile: { raw?: File; name: string }) => {
  const rawFile = uploadFile?.raw
  if (!rawFile) {
    ElMessage.error('文件读取失败，请重新选择')
    return
  }
  if (!validateImportFile(rawFile)) return
  const loading = ElMessage({
    message: `正在解析 ${rawFile.name}…`,
    duration: 0,
    type: 'info',
  })
  try {
    const result = await extractFileText(rawFile)
    const name = fileNameToScriptName(rawFile.name)
    if (!result.text.trim()) {
      ElMessage.warning(`「${rawFile.name}」未读取到文本内容，已跳过`)
      return
    }
    bulkSeq += 1
    bulkParsed.value.push({
      key: bulkSeq,
      name,
      detail: `${rawFile.name} · ${result.detail}`,
      content: result.text.trim(),
    })
    ElMessage.success(`已就绪：${name}（${result.text.length} 字符）`)
  } catch (err) {
    ElMessage.error(`解析失败：${(err as Error).message}`)
  } finally {
    loading.close()
  }
}

const removeBulkItem = (idx: number) => {
  bulkParsed.value.splice(idx, 1)
}

const onImportSelectionChange = (rows: ImportScriptDraft[]) => {
  importSelectedRows.value = rows
}

const goImportNext = () => {
  if (importMode.value === 'bulk') {
    if (bulkParsed.value.length === 0) {
      ElMessage.warning('请先上传至少一份剧本文件')
      return
    }
  } else {
    if (!importRaw.value.trim()) {
      ElMessage.warning('请先上传文件或粘贴剧本全文')
      return
    }
    if (splitParsed.value.length === 0) {
      ElMessage.warning('未识别到剧本，请检查切分规则')
      return
    }
  }
  importStep.value = 2
  snapshotImportParsed()
  nextTick(() => {
    importTableRef.value?.toggleAllSelection?.()
  })
}

const submitImport = async () => {
  if (importSelectedRows.value.length === 0) {
    ElMessage.warning('请至少选择一份剧本')
    return
  }
  if (!projectPublicId.value) {
    ElMessage.warning('未指定项目，无法导入')
    return
  }
  importSubmitting.value = true
  let success = 0
  const failed: string[] = []
  for (const draft of importSelectedRows.value) {
    try {
      await createScriptPlanApi(projectPublicId.value, {
        title: draft.name,
        content: draft.content,
      })
      success += 1
    } catch {
      failed.push(draft.name)
    }
  }
  importSubmitting.value = false

  if (success > 0) {
    ElMessage.success(`已导入 ${success} 份剧本`)
  }
  if (failed.length > 0) {
    ElMessage.warning(`${failed.length} 份导入失败（可能未解析出分集）：${failed.join('、')}`)
  }
  if (success > 0) {
    importDialogVisible.value = false
    await loadEpisodes()
  }
}

const resetImportState = () => {
  importStep.value = 1
  importMode.value = 'bulk'
  importRaw.value = ''
  importFileName.value = ''
  bulkParsed.value = []
  importParsed.value = []
  importSelectedRows.value = []
  importSubmitting.value = false
  splitPresetKey.value = 'md-h1'
}

const goProject = () => {
  router.push('/project')
}

// 返回当前项目的剧本创作页面（创作页以 ?id= 读取项目）。
const goScreenwriting = () => {
  if (!projectPublicId.value) {
    ElMessage.warning('缺少项目信息，无法返回剧本创作')
    return
  }
  router.push({ path: '/screenwriting', query: { id: projectPublicId.value } })
}

const goTasks = (jobPublicId = '') => {
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  router.push({
    path: '/tasks',
    query: {
      id: projectPublicId.value,
      type: 'script',
      from: route.fullPath,
      ...(jobPublicId ? { job: jobPublicId } : {}),
    },
  })
}

const showComingSoon = () => {
  ElMessage.info('功能开发中')
}
</script>