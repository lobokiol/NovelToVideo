import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadProjectMediaApi } from '@/api/media'
import { errorDetail } from '@/utils/httpError'
import { clipDurationMs } from '@/components/editor/timelineDoc'
import type { TimelineClip, TimelineTrack } from '@/components/editor/types'

/** 导出完成后建议跳转的素材页签。 */
export type ExportedTab = 'shots' | 'images' | 'audio' | 'exports'

export interface TimelineExportOptions {
  projectPublicId: () => string
  projectName: () => string
  /** 画幅比例（'16:9' 或竖屏），决定合成分辨率。 */
  ratio: () => string
  tracks: () => TimelineTrack[]
  resolveMediaUrl: (mediaPublicId: string) => string
  /** 导出产物回传媒体库成功后触发，携带产物归属页签，页面用于切换并刷新列表。 */
  onExported?: (tab: ExportedTab) => void | Promise<void>
}

type Mp4ClipCtor = typeof import('@webav/av-cliper').MP4Clip
type AudioClipCtor = typeof import('@webav/av-cliper').AudioClip
type ImgClipCtor = typeof import('@webav/av-cliper').ImgClip
type RenderTxt2ImgBitmap = typeof import('@webav/av-cliper').renderTxt2ImgBitmap

/** 文本片段导出时的渲染样式，与预览层字幕样式保持一致的观感（含缩放倍率与换行盒宽）。 */
const textCssFor = (height: number, scale: number, boxWidthPx = 0) => (
  `font-size: ${Math.max(8, Math.round(height * 0.06 * scale))}px; color: #ffffff; font-weight: 600;` +
  ' text-shadow: 0 2px 10px rgba(0, 0, 0, 0.85);' +
  " font-family: Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif;" +
  (boxWidthPx > 0 ? ` width: ${Math.round(boxWidthPx)}px; text-align: center; white-space: pre-wrap; word-break: break-word;` : '')
)

/** 16bit PCM WAV 编码：截取 [offsetFrames, offsetFrames+frames) 并应用增益。 */
const encodeWavBlob = (
  buffer: AudioBuffer,
  offsetFrames: number,
  frames: number,
  gain: number,
): Blob => {
  const channels = Math.max(1, Math.min(2, buffer.numberOfChannels))
  const sampleRate = buffer.sampleRate
  const dataBytes = frames * channels * 2
  const arrayBuffer = new ArrayBuffer(44 + dataBytes)
  const view = new DataView(arrayBuffer)
  const writeAscii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
  }
  writeAscii(0, 'RIFF')
  view.setUint32(4, 36 + dataBytes, true)
  writeAscii(8, 'WAVE')
  writeAscii(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, channels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * channels * 2, true)
  view.setUint16(32, channels * 2, true)
  view.setUint16(34, 16, true)
  writeAscii(36, 'data')
  view.setUint32(40, dataBytes, true)
  let cursor = 44
  const channelData: Float32Array[] = []
  for (let ch = 0; ch < channels; ch += 1) channelData.push(buffer.getChannelData(ch))
  for (let frame = 0; frame < frames; frame += 1) {
    for (let ch = 0; ch < channels; ch += 1) {
      const sample = Math.max(-1, Math.min(1, (channelData[ch][offsetFrames + frame] ?? 0) * gain))
      view.setInt16(cursor, Math.round(sample * 32767), true)
      cursor += 2
    }
  }
  return new Blob([arrayBuffer], { type: 'audio/wav' })
}

/**
 * 多轨时间线浏览器端合成导出（WebCodecs）。
 *
 * 视频层级与时间线一致：磁性主轨 zIndex 0 在最底层，副轨越靠上层级越高；
 * 音频轨全部混入。轨道静音只作用于声音，不隐藏画面。
 */
export function useTimelineExport(opts: TimelineExportOptions) {
  const exporting = ref(false)
  const exportProgress = ref('')

  const ratioSize = (): [number, number] => (opts.ratio() === '16:9' ? [1280, 720] : [720, 1280])

  const fetchMediaStream = async (mediaPublicId: string) => {
    const response = await fetch(opts.resolveMediaUrl(mediaPublicId))
    if (!response.ok || !response.body) throw new Error('拉取媒体内容失败')
    return response.body
  }

  /** 按片段 in/out 裁剪出参与合成的 MP4Clip。 */
  const buildVideoSource = async (MP4Clip: Mp4ClipCtor, clip: TimelineClip, audioEnabled: boolean) => {
    let mp4Clip = new MP4Clip(await fetchMediaStream(clip.mediaPublicId), {
      audio: audioEnabled ? { volume: clip.volume } : false,
    })
    await mp4Clip.ready
    if (clip.inMs > 0) {
      const [, tail] = await mp4Clip.split(clip.inMs * 1000)
      mp4Clip = tail
    }
    const keepUs = clipDurationMs(clip) * 1000
    const meta = await mp4Clip.ready
    if (meta.duration > keepUs + 1000) {
      const [head] = await mp4Clip.split(keepUs)
      mp4Clip = head
    }
    return mp4Clip
  }

  /** 按片段 in/out 裁剪出参与混音的 AudioClip。 */
  const buildAudioSource = async (AudioClip: AudioClipCtor, clip: TimelineClip) => {
    let audioClip = new AudioClip(await fetchMediaStream(clip.mediaPublicId), { volume: clip.volume })
    await audioClip.ready
    if (clip.inMs > 0) {
      const [, tail] = await audioClip.split(clip.inMs * 1000)
      audioClip = tail
    }
    const keepUs = clipDurationMs(clip) * 1000
    const meta = await audioClip.ready
    if (meta.duration > keepUs + 1000) {
      const [head] = await audioClip.split(keepUs)
      audioClip = head
    }
    return audioClip
  }

  /** 图片静帧：整段取同一画面，时长由 sprite.time.duration 决定。 */
  const buildImageSource = async (ImgClip: ImgClipCtor, clip: TimelineClip) => {
    const imgClip = new ImgClip(await fetchMediaStream(clip.mediaPublicId))
    await imgClip.ready
    return imgClip
  }

  /** 文本片段：文字按换行盒宽渲染为位图后作为静帧参与合成。 */
  const buildTextSource = async (
    ImgClip: ImgClipCtor,
    renderTxt2ImgBitmap: RenderTxt2ImgBitmap,
    clip: TimelineClip,
    outputWidth: number,
    outputHeight: number,
  ) => {
    const boxWidthPx = outputWidth * (clip.textBoxWidth || 0.88)
    const bitmap = await renderTxt2ImgBitmap(
      clip.text || clip.label,
      textCssFor(outputHeight, clip.textScale || 1, boxWidthPx),
    )
    const imgClip = new ImgClip(bitmap)
    await imgClip.ready
    return imgClip
  }

  /**
   * 音频片段导出为音频素材：解码原始内容，按 in/out 截取并应用片段音量，
   * 编码为 16bit PCM WAV 回传音频素材库。
   */
  const exportAudioClip = async (clip: TimelineClip) => {
    exporting.value = true
    exportProgress.value = '解码音频'
    try {
      const response = await fetch(opts.resolveMediaUrl(clip.mediaPublicId))
      if (!response.ok) throw new Error('拉取媒体内容失败')
      const audioContext = new AudioContext()
      let buffer: AudioBuffer
      try {
        buffer = await audioContext.decodeAudioData(await response.arrayBuffer())
      } finally {
        void audioContext.close()
      }
      const sampleRate = buffer.sampleRate
      const from = Math.max(0, Math.floor((clip.inMs / 1000) * sampleRate))
      const to = Math.min(buffer.length, Math.ceil((clip.outMs / 1000) * sampleRate))
      if (to - from < 1) throw new Error('音频片段区间无有效采样')
      exportProgress.value = '编码 WAV'
      const blob = encodeWavBlob(buffer, from, to - from, clip.muted ? 0 : clip.volume)
      exportProgress.value = '回传媒体库'
      await uploadProjectMediaApi(opts.projectPublicId(), blob, {
        filename: `${clip.label}-片段-${Date.now()}.wav`,
        scopeType: 'project',
        mediaRole: 'reference',
      })
      ElMessage.success('片段已导出到音频素材')
      await opts.onExported?.('audio')
    } catch (error) {
      console.error('导出音频片段失败', error)
      ElMessage.error(errorDetail(error, '导出音频片段失败'))
    } finally {
      exporting.value = false
      exportProgress.value = ''
    }
  }

  /**
   * 图片/文本片段导出为图片素材：图片片段转存原图内容，
   * 文本片段按导出分辨率渲染为透明底 PNG，均回传图片素材库。
   */
  const exportStillClip = async (clip: TimelineClip) => {
    exporting.value = true
    exportProgress.value = '生成图片'
    try {
      let blob: Blob
      let filename: string
      if (clip.mediaType === 'image') {
        const response = await fetch(opts.resolveMediaUrl(clip.mediaPublicId))
        if (!response.ok) throw new Error('拉取媒体内容失败')
        blob = await response.blob()
        const ext = (blob.type.split('/')[1] || 'png').split('+')[0]
        filename = `${clip.label}-片段-${Date.now()}.${ext}`
      } else {
        const { renderTxt2ImgBitmap } = await import('@webav/av-cliper')
        const [width, height] = ratioSize()
        const bitmap = await renderTxt2ImgBitmap(
          clip.text || clip.label,
          textCssFor(height, clip.textScale || 1, width * (clip.textBoxWidth || 0.88)),
        )
        const canvas = new OffscreenCanvas(bitmap.width, bitmap.height)
        canvas.getContext('2d')?.drawImage(bitmap, 0, 0)
        blob = await canvas.convertToBlob({ type: 'image/png' })
        filename = `文本片段-${Date.now()}.png`
      }
      exportProgress.value = '回传媒体库'
      await uploadProjectMediaApi(opts.projectPublicId(), blob, {
        filename,
        scopeType: 'project',
        mediaRole: 'reference',
      })
      ElMessage.success('片段已导出到图片素材')
      await opts.onExported?.('images')
    } catch (error) {
      console.error('导出片段失败', error)
      ElMessage.error(errorDetail(error, '导出片段失败'))
    } finally {
      exporting.value = false
      exportProgress.value = ''
    }
  }

  const exportTimeline = async (mode: 'full' | 'selection', selectionClip?: TimelineClip | null, title?: string) => {
    const tracks = opts.tracks()
    const videoTracks = tracks.filter((track) => track.kind === 'video')

    interface VideoJob {
      clip: TimelineClip
      track: TimelineTrack
      zIndex: number
      offsetMs: number
    }
    const jobs: VideoJob[] = []
    if (mode === 'selection') {
      if (!selectionClip) {
        ElMessage.warning('请先选中要导出的片段')
        return
      }
      // 片段导出按素材类型分流：图片/文本产出图片素材，音频产出 WAV，视频走合成。
      if (selectionClip.mediaType === 'image' || selectionClip.mediaType === 'text') {
        await exportStillClip(selectionClip)
        return
      }
      if (selectionClip.mediaType === 'audio') {
        await exportAudioClip(selectionClip)
        return
      }
      const track = videoTracks.find((item) => item.clips.some((clip) => clip.id === selectionClip.id))
      if (!track) {
        ElMessage.warning('请先选中要导出的视频片段')
        return
      }
      jobs.push({ clip: selectionClip, track, zIndex: 0, offsetMs: 0 })
    } else {
      // videoTracks 数组自上而下即层级自高到低；zIndex 越小越靠底层。隐藏轨整体不参与合成。
      for (const [index, track] of videoTracks.entries()) {
        if (track.hidden) continue
        const zIndex = videoTracks.length - 1 - index
        for (const clip of track.clips) {
          jobs.push({ clip, track, zIndex, offsetMs: clip.startMs })
        }
      }
      jobs.sort((a, b) => a.zIndex - b.zIndex || a.offsetMs - b.offsetMs)
    }
    if (jobs.length === 0) {
      ElMessage.warning('时间线上还没有视频片段')
      return
    }

    exporting.value = true
    exportProgress.value = '准备中'
    try {
      const { Combinator, OffscreenSprite, MP4Clip, AudioClip, ImgClip, renderTxt2ImgBitmap } =
        await import('@webav/av-cliper')
      const [width, height] = ratioSize()
      const combinator = new Combinator({ width, height, bgColor: '#000' })

      for (const [index, job] of jobs.entries()) {
        exportProgress.value = `解码素材 ${index + 1}/${jobs.length}`
        const keepUs = clipDurationMs(job.clip) * 1000
        let sprite: InstanceType<typeof OffscreenSprite>
        if (job.clip.mediaType === 'image') {
          sprite = new OffscreenSprite(await buildImageSource(ImgClip, job.clip))
          await sprite.ready
          sprite.time.duration = keepUs
          // 图片等比缩放居中（与预览层 contain 观感一致），避免任意比例素材被拉伸。
          const scale = Math.min(width / sprite.rect.w, height / sprite.rect.h)
          sprite.rect.w *= scale
          sprite.rect.h *= scale
          sprite.rect.x = (width - sprite.rect.w) / 2
          sprite.rect.y = (height - sprite.rect.h) / 2
        } else if (job.clip.mediaType === 'text') {
          sprite = new OffscreenSprite(await buildTextSource(ImgClip, renderTxt2ImgBitmap, job.clip, width, height))
          await sprite.ready
          sprite.time.duration = keepUs
          // 应用文本变换：位置偏移（相对画面中心）与旋转，与预览层一致。
          sprite.rect.x = (width - sprite.rect.w) / 2 + (job.clip.textX || 0) * width
          sprite.rect.y = (height - sprite.rect.h) / 2 + (job.clip.textY || 0) * height
          sprite.rect.angle = ((job.clip.textRotate || 0) * Math.PI) / 180
        } else {
          const audioEnabled = !(job.track.muted || job.clip.muted)
          sprite = new OffscreenSprite(await buildVideoSource(MP4Clip, job.clip, audioEnabled))
          await sprite.ready
          sprite.rect.w = width
          sprite.rect.h = height
        }
        sprite.time.offset = job.offsetMs * 1000
        sprite.zIndex = job.zIndex
        await combinator.addSprite(sprite)
      }

      if (mode === 'full') {
        for (const track of tracks) {
          if (track.kind !== 'audio' || track.muted) continue
          for (const clip of track.clips) {
            if (clip.muted) continue
            exportProgress.value = '合成音轨'
            const source = await buildAudioSource(AudioClip, clip)
            const sprite = new OffscreenSprite(source)
            await sprite.ready
            sprite.time.offset = clip.startMs * 1000
            await combinator.addSprite(sprite)
          }
        }
      }

      exportProgress.value = '编码合成中'
      const raw = await new Response(combinator.output()).blob()
      // 合成流转出的 Blob 无 MIME 类型，后端按 Content-Type 校验媒体类型，需显式声明。
      const blob = new Blob([raw], { type: 'video/mp4' })
      exportProgress.value = '回传媒体库'
      // 完整成片归成片页签（final）；片段导出归镜头片段页签（reference，可再次拖轨复用）。
      const fallbackName = mode === 'selection'
        ? `${selectionClip?.label || '片段'}-片段-${Date.now()}`
        : `${opts.projectName() || '项目'}-成片-${Date.now()}`
      const exportName = (title || '').trim() || fallbackName
      await uploadProjectMediaApi(opts.projectPublicId(), blob, {
        filename: `${exportName}.mp4`,
        scopeType: 'project',
        mediaRole: mode === 'selection' ? 'reference' : 'final',
      })
      ElMessage.success(mode === 'selection' ? '片段已导出到镜头片段素材' : '成片导出完成，已回传媒体库')
      await opts.onExported?.(mode === 'selection' ? 'shots' : 'exports')
    } catch (error) {
      console.error('导出失败', error)
      ElMessage.error(errorDetail(error, '导出失败：当前浏览器可能不支持 WebCodecs，请使用新版 Chrome/Edge'))
    } finally {
      exporting.value = false
      exportProgress.value = ''
    }
  }

  return { exporting, exportProgress, exportTimeline }
}