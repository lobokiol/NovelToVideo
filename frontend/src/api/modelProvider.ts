import request from '@/request'

export type ProviderInputType = 'text' | 'password' | 'url'
export type ProviderModelType = 'text' | 'image' | 'video' | 'tts'

export interface ProviderInput {
  key: string
  label: string
  type: ProviderInputType
  required: boolean
}

export interface ProviderDurationResolution {
  duration: number[]
  resolution: string[]
}

export interface ProviderVoice {
  title: string
  voice: string
}

export interface ProviderModel {
  name: string
  model_id: string
  model_type: ProviderModelType
  description: string
  modes: (string | string[])[]
  think?: boolean | null
  audio?: boolean | string | null
  duration_resolution_map?: ProviderDurationResolution[] | null
  voices?: ProviderVoice[] | null
  aspect_ratios?: string[]
  sizes?: string[]
  fps?: number[]
  raw_config?: Record<string, unknown>
}

export interface ProviderConfig {
  key: string
  protocol: string
  version: string
  name: string
  description: string
  decs_url: string
  icon: string
  inputs: ProviderInput[]
  input_values: Record<string, string>
  base_url: string
  enabled: boolean
  sort_order: number
  models: ProviderModel[]
  url: string
}

export interface ProviderCreatePayload {
  config: ProviderConfig
  code?: string | null
}

export interface ProviderFileRead {
  config: ProviderConfig
  code: string
}

export interface ProviderTemplateRead {
  code: string
}

export interface ProviderTemplateGeneratePayload {
  config: ProviderConfig
}

export interface ProviderInputValuesUpdate {
  input_values: Record<string, string>
}

export interface ProviderModelsFetchPayload {
  config: ProviderConfig
}

export interface ProviderCodeUpdate {
  code: string
}

export const listProvidersApi = () =>
  request.get<ProviderConfig[]>('/providers/')

export const getProviderTemplateApi = () =>
  request.get<ProviderTemplateRead>('/providers/template')

export const generateProviderTemplateApi = (payload: ProviderTemplateGeneratePayload) =>
  request.post<ProviderTemplateRead>('/providers/template', payload)

export const getProviderApi = (key: string) =>
  request.get<ProviderFileRead>(`/providers/${encodeURIComponent(key)}`)

export const createProviderApi = (payload: ProviderCreatePayload) =>
  request.post<ProviderConfig>('/providers/', payload)

export const updateProviderConfigApi = (key: string, payload: ProviderConfig) =>
  request.put<ProviderConfig>(`/providers/${encodeURIComponent(key)}/config`, payload)

export const updateProviderInputValuesApi = (key: string, payload: ProviderInputValuesUpdate) =>
  request.put<ProviderConfig>(`/providers/${encodeURIComponent(key)}/inputs`, payload)

export const fetchProviderModelsApi = (payload: ProviderModelsFetchPayload) =>
  request.post<ProviderModel[]>('/providers/models/fetch', payload)

export const updateProviderCodeApi = (key: string, payload: ProviderCodeUpdate) =>
  request.put<ProviderFileRead>(`/providers/${encodeURIComponent(key)}/code`, payload)

export const deleteProviderApi = (key: string) =>
  request.delete<void>(`/providers/${encodeURIComponent(key)}`)
