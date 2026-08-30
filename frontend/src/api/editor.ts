import request from '@/request'

export interface EditorProjectRecord {
  publicId: string
  name: string
  timeline: string
  durationMs: number
  ratio: string
  updatedAt: string
}

export interface EditorProjectSavePayload {
  timeline: string
  durationMs: number
  ratio?: string
  name?: string
}

const editorPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/editor/project`
)

export const getEditorProjectApi = (projectPublicId: string) => (
  request.get<EditorProjectRecord>(editorPath(projectPublicId))
)

export const saveEditorProjectApi = (
  projectPublicId: string,
  payload: EditorProjectSavePayload,
) => (
  request.put<EditorProjectRecord>(editorPath(projectPublicId), payload)
)

/**
 * 页面卸载兜底保存：keepalive 请求在刷新/关闭页面后仍会送达服务端。
 * 注意 keepalive 请求体上限约 64KB，超限时本次兜底会被浏览器拒绝，
 * 此时由防抖自动保存（最迟 5 秒一次）保证丢失窗口足够小。
 */
export const saveEditorProjectKeepalive = (
  projectPublicId: string,
  payload: EditorProjectSavePayload,
) => {
  const token = localStorage.getItem('access_token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    void fetch(`/api${editorPath(projectPublicId)}`, {
      method: 'PUT',
      keepalive: true,
      headers,
      body: JSON.stringify(payload),
    }).catch(() => undefined)
  } catch {
    // 卸载兜底尽力而为，失败不阻断页面关闭
  }
}