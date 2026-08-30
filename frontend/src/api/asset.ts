import request from '@/request'
import { toTaskJob, type BackendTaskJobDetail, type TaskJobResponse } from '@/api/task'

export type AssetType = 'role' | 'faction' | 'prop' | 'scene'

export interface AssetItem {
  publicId: string
  assetType: AssetType
  name: string
  keyword: string
  colors: string
  summary: string
  description: string
  details: string
  accessories: string
  status: 'draft' | 'locked'
  mainAsset: boolean
  variantLabel: string
  createdAt: string
  updatedAt: string
  // 资产封面缩略图 URL；由后续媒体阶段（参考图/生成图）填充，当前可能为空。
  thumbnailUrl?: string
}

export interface AssetExtractPayload {
  modelId: string
  episodePublicIds?: string[]
}

export interface AssetAutocompletePayload {
  modelId: string
  assetPublicIds: string[]
}

export interface AssetAssociationPayload {
  episodePublicId: string
  assetPublicIds: string[]
}

export interface AssetAssociationResult {
  affected: number
  assets: AssetItem[]
}

const projectAssetPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/assets`
)
const ASSET_TASK_SUBMIT_TIMEOUT_MS = 60000

// 资产抽取只提交异步任务，真正的模型调用由 Worker 执行。
export const extractAssetsApi = (
  projectPublicId: string,
  payload: AssetExtractPayload,
) => (
  request
    .post<BackendTaskJobDetail>(
      `${projectAssetPath(projectPublicId)}/extract`,
      payload,
      { timeout: ASSET_TASK_SUBMIT_TIMEOUT_MS },
    )
    .then((response) => ({
      ...response,
      data: toTaskJob(response.data, projectPublicId, response.data.items),
    } as typeof response & { data: TaskJobResponse }))
)

// 资产描述补全同样只提交异步任务，真正的模型调用由 Worker 执行。
export const autocompleteAssetsApi = (
  projectPublicId: string,
  payload: AssetAutocompletePayload,
) => (
  request
    .post<BackendTaskJobDetail>(
      `${projectAssetPath(projectPublicId)}/autocomplete`,
      payload,
      { timeout: ASSET_TASK_SUBMIT_TIMEOUT_MS },
    )
    .then((response) => ({
      ...response,
      data: toTaskJob(response.data, projectPublicId, response.data.items),
    } as typeof response & { data: TaskJobResponse }))
)

export const listAssetsApi = (projectPublicId: string, assetType = '') => {
  const params = assetType ? { assetType } : undefined
  return request.get<AssetItem[]>(projectAssetPath(projectPublicId), params ? { params } : undefined)
}

export const setEpisodeAssetsApi = (
  projectPublicId: string,
  payload: AssetAssociationPayload,
) => request.post<AssetAssociationResult>(`${projectAssetPath(projectPublicId)}/associations`, payload)

// ---------------------------------------------------------------------------
// 资产管理：分页树 / 引用 / 手动增改 / 语音子资产 / 批量与级联删除
// ---------------------------------------------------------------------------

export interface AssetReferenceItem {
  episodePublicId: string
  episodeIndex: number
  episodeTitle: string
  planPublicId: string
  planTitle: string
  source: 'association' | 'text'
  snippet: string
}

export interface AssetManageItem extends AssetItem {
  children: AssetManageItem[]
  references: AssetReferenceItem[]
}

export interface AssetListQuery {
  assetType?: AssetType | ''
  keyword?: string
  status?: 'draft' | 'locked' | ''
  referenced?: 'with' | 'without' | ''
  page?: number
  pageSize?: number
}

export interface AssetManageListResult {
  items: AssetManageItem[]
  total: number
  page: number
  pageSize: number
  pages: number
}

export interface AssetCreatePayload {
  assetType: AssetType
  name: string
  keyword?: string
  colors?: string
  summary?: string
  description?: string
  details?: string
  accessories?: string
  mainAsset?: boolean
  variantLabel?: string
}

export interface AssetUpdatePayload {
  name?: string
  keyword?: string
  colors?: string
  summary?: string
  description?: string
  details?: string
  accessories?: string
  variantLabel?: string
}

export interface AssetParentUpdatePayload {
  parentAssetPublicId?: string | null
}

export interface AssetBatchPayload {
  assetPublicIds: string[]
  operation: 'lock' | 'unlock' | 'delete'
}

export interface AssetBatchResult {
  affected: number
  assets: AssetItem[]
}

export const listManagedAssetsApi = (projectPublicId: string, query: AssetListQuery = {}) => {
  const params: Record<string, string | number> = {}
  if (query.assetType) params.assetType = query.assetType
  if (query.keyword) params.keyword = query.keyword
  if (query.status) params.status = query.status
  if (query.referenced) params.referenced = query.referenced
  params.page = query.page ?? 1
  params.pageSize = query.pageSize ?? 20
  return request.get<AssetManageListResult>(`${projectAssetPath(projectPublicId)}/manage`, { params })
}

export const createAssetApi = (projectPublicId: string, payload: AssetCreatePayload) =>
  request.post<AssetItem>(projectAssetPath(projectPublicId), payload)

export const updateAssetApi = (
  projectPublicId: string,
  assetPublicId: string,
  payload: AssetUpdatePayload,
) => request.put<AssetItem>(`${projectAssetPath(projectPublicId)}/${encodeURIComponent(assetPublicId)}`, payload)

export const setAssetParentApi = (
  projectPublicId: string,
  assetPublicId: string,
  payload: AssetParentUpdatePayload,
) => request.put<AssetItem>(
  `${projectAssetPath(projectPublicId)}/${encodeURIComponent(assetPublicId)}/parent`,
  payload,
)

export const batchAssetsApi = (projectPublicId: string, payload: AssetBatchPayload) =>
  request.post<AssetBatchResult>(`${projectAssetPath(projectPublicId)}/batch`, payload)

export const deleteAssetApi = (projectPublicId: string, assetPublicId: string) =>
  request.delete<void>(`${projectAssetPath(projectPublicId)}/${encodeURIComponent(assetPublicId)}`)

export const lockAssetApi = (projectPublicId: string, assetPublicId: string) =>
  request.post<AssetItem>(`${projectAssetPath(projectPublicId)}/${encodeURIComponent(assetPublicId)}/lock`)

export const unlockAssetApi = (projectPublicId: string, assetPublicId: string) =>
  request.post<AssetItem>(`${projectAssetPath(projectPublicId)}/${encodeURIComponent(assetPublicId)}/unlock`)

// ---------------------------------------------------------------------------
// 资产媒体（图像生成 / 画廊 / 封面 / 删除）
// ---------------------------------------------------------------------------

export interface AssetMediaItem {
  publicId: string
  mediaType: string
  mediaRole: string
  url: string
  mimeType: string
  width: number
  height: number
  prompt: string
  createdAt: string
}

export interface AssetImageGeneratePayload {
  modelId: string
  assetPublicIds: string[]
  prompt?: string
  aspectRatio?: string
  imageSize?: string
  referenceMediaPublicIds?: string[]
  count?: number
}

// 配图生成只提交异步任务，真正的模型调用由 Worker 执行。
export const generateAssetImagesApi = (
  projectPublicId: string,
  payload: AssetImageGeneratePayload,
) => (
  request
    .post<BackendTaskJobDetail>(
      `${projectAssetPath(projectPublicId)}/media/generate`,
      payload,
      { timeout: ASSET_TASK_SUBMIT_TIMEOUT_MS },
    )
    .then((response) => ({
      ...response,
      data: toTaskJob(response.data, projectPublicId, response.data.items),
    } as typeof response & { data: TaskJobResponse }))
)

export const synthesizeAssetImagePromptApi = (
  projectPublicId: string,
  assetPublicId: string,
) => (
  request
    .post<BackendTaskJobDetail>(
      `${projectAssetPath(projectPublicId)}/${encodeURIComponent(assetPublicId)}/media/prompt`,
      undefined,
      { timeout: ASSET_TASK_SUBMIT_TIMEOUT_MS },
    )
    .then((response) => ({
      ...response,
      data: toTaskJob(response.data, projectPublicId, response.data.items),
    } as typeof response & { data: TaskJobResponse }))
)

export const listAssetMediaApi = (projectPublicId: string, assetPublicId: string) =>
  request.get<AssetMediaItem[]>(
    `${projectAssetPath(projectPublicId)}/${encodeURIComponent(assetPublicId)}/media`,
  )

export const uploadAssetReferenceImageApi = (
  projectPublicId: string,
  assetPublicId: string,
  file: File,
) => {
  const form = new FormData()
  form.append('file', file)
  return request.post<AssetMediaItem>(
    `${projectAssetPath(projectPublicId)}/${encodeURIComponent(assetPublicId)}/media/reference`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: ASSET_TASK_SUBMIT_TIMEOUT_MS },
  )
}

export const setAssetMediaCoverApi = (projectPublicId: string, mediaPublicId: string) =>
  request.post<AssetMediaItem>(
    `${projectAssetPath(projectPublicId)}/media/${encodeURIComponent(mediaPublicId)}/cover`,
  )

export const deleteAssetMediaApi = (projectPublicId: string, mediaPublicId: string) =>
  request.delete<void>(
    `${projectAssetPath(projectPublicId)}/media/${encodeURIComponent(mediaPublicId)}`,
  )
