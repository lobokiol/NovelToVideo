import { ref } from 'vue'
import { ElMessage } from 'element-plus'

type MessageType = 'error' | 'warning'

const detailToMessage = (detail: unknown) => {
  if (typeof detail === 'string') return detail.trim()
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item.trim()
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg?: unknown }).msg ?? '').trim()
        }
        return ''
      })
      .filter(Boolean)
      .join('；')
  }
  return ''
}

export const getErrorMessage = (error: unknown, fallback: string) => {
  if (typeof error === 'string') {
    return error.trim() || fallback
  }
  if (error instanceof Error) {
    return error.message.trim() || fallback
  }
  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>
    return (
      detailToMessage(record.detail) ||
      detailToMessage(record.error) ||
      detailToMessage(record.message) ||
      fallback
    )
  }
  return fallback
}

export const usePollErrorNotice = (fallback: string) => {
  const errorMessage = ref<string | null>(null)
  const notified = ref(false)

  const clearError = () => {
    errorMessage.value = null
    notified.value = false
  }

  // 轮询失败时只在错误状态变化时提示，避免后端不可用时持续刷屏。
  const notifyError = (
    error: unknown,
    options: { fallback?: string; type?: MessageType } = {},
  ) => {
    const nextMessage = getErrorMessage(error, options.fallback ?? fallback)
    const shouldNotify = !notified.value || errorMessage.value !== nextMessage

    errorMessage.value = nextMessage
    notified.value = true

    if (shouldNotify) {
      if (options.type === 'warning') {
        ElMessage.warning(nextMessage)
      } else {
        ElMessage.error(nextMessage)
      }
    }

    return shouldNotify
  }

  return {
    errorMessage,
    clearError,
    notifyError,
  }
}
