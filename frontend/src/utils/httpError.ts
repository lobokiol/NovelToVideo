/** 从 axios 错误中提取后端 detail 文案，失败时回退到给定提示。 */
export const errorDetail = (error: unknown, fallback: string): string => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (error instanceof Error && error.message) return error.message
  return fallback
}