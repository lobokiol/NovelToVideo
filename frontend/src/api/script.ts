import request from '@/request'

export interface ScriptScene {
  number: string
  title: string
  location: string
  dayNight: string
  interiorExterior: string
}

export interface ScriptEpisode {
  publicId: string
  episodeIndex: number
  title: string
  summary: string
  body: string
  scenes: ScriptScene[]
  version: number
  isLocked: boolean
}

export interface ScriptPlanSummary {
  publicId: string
  title: string
  totalEpisodes: string
  episodeDuration: string
  status: string
  updatedAt: string
}

export interface ScriptPlanDetail extends ScriptPlanSummary {
  sourceRange: string
  platformSpec: string
  style: string
  paywall: string
  episodes: ScriptEpisode[]
}

export interface ScriptAsset {
  publicId: string
  assetType: 'role' | 'faction' | 'prop' | 'scene'
  name: string
  summary: string
  description: string
  status: 'draft' | 'locked'
}

// 分集平铺列表项：携带所属剧本计划信息，供「我的剧本」卡片直接展示与编辑。
export interface ScriptEpisodeListItem {
  publicId: string
  planPublicId: string
  planTitle: string
  episodeIndex: number
  title: string
  summary: string
  body: string
  scenes: ScriptScene[]
  version: number
  isLocked: boolean
  updatedAt: string
  assets: ScriptAsset[]
}

export interface ScriptPlanCreatePayload {
  title?: string
  content: string
}

export interface ScriptEpisodeUpdatePayload {
  title?: string
  summary?: string
  body?: string
}

export interface ScriptExportPayload {
  episodePublicIds: string[]
}

const projectScriptPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/scripts`
)

export const listScriptPlansApi = (projectPublicId: string) => (
  request.get<ScriptPlanSummary[]>(`${projectScriptPath(projectPublicId)}/plans`)
)

export const getScriptPlanApi = (projectPublicId: string, planPublicId: string) => (
  request.get<ScriptPlanDetail>(
    `${projectScriptPath(projectPublicId)}/plans/${encodeURIComponent(planPublicId)}`,
  )
)

export const syncScriptPlanApi = (projectPublicId: string, title = '') => (
  request.post<ScriptPlanDetail>(
    `${projectScriptPath(projectPublicId)}/sync`,
    { title },
    { timeout: 60000 },
  )
)

// 平铺列出项目下当前用户的全部分集（按所属计划更新时间倒序、集号正序）。
export const listProjectEpisodesApi = (projectPublicId: string) => (
  request.get<ScriptEpisodeListItem[]>(`${projectScriptPath(projectPublicId)}/episodes`)
)

// 手动新建/导入整部剧本：把整段 Markdown 解析为分集落库。
export const createScriptPlanApi = (
  projectPublicId: string,
  payload: ScriptPlanCreatePayload,
) => (
  request.post<ScriptPlanDetail>(
    `${projectScriptPath(projectPublicId)}/plans`,
    payload,
    { timeout: 60000 },
  )
)

// 导出选中的剧本分集，后端返回 ZIP 文件流。
export const exportScriptEpisodesApi = (
  projectPublicId: string,
  payload: ScriptExportPayload,
) => (
  request.post<Blob>(
    `${projectScriptPath(projectPublicId)}/export`,
    payload,
    {
      responseType: 'blob',
      timeout: 60000,
    },
  )
)

// 编辑单集：正文变更会在后端重解析场次并递增版本。
export const updateScriptEpisodeApi = (
  projectPublicId: string,
  episodePublicId: string,
  payload: ScriptEpisodeUpdatePayload,
) => (
  request.put<ScriptEpisodeListItem>(
    `${projectScriptPath(projectPublicId)}/episodes/${encodeURIComponent(episodePublicId)}`,
    payload,
  )
)

// 删除单个分集。
export const deleteScriptEpisodeApi = (
  projectPublicId: string,
  episodePublicId: string,
) => (
  request.delete<void>(
    `${projectScriptPath(projectPublicId)}/episodes/${encodeURIComponent(episodePublicId)}`,
  )
)

export interface ScriptPlanUpdatePayload {
  title: string
}

// 更新剧本计划元信息（当前支持改剧名）。
export const updateScriptPlanApi = (
  projectPublicId: string,
  planPublicId: string,
  payload: ScriptPlanUpdatePayload,
) => (
  request.put<ScriptPlanDetail>(
    `${projectScriptPath(projectPublicId)}/plans/${encodeURIComponent(planPublicId)}`,
    payload,
  )
)

// 删除整部剧本计划及其全部分集。
export const deleteScriptPlanApi = (
  projectPublicId: string,
  planPublicId: string,
) => (
  request.delete<void>(
    `${projectScriptPath(projectPublicId)}/plans/${encodeURIComponent(planPublicId)}`,
  )
)

// 锁定分集：后续从创作工作台同步时不覆盖该集。
export const lockScriptEpisodeApi = (
  projectPublicId: string,
  episodePublicId: string,
) => (
  request.patch<ScriptEpisodeListItem>(
    `${projectScriptPath(projectPublicId)}/episodes/${encodeURIComponent(episodePublicId)}/lock`,
  )
)

// 解除分集锁定。
export const unlockScriptEpisodeApi = (
  projectPublicId: string,
  episodePublicId: string,
) => (
  request.patch<ScriptEpisodeListItem>(
    `${projectScriptPath(projectPublicId)}/episodes/${encodeURIComponent(episodePublicId)}/unlock`,
  )
)