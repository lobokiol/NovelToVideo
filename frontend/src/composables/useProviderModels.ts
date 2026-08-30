import { computed, ref } from 'vue'
import {
  listProvidersApi,
  type ProviderConfig,
  type ProviderModelType,
} from '@/api/modelProvider'

export interface ProviderModelOption {
  label: string
  value: string
  category: string
  description: string
}

export interface ProviderModelGroup {
  key: string
  platform: string
  icon: string
  models: ProviderModelOption[]
}

export const MODEL_TYPE_LABELS: Record<ProviderModelType, string> = {
  text: '文本',
  image: '图像',
  video: '视频',
  tts: '语音',
}

const createEmptyGroups = (): Record<ProviderModelType, ProviderModelGroup[]> => ({
  text: [],
  image: [],
  video: [],
  tts: [],
})

const createEmptyBuckets = (): Record<ProviderModelType, ProviderModelOption[]> => ({
  text: [],
  image: [],
  video: [],
  tts: [],
})

// 加载模型平台配置，并将启用平台的模型按类型聚合为分组选项，
// 供 ModelGroupSelect 等分组模型选择器直接消费。
export function useProviderModels() {
  const providers = ref<ProviderConfig[]>([])
  const loading = ref(false)

  const load = async () => {
    loading.value = true
    try {
      const { data } = await listProvidersApi()
      providers.value = data
    } finally {
      loading.value = false
    }
  }

  const groupsByType = computed<Record<ProviderModelType, ProviderModelGroup[]>>(() => {
    const groups = createEmptyGroups()
    for (const provider of providers.value) {
      if (!provider.enabled) continue

      const buckets = createEmptyBuckets()
      for (const model of provider.models) {
        buckets[model.model_type].push({
          label: model.name || model.model_id,
          value: model.model_id,
          category: MODEL_TYPE_LABELS[model.model_type],
          description: model.description || model.model_id,
        })
      }

      for (const modelType of Object.keys(buckets) as ProviderModelType[]) {
        if (buckets[modelType].length === 0) continue
        groups[modelType].push({
          key: provider.key,
          platform: provider.name || provider.key,
          icon: provider.icon,
          models: buckets[modelType],
        })
      }
    }
    return groups
  })

  const textModelGroups = computed(() => groupsByType.value.text)
  const imageModelGroups = computed(() => groupsByType.value.image)
  const videoModelGroups = computed(() => groupsByType.value.video)
  const ttsModelGroups = computed(() => groupsByType.value.tts)

  return {
    providers,
    loading,
    load,
    groupsByType,
    textModelGroups,
    imageModelGroups,
    videoModelGroups,
    ttsModelGroups,
  }
}
