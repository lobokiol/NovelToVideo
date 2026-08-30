import request from '@/request'

export type ProjectVideoMode =
  | 'text'
  | 'singleImage'
  | 'multiReference'
  | 'startEndRequired'
  | 'endFrameOptional'
  | 'startFrameOptional'

export type ProjectMemberRole = 'owner' | 'admin' | 'manager' | 'editor' | 'viewer'

export interface ProjectRecord {
  id: number
  public_id: string
  owner_id: string
  name: string
  intro: string
  project_type: string
  content_type: string
  art_style: string
  director_manual: string
  video_ratio: string
  text_model: string
  image_model: string
  video_model: string
  tts_model: string
  image_quality: string
  mode: ProjectVideoMode
  my_role?: ProjectMemberRole | null
  sort_order: number
  created_at: string
  updated_at: string
  disabled_at?: string | null
}

export interface ProjectPayload {
  name: string
  intro: string
  project_type: string
  content_type: string
  art_style: string
  director_manual: string
  video_ratio: string
  text_model: string
  image_model: string
  video_model: string
  tts_model: string
  image_quality: string
  mode: ProjectVideoMode
}

export interface ProjectMemberRecord {
  id: number
  project_id: number
  user_public_id: string
  user_email: string | null
  role: ProjectMemberRole
  joined_at: string
}

export interface ProjectMemberInvitePayload {
  user_public_id: string
  role: ProjectMemberRole
}

export interface UserRecord {
  public_id: string
  username: string
  nickname?: string | null
  email?: string | null
  avatar_url?: string | null
  sort_order: number
  is_superuser: boolean
  disabled_at?: string | null
  last_login_at?: string | null
  created_at: string
  updated_at: string
}

export interface VisualStyleFileRecord {
  path: string
  content: string
  size_bytes: number
}

export interface VisualStyleImageRecord {
  filename: string
  path: string
  url: string
  size_bytes: number
}

export interface VisualStyleRecord {
  style_path: string
  name: string
  files: VisualStyleFileRecord[]
  images: VisualStyleImageRecord[]
}

export interface VisualStyleFilePayload {
  path: string
  content: string
}

export interface VisualStyleImagePayload {
  filename: string
  data: string
}

export interface VisualStyleCreatePayload {
  style_path: string
  name: string
  files: VisualStyleFilePayload[]
  images: VisualStyleImagePayload[]
}


export interface DirectorManualFileRecord {
  path: string
  content: string
  size_bytes: number
}

export interface DirectorManualImageRecord {
  filename: string
  path: string
  url: string
  size_bytes: number
}

export interface DirectorManualRecord {
  manual_path: string
  name: string
  files: DirectorManualFileRecord[]
  images: DirectorManualImageRecord[]
}

export interface DirectorManualFilePayload {
  path: string
  content: string
}

export interface DirectorManualImagePayload {
  filename: string
  data: string
}

export interface DirectorManualCreatePayload {
  manual_path: string
  name: string
  files: DirectorManualFilePayload[]
  images: DirectorManualImagePayload[]
}


// export 表示把当前函数暴露给外界，允许其他模块通过 import {函数名} from "模块名"进行调用
export const listProjectsApi = () => request.get<ProjectRecord[]>('/projects/')

export const listVisualStylesApi = () => request.get<VisualStyleRecord[]>('/projects/visual-styles')

export const createVisualStyleApi = (data: VisualStyleCreatePayload) => (
  request.post<VisualStyleRecord>('/projects/visual-styles', data)
)

export const getVisualStyleApi = (stylePath: string) => (
  request.get<VisualStyleRecord>(`/projects/visual-styles/${encodeUrlSegment(stylePath)}`)
)

export const writeVisualStyleFileApi = (
  stylePath: string,
  filePath: string,
  data: VisualStyleFilePayload,
) => (
  request.put<VisualStyleFileRecord>(
    `/projects/visual-styles/${encodeUrlSegment(stylePath)}/files/${encodeUrlPath(filePath)}`,
    data,
  )
)

export const deleteVisualStyleFileApi = (stylePath: string, filePath: string) => (
  request.delete(`/projects/visual-styles/${encodeUrlSegment(stylePath)}/files/${encodeUrlPath(filePath)}`)
)

export const writeVisualStyleImageApi = (
  stylePath: string,
  filename: string,
  data: VisualStyleImagePayload,
) => (
  request.put<VisualStyleImageRecord>(
    `/projects/visual-styles/${encodeUrlSegment(stylePath)}/images/${encodeUrlSegment(filename)}`,
    data,
  )
)

export const deleteVisualStyleImageApi = (stylePath: string, filename: string) => (
  request.delete(`/projects/visual-styles/${encodeUrlSegment(stylePath)}/images/${encodeUrlSegment(filename)}`)
)

export const listDirectorManualsApi = () => request.get<DirectorManualRecord[]>('/projects/director-manuals')

export const createDirectorManualApi = (data: DirectorManualCreatePayload) => (
  request.post<DirectorManualRecord>('/projects/director-manuals', data)
)

export const writeDirectorManualFileApi = (
  manualPath: string,
  filePath: string,
  data: DirectorManualFilePayload,
) => (
  request.put<DirectorManualFileRecord>(
    `/projects/director-manuals/${encodeUrlSegment(manualPath)}/files/${encodeUrlPath(filePath)}`,
    data,
  )
)

export const deleteDirectorManualFileApi = (manualPath: string, filePath: string) => (
  request.delete(`/projects/director-manuals/${encodeUrlSegment(manualPath)}/files/${encodeUrlPath(filePath)}`)
)

export const writeDirectorManualImageApi = (
  manualPath: string,
  filename: string,
  data: DirectorManualImagePayload,
) => (
  request.put<DirectorManualImageRecord>(
    `/projects/director-manuals/${encodeUrlSegment(manualPath)}/images/${encodeUrlSegment(filename)}`,
    data,
  )
)

export const deleteDirectorManualImageApi = (manualPath: string, filename: string) => (
  request.delete(`/projects/director-manuals/${encodeUrlSegment(manualPath)}/images/${encodeUrlSegment(filename)}`)
)

export const searchProjectsByNameApi = (name: string) => (
  request.get<ProjectRecord[]>('/projects/search/by-name', { params: { name } })
)

export const createProjectApi = (data: ProjectPayload) => request.post<ProjectRecord>('/projects/', data)

export const updateProjectApi = (publicId: string, data: Partial<ProjectPayload>) => (
  request.put<ProjectRecord>(`/projects/${publicId}`, data)
)

export const disableProjectApi = (publicId: string) => request.patch<ProjectRecord>(`/projects/${publicId}/disable`)

export const enableProjectApi = (publicId: string) => request.patch<ProjectRecord>(`/projects/${publicId}/enable`)

export const deleteProjectApi = (publicId: string) => request.delete(`/projects/${publicId}`)

export const listProjectMembersApi = (publicId: string) => (
  request.get<ProjectMemberRecord[]>(`/projects/${publicId}/members`)
)

export const searchProjectMemberCandidatesApi = (publicId: string, keyword: string) => (
  request.get<UserRecord[]>(`/projects/${publicId}/members/candidates`, { params: { keyword } })
)

export const inviteProjectMemberApi = (publicId: string, data: ProjectMemberInvitePayload) => (
  request.post<ProjectMemberRecord>(`/projects/${publicId}/members/invitations`, data)
)

export const updateProjectMemberRoleApi = (
  publicId: string,
  userPublicId: string,
  role: ProjectMemberRole,
) => (
  request.patch<ProjectMemberRecord>(`/projects/${publicId}/members/${userPublicId}`, null, { params: { role } })
)

export const removeProjectMemberApi = (publicId: string, userPublicId: string) => (
  request.delete(`/projects/${publicId}/members/${userPublicId}`)
)

const encodeUrlSegment = (value: string) => encodeURIComponent(value.trim())

const encodeUrlPath = (value: string) => (
  value
    .trim()
    .replace(/\\/g, '/')
    .split('/')
    .map(encodeURIComponent)
    .join('/')
)
