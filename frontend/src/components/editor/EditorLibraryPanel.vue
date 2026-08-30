<template>
  <aside class="library-panel">
    <el-tabs :model-value="activeTab" class="library-tabs" @update:model-value="onTabChange">
      <el-tab-pane label="镜头片段" name="shots">
        <div class="library-upload">
          <el-upload :show-file-list="false" accept="video/*" :before-upload="onUploadVideo">
            <el-button class="ghost-button" size="small">
              <el-icon><Plus /></el-icon>
              上传视频
            </el-button>
          </el-upload>
        </div>
        <div v-loading="loading" class="library-list" element-loading-background="rgba(7, 10, 16, 0.7)">
          <div
            v-for="item in shotLibrary"
            :key="item.media.publicId"
            class="library-item"
            draggable="true"
            @dragstart="onVideoDragStart($event, item)"
          >
            <div
              class="library-item__preview"
              :class="{ 'is-playing': activePlayId === item.media.publicId }"
              @click="togglePlay(item.media.publicId)"
            >
              <video
                :ref="(el) => registerMediaEl(item.media.publicId, el)"
                v-lazy-src="mediaContentUrl(projectPublicId, item.media.publicId)"
                class="preview-media"
                :muted="activePlayId !== item.media.publicId"
                preload="metadata"
                playsinline
                draggable="false"
                @ended="onMediaEnded(item.media.publicId)"
              ></video>
              <span v-if="isUsed(item.media.publicId)" class="badge badge--added">已添加</span>
              <span class="badge badge--duration">{{ formatShortMs(item.media.durationMs) }}</span>
              <button class="overlay-btn overlay-btn--play" type="button" :title="activePlayId === item.media.publicId ? '暂停' : '播放'">
                <el-icon><VideoPause v-if="activePlayId === item.media.publicId" /><VideoPlay v-else /></el-icon>
              </button>
              <button
                class="overlay-btn overlay-btn--add"
                type="button"
                title="加入主轨"
                @click.stop="emit('add-video', item)"
              >
                <el-icon><Plus /></el-icon>
              </button>
            </div>
            <div class="library-item__name" :title="item.label">
              {{ item.label }}<em v-if="item.media.mediaRole === 'final'"> · 选定</em>
            </div>
          </div>
          <el-empty v-if="!loading && shotLibrary.length === 0" description="暂无镜头视频，可在制作工作台生成或上传" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="图片" name="images">
        <div class="library-upload">
          <el-upload :show-file-list="false" accept="image/*" :before-upload="onUploadImage">
            <el-button class="ghost-button" size="small">
              <el-icon><Plus /></el-icon>
              上传图片
            </el-button>
          </el-upload>
        </div>
        <div v-loading="loading" class="library-list" element-loading-background="rgba(7, 10, 16, 0.7)">
          <div
            v-for="item in imageLibrary"
            :key="item.media.publicId"
            class="library-item"
            draggable="true"
            @dragstart="onImageDragStart($event, item)"
          >
            <div class="library-item__preview is-static">
              <img
                v-lazy-src="mediaContentUrl(projectPublicId, item.media.publicId)"
                class="preview-media"
                draggable="false"
                alt=""
              />
              <span v-if="isUsed(item.media.publicId)" class="badge badge--added">已添加</span>
              <button
                class="overlay-btn overlay-btn--add"
                type="button"
                title="加入主轨"
                @click.stop="emit('add-image', item.media, item.label)"
              >
                <el-icon><Plus /></el-icon>
              </button>
            </div>
            <div class="library-item__name" :title="item.label">
              {{ item.label }}
            </div>
          </div>
          <el-empty v-if="!loading && imageLibrary.length === 0" description="暂无图片素材" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="音频" name="audio">
        <div class="library-upload">
          <el-upload :show-file-list="false" accept="audio/*" :before-upload="onUploadAudio">
            <el-button class="ghost-button" size="small">
              <el-icon><Plus /></el-icon>
              上传音频
            </el-button>
          </el-upload>
        </div>
        <div v-loading="loading" class="library-list" element-loading-background="rgba(7, 10, 16, 0.7)">
          <div
            v-for="media in audioLibrary"
            :key="media.publicId"
            class="library-item is-audio"
            draggable="true"
            @dragstart="onAudioDragStart($event, media)"
          >
            <button
              class="audio-row"
              :class="{ 'is-playing': activePlayId === media.publicId }"
              type="button"
              @click="togglePlay(media.publicId)"
            >
              <el-icon class="audio-icon"><VideoPause v-if="activePlayId === media.publicId" /><VideoPlay v-else /></el-icon>
              <span class="audio-title" :title="audioLabel(media)">{{ audioLabel(media) }}</span>
              <span v-if="isUsed(media.publicId)" class="badge badge--added is-inline">已添加</span>
              <span class="audio-duration">{{ formatShortMs(media.durationMs) }}</span>
              <audio
                :ref="(el) => registerMediaEl(media.publicId, el)"
                :src="mediaContentUrl(projectPublicId, media.publicId)"
                preload="none"
                @ended="onMediaEnded(media.publicId)"
              ></audio>
            </button>
            <button
              class="overlay-btn overlay-btn--add is-inline"
              type="button"
              title="加入音轨"
              @click.stop="emit('add-audio', media, audioLabel(media))"
            >
              <el-icon><Plus /></el-icon>
            </button>
          </div>
          <el-empty v-if="!loading && audioLibrary.length === 0" description="暂无音频素材" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="成片" name="exports">
        <div v-loading="loading" class="library-list" element-loading-background="rgba(7, 10, 16, 0.7)">
          <div v-for="media in exportLibrary" :key="media.publicId" class="library-item">
            <video
              v-lazy-src="mediaContentUrl(projectPublicId, media.publicId)"
              class="library-item__export-video"
              preload="metadata"
              controls
              draggable="false"
            ></video>
            <div class="library-item__name" :title="exportName(media)">
              {{ exportName(media) }}
              <em class="export-time">{{ new Date(media.createdAt).toLocaleString() }}</em>
            </div>
            <div class="export-actions">
              <el-button size="small" type="primary" @click="downloadExport(media)">
                <el-icon><Download /></el-icon>
                导出下载
              </el-button>
              <el-button size="small" class="danger-button" @click="emit('delete-export', media)">
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </div>
          </div>
          <el-empty v-if="!loading && exportLibrary.length === 0" description="暂无导出成片" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </aside>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { Delete, Download, Plus, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { mediaContentUrl, type MediaAssetRecord } from '@/api/media'
import { formatShortMs } from './timelineDoc'
import { disconnectLazyObservers, lazySrcDirective } from './lazyMedia'
import { mediaDragMime, type MediaDragPayload, type ShotLibraryItem } from './types'

/** 素材缩略图/预览懒加载：初始只载第 1、2 屏，其余跟随滚动加载（v-lazy-src）。 */
const vLazySrc = lazySrcDirective

const props = defineProps<{
  projectPublicId: string
  loading: boolean
  activeTab: string
  shotLibrary: ShotLibraryItem[]
  /** 图片素材，label 已在页面侧解析（文件名/分镜归属）。 */
  imageLibrary: ShotLibraryItem[]
  audioLibrary: MediaAssetRecord[]
  exportLibrary: MediaAssetRecord[]
  /** 已被时间线任一片段引用的媒体标识，用于「已添加」角标。 */
  usedMediaIds: string[]
}>()

const emit = defineEmits<{
  (e: 'update:activeTab', tab: string): void
  (e: 'add-video', item: ShotLibraryItem): void
  (e: 'add-image', media: MediaAssetRecord, label: string): void
  (e: 'add-audio', media: MediaAssetRecord, label: string): void
  (e: 'upload-audio', file: File): void
  (e: 'upload-video', file: File): void
  (e: 'upload-image', file: File): void
  (e: 'delete-export', media: MediaAssetRecord): void
}>()

const onTabChange = (tab: string | number) => emit('update:activeTab', String(tab))

const isUsed = (publicId: string) => props.usedMediaIds.includes(publicId)

// ---------------------------------------------------------------------------
// 素材就地试听：一次仅一个媒体播放，暂停/播完进度归零等待下次。
// ---------------------------------------------------------------------------

const mediaEls = new Map<string, HTMLMediaElement>()
const activePlayId = ref('')

const registerMediaEl = (publicId: string, el: unknown) => {
  if (el instanceof HTMLMediaElement) mediaEls.set(publicId, el)
  else mediaEls.delete(publicId)
}

const resetMedia = (publicId: string) => {
  const el = mediaEls.get(publicId)
  if (!el) return
  el.pause()
  el.currentTime = 0
}

const togglePlay = (publicId: string) => {
  if (activePlayId.value === publicId) {
    resetMedia(publicId)
    activePlayId.value = ''
    return
  }
  if (activePlayId.value) resetMedia(activePlayId.value)
  const el = mediaEls.get(publicId)
  if (!el) return
  activePlayId.value = publicId
  void el.play().catch(() => {
    activePlayId.value = ''
  })
}

const onMediaEnded = (publicId: string) => {
  resetMedia(publicId)
  if (activePlayId.value === publicId) activePlayId.value = ''
}

onBeforeUnmount(() => {
  for (const el of mediaEls.values()) el.pause()
  mediaEls.clear()
  disconnectLazyObservers()
})

// ---------------------------------------------------------------------------
// 素材标签与拖拽负载
// ---------------------------------------------------------------------------

/** 素材展示名：优先上传/生成时记录的文件名。 */
const mediaLabel = (media: MediaAssetRecord, fallback: string) => {
  try {
    const params = JSON.parse(media.params || '{}') as { filename?: string }
    if (params.filename) return params.filename
  } catch {
    // params 非法时退回默认标签
  }
  return fallback
}

const audioLabel = (media: MediaAssetRecord) => mediaLabel(media, '音频素材')

/** 成片显示名：优先导出时设置的标题（存于 params.filename，去掉扩展名）。 */
const exportName = (media: MediaAssetRecord) => {
  const filename = mediaLabel(media, '')
  if (filename) return filename.replace(/\.[a-z0-9]+$/i, '')
  return media.mediaRole === 'final' ? '完整成片' : '导出片段'
}

/** 成片导出下载：同源内容 URL 直接触发浏览器下载，文件名取导出标题。 */
const downloadExport = (media: MediaAssetRecord) => {
  const anchor = document.createElement('a')
  anchor.href = mediaContentUrl(props.projectPublicId, media.publicId)
  anchor.download = `${exportName(media)}.mp4`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

const setDragPayload = (event: DragEvent, payload: MediaDragPayload) => {
  if (!event.dataTransfer) return
  event.dataTransfer.setData(mediaDragMime(payload.kind), JSON.stringify(payload))
  event.dataTransfer.effectAllowed = 'copy'
}

const onVideoDragStart = (event: DragEvent, item: ShotLibraryItem) => {
  setDragPayload(event, {
    kind: 'video',
    mediaType: 'video',
    mediaPublicId: item.media.publicId,
    label: item.label,
    durationMs: item.media.durationMs || 0,
  })
}

const onImageDragStart = (event: DragEvent, item: ShotLibraryItem) => {
  setDragPayload(event, {
    kind: 'video',
    mediaType: 'image',
    mediaPublicId: item.media.publicId,
    label: item.label,
    durationMs: 0,
  })
}

const onAudioDragStart = (event: DragEvent, media: MediaAssetRecord) => {
  setDragPayload(event, {
    kind: 'audio',
    mediaType: 'audio',
    mediaPublicId: media.publicId,
    label: audioLabel(media),
    durationMs: media.durationMs || 0,
  })
}

const onUploadAudio = (file: File) => {
  emit('upload-audio', file)
  return false
}

const onUploadVideo = (file: File) => {
  emit('upload-video', file)
  return false
}

const onUploadImage = (file: File) => {
  emit('upload-image', file)
  return false
}
</script>

<style scoped>
.library-panel {
  min-height: 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(13, 17, 23, 0.86);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.library-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 0 10px;
}

.library-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.library-tabs :deep(.el-tab-pane) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.library-upload {
  padding: 4px 0 8px;
}

.library-list {
  flex: 1;
  min-height: 120px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 12px;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.34) transparent;
}

.library-list::-webkit-scrollbar {
  width: 8px;
}

.library-list::-webkit-scrollbar-track {
  background: transparent;
}

.library-list::-webkit-scrollbar-thumb {
  min-height: 32px;
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.32);
  background-clip: padding-box;
}

.library-list::-webkit-scrollbar-thumb:hover {
  background: rgba(203, 213, 225, 0.46);
  background-clip: padding-box;
}

.library-item[draggable='true'] {
  cursor: grab;
}

.library-item[draggable='true']:active {
  cursor: grabbing;
}

/* 预览容器：16:9，媒体等比 contain 完整展示不裁切。 */
.library-item__preview {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 6px;
  overflow: hidden;
  background: #000;
  cursor: pointer;
}

.library-item__preview.is-static {
  cursor: default;
}

.preview-media {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  pointer-events: none;
}

/* 剪映式角标：黑底半透明小标签叠在缩略图上。 */
.badge {
  position: absolute;
  z-index: 2;
  padding: 1px 4px;
  border-radius: 2px;
  background: rgba(0, 0, 0, 0.68);
  color: #e6edf3;
  font-size: 9px;
  line-height: 14px;
  pointer-events: none;
}

.badge--added {
  top: 4px;
  left: 4px;
}

.badge--duration {
  top: 4px;
  right: 4px;
  font-variant-numeric: tabular-nums;
}

.badge.is-inline {
  position: static;
  flex-shrink: 0;
}

.overlay-btn {
  position: absolute;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease;
}

.overlay-btn--play {
  inset: 0;
  margin: auto;
  width: 36px;
  height: 36px;
  font-size: 18px;
}

.overlay-btn--add {
  right: 6px;
  bottom: 6px;
  width: 24px;
  height: 24px;
  font-size: 14px;
  background: rgba(37, 99, 235, 0.9);
}

.library-item__preview:hover .overlay-btn,
.library-item__preview.is-playing .overlay-btn--play {
  opacity: 1;
}

.overlay-btn--play:hover {
  background: rgba(37, 99, 235, 0.85);
}

.overlay-btn--add:hover {
  background: #2563eb;
}

/* 名称与时长角标采用更小字号，缩略图信息密度更高。 */
.library-item__name {
  margin-top: 4px;
  color: #c5cdd6;
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.library-item__name em {
  color: #4ade80;
  font-style: normal;
}

.library-item__name .export-time {
  color: #6e7681;
  font-size: 10px;
}

.export-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 5px 0 2px;
}

/* 成片操作钮整体缩小：高度约为 small 尺寸的 60%，字体同步缩小。 */
.export-actions :deep(.el-button) {
  height: 18px;
  padding: 0 7px;
  font-size: 10px;
  border-radius: 4px;
}

.export-actions :deep(.el-button .el-icon) {
  font-size: 10px;
}

.export-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.danger-button {
  --el-button-bg-color: rgba(248, 113, 113, 0.12);
  --el-button-border-color: rgba(248, 113, 113, 0.4);
  --el-button-text-color: #fca5a5;
  --el-button-hover-bg-color: rgba(248, 113, 113, 0.2);
  --el-button-hover-border-color: rgba(248, 113, 113, 0.6);
  --el-button-hover-text-color: #fecaca;
}

/* 音频行卡：整行播放/暂停，右侧悬停加入按钮。 */
.library-item.is-audio {
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}

.audio-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 34px 8px 10px;
  border: none;
  background: transparent;
  color: #e6edf3;
  cursor: pointer;
  text-align: left;
}

.audio-row .audio-icon {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: rgba(74, 222, 128, 0.16);
  color: #4ade80;
  font-size: 14px;
}

.audio-row.is-playing .audio-icon {
  background: rgba(74, 222, 128, 0.34);
}

.audio-title {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.audio-duration {
  flex-shrink: 0;
  color: #6e7681;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.audio-row audio {
  display: none;
}

.library-item.is-audio .overlay-btn--add.is-inline {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  bottom: auto;
}

.library-item.is-audio:hover .overlay-btn--add.is-inline {
  opacity: 1;
}

.library-item__export-video {
  width: 100%;
  max-height: 120px;
  display: block;
  border-radius: 6px;
  background: #000;
}

.ghost-button {
  --el-button-bg-color: rgba(255, 255, 255, 0.04);
  --el-button-border-color: rgba(255, 255, 255, 0.14);
  --el-button-text-color: #c5cdd6;
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.08);
  --el-button-hover-border-color: rgba(255, 255, 255, 0.24);
  --el-button-hover-text-color: #fff;
}

:deep(.el-tabs__item) {
  color: #8b949e;
}

:deep(.el-tabs__item.is-active) {
  color: #93c5fd;
}

:deep(.el-tabs__nav-wrap::after) {
  background: rgba(255, 255, 255, 0.08);
}
</style>