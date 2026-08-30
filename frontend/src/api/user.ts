import request from '@/request'

export interface LoginParams {
  username: string
  password: string
}

export interface LoginUserInfo {
  public_id: string
  username: string
  nickname?: string | null
}

export interface LoginResult {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: LoginUserInfo
}

export interface UserRecord {
  public_id: string
  username: string
  nickname: string | null
  email: string | null
  avatar_url: string | null
  sort_order: number
  is_superuser: boolean
  disabled_at: string | null
  last_login_at: string | null
  created_at: string
  updated_at: string
}

export interface UserUpdatePayload {
  username?: string
  nickname?: string | null
  email?: string | null
  avatar_url?: string | null
  password?: string
  sort_order?: number
  is_superuser?: boolean
  disabled_at?: string | null
}

export interface UserProfileUpdatePayload {
  username?: string
  nickname?: string | null
  email?: string | null
}

export interface UserPasswordUpdatePayload {
  old_password: string
  new_password: string
  confirm_password: string
}

export const loginApi = (data: LoginParams) => {
  return request.post<LoginResult>('/users/login', data)
}

export const updateUserApi = (publicId: string, payload: UserUpdatePayload) => {
  return request.put<UserRecord>(`/users/${publicId}`, payload)
}

export const getCurrentUserApi = () => {
  return request.get<UserRecord>('/users/me')
}

export const updateCurrentUserProfileApi = (payload: UserProfileUpdatePayload) => {
  return request.put<UserRecord>('/users/me/profile', payload)
}

export const updateCurrentUserPasswordApi = (payload: UserPasswordUpdatePayload) => {
  return request.put<UserRecord>('/users/me/password', payload)
}

export const updateCurrentUserAvatarApi = (avatarUrl: string | null) => {
  return request.put<UserRecord>('/users/me/avatar', { avatar_url: avatarUrl })
}

export const uploadCurrentUserAvatarApi = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return request.post<UserRecord>('/users/me/avatar/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
