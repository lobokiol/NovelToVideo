<template>
  <main class="editor-page">
    <EditorPageHeader
      :project-name="currentProject?.name || ''"
      :save-state-label="saveStateLabel"
      :library-loading="libraryLoading"
      :saving="saving"
      :exporting="exporting"
      :export-progress="exportProgress"
      :can-export="hasVideoContent"
      :can-export-selection="canExportSelection"
      @back="goProduction"
      @refresh="loadLibrary"
      @save="saveProjectNow"
      @export-full="onExportFull"
      @export-selection="onExportSelection"
    />

    <section class="editor-body" :class="{ 'is-library-collapsed': libraryCollapsed }">
      <EditorLibraryPanel
        v-show="!libraryCollapsed"
        v-model:active-tab="libraryTab"
        :project-public-id="projectPublicId"
        :loading="libraryLoading"
        :shot-library="shotLibrary"
        :image-library="imageLibrary"
        :audio-library="audioLibrary"
        :export-library="exportLibrary"
        :used-media-ids="usedMediaIds"
        @add-video="addVideoToMainTrack"
        @add-image="addImageToMainTrack"
        @add-audio="addAudioToTrack"
        @upload-audio="uploadAudioAsset"
        @upload-video="uploadVideoAsset"
        @upload-image="uploadImageAsset"
        @delete-export="deleteExportMedia"
      />

      <section class="stage-panel">
        <EditorPreviewStage
          :project-public-id="projectPublicId"
          :project-name="currentProject?.name || ''"
          :ratio="ratio"
          :video-tracks="videoTracks"
          :playing="playing"
          :playhead-ms="playheadMs"
          :total-duration-ms="totalDurationMs"
          :is-portrait="isPortrait"
          :has-content="hasVideoContent"
          :selected-clip-id="primarySelectedClipId"
          :library-collapsed="libraryCollapsed"
          :timeline-collapsed="timelineCollapsed"
          @toggle-play="togglePlay"
          @register-video="onRegisterVideo"
          @update-text-scale="onClipTextScaleChange"
          @update-text-transform="onClipTextTransform"
          @toggle-library="libraryCollapsed = !libraryCollapsed"
          @toggle-timeline="timelineCollapsed = !timelineCollapsed"
          @seek="onSeek"
          @scrub-start="onScrubStart"
        />

        <EditorInspectorBar
          v-if="selectedClip && selectedClipIds.length === 1 && !timelineCollapsed"
          :clip="selectedClip"
          @update-trim="onTrimChange"
          @update-volume="onVolumeChange"
          @update-muted="onClipMutedChange"
          @update-text="onClipTextChange"
          @update-text-scale="onClipTextScaleChange"
          @update-duration="onClipDurationChange"
        />

        <EditorTimeline
          v-show="!timelineCollapsed"
          v-model:px-per-second="pxPerSecond"
          :project-public-id="projectPublicId"
          :tracks="tracks"
          :playhead-ms="playheadMs"
          :playing="playing"
          :selected-clip-ids="selectedClipIds"
          :total-duration-ms="totalDurationMs"
          :can-undo="canUndo"
          :can-redo="canRedo"
          @seek="onSeek"
          @scrub-start="onScrubStart"
          @undo="undoTimeline"
          @redo="redoTimeline"
          @select-clip="selectClip"
          @clear-selection="clearSelection"
          @split-selected="splitSelectedClip"
          @remove-selected="removeSelectedClips"
          @detach-audio="detachAudioFromClip"
          @add-text="addTextClip"
          @toggle-track-mute="toggleTrackMute"
          @toggle-track-hidden="toggleTrackHidden"
          @remove-track="removeTrack"
          @media-drop="onMediaDrop"
          @clip-move="onClipMove"
          @clips-shift="onClipsShift"
        />
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getEditorProjectApi, saveEditorProjectApi, saveEditorProjectKeepalive } from '@/api/editor'
import {
  deleteProjectMediaApi,
  listProjectMediaApi,
  mediaContentUrl,
  uploadProjectMediaApi,
  type MediaAssetRecord,
} from '@/api/media'
import { listStoryboardShotsApi, type StoryboardShot } from '@/api/storyboard'
import { listProjectsApi, type ProjectRecord } from '@/api/project'
import { errorDetail } from '@/utils/httpError'
import { useTimelinePlayback } from '@/composables/useTimelinePlayback'
import { useTimelineExport } from '@/composables/useTimelineExport'
import { useTimelineHistory } from '@/composables/useTimelineHistory'
import EditorPageHeader from '@/components/editor/EditorPageHeader.vue'
import EditorLibraryPanel from '@/components/editor/EditorLibraryPanel.vue'
import EditorPreviewStage from '@/components/editor/EditorPreviewStage.vue'
import EditorInspectorBar from '@/components/editor/EditorInspectorBar.vue'
import EditorTimeline from '@/components/editor/EditorTimeline.vue'
import {
  buildTimelineDoc,
  clampTextBoxWidth,
  clampTextOffset,
  clampTextRotate,
  clampTextScale,
  clipDurationMs,
  clipEndMs,
  createClip,
  createTrack,
  isStillClip,
  magneticInsertIndex,
  maxFreeOutMs,
  parseTimelineDoc,
  relayoutMagneticTrack,
  resolveFreeStart,
  sortFreeTrack,
  splitClipAt,
  timelineDurationMs,
} from '@/components/editor/timelineDoc'
import {
  DEFAULT_IMAGE_DURATION_MS,
  DEFAULT_TEXT_CONTENT,
  DEFAULT_TEXT_DURATION_MS,
  MAX_STILL_DURATION_MS,
  MIN_CLIP_MS,
  type ClipDropTarget,
  type ClipMediaType,
  type MediaDragPayload,
  type ShotLibraryItem,
  type TimelineClip,
  type TimelineTrack,
} from '@/components/editor/types'

const route = useRoute()
const router = useRouter()

const resolveQueryString = (value: unknown) => {
  if (Array.isArray(value)) return String(value[0] ?? '')
  return typeof value === 'string' ? value : ''
}

const projectPublicId = ref(
  (resolveQueryString(route.query.id) || resolveQueryString(route.query.projectId)).trim(),
)
const currentProject = ref<ProjectRecord | null>(null)

// ---------------------------------------------------------------------------
// 素材库
// ---------------------------------------------------------------------------

const libraryTab = ref('shots')
const libraryLoading = ref(false)
const shotLibrary = ref<ShotLibraryItem[]>([])
const imageLibrary = ref<ShotLibraryItem[]>([])
const audioLibrary = ref<MediaAssetRecord[]>([])
const exportLibrary = ref<MediaAssetRecord[]>([])
const mediaDurations = ref<Map<string, number>>(new Map())

// ---------------------------------------------------------------------------
// 时间线核心状态
// ---------------------------------------------------------------------------

const tracks = ref<TimelineTrack[]>([
  createTrack('video', { name: '主视频轨', magnetic: true }),
  createTrack('audio', { name: '音轨 1' }),
])
const ratio = ref('9:16')
/** 选中片段集合：末位为主选中（属性条/切割作用对象），Ctrl 点击可增删。 */
const selectedClipIds = ref<string[]>([])
const playheadMs = ref(0)
const pxPerSecond = ref(60)

/** 布局折叠：收起左侧素材区 / 底部轨道区，给播放器让出空间。 */
const libraryCollapsed = ref(false)
const timelineCollapsed = ref(false)

const saving = ref(false)
const dirty = ref(false)
const lastSavedAt = ref('')

/** 每条视频轨的两个预览层元素（双缓冲：一层显示当前片段，一层预载下一片段）。 */
const videoLayerMap = new Map<string, [HTMLVideoElement | null, HTMLVideoElement | null]>()
let saveTimer: ReturnType<typeof setTimeout> | null = null
/** 首笔未保存变更的时刻；防抖被连续编辑不断重置时，据此强制触发保存。 */
let dirtySinceTs = 0
let suppressDirty = false

const AUTO_SAVE_DEBOUNCE_MS = 2000
const AUTO_SAVE_MAX_WAIT_MS = 5000

const videoTracks = computed(() => tracks.value.filter((track) => track.kind === 'video'))
const mainTrack = computed(() => tracks.value.find((track) => track.magnetic) ?? null)
const totalDurationMs = computed(() => timelineDurationMs(tracks.value))
const isPortrait = computed(() => ratio.value !== '16:9')
const hasVideoContent = computed(() => videoTracks.value.some((track) => track.clips.length > 0))

/** 时间线上已被引用的媒体标识，素材库据此显示「已添加」角标。 */
const usedMediaIds = computed(() => {
  const ids = new Set<string>()
  for (const track of tracks.value) {
    for (const clip of track.clips) {
      if (clip.mediaPublicId) ids.add(clip.mediaPublicId)
    }
  }
  return Array.from(ids)
})

const selectedInfo = computed(() => {
  const primaryId = selectedClipIds.value[selectedClipIds.value.length - 1]
  if (!primaryId) return null
  for (const track of tracks.value) {
    const clip = track.clips.find((item) => item.id === primaryId)
    if (clip) return { track, clip }
  }
  return null
})
const selectedClip = computed(() => selectedInfo.value?.clip ?? null)
const primarySelectedClipId = computed(() => selectedInfo.value?.clip.id ?? '')
const canExportSelection = computed(() => selectedInfo.value?.track.kind === 'video')

const saveStateLabel = computed(() => {
  if (saving.value) return '保存中…'
  if (dirty.value) return '有未保存修改'
  return lastSavedAt.value ? `已保存 ${lastSavedAt.value}` : ''
})

const resolveMediaUrl = (mediaPublicId: string) => mediaContentUrl(projectPublicId.value, mediaPublicId)

// ---------------------------------------------------------------------------
// 播放引擎与导出
// ---------------------------------------------------------------------------

const playback = useTimelinePlayback({
  tracks: () => tracks.value,
  playheadMs,
  totalDurationMs: () => totalDurationMs.value,
  resolveMediaUrl,
  getVideoLayers: (trackId) => {
    const layers = videoLayerMap.get(trackId)
    // 双缓冲要求两层皆已挂载才可调度；任一缺失则本轮跳过（下一帧重试）。
    return layers && layers[0] && layers[1] ? ([layers[0], layers[1]] as const) : null
  },
})
const playing = playback.playing

const { exporting, exportProgress, exportTimeline } = useTimelineExport({
  projectPublicId: () => projectPublicId.value,
  projectName: () => currentProject.value?.name || '',
  ratio: () => ratio.value,
  tracks: () => tracks.value,
  resolveMediaUrl,
  onExported: async (tab) => {
    libraryTab.value = tab
    await loadLibrary()
  },
})

const togglePlay = () => playback.toggle()
const onSeek = (ms: number) => playback.seekTo(ms)
const onScrubStart = () => playback.beginScrub()

// ---------------------------------------------------------------------------
// 撤销 / 重做
// ---------------------------------------------------------------------------

const history = useTimelineHistory({
  tracks,
  isSuppressed: () => suppressDirty,
  onRestore: () => {
    // 恢复后选中片段可能已不存在：过滤失效成员；暂停态下同步一帧预览。
    const alive = new Set<string>()
    for (const track of tracks.value) for (const clip of track.clips) alive.add(clip.id)
    selectedClipIds.value = selectedClipIds.value.filter((id) => alive.has(id))
    if (!playing.value) playback.syncAll(false)
  },
})
const canUndo = history.canUndo
const canRedo = history.canRedo
const undoTimeline = () => history.undo()
const redoTimeline = () => history.redo()

const onRegisterVideo = (trackId: string, layerIndex: number, el: HTMLVideoElement | null) => {
  const layers = videoLayerMap.get(trackId) ?? [null, null]
  layers[layerIndex === 0 ? 0 : 1] = el
  if (layers[0] || layers[1]) videoLayerMap.set(trackId, layers)
  else videoLayerMap.delete(trackId)
}

/** 导出完整视频前弹窗设置标题，作为回传媒体库与下载时的文件名。 */
const onExportFull = async () => {
  try {
    const { value } = await ElMessageBox.prompt('设置成片标题，导出下载时将用作文件名', '导出完整视频', {
      inputValue: `${currentProject.value?.name || '项目'}-成片`,
      inputPattern: /\S+/,
      inputErrorMessage: '标题不能为空',
      confirmButtonText: '开始导出',
      cancelButtonText: '取消',
      customClass: 'editor-dark-confirm',
    })
    void exportTimeline('full', null, value.trim())
  } catch {
    // 用户取消导出
  }
}

const onExportSelection = () => {
  void exportTimeline('selection', selectedClip.value)
}

/** 删除成片：确认后从媒体库移除并刷新列表。 */
const deleteExportMedia = async (media: MediaAssetRecord) => {
  try {
    await ElMessageBox.confirm('删除后不可恢复，确定删除该成片吗？', '删除成片', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'editor-dark-confirm',
    })
  } catch {
    return
  }
  try {
    await deleteProjectMediaApi(projectPublicId.value, media.publicId)
    ElMessage.success('成片已删除')
    await loadLibrary()
  } catch (error) {
    ElMessage.error(errorDetail(error, '删除成片失败'))
  }
}

// ---------------------------------------------------------------------------
// 加载：项目 / 素材库 / 剪辑工程
// ---------------------------------------------------------------------------

const loadProject = async () => {
  const { data } = await listProjectsApi()
  currentProject.value = data.find((item) => item.public_id === projectPublicId.value) ?? null
  if (currentProject.value?.video_ratio) ratio.value = currentProject.value.video_ratio
}

const shotLabelMap = (shots: StoryboardShot[]) => {
  const map = new Map<string, string>()
  for (const shot of shots) {
    map.set(shot.publicId, `EP${String(shot.episodeIndex).padStart(2, '0')} #${shot.shotIndex}`)
  }
  return map
}

const loadLibrary = async () => {
  libraryLoading.value = true
  try {
    const [videoResult, imageResult, audioResult, exportResult, shotsResult] = await Promise.all([
      listProjectMediaApi(projectPublicId.value, {
        mediaType: 'video',
        scopeType: 'shot',
        status: 'ready',
        limit: 500,
      }),
      listProjectMediaApi(projectPublicId.value, { mediaType: 'image', status: 'ready', limit: 300 }),
      listProjectMediaApi(projectPublicId.value, { mediaType: 'audio', status: 'ready', limit: 200 }),
      listProjectMediaApi(projectPublicId.value, {
        mediaType: 'video',
        scopeType: 'project',
        status: 'ready',
        limit: 100,
      }),
      listStoryboardShotsApi(projectPublicId.value),
    ])
    const labels = shotLabelMap(shotsResult.data)
    const items: ShotLibraryItem[] = videoResult.data.map((media) => ({
      media,
      label: labels.get(media.scopePublicId) || '镜头视频',
    }))
    // 每镜选定视频优先展示，其余候选排在其后。
    items.sort((a, b) => {
      if (a.label !== b.label) return a.label.localeCompare(b.label, 'zh-Hans-CN')
      if (a.media.mediaRole === 'final') return -1
      if (b.media.mediaRole === 'final') return 1
      return 0
    })
    // 项目级视频按角色拆分：上传/导出片段（reference）并入镜头片段供拖轨，成片（final/preview）归成片页签。
    const uploadedItems: ShotLibraryItem[] = exportResult.data
      .filter((media) => media.mediaRole === 'reference')
      .map((media) => {
        let label = ''
        try {
          const params = JSON.parse(media.params || '{}') as { filename?: string }
          if (params.filename) label = params.filename.replace(/\.[a-z0-9]+$/i, '')
        } catch {
          // params 非法时退回默认标签
        }
        return { media, label: label || '上传视频' }
      })
    shotLibrary.value = [...uploadedItems, ...items]
    // 图片名称：优先上传文件名，其次分镜归属（EPxx #n 分镜图），兜底序号。
    imageLibrary.value = imageResult.data.map((media, index) => {
      let label = ''
      try {
        const params = JSON.parse(media.params || '{}') as { filename?: string }
        if (params.filename) label = params.filename
      } catch {
        // params 非法时继续走归属命名
      }
      if (!label && media.scopeType === 'shot') {
        const shotLabel = labels.get(media.scopePublicId)
        if (shotLabel) label = `${shotLabel} 分镜图`
      }
      return { media, label: label || `图片 ${index + 1}` }
    })
    audioLibrary.value = audioResult.data
    exportLibrary.value = exportResult.data.filter((media) => media.mediaRole !== 'reference')
    const durations = new Map<string, number>()
    for (const media of [...videoResult.data, ...exportResult.data, ...audioResult.data]) {
      durations.set(media.publicId, media.durationMs || 0)
    }
    mediaDurations.value = durations
  } catch (error) {
    ElMessage.error(errorDetail(error, '加载素材库失败'))
  } finally {
    libraryLoading.value = false
  }
}

const loadEditorProject = async () => {
  const { data } = await getEditorProjectApi(projectPublicId.value)
  if (data.ratio) ratio.value = data.ratio
  try {
    const parsed = parseTimelineDoc(data.timeline)
    suppressDirty = true
    tracks.value = parsed.tracks
    if (parsed.ratio) ratio.value = parsed.ratio
  } catch {
    ElMessage.warning('剪辑工程数据无法解析，已重置为空时间线')
  }
  await nextTick()
  suppressDirty = false
  dirty.value = false
  lastSavedAt.value = new Date(data.updatedAt).toLocaleTimeString()
  history.reset()
  playback.seekTo(0)
}

// ---------------------------------------------------------------------------
// 保存：手动 + 防抖自动保存（连续编辑时距首笔变更最迟 5 秒强制落库）+ 卸载兜底
// ---------------------------------------------------------------------------

const buildSavePayload = () => ({
  timeline: JSON.stringify(buildTimelineDoc(ratio.value, tracks.value)),
  durationMs: totalDurationMs.value,
  ratio: ratio.value,
})

const saveProjectNow = async () => {
  if (!projectPublicId.value) return
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  dirtySinceTs = 0
  saving.value = true
  try {
    const { data } = await saveEditorProjectApi(projectPublicId.value, buildSavePayload())
    dirty.value = false
    lastSavedAt.value = new Date(data.updatedAt).toLocaleTimeString()
  } catch (error) {
    ElMessage.error(errorDetail(error, '保存剪辑工程失败'))
  } finally {
    saving.value = false
  }
}

const markDirty = () => {
  dirty.value = true
  const now = Date.now()
  if (!dirtySinceTs) dirtySinceTs = now
  if (saveTimer) clearTimeout(saveTimer)
  // 防抖 2 秒；拖拽等连续编辑会不断重置计时器，故距首笔未保存变更最迟 5 秒强制保存。
  const delay = Math.min(AUTO_SAVE_DEBOUNCE_MS, Math.max(0, dirtySinceTs + AUTO_SAVE_MAX_WAIT_MS - now))
  saveTimer = setTimeout(() => {
    void saveProjectNow()
  }, delay)
}

/** 刷新/关闭/离开页面时的兜底：把未落库的时间线用 keepalive 请求送出。 */
const flushPendingSave = () => {
  if (!dirty.value || !projectPublicId.value) return
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  dirtySinceTs = 0
  saveEditorProjectKeepalive(projectPublicId.value, buildSavePayload())
  dirty.value = false
}

watch(
  tracks,
  () => {
    if (suppressDirty) return
    markDirty()
    // 暂停态下片段增删改后刷新各预览层的显隐与音量。
    if (!playing.value) playback.syncAll(false)
  },
  { deep: true },
)

// ---------------------------------------------------------------------------
// 轨道与片段操作
// ---------------------------------------------------------------------------

/** 选中片段：additive（Ctrl 点击）时切换成员资格，否则重置为单选。 */
const selectClip = (clipId: string, additive = false) => {
  if (!additive) {
    selectedClipIds.value = [clipId]
    return
  }
  const index = selectedClipIds.value.indexOf(clipId)
  if (index >= 0) selectedClipIds.value = selectedClipIds.value.filter((id) => id !== clipId)
  else selectedClipIds.value = [...selectedClipIds.value, clipId]
}

const clearSelection = () => {
  selectedClipIds.value = []
}

interface MakeClipOptions {
  mediaPublicId: string
  mediaType: ClipMediaType
  label: string
  fallbackDurationMs: number
  startMs: number
  text?: string
}

const makeClipFrom = (options: MakeClipOptions) => {
  if (options.mediaType === 'text') {
    return createClip({
      mediaPublicId: '',
      mediaType: 'text',
      label: options.label,
      text: options.text ?? DEFAULT_TEXT_CONTENT,
      srcDurationMs: MAX_STILL_DURATION_MS,
      durationMs: DEFAULT_TEXT_DURATION_MS,
      startMs: options.startMs,
    })
  }
  if (options.mediaType === 'image') {
    return createClip({
      mediaPublicId: options.mediaPublicId,
      mediaType: 'image',
      label: options.label,
      srcDurationMs: MAX_STILL_DURATION_MS,
      durationMs: DEFAULT_IMAGE_DURATION_MS,
      startMs: options.startMs,
    })
  }
  const srcDurationMs = mediaDurations.value.get(options.mediaPublicId) || options.fallbackDurationMs || 5000
  return createClip({
    mediaPublicId: options.mediaPublicId,
    mediaType: options.mediaType,
    label: options.label,
    srcDurationMs,
    startMs: options.startMs,
  })
}

const nextTrackName = (kind: 'video' | 'audio') => {
  if (kind === 'video') {
    const count = tracks.value.filter((track) => track.kind === 'video' && !track.magnetic).length
    return `视频轨 ${count + 1}`
  }
  const count = tracks.value.filter((track) => track.kind === 'audio').length
  return `音轨 ${count + 1}`
}

/** 把片段放入目标轨道（或新建轨道），磁性轨按落点插入、自由轨夹紧防重叠。 */
const placeClip = (clip: TimelineClip, kind: 'video' | 'audio', target: ClipDropTarget) => {
  if (target.type === 'new-video') {
    if (kind !== 'video') return false
    const track = createTrack('video', { name: nextTrackName('video') })
    clip.startMs = Math.max(0, target.ms)
    track.clips.push(clip)
    // 新副轨插到视频组最上层。
    tracks.value.unshift(track)
    return true
  }
  if (target.type === 'new-video-below') {
    if (kind !== 'video') return false
    const track = createTrack('video', { name: nextTrackName('video') })
    clip.startMs = Math.max(0, target.ms)
    track.clips.push(clip)
    // 主轨下方副轨：层级低于主轨，主轨画面之下垫底。
    const mainIndex = tracks.value.findIndex((item) => item.magnetic)
    tracks.value.splice(mainIndex + 1, 0, track)
    return true
  }
  if (target.type === 'new-audio') {
    if (kind !== 'audio') return false
    const track = createTrack('audio', { name: nextTrackName('audio') })
    clip.startMs = Math.max(0, target.ms)
    track.clips.push(clip)
    tracks.value.push(track)
    return true
  }
  const track = tracks.value.find((item) => item.id === target.trackId)
  if (!track || track.kind !== kind) return false
  // 文本/图片拖到磁性主轨时自动新建上方副轨承接：叠加素材自由落位（任意时间刻度），
  // 不进入主轨磁性序列；要把图片编入内容流请使用素材卡的「加入主轨」。
  if (track.magnetic && (clip.mediaType === 'text' || clip.mediaType === 'image')) {
    const overlay = createTrack('video', { name: nextTrackName('video') })
    clip.startMs = Math.max(0, target.ms)
    overlay.clips.push(clip)
    tracks.value.unshift(overlay)
    return true
  }
  if (track.magnetic) {
    const index = magneticInsertIndex(track.clips, target.ms)
    track.clips.splice(index, 0, clip)
    relayoutMagneticTrack(track)
  } else {
    clip.startMs = resolveFreeStart(track, clip.id, target.ms, clipDurationMs(clip))
    track.clips.push(clip)
    sortFreeTrack(track)
  }
  return true
}

const addVideoToMainTrack = (item: ShotLibraryItem) => {
  const track = mainTrack.value
  if (!track) return
  const clip = makeClipFrom({
    mediaPublicId: item.media.publicId,
    mediaType: 'video',
    label: item.label,
    fallbackDurationMs: item.media.durationMs,
    startMs: 0,
  })
  track.clips.push(clip)
  relayoutMagneticTrack(track)
  selectClip(clip.id)
}

const addImageToMainTrack = (media: MediaAssetRecord, label: string) => {
  const track = mainTrack.value
  if (!track) return
  const clip = makeClipFrom({
    mediaPublicId: media.publicId,
    mediaType: 'image',
    label,
    fallbackDurationMs: 0,
    startMs: 0,
  })
  track.clips.push(clip)
  relayoutMagneticTrack(track)
  selectClip(clip.id)
}

/** 文本片段落到第一条非磁性视频轨（无则新建），紧跟播放头且不与同轨重叠。 */
const addTextClip = () => {
  let track = tracks.value.find((item) => item.kind === 'video' && !item.magnetic)
  if (!track) {
    track = createTrack('video', { name: nextTrackName('video') })
    tracks.value.unshift(track)
  }
  const clip = makeClipFrom({
    mediaPublicId: '',
    mediaType: 'text',
    label: '文本',
    fallbackDurationMs: 0,
    startMs: 0,
  })
  clip.startMs = resolveFreeStart(track, clip.id, playheadMs.value, clipDurationMs(clip))
  track.clips.push(clip)
  sortFreeTrack(track)
  selectClip(clip.id)
}

/** 音频入轨：落播放头位置；现有音轨该区间被占用时依次尝试，全部冲突则自动新增音轨。 */
const addAudioToTrack = (media: MediaAssetRecord, label: string) => {
  const clip = makeClipFrom({
    mediaPublicId: media.publicId,
    mediaType: 'audio',
    label,
    fallbackDurationMs: media.durationMs,
    startMs: 0,
  })
  const durationMs = clipDurationMs(clip)
  let target = tracks.value.find(
    (track) =>
      track.kind === 'audio' &&
      resolveFreeStart(track, clip.id, playheadMs.value, durationMs) === playheadMs.value,
  )
  if (!target) {
    target = createTrack('audio', { name: nextTrackName('audio') })
    tracks.value.push(target)
  }
  clip.startMs = playheadMs.value
  target.clips.push(clip)
  sortFreeTrack(target)
  selectClip(clip.id)
}

const uploadAudioAsset = async (file: File) => {
  try {
    await uploadProjectMediaApi(projectPublicId.value, file, {
      filename: file.name,
      scopeType: 'project',
      mediaRole: 'reference',
    })
    ElMessage.success('音频已上传')
    await loadLibrary()
  } catch (error) {
    ElMessage.error(errorDetail(error, '音频上传失败'))
  }
}

const uploadVideoAsset = async (file: File) => {
  try {
    await uploadProjectMediaApi(projectPublicId.value, file, {
      filename: file.name,
      scopeType: 'project',
      mediaRole: 'reference',
    })
    ElMessage.success('视频已上传')
    libraryTab.value = 'shots'
    await loadLibrary()
  } catch (error) {
    ElMessage.error(errorDetail(error, '视频上传失败'))
  }
}

const uploadImageAsset = async (file: File) => {
  try {
    await uploadProjectMediaApi(projectPublicId.value, file, {
      filename: file.name,
      scopeType: 'project',
      mediaRole: 'reference',
    })
    ElMessage.success('图片已上传')
    libraryTab.value = 'images'
    await loadLibrary()
  } catch (error) {
    ElMessage.error(errorDetail(error, '图片上传失败'))
  }
}

const onMediaDrop = (payload: MediaDragPayload, target: ClipDropTarget) => {
  const clip = makeClipFrom({
    mediaPublicId: payload.mediaPublicId,
    mediaType: payload.mediaType,
    label: payload.label,
    fallbackDurationMs: payload.durationMs,
    startMs: 0,
  })
  if (placeClip(clip, payload.kind, target)) selectClip(clip.id)
}

const onClipMove = (clipId: string, fromTrackId: string, target: ClipDropTarget) => {
  const fromTrack = tracks.value.find((item) => item.id === fromTrackId)
  if (!fromTrack) return
  const index = fromTrack.clips.findIndex((item) => item.id === clipId)
  if (index < 0) return
  const [clip] = fromTrack.clips.splice(index, 1)
  if (!placeClip(clip, fromTrack.kind, target)) {
    // 放置失败（目标类型不匹配等）时回退到源轨原位。
    fromTrack.clips.splice(index, 0, clip)
  }
  if (fromTrack.magnetic) relayoutMagneticTrack(fromTrack)
  else sortFreeTrack(fromTrack)
  // 片段移走后源辅轨可能被清空，按规则自动移除。
  pruneTrackIfEmpty(fromTrackId)
}

const onTrimChange = (range: [number, number]) => {
  const info = selectedInfo.value
  if (!info) return
  const [inMs, outMs] = range
  if (outMs - inMs < MIN_CLIP_MS) return
  info.clip.inMs = inMs
  // 自由轨裁剪出点不得越过右侧相邻片段，避免重叠。
  info.clip.outMs = info.track.magnetic ? outMs : Math.min(outMs, maxFreeOutMs(info.track, info.clip))
  if (info.track.magnetic) relayoutMagneticTrack(info.track)
}

const onVolumeChange = (volume: number) => {
  const clip = selectedClip.value
  if (clip) clip.volume = volume
}

const onClipMutedChange = (muted: boolean) => {
  const clip = selectedClip.value
  if (clip) clip.muted = muted
}

const onClipTextChange = (text: string) => {
  const clip = selectedClip.value
  if (clip) clip.text = text
}

const onClipTextScaleChange = (scale: number) => {
  const clip = selectedClip.value
  if (clip && clip.mediaType === 'text') clip.textScale = clampTextScale(scale)
}

/** 播放区文本变换（移动/旋转/文本框宽度），字段各自合法化后写回片段。 */
const onClipTextTransform = (patch: { x?: number; y?: number; rotate?: number; boxWidth?: number }) => {
  const clip = selectedClip.value
  if (!clip || clip.mediaType !== 'text') return
  if (patch.x !== undefined) clip.textX = clampTextOffset(patch.x)
  if (patch.y !== undefined) clip.textY = clampTextOffset(patch.y)
  if (patch.rotate !== undefined) clip.textRotate = clampTextRotate(patch.rotate)
  if (patch.boxWidth !== undefined) clip.textBoxWidth = clampTextBoxWidth(patch.boxWidth)
}

/** 图片/文本等静态片段调整时长：磁性轨直接改、自由轨夹紧到右侧空隙。 */
const onClipDurationChange = (durationMs: number) => {
  const info = selectedInfo.value
  if (!info || !isStillClip(info.clip)) return
  const target = Math.min(MAX_STILL_DURATION_MS, Math.max(MIN_CLIP_MS, durationMs))
  info.clip.outMs = info.track.magnetic
    ? info.clip.inMs + target
    : Math.min(info.clip.inMs + target, maxFreeOutMs(info.track, info.clip))
  if (info.track.magnetic) relayoutMagneticTrack(info.track)
}

const splitSelectedClip = () => {
  const info = selectedInfo.value
  if (!info) return
  const tail = splitClipAt(info.clip, playheadMs.value)
  if (!tail) {
    ElMessage.warning('请把播放头移动到片段内部再切割')
    return
  }
  const index = info.track.clips.findIndex((item) => item.id === info.clip.id)
  info.track.clips.splice(index + 1, 0, tail)
  if (info.track.magnetic) relayoutMagneticTrack(info.track)
}

/** 主音轨判定：音轨组首条恒保留，自动清理与手动删除均不作用于它。 */
const isPrimaryAudioTrack = (track: TimelineTrack) => {
  if (track.kind !== 'audio') return false
  return tracks.value.filter((item) => item.kind === 'audio').indexOf(track) === 0
}

/** 辅轨清空自动移除：磁性主轨与主音轨恒保留。 */
const pruneTrackIfEmpty = (trackId: string) => {
  const track = tracks.value.find((item) => item.id === trackId)
  if (!track || track.magnetic || track.clips.length > 0) return
  if (isPrimaryAudioTrack(track)) return
  tracks.value = tracks.value.filter((item) => item.id !== trackId)
}

/** 批量删除选中片段：涉及的磁性轨重排、自由轨保序，空辅轨自动移除。 */
const removeSelectedClips = () => {
  const idSet = new Set(selectedClipIds.value)
  if (idSet.size === 0) return
  const touchedTrackIds: string[] = []
  for (const track of tracks.value) {
    const before = track.clips.length
    track.clips = track.clips.filter((clip) => !idSet.has(clip.id))
    if (track.clips.length === before) continue
    if (track.magnetic) relayoutMagneticTrack(track)
    touchedTrackIds.push(track.id)
  }
  clearSelection()
  for (const trackId of touchedTrackIds) pruneTrackIfEmpty(trackId)
}

/**
 * 批量水平平移（Ctrl 多选后整组拖动）：对每条涉及的自由轨计算与未选中片段
 * 的碰撞边界，整组取交集后统一平移，保证不产生同轨重叠；磁性轨片段不平移。
 */
const onClipsShift = (clipIds: string[], deltaMs: number) => {
  const idSet = new Set(clipIds)
  let lo = Number.NEGATIVE_INFINITY
  let hi = Number.POSITIVE_INFINITY
  const groups: Array<{ track: TimelineTrack; clips: TimelineClip[] }> = []
  for (const track of tracks.value) {
    if (track.magnetic) continue
    const selected = track.clips.filter((clip) => idSet.has(clip.id))
    if (selected.length === 0) continue
    groups.push({ track, clips: selected })
    const others = track.clips.filter((clip) => !idSet.has(clip.id))
    for (const clip of selected) {
      lo = Math.max(lo, -clip.startMs)
      const end = clipEndMs(clip)
      for (const other of others) {
        if (clipEndMs(other) <= clip.startMs) lo = Math.max(lo, clipEndMs(other) - clip.startMs)
        else if (other.startMs >= end) hi = Math.min(hi, other.startMs - end)
      }
    }
  }
  if (groups.length === 0 || lo > hi) return
  const delta = Math.round(Math.min(hi, Math.max(lo, deltaMs)))
  if (delta === 0) return
  for (const group of groups) {
    for (const clip of group.clips) clip.startMs += delta
    sortFreeTrack(group.track)
  }
}

/**
 * 音视频分离：视频片段静音，其声音以同素材音频片段落入音轨同一时间位置；
 * 现有音轨该区间被占用时依次尝试下一条，全部冲突则新建音轨。
 */
const detachAudioFromClip = () => {
  const info = selectedInfo.value
  if (!info || info.track.kind !== 'video' || info.clip.mediaType !== 'video') return
  const source = info.clip
  if (source.muted) {
    ElMessage.warning('该片段已静音，无声音可分离')
    return
  }
  const audioClip = createClip({
    mediaPublicId: source.mediaPublicId,
    mediaType: 'audio',
    label: `${source.label} 音频`,
    srcDurationMs: source.srcDurationMs,
    startMs: source.startMs,
  })
  audioClip.inMs = source.inMs
  audioClip.outMs = source.outMs
  audioClip.volume = source.volume
  const durationMs = clipDurationMs(audioClip)
  let target = tracks.value.find(
    (track) =>
      track.kind === 'audio' &&
      resolveFreeStart(track, audioClip.id, source.startMs, durationMs) === source.startMs,
  )
  if (!target) {
    target = createTrack('audio', { name: nextTrackName('audio') })
    tracks.value.push(target)
  }
  audioClip.startMs = source.startMs
  target.clips.push(audioClip)
  sortFreeTrack(target)
  source.muted = true
  ElMessage.success('已分离音频到音轨，原片段已静音')
  selectClip(audioClip.id)
}

const toggleTrackMute = (trackId: string) => {
  const track = tracks.value.find((item) => item.id === trackId)
  if (track) track.muted = !track.muted
}

const toggleTrackHidden = (trackId: string) => {
  const track = tracks.value.find((item) => item.id === trackId)
  if (track && track.kind === 'video') track.hidden = !track.hidden
}

const removeTrack = async (trackId: string) => {
  const track = tracks.value.find((item) => item.id === trackId)
  if (!track || track.magnetic || isPrimaryAudioTrack(track)) return
  if (track.clips.length > 0) {
    try {
      await ElMessageBox.confirm(`轨道「${track.name}」上有 ${track.clips.length} 个片段，删除后不可恢复。`, '删除轨道', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'editor-dark-confirm',
      })
    } catch {
      return
    }
  }
  if (track.clips.some((item) => selectedClipIds.value.includes(item.id))) {
    selectedClipIds.value = selectedClipIds.value.filter(
      (id) => !track.clips.some((item) => item.id === id),
    )
  }
  tracks.value = tracks.value.filter((item) => item.id !== trackId)
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------

const goProduction = () => {
  router.push({ path: '/production', query: { id: projectPublicId.value } })
}

/**
 * 全局快捷键：空格播放/暂停，Ctrl+Z / Ctrl+Shift+Z（或 Ctrl+Y）撤销重做，
 * Delete/Backspace 删除选中片段；输入控件聚焦时不拦截。
 */
const onKeydown = (event: KeyboardEvent) => {
  const target = event.target as HTMLElement | null
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
  if ((event.ctrlKey || event.metaKey) && (event.code === 'KeyZ' || event.code === 'KeyY')) {
    event.preventDefault()
    if (event.code === 'KeyY' || event.shiftKey) redoTimeline()
    else undoTimeline()
    return
  }
  if ((event.code === 'Delete' || event.code === 'Backspace') && selectedClipIds.value.length > 0) {
    event.preventDefault()
    removeSelectedClips()
    return
  }
  if (event.code !== 'Space' || event.repeat) return
  event.preventDefault()
  togglePlay()
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  // 刷新/关闭页面时兜底保存未落库的时间线（pagehide 比 beforeunload 在各端更可靠）。
  window.addEventListener('pagehide', flushPendingSave)
  if (!projectPublicId.value) {
    ElMessage.error('缺少项目标识，请从制作工作台进入剪辑台')
    return
  }
  try {
    await Promise.all([loadProject(), loadLibrary()])
    await loadEditorProject()
  } catch (error) {
    ElMessage.error(errorDetail(error, '加载剪辑台失败'))
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('pagehide', flushPendingSave)
  // SPA 内路由离开：页面存活，keepalive 请求可正常完成。
  flushPendingSave()
  playback.destroy()
  if (saveTimer) clearTimeout(saveTimer)
})
</script>

<style scoped>
.editor-page {
  box-sizing: border-box;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 20px;
  color: #e6edf3;
  font-family: Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background:
    radial-gradient(circle at top, rgba(100, 116, 139, 0.18) 0%, rgba(11, 13, 16, 0) 32%),
    linear-gradient(180deg, #0d1117 0%, #0b0d10 100%);
}

.editor-body {
  flex: 1;
  min-height: 0;
  display: grid;
  /* 素材区加宽，与播放区之间不留列间距（原间距并入素材区宽度）。 */
  grid-template-columns: 248px minmax(0, 1fr);
  column-gap: 0;
  row-gap: 14px;
}

/* 素材区收起：面板 display:none 后网格改单列，播放器占满整行。 */
.editor-body.is-library-collapsed {
  grid-template-columns: minmax(0, 1fr);
}

.stage-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>

<style>
/* ElMessageBox 挂载于 body，需用全局样式适配剪辑台暗色风格。 */
.editor-dark-confirm {
  --el-messagebox-title-color: #e6edf3;
  --el-messagebox-content-color: #c5cdd6;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: #161b22;
}

.editor-dark-confirm .el-message-box__headerbtn .el-message-box__close {
  color: #8b949e;
}

/* 导出下拉菜单同样挂载于 body，统一暗色弹层。 */
.editor-dark-popper.el-popper {
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: #161b22;
}

.editor-dark-popper .el-dropdown-menu {
  background: transparent;
}

.editor-dark-popper .el-dropdown-menu__item {
  color: #c5cdd6;
}

.editor-dark-popper .el-dropdown-menu__item:not(.is-disabled):hover {
  color: #ffffff;
  background: rgba(37, 99, 235, 0.25);
}

.editor-dark-popper .el-popper__arrow::before {
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: #161b22;
}
</style>