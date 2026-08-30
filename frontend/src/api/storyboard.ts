import request from '@/request'
import { toTaskJob, type BackendTaskJobDetail, type TaskJobResponse } from '@/api/task'

export type StoryboardShotStatus = 'draft' | 'locked'

export interface StoryboardGeneratePayload {
  modelId: string
  episodePublicIds?: string[]
  /** 按镜头重生成：只重写这些镜头的分镜脚本字段；留空表示整集生成。 */
  shotPublicIds?: string[]
  artStyle?: string
  directorStyle?: string
}

export interface StoryboardShot {
  publicId: string
  episodePublicId: string
  episodeIndex: number
  sceneNumber: string
  shotIndex: number
  shotSize: string
  camera: string
  action: string
  dialogue: string
  durationSeconds: number
  assetPublicIds: string
  assetNames: string
  artStyleKey: string
  directorStyleKey: string
  modelId: string
  prompt: string
  negativePrompt: string
  referenceMediaPublicId: string
  lastFrameMediaPublicId: string
  seed: string
  status: StoryboardShotStatus
  createdAt: string
  updatedAt: string
}

export interface StoryboardShotUpdatePayload {
  sceneNumber?: string
  shotSize?: string
  camera?: string
  action?: string
  dialogue?: string
  durationSeconds?: number
  assetPublicIds?: string
  assetNames?: string
  artStyleKey?: string
  directorStyleKey?: string
  modelId?: string
  prompt?: string
  negativePrompt?: string
  referenceMediaPublicId?: string
  lastFrameMediaPublicId?: string
  seed?: string
}

const STORYBOARD_TASK_SUBMIT_TIMEOUT_MS = 60000

const projectStoryboardPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/storyboards`
)

export const generateStoryboardsApi = (
  projectPublicId: string,
  payload: StoryboardGeneratePayload,
) => (
  request
    .post<BackendTaskJobDetail>(
      `${projectStoryboardPath(projectPublicId)}/generate`,
      payload,
      { timeout: STORYBOARD_TASK_SUBMIT_TIMEOUT_MS },
    )
    .then((response) => ({
      ...response,
      data: toTaskJob(response.data, projectPublicId, response.data.items),
    } as typeof response & { data: TaskJobResponse }))
)

export interface StoryboardGridImagePayload {
  gridSize: number
  imageSize?: string
  episodePublicIds?: string[]
  shotPublicIds?: string[]
  onlyMissing?: boolean
  modelId?: string
}

export const generateStoryboardGridImagesApi = (
  projectPublicId: string,
  payload: StoryboardGridImagePayload,
) => (
  request
    .post<BackendTaskJobDetail>(
      `${projectStoryboardPath(projectPublicId)}/images/generate`,
      payload,
      { timeout: STORYBOARD_TASK_SUBMIT_TIMEOUT_MS },
    )
    .then((response) => ({
      ...response,
      data: toTaskJob(response.data, projectPublicId, response.data.items),
    } as typeof response & { data: TaskJobResponse }))
)

export interface StoryboardShotVideoPayload {
  episodePublicIds?: string[]
  shotPublicIds?: string[]
  /** 仅为尚无选定视频的镜头生成；重复提交同镜头会新增候选。 */
  onlyMissing?: boolean
  /** 是否随视频同生音频（需模型支持音画同生）。 */
  generateAudio?: boolean
  /** 本次单镜生成时长，Seedance 支持 4～15 秒。 */
  durationSeconds?: number
  /** 视频比例（9:16 / 16:9 等）；留空沿用项目设置。 */
  ratio?: string
  /** 分辨率档位（720p / 1080p 等）；留空沿用分镜图继承值。 */
  resolution?: string
  /** 每个目标镜头生成的候选数量；批量入口省略时为 1。 */
  quantity?: number
}

export const generateStoryboardShotVideosApi = (
  projectPublicId: string,
  payload: StoryboardShotVideoPayload,
) => (
  request
    .post<BackendTaskJobDetail>(
      `${projectStoryboardPath(projectPublicId)}/videos/generate`,
      payload,
      { timeout: STORYBOARD_TASK_SUBMIT_TIMEOUT_MS },
    )
    .then((response) => ({
      ...response,
      data: toTaskJob(response.data, projectPublicId, response.data.items),
    } as typeof response & { data: TaskJobResponse }))
)

export const listStoryboardShotsApi = (
  projectPublicId: string,
  episodePublicId = '',
) => (
  request.get<StoryboardShot[]>(projectStoryboardPath(projectPublicId), {
    params: episodePublicId ? { episodePublicId } : undefined,
  })
)

export const updateStoryboardShotApi = (
  projectPublicId: string,
  shotPublicId: string,
  payload: StoryboardShotUpdatePayload,
) => (
  request.put<StoryboardShot>(
    `${projectStoryboardPath(projectPublicId)}/${encodeURIComponent(shotPublicId)}`,
    payload,
  )
)

export const lockStoryboardShotApi = (
  projectPublicId: string,
  shotPublicId: string,
) => (
  request.post<StoryboardShot>(
    `${projectStoryboardPath(projectPublicId)}/${encodeURIComponent(shotPublicId)}/lock`,
  )
)

export const unlockStoryboardShotApi = (
  projectPublicId: string,
  shotPublicId: string,
) => (
  request.post<StoryboardShot>(
    `${projectStoryboardPath(projectPublicId)}/${encodeURIComponent(shotPublicId)}/unlock`,
  )
)

export const deleteStoryboardShotApi = (
  projectPublicId: string,
  shotPublicId: string,
) => (
  request.delete<void>(
    `${projectStoryboardPath(projectPublicId)}/${encodeURIComponent(shotPublicId)}`,
  )
)