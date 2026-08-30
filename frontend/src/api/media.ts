import request from '@/request'

export type MediaType = 'image' | 'video' | 'audio'
export type MediaStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface MediaAssetRecord {
  publicId: string
  mediaType: MediaType
  source: string
  status: MediaStatus
  scopeType: string
  scopePublicId: string
  mediaRole: string
  modelId: string
  prompt: string
  params: string
  seed: string
  url: string
  mimeType: string
  fileSize: number
  width: number
  height: number
  durationMs: number
  costTokens: number
  taskJobPublicId: string
  errorMessage: string
  createdAt: string
  updatedAt: string
}

export interface MediaListQuery {
  mediaType?: string
  status?: string
  source?: string
  scopeType?: string
  scopePublicId?: string
  mediaRole?: string
  limit?: number
  offset?: number
}

export interface MediaUploadOptions {
  /** 上传文件名；Blob（如剪辑台合成成片）必填，File 默认取其自身名称。 */
  filename?: string
  scopeType?: string
  scopePublicId?: string
  mediaRole?: string
}

const MEDIA_UPLOAD_TIMEOUT_MS = 600000

const projectMediaPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/media`
)

/** 媒体原始内容 URL，可直接用于 <img>/<video> src。 */
export const mediaContentUrl = (projectPublicId: string, mediaPublicId: string) => (
  `/api${projectMediaPath(projectPublicId)}/${encodeURIComponent(mediaPublicId)}/content`
)

/** 图像媒体缩略图 URL（服务端懒生成并缓存）。 */
export const mediaThumbnailUrl = (projectPublicId: string, mediaPublicId: string) => (
  `/api${projectMediaPath(projectPublicId)}/${encodeURIComponent(mediaPublicId)}/thumbnail`
)

export const listProjectMediaApi = (
  projectPublicId: string,
  query: MediaListQuery = {},
) => (
  request.get<MediaAssetRecord[]>(projectMediaPath(projectPublicId), { params: query })
)

/** 把候选媒体设为其挂靠对象的选定媒体（final），同对象同类型的其他选定自动降级。 */
export const selectProjectMediaApi = (
  projectPublicId: string,
  mediaPublicId: string,
) => (
  request.post<MediaAssetRecord>(
    `${projectMediaPath(projectPublicId)}/${encodeURIComponent(mediaPublicId)}/select`,
  )
)

export const uploadProjectMediaApi = (
  projectPublicId: string,
  file: File | Blob,
  options: MediaUploadOptions = {},
) => {
  const form = new FormData()
  const filename = options.filename || (file instanceof File ? file.name : '')
  if (filename) form.append('file', file, filename)
  else form.append('file', file)
  return request.post<MediaAssetRecord>(
    `${projectMediaPath(projectPublicId)}/upload`,
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: {
        scopeType: options.scopeType,
        scopePublicId: options.scopePublicId,
        mediaRole: options.mediaRole,
      },
      timeout: MEDIA_UPLOAD_TIMEOUT_MS,
    },
  )
}

export const deleteProjectMediaApi = (
  projectPublicId: string,
  mediaPublicId: string,
) => (
  request.delete<void>(`${projectMediaPath(projectPublicId)}/${encodeURIComponent(mediaPublicId)}`)
)