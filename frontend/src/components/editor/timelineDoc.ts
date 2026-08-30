import {
  EDITOR_FPS,
  MAX_STILL_DURATION_MS,
  MIN_CLIP_MS,
  TEXT_BOX_WIDTH_DEFAULT,
  TEXT_BOX_WIDTH_MAX,
  TEXT_BOX_WIDTH_MIN,
  TEXT_OFFSET_LIMIT,
  TEXT_OFFSET_Y_DEFAULT,
  TEXT_SCALE_MAX,
  TEXT_SCALE_MIN,
  type ClipMediaType,
  type TimelineClip,
  type TimelineDoc,
  type TimelineTrack,
  type TrackKind,
} from './types'

let idSeed = 0

/** 生成时间线内唯一 ID；Date.now 保证跨会话，seed 保证同毫秒不冲突。 */
export const nextTimelineId = (prefix: string) => {
  idSeed += 1
  return `${prefix}-${Date.now()}-${idSeed}`
}

export const clipDurationMs = (clip: TimelineClip) => Math.max(0, clip.outMs - clip.inMs)

export const clipEndMs = (clip: TimelineClip) => clip.startMs + clipDurationMs(clip)

/** 图片/文本这类无固有素材时长、可自由拉伸的静态片段。 */
export const isStillClip = (clip: TimelineClip) => clip.mediaType === 'image' || clip.mediaType === 'text'

/** 磁性轨道重排：startMs 恒由数组顺序上前序片段时长累计得出。 */
export const relayoutMagneticTrack = (track: TimelineTrack) => {
  let cursor = 0
  for (const clip of track.clips) {
    clip.startMs = cursor
    cursor += clipDurationMs(clip)
  }
}

/** 自由轨道按 startMs 升序，保证渲染次序与命中判断稳定。 */
export const sortFreeTrack = (track: TimelineTrack) => {
  track.clips.sort((a, b) => a.startMs - b.startMs)
}

/**
 * 求片段在自由轨道上的合法起点：期望位置落入可容纳空隙则原样返回，
 * 否则夹紧到距离最近的可容纳空隙边界，保证同轨片段互不重叠。
 */
export const resolveFreeStart = (
  track: TimelineTrack,
  movingClipId: string,
  desiredStartMs: number,
  durationMs: number,
): number => {
  const others = track.clips
    .filter((clip) => clip.id !== movingClipId)
    .sort((a, b) => a.startMs - b.startMs)
  const gaps: Array<[number, number]> = []
  let prevEnd = 0
  for (const clip of others) {
    if (clip.startMs - prevEnd >= durationMs) gaps.push([prevEnd, clip.startMs])
    prevEnd = Math.max(prevEnd, clipEndMs(clip))
  }
  gaps.push([prevEnd, Number.POSITIVE_INFINITY])
  let best = prevEnd
  let bestDistance = Number.POSITIVE_INFINITY
  for (const [gapStart, gapEnd] of gaps) {
    const clamped = Math.min(Math.max(desiredStartMs, gapStart), gapEnd - durationMs)
    const distance = Math.abs(clamped - desiredStartMs)
    if (distance < bestDistance) {
      bestDistance = distance
      best = clamped
    }
  }
  return Math.max(0, Math.round(best))
}

/**
 * 自由轨道上片段允许的最大 outMs：出点拉伸不得越过右侧最近片段的起点，
 * 保证任何裁剪操作都不会造成同轨重叠。
 */
export const maxFreeOutMs = (track: TimelineTrack, clip: TimelineClip): number => {
  let nextStart = Number.POSITIVE_INFINITY
  for (const other of track.clips) {
    if (other.id === clip.id) continue
    if (other.startMs >= clip.startMs && other.startMs < nextStart) nextStart = other.startMs
  }
  if (nextStart === Number.POSITIVE_INFINITY) return clip.srcDurationMs
  return Math.min(clip.srcDurationMs, clip.inMs + (nextStart - clip.startMs))
}

/** 磁性轨道插入序号：以各片段中点为界，返回落点 ms 应插入的位置。 */
export const magneticInsertIndex = (clips: TimelineClip[], ms: number): number => {
  let index = 0
  for (const clip of clips) {
    if (ms > clip.startMs + clipDurationMs(clip) / 2) index += 1
  }
  return index
}

/**
 * 在全局播放头位置分割片段：原片段收尾为前段，返回新建的后段；
 * 播放头距片段边缘不足最短时长时不分割并返回 null。
 */
export const splitClipAt = (clip: TimelineClip, playheadMs: number): TimelineClip | null => {
  const localMs = playheadMs - clip.startMs
  if (localMs < MIN_CLIP_MS || localMs > clipDurationMs(clip) - MIN_CLIP_MS) return null
  const splitPoint = clip.inMs + localMs
  const tail: TimelineClip = {
    ...clip,
    id: nextTimelineId('clip'),
    inMs: splitPoint,
    startMs: clip.startMs + localMs,
  }
  clip.outMs = splitPoint
  return tail
}

/** 文本缩放倍率合法化：非法输入回退基准 1。 */
export const clampTextScale = (value: unknown): number => {
  const scale = Number(value)
  if (!Number.isFinite(scale) || scale <= 0) return 1
  return Math.min(TEXT_SCALE_MAX, Math.max(TEXT_SCALE_MIN, scale))
}

/** 文本位置偏移合法化（相对画面比例，中心为 0）。 */
export const clampTextOffset = (value: unknown, fallback = 0): number => {
  const offset = Number(value)
  if (!Number.isFinite(offset)) return fallback
  return Math.min(TEXT_OFFSET_LIMIT, Math.max(-TEXT_OFFSET_LIMIT, offset))
}

/** 文本旋转角合法化：归一到 (-180, 180]。 */
export const clampTextRotate = (value: unknown): number => {
  const rotate = Number(value)
  if (!Number.isFinite(rotate)) return 0
  const normalized = ((rotate % 360) + 540) % 360 - 180
  return normalized === -180 ? 180 : normalized
}

/** 文本框宽度合法化（相对画面宽度比例）。 */
export const clampTextBoxWidth = (value: unknown): number => {
  const width = Number(value)
  if (!Number.isFinite(width) || width <= 0) return TEXT_BOX_WIDTH_DEFAULT
  return Math.min(TEXT_BOX_WIDTH_MAX, Math.max(TEXT_BOX_WIDTH_MIN, width))
}

export interface CreateClipOptions {
  mediaPublicId: string
  mediaType: ClipMediaType
  label: string
  srcDurationMs: number
  startMs: number
  /** 初始片段时长，默认取素材全长。 */
  durationMs?: number
  text?: string
}

export const createClip = (options: CreateClipOptions): TimelineClip => {
  const srcDurationMs = Math.max(0, options.srcDurationMs)
  const outMs = Math.min(srcDurationMs, Math.max(0, options.durationMs ?? srcDurationMs))
  return {
    id: nextTimelineId('clip'),
    mediaPublicId: options.mediaPublicId,
    mediaType: options.mediaType,
    label: options.label,
    text: options.text ?? '',
    textScale: 1,
    textX: 0,
    textY: TEXT_OFFSET_Y_DEFAULT,
    textRotate: 0,
    textBoxWidth: TEXT_BOX_WIDTH_DEFAULT,
    srcDurationMs,
    inMs: 0,
    outMs,
    startMs: Math.max(0, options.startMs),
    volume: 1,
    muted: false,
  }
}

export const createTrack = (
  kind: TrackKind,
  options: { name: string; magnetic?: boolean },
): TimelineTrack => ({
  id: nextTimelineId('track'),
  kind,
  name: options.name,
  muted: false,
  hidden: false,
  magnetic: Boolean(options.magnetic),
  clips: [],
})

/** 全时间线总时长：所有轨道片段的最晚结束时刻。 */
export const timelineDurationMs = (tracks: TimelineTrack[]): number => {
  let end = 0
  for (const track of tracks) {
    for (const clip of track.clips) end = Math.max(end, clipEndMs(clip))
  }
  return end
}

export const buildTimelineDoc = (ratio: string, tracks: TimelineTrack[]): TimelineDoc => ({
  version: 2,
  ratio,
  tracks: tracks.map((track) => ({
    id: track.id,
    kind: track.kind,
    name: track.name,
    muted: track.muted,
    hidden: track.hidden,
    magnetic: track.magnetic,
    clips: track.clips.map((clip) => ({ ...clip })),
  })),
})

const CLIP_MEDIA_TYPES: ClipMediaType[] = ['video', 'audio', 'image', 'text']

const normalizeClip = (raw: Partial<TimelineClip>, fallbackType: ClipMediaType): TimelineClip | null => {
  const mediaType = CLIP_MEDIA_TYPES.includes(raw.mediaType as ClipMediaType)
    ? (raw.mediaType as ClipMediaType)
    : fallbackType
  const mediaPublicId = String(raw.mediaPublicId || '').trim()
  // 文本片段无媒体标识；其余类型缺失标识视为脏数据丢弃。
  if (!mediaPublicId && mediaType !== 'text') return null
  const srcDurationMs = mediaType === 'image' || mediaType === 'text'
    ? Math.max(MAX_STILL_DURATION_MS, Number(raw.srcDurationMs) || 0)
    : Math.max(0, Number(raw.srcDurationMs) || 0)
  const outMs = Math.min(srcDurationMs || Number(raw.outMs) || 0, Number(raw.outMs) || srcDurationMs)
  return {
    id: String(raw.id || nextTimelineId('clip')),
    mediaPublicId,
    mediaType,
    label: String(raw.label || '片段'),
    text: String(raw.text || ''),
    textScale: clampTextScale(raw.textScale ?? 1),
    textX: clampTextOffset(raw.textX ?? 0),
    textY: clampTextOffset(raw.textY ?? TEXT_OFFSET_Y_DEFAULT, TEXT_OFFSET_Y_DEFAULT),
    textRotate: clampTextRotate(raw.textRotate ?? 0),
    textBoxWidth: clampTextBoxWidth(raw.textBoxWidth ?? TEXT_BOX_WIDTH_DEFAULT),
    srcDurationMs,
    inMs: Math.max(0, Number(raw.inMs) || 0),
    outMs: Math.max(0, outMs),
    startMs: Math.max(0, Number(raw.startMs) || 0),
    volume: Math.min(1, Math.max(0, Number(raw.volume ?? 1))),
    muted: Boolean(raw.muted),
  }
}

interface RawTrack {
  id?: unknown
  kind?: unknown
  name?: unknown
  muted?: unknown
  hidden?: unknown
  magnetic?: unknown
  clips?: Array<Partial<TimelineClip>>
}

export interface ParsedTimeline {
  ratio: string
  tracks: TimelineTrack[]
}

/**
 * 解析并归一化剪辑工程 JSON。
 *
 * 兼容 v1（单视频轨 + 单音频轨，无 muted/magnetic/mediaType 字段）与 v2 结构，统一产出：
 * 视频轨保持保存时的相对顺序（磁性主轨可居中，允许其下方存在副轨）、音轨殿后；
 * 恰有一条磁性主轨；磁性轨重排、自由轨排序；空辅轨直接剔除（与运行时自动清理一致），
 * 至少保证一条主轨与一条音轨存在。解析失败时抛出异常，由调用方决定重置策略。
 */
export const parseTimelineDoc = (json: string): ParsedTimeline => {
  const doc = JSON.parse(json || '{}') as { ratio?: unknown; tracks?: RawTrack[] }
  const rawTracks = Array.isArray(doc.tracks) ? doc.tracks : []
  const videoTracks: TimelineTrack[] = []
  const audioTracks: TimelineTrack[] = []
  for (const raw of rawTracks) {
    const kind = raw.kind === 'video' || raw.kind === 'audio' ? raw.kind : null
    if (!kind) continue
    const clips = (Array.isArray(raw.clips) ? raw.clips : [])
      .map((clip) => normalizeClip(clip, kind))
      .filter((clip): clip is TimelineClip => clip !== null)
    const track: TimelineTrack = {
      id: String(raw.id || nextTimelineId('track')),
      kind,
      name: String(raw.name || (kind === 'video' ? '视频轨' : '音频轨')),
      muted: Boolean(raw.muted),
      hidden: kind === 'video' && Boolean(raw.hidden),
      magnetic: kind === 'video' && Boolean(raw.magnetic),
      clips,
    }
    if (kind === 'video') videoTracks.push(track)
    else audioTracks.push(track)
  }

  // 保证恰有一条磁性主轨：优先首个声明者，缺失时取首条视频轨（覆盖 v1 单轨场景）。
  const magneticIndex = videoTracks.findIndex((track) => track.magnetic)
  const chosenIndex = magneticIndex === -1 ? 0 : magneticIndex
  for (const [index, track] of videoTracks.entries()) {
    track.magnetic = index === chosenIndex
  }
  let mainTrack = videoTracks.find((track) => track.magnetic)
  if (!mainTrack) {
    mainTrack = createTrack('video', { name: '主视频轨', magnetic: true })
    videoTracks.push(mainTrack)
  }
  mainTrack.name = '主视频轨'

  // 空辅轨不落地：与运行时「辅轨清空自动移除」规则一致；主音轨（首条）恒保留。
  const keptVideo = videoTracks.filter((track) => track.magnetic || track.clips.length > 0)
  let keptAudio = audioTracks.filter((track, index) => index === 0 || track.clips.length > 0)
  if (keptAudio.length === 0) keptAudio = [createTrack('audio', { name: '音轨 1' })]

  const tracks = [...keptVideo, ...keptAudio]
  for (const track of tracks) {
    if (track.magnetic) relayoutMagneticTrack(track)
    else sortFreeTrack(track)
  }
  return { ratio: typeof doc.ratio === 'string' ? doc.ratio : '', tracks }
}

const pad2 = (value: number) => String(value).padStart(2, '0')

/** 统一时长/位置显示：固定 时:分:秒（00:00:00），秒向下取整。 */
export const formatClockMs = (ms: number) => {
  const total = Math.max(0, Math.floor(ms / 1000))
  return `${pad2(Math.floor(total / 3600))}:${pad2(Math.floor((total % 3600) / 60))}:${pad2(total % 60)}`
}

/** 素材角标/标尺短格式：分:秒（超一小时自动升为 时:分:秒），永不溢出进位。 */
export const formatShortMs = (ms: number) => {
  const total = Math.max(0, Math.floor(ms / 1000))
  if (total >= 3600) return formatClockMs(ms)
  return `${pad2(Math.floor(total / 60))}:${pad2(total % 60)}`
}

/** 播放器/片段时间码：时:分:秒:帧（按 EDITOR_FPS 换算显示帧）。 */
export const formatTimecodeMs = (ms: number) => {
  const clamped = Math.max(0, ms)
  const frames = Math.floor(((clamped % 1000) / 1000) * EDITOR_FPS)
  return `${formatClockMs(clamped)}:${pad2(frames)}`
}

/**
 * 标尺刻度规格：像素/秒越大，主刻度间隔越小，保证相邻主刻度不小于约 64px；
 * subMs 为次刻度间隔（主刻度的 1/5，用于细分格线）。
 */
export const rulerTickSpec = (pxPerSecond: number): { majorMs: number; subMs: number } => {
  // 主刻度候选（毫秒），从密到疏，取第一个宽度达标者。
  const candidates = [1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000, 600000]
  const minMajorPx = 64
  for (const majorMs of candidates) {
    if ((majorMs / 1000) * pxPerSecond >= minMajorPx) return { majorMs, subMs: majorMs / 5 }
  }
  const last = candidates[candidates.length - 1]
  return { majorMs: last, subMs: last / 5 }
}