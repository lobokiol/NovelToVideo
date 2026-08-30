import type { MediaAssetRecord } from '@/api/media'

export type TrackKind = 'video' | 'audio'

/** 片段素材类型：视频/音频来自媒体中枢，图片入视频轨为静帧，文本为轨上叠加字幕框。 */
export type ClipMediaType = 'video' | 'audio' | 'image' | 'text'

/** 时间线片段：inMs/outMs 为素材内部裁剪区间，startMs 为时间线全局起点。 */
export interface TimelineClip {
  id: string
  /** 图片/视频/音频为媒体中枢标识；文本片段为空串。 */
  mediaPublicId: string
  mediaType: ClipMediaType
  label: string
  /** 文本片段的内容；其余类型恒为空串。 */
  text: string
  /** 文本片段在画面上的缩放倍率（1 为基准字号），其余类型忽略。 */
  textScale: number
  /** 文本位置偏移：相对画面宽/高的比例，0 为画面中心。 */
  textX: number
  textY: number
  /** 文本旋转角度（度，顺时针）。 */
  textRotate: number
  /** 文本框宽度（相对画面宽度比例），决定换行盒。 */
  textBoxWidth: number
  srcDurationMs: number
  inMs: number
  outMs: number
  startMs: number
  volume: number
  muted: boolean
}

/**
 * 轨道。tracks 数组顺序即 UI 自上而下顺序：视频轨组（数组越靠前层级越高，
 * 磁性主轨可有下方副轨）→ 音轨组。magnetic 主轨全局恰有一条，片段首尾磁性相接；
 * 其余轨道片段自由定位且同轨不重叠。
 * hidden 仅对视频轨有意义：隐藏后预览与导出均跳过该轨（画面与声音一并失效）。
 */
export interface TimelineTrack {
  id: string
  kind: TrackKind
  name: string
  muted: boolean
  hidden: boolean
  magnetic: boolean
  clips: TimelineClip[]
}

/** 剪辑工程持久化文档（timeline JSON version 2）。 */
export interface TimelineDoc {
  version: 2
  ratio: string
  tracks: TimelineTrack[]
}

/** 素材库列表项：镜头视频携带「EPxx #n」标签。 */
export interface ShotLibraryItem {
  media: MediaAssetRecord
  label: string
}

/** 素材从库面板拖入时间线的负载。 */
export interface MediaDragPayload {
  /** 可落入的轨道类型（图片落视频轨，kind 为 video）。 */
  kind: TrackKind
  mediaType: ClipMediaType
  mediaPublicId: string
  label: string
  durationMs: number
}

/**
 * 拖拽负载 MIME 按轨道类型区分，使轨道在 dragover 阶段（无法读取数据、
 * 只能读取 types）即可判断能否接收，从而正确展示落点反馈。
 */
export const mediaDragMime = (kind: TrackKind) => `application/x-editor-media-${kind}`

/** 片段最短保留时长（毫秒），分割与裁剪均不得低于该值。 */
export const MIN_CLIP_MS = 200

/** 时间线轨头（sticky 紧凑图标列）宽度，播放头与坐标换算共用。 */
export const TRACK_HEAD_WIDTH = 64

/** 轨道内容区相对轨头的左侧留白，保证 0 点刻度与片段起点不被轨头压边。 */
export const TIMELINE_LANE_PAD = 8

/** 文本片段缩放倍率的允许区间。 */
export const TEXT_SCALE_MIN = 0.4
export const TEXT_SCALE_MAX = 3

/** 文本位置偏移上限（相对画面宽/高比例，中心为 0）。 */
export const TEXT_OFFSET_LIMIT = 0.5

/** 文本框宽度（相对画面宽度比例）允许区间与默认值。 */
export const TEXT_BOX_WIDTH_MIN = 0.2
export const TEXT_BOX_WIDTH_MAX = 0.96
export const TEXT_BOX_WIDTH_DEFAULT = 0.88

/** 文本默认纵向偏移：画面中心下移 30%，接近字幕位。 */
export const TEXT_OFFSET_Y_DEFAULT = 0.3

/** 时间码换算帧率（预览与角标显示用，非导出编码帧率）。 */
export const EDITOR_FPS = 25

/** 图片静帧片段的默认时长。 */
export const DEFAULT_IMAGE_DURATION_MS = 4000

/** 文本片段的默认时长与默认内容。 */
export const DEFAULT_TEXT_DURATION_MS = 3000
export const DEFAULT_TEXT_CONTENT = '默认文本'

/** 图片/文本等静态片段可拉伸的时长上限。 */
export const MAX_STILL_DURATION_MS = 600000

/** 片段拖拽的目标描述：既有轨道，或经由放置区新建的轨道。 */
export type ClipDropTarget =
  | { type: 'track'; trackId: string; ms: number }
  | { type: 'new-video'; ms: number }
  | { type: 'new-video-below'; ms: number }
  | { type: 'new-audio'; ms: number }