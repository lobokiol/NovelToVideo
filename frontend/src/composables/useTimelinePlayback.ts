import { onScopeDispose, ref, type Ref } from 'vue'
import { clipDurationMs, clipEndMs } from '@/components/editor/timelineDoc'
import type { TimelineClip, TimelineTrack } from '@/components/editor/types'

export interface TimelinePlaybackOptions {
  /** 全部轨道（视频 + 音频），引擎按 kind 分别调度。 */
  tracks: () => TimelineTrack[]
  /** 播放头（毫秒），由引擎在播放推进与 seek 时写入。 */
  playheadMs: Ref<number>
  /** 时间线总时长（毫秒）。 */
  totalDurationMs: () => number
  /** 由媒体标识解析可播放 URL。 */
  resolveMediaUrl: (mediaPublicId: string) => string
  /** 取视频轨的两个预览层元素（双缓冲：一层播放、一层预载下一片段）；未挂载时返回 null。 */
  getVideoLayers: (trackId: string) => readonly [HTMLVideoElement, HTMLVideoElement] | null
}

/** 播放中允许的媒体元素时间偏差（秒），超出才校正，避免频繁 seek 造成卡顿。 */
const SYNC_TOLERANCE_SEC = 0.3

/**
 * 多轨时间线播放引擎。
 *
 * 以 performance.now 为主时钟推进播放头，每帧把各视频轨预览层与音频元素池
 * 对齐到全局时间；媒体元素只做跟随，不反向驱动时钟，因此轨道数量可任意扩展。
 */
export function useTimelinePlayback(opts: TimelinePlaybackOptions) {
  const playing = ref(false)
  const audioPool = new Map<string, HTMLAudioElement>()
  // 每条视频轨的双缓冲状态：front 为当前显示层，另一层预载下一片段以实现无缝拼接。
  const videoTrackState = new Map<
    string,
    { frontIndex: 0 | 1; frontClipId: string; standbyClipId: string }
  >()
  let rafHandle = 0
  let originPlayheadMs = 0
  let originTimestamp = 0

  const clipAt = (track: TimelineTrack, ms: number): TimelineClip | null => {
    for (const clip of track.clips) {
      if (ms >= clip.startMs && ms < clipEndMs(clip)) return clip
    }
    return null
  }

  const effectiveVolume = (track: TimelineTrack, clip: TimelineClip) => (
    track.muted || clip.muted ? 0 : clip.volume
  )

  /** 同轨紧随当前片段之后、最近的下一个视频片段（用于预载到待机层）；无则 null。 */
  const nextVideoClipAfter = (track: TimelineTrack, clip: TimelineClip): TimelineClip | null => {
    const end = clipEndMs(clip)
    let best: TimelineClip | null = null
    for (const candidate of track.clips) {
      if (candidate.id === clip.id || candidate.mediaType !== 'video') continue
      if (candidate.startMs < end) continue
      if (!best || candidate.startMs < best.startMs) best = candidate
    }
    return best
  }

  /** 令某视频层进入闲置：暂停并隐藏（不清空 src，保留已解码帧便于回退复用）。 */
  const idleVideoLayer = (layer: HTMLVideoElement) => {
    if (!layer.paused) layer.pause()
    layer.style.visibility = 'hidden'
  }

  /**
   * 预热待机层：设定 src 与入点后短暂触发解码，使首帧就绪，随后停在入点保持暂停。
   *
   * 隐藏(visibility:hidden)且从未播放的 <video> 仅设 currentTime 不会解码出可显示帧
   * （videoWidth 恒为 0），晋升为 front 后首帧空白即黑屏。故此处主动 play() 启动解码，
   * 待 seeked（首帧解码完成）后立即 pause() 停在入点，晋升时即有首帧可即时呈现。
   */
  const primeStandbyLayer = (layer: HTMLVideoElement, src: string, inSec: number) => {
    if (!layer.src || !layer.src.endsWith(src)) layer.src = src
    layer.muted = true // 预热期间静音，避免下一片段声音提前泄漏。
    layer.currentTime = inSec
    // 首帧解码完成即暂停停在入点；一次性监听，避免重复绑定。seeked 统一负责暂停。
    const settle = () => {
      layer.pause()
      layer.removeEventListener('seeked', settle)
    }
    layer.addEventListener('seeked', settle)
    // play() 仅为启动解码；失败（自动播放策略等）时回退为静止预载，不影响主播放。
    void layer.play().catch(() => layer.removeEventListener('seeked', settle))
  }

  /**
   * 视频轨双缓冲同步。
   *
   * front 层显示当前片段，standby 层预载"下一片段"并停在其入点（首帧已解码）。
   * 跨片段边界时，若 standby 已持有新的当前片段，仅翻转 front 指针完成无缝切换，
   * 不触发 src 重载，从而消除多段视频拼接播放时的换源黑屏；仅在随机 seek 到
   * 未预载片段时才回退为直接换源（短暂且不可避免）。
   */
  const syncVideoTrack = (track: TimelineTrack, globalMs: number, exact: boolean) => {
    const layers = opts.getVideoLayers(track.id)
    if (!layers) return
    const state = videoTrackState.get(track.id) ?? { frontIndex: 0 as 0 | 1, frontClipId: '', standbyClipId: '' }

    const clip = track.hidden ? null : clipAt(track, globalMs)
    // 隐藏轨、图片/文本片段均不占用视频层：两层皆闲置，但保留双缓冲状态以便边界续接。
    if (!clip || clip.mediaType !== 'video') {
      idleVideoLayer(layers[0])
      idleVideoLayer(layers[1])
      videoTrackState.set(track.id, state)
      return
    }

    // 待机层已预载好本片段 → 翻转指针完成无缝切换，无需换源。
    if (clip.id !== state.frontClipId && clip.id === state.standbyClipId) {
      state.frontIndex = (state.frontIndex === 0 ? 1 : 0) as 0 | 1
      state.frontClipId = clip.id
      state.standbyClipId = ''
    }

    const front = layers[state.frontIndex]
    const standby = layers[state.frontIndex === 0 ? 1 : 0]

    // front 层对齐当前片段：src 不符才换源（seek 到位），否则仅按容差校正播放位置。
    const src = opts.resolveMediaUrl(clip.mediaPublicId)
    const targetSec = (clip.inMs + (globalMs - clip.startMs)) / 1000
    if (!front.src || !front.src.endsWith(src)) {
      front.src = src
      front.currentTime = targetSec
      state.frontClipId = clip.id
    } else if (exact || Math.abs(front.currentTime - targetSec) > SYNC_TOLERANCE_SEC) {
      front.currentTime = targetSec
    }
    // 晋升自预热层时其被静音过，这里按当前片段音量恢复；muted 由片段/轨道状态决定。
    front.muted = false
    front.volume = effectiveVolume(track, clip)
    front.style.visibility = 'visible'
    if (playing.value) {
      if (front.paused) void front.play().catch(() => undefined)
    } else if (!front.paused) {
      front.pause()
    }

    // standby 层预热下一视频片段（解码首帧并停在入点），边界到来即可零延迟晋升。
    const next = nextVideoClipAfter(track, clip)
    if (next) {
      if (state.standbyClipId !== next.id) {
        primeStandbyLayer(standby, opts.resolveMediaUrl(next.mediaPublicId), next.inMs / 1000)
        state.standbyClipId = next.id
      }
      standby.style.visibility = 'hidden'
    } else {
      // 末段之后无预载目标：闲置待机层并清空标记，避免陈旧片段被误当作可晋升的待机片段。
      idleVideoLayer(standby)
      state.standbyClipId = ''
    }
    videoTrackState.set(track.id, state)
  }

  const ensureAudioElement = (clip: TimelineClip) => {
    let element = audioPool.get(clip.id)
    if (!element) {
      element = new Audio(opts.resolveMediaUrl(clip.mediaPublicId))
      element.preload = 'auto'
      audioPool.set(clip.id, element)
    }
    return element
  }

  const syncAudioTrack = (track: TimelineTrack, globalMs: number, exact: boolean) => {
    for (const clip of track.clips) {
      const element = ensureAudioElement(clip)
      const localMs = globalMs - clip.startMs
      const inRange = localMs >= 0 && localMs < clipDurationMs(clip)
      const targetSec = (clip.inMs + localMs) / 1000
      if (playing.value && inRange) {
        if (Math.abs(element.currentTime - targetSec) > SYNC_TOLERANCE_SEC) {
          element.currentTime = targetSec
        }
        element.volume = effectiveVolume(track, clip)
        if (element.paused) void element.play().catch(() => undefined)
      } else {
        if (!element.paused) element.pause()
        // 暂停态 seek 时也把音频对齐，恢复播放时不会出现声画跳变。
        if (exact && inRange) element.currentTime = targetSec
      }
    }
  }

  const pruneAudioPool = () => {
    const validIds = new Set<string>()
    for (const track of opts.tracks()) {
      if (track.kind !== 'audio') continue
      for (const clip of track.clips) validIds.add(clip.id)
    }
    for (const [clipId, element] of audioPool) {
      if (validIds.has(clipId)) continue
      element.pause()
      element.removeAttribute('src')
      audioPool.delete(clipId)
    }
  }

  /** 清理已删除视频轨的双缓冲状态，防止 Map 随轨道增删无限膨胀。 */
  const pruneVideoTrackState = () => {
    const validIds = new Set<string>()
    for (const track of opts.tracks()) {
      if (track.kind === 'video') validIds.add(track.id)
    }
    for (const trackId of videoTrackState.keys()) {
      if (!validIds.has(trackId)) videoTrackState.delete(trackId)
    }
  }

  const syncAll = (exact: boolean) => {
    const globalMs = opts.playheadMs.value
    for (const track of opts.tracks()) {
      if (track.kind === 'video') syncVideoTrack(track, globalMs, exact)
      else syncAudioTrack(track, globalMs, exact)
    }
    pruneAudioPool()
    pruneVideoTrackState()
  }

  const tick = () => {
    if (!playing.value) return
    const nextMs = originPlayheadMs + (performance.now() - originTimestamp)
    const total = opts.totalDurationMs()
    if (total <= 0 || nextMs >= total) {
      opts.playheadMs.value = Math.max(0, total)
      playing.value = false
      syncAll(false)
      return
    }
    opts.playheadMs.value = nextMs
    syncAll(false)
    rafHandle = requestAnimationFrame(tick)
  }

  const play = () => {
    const total = opts.totalDurationMs()
    if (playing.value || total <= 0) return
    // 播放头停在末尾时再次播放，从头开始。
    if (opts.playheadMs.value >= total) opts.playheadMs.value = 0
    playing.value = true
    originPlayheadMs = opts.playheadMs.value
    originTimestamp = performance.now()
    syncAll(true)
    rafHandle = requestAnimationFrame(tick)
  }

  const pause = () => {
    if (playing.value) {
      playing.value = false
      cancelAnimationFrame(rafHandle)
    }
    syncAll(false)
  }

  const toggle = () => {
    if (playing.value) pause()
    else play()
  }

  const seekTo = (ms: number) => {
    const total = opts.totalDurationMs()
    const clamped = Math.min(Math.max(0, ms), total)
    opts.playheadMs.value = clamped
    originPlayheadMs = clamped
    originTimestamp = performance.now()
    syncAll(true)
  }

  /** CTI 拖动开始：处于播放态则立即暂停，随后由拖动持续精确 seek 到竖线位置。 */
  const beginScrub = () => {
    if (playing.value) pause()
  }

  const destroy = () => {
    playing.value = false
    cancelAnimationFrame(rafHandle)
    for (const element of audioPool.values()) {
      element.pause()
      element.removeAttribute('src')
    }
    audioPool.clear()
    videoTrackState.clear()
  }

  onScopeDispose(destroy)

  return { playing, play, pause, toggle, seekTo, beginScrub, syncAll, destroy }
}