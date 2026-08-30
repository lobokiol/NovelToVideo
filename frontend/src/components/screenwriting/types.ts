import type { Component } from 'vue'
import type { ScreenwritingActiveTab, ScreenwritingRagPayload, ScreenwritingServerTimings } from '@/api/screenwriting'

export interface AgentActionEntry {
  phase: string
  message: string
  detail?: string
  targetTab?: string
}

export interface ChatMessage {
  id: number
  role: 'assistant' | 'user'
  content: string
  time: string
  rag?: ScreenwritingRagPayload
  thinkingElapsedMs?: number
  serverTimings?: ScreenwritingServerTimings
  actions?: AgentActionEntry[]
}

export type ScreenwritingRagWarmupStatus = 'idle' | 'starting' | 'running' | 'ready' | 'failed'

export interface ScreenwritingRagWarmupViewState {
  status: ScreenwritingRagWarmupStatus
  label: string
  detail?: string
}

export type ScriptSceneLineType = 'action' | 'dialogue' | 'transition' | 'text'

export interface ScriptSceneLine {
  type: ScriptSceneLineType
  text: string
}

export interface ScriptSceneCard {
  key: string
  number: string
  title: string
  people: string
  /** 场次时长原文（如 "60s"），无标记时为空。 */
  duration: string
  /** 场次正文按原始顺序的全部内容行（动作/对白/转场/其他）。 */
  lines: ScriptSceneLine[]
}

export interface ScriptEpisodeCard {
  key: string
  episodeNo: number
  title: string
  summary: string
  meta: string[]
  synopsis: string
  scenes: ScriptSceneCard[]
  /** 该集在剧本全文中的起始字符偏移（编辑/删除回写锚点）。 */
  start: number
  /** 该集结束偏移（下一集标题起点或全文末尾）。 */
  end: number
}

export interface ScreenwritingTab {
  name: ScreenwritingActiveTab
  label: string
  icon: Component
  desc: string
  action: string
  title: string
  hint: string
  starter: string
}