import type { ScriptEpisodeCard, ScriptSceneCard, ScriptSceneLine } from '@/components/screenwriting/types'

/**
 * 剧本工作区 Markdown → 分集卡片解析。
 *
 * 解析为单向纯函数：卡片携带 start/end 字符偏移作为回写锚点，
 * 单集编辑/删除由调用方按偏移做字符串切片拼接。
 */

const parseScriptEpisodeHeading = (line: string) => {
  const text = line.trim()
  const epMatch = text.match(/^#{1,3}\s*(.+?\bEP\s*0?(\d+)\s*[：:\-\s]*(.*))$/i)
  if (epMatch) {
    const episodeNo = Number.parseInt(epMatch[2], 10)
    const titleTail = epMatch[3]?.trim()
    return {
      episodeNo,
      title: titleTail || epMatch[1].replace(/^.*?\bEP\s*0?\d+\s*[：:\-\s]*/i, '').trim() || epMatch[1].trim(),
    }
  }

  const cnMatch = text.match(/^#{1,3}\s*第\s*(\d+)\s*集\s*(.*)$/)
  if (cnMatch) {
    const episodeNo = Number.parseInt(cnMatch[1], 10)
    const titleTail = cnMatch[2]?.trim()
    return {
      episodeNo,
      title: titleTail || `第${episodeNo}集`,
    }
  }

  return null
}

const parseScriptSceneHeading = (line: string) => {
  const text = line.trim()
  const slugMatch = text.match(/^(\d+\s*[-－]\s*\d+)\s+(.+)$/)
  if (
    slugMatch
    && /(日|夜|晨|清晨|上午|中午|午后|下午|傍晚|黄昏|深夜|连续).*(内|外)/.test(slugMatch[2])
  ) {
    return {
      number: slugMatch[1].replace(/\s+/g, ''),
      title: slugMatch[2].trim(),
    }
  }

  const markdownMatch = text.match(/^#{1,6}\s*(场景[一二三四五六七八九十\d]+)[：:]\s*(.+)$/)
  if (markdownMatch) {
    return {
      number: markdownMatch[1],
      title: markdownMatch[2].trim(),
    }
  }

  return null
}

const scriptNonDialogueLabels = new Set([
  '人物',
  '角色',
  '剧情梗概',
  '目标时长',
  '时长',
  '平台',
  '风格',
  '节拍',
  '场景',
  '动作',
  '对白',
  '信息点',
  '本集功能',
  '集尾钩子',
  '付费点',
])

const isScriptDialogueLine = (line: string) => {
  const text = line.trim()
  if (!text || ['#', '△', '[', '【', '-', '*', '|'].some((prefix) => text.startsWith(prefix))) {
    return false
  }
  const match = text.match(/^(.{1,40}?)[：:].+/)
  if (!match) return false
  const speaker = match[1].trim()
  if (!/[㐀-鿿A-Za-z]/.test(speaker)) return false
  if (/\s/.test(speaker) && !/[（(].*[）)]/.test(speaker)) return false
  const normalizedSpeaker = speaker.replace(/[（(].*[）)]$/, '').trim()
  return Boolean(normalizedSpeaker && !scriptNonDialogueLabels.has(normalizedSpeaker))
}

const extractScriptSynopsis = (block: string) => {
  const lines = block.split('\n')
  const summaryIndex = lines.findIndex((line) => /^#{1,6}\s*剧情梗概\s*$/.test(line.trim()))
  if (summaryIndex >= 0) {
    const collected: string[] = []
    for (const line of lines.slice(summaryIndex + 1)) {
      const trimmed = line.trim()
      if (!trimmed) continue
      if (trimmed === '---' || parseScriptSceneHeading(trimmed) || /^#{1,6}\s+/.test(trimmed)) break
      collected.push(trimmed)
    }
    if (collected.length) return collected.join('')
  }

  const fallback = lines
    .map((line) => line.trim())
    .find((line) => (
      line.length >= 24
      && !line.startsWith('#')
      && line !== '---'
      && !parseScriptSceneHeading(line)
      && !line.startsWith('人物：')
      && !line.startsWith('△')
      && !isScriptDialogueLine(line)
    ))
  return fallback || ''
}

const TRANSITION_LINE_RE = /^\[(硬切|淡入|淡出|叠化|闪黑|切至|转场|黑场|定格)\]$/

const classifySceneLine = (line: string): ScriptSceneLine => {
  if (line.startsWith('△')) return { type: 'action', text: line }
  if (TRANSITION_LINE_RE.test(line)) return { type: 'transition', text: line }
  if (isScriptDialogueLine(line)) return { type: 'dialogue', text: line }
  return { type: 'text', text: line }
}

const parseScriptScenes = (block: string, episodeKey: string): ScriptSceneCard[] => {
  const lines = block.split('\n')
  const sceneStarts = lines
    .map((line, index) => ({ scene: parseScriptSceneHeading(line), index }))
    .filter((item): item is { scene: { number: string, title: string }, index: number } => item.scene !== null)

  return sceneStarts.map((item, sceneIndex) => {
    const nextStart = sceneStarts[sceneIndex + 1]?.index ?? lines.length
    const sceneLines = lines.slice(item.index + 1, nextStart).map((line) => line.trim()).filter(Boolean)
    const people = sceneLines.find((line) => /^人物[：:]/.test(line))?.replace(/^人物[：:]\s*/, '') ?? ''
    const duration = sceneLines.find((line) => /^时长[：:]/.test(line))?.replace(/^时长[：:]\s*/, '') ?? ''
    // 场次正文完整保留（不截断对白/动作），仅剔除已单独提取的人物/时长标签行与分隔线。
    const contentLines = sceneLines
      .filter((line) => !/^(人物|时长)[：:]/.test(line) && !/^(-{3,}|\*{3,}|_{3,}|={3,})$/.test(line))
      .map(classifySceneLine)

    return {
      key: `${episodeKey}-scene-${sceneIndex}`,
      number: item.scene.number,
      title: item.scene.title,
      people,
      duration,
      lines: contentLines,
    }
  })
}

const parseDurationSeconds = (value: string): number => {
  const clock = value.trim().match(/^(\d+)\s*[:：]\s*(\d{1,2})$/)
  if (clock) return Number.parseInt(clock[1], 10) * 60 + Number.parseInt(clock[2], 10)
  let total = 0
  const minutes = value.match(/(\d+(?:\.\d+)?)\s*分钟?/)
  if (minutes) total += Number.parseFloat(minutes[1]) * 60
  const seconds = value.match(/(\d+(?:\.\d+)?)\s*(?:s|秒)/i)
  if (seconds) total += Number.parseFloat(seconds[1])
  return Math.round(total)
}

const buildEpisodeMeta = (block: string, scenes: ScriptSceneCard[]): string[] => {
  const meta: string[] = []
  const targetMatch = block.match(/目标时长[：:]\s*(\d+(?:\.\d+)?)\s*分钟/)
  const actualSeconds = scenes.reduce((sum, scene) => sum + parseDurationSeconds(scene.duration), 0)
  if (targetMatch) {
    const actualLabel = actualSeconds > 0 ? ` · 实际约 ${actualSeconds} 秒` : ''
    meta.push(`目标 ${targetMatch[1]} 分钟${actualLabel}`)
  } else if (actualSeconds > 0) {
    meta.push(`实际约 ${actualSeconds} 秒`)
  }
  const platformLine = block
    .split('\n')
    .map((line) => line.trim().replace(/^#{1,6}\s*/, ''))
    .find((line) => /^平台[：:]/.test(line))
  if (platformLine) {
    meta.push(platformLine)
  }
  return meta
}

export const normalizeScriptContent = (content: string) => content.replace(/\r\n/g, '\n').trim()

export const parseScriptEpisodes = (content: string): ScriptEpisodeCard[] => {
  const source = normalizeScriptContent(content)
  if (!source) return []

  const lines: Array<{ text: string, start: number, end: number }> = []
  let offset = 0
  source.split('\n').forEach((text) => {
    const start = offset
    const end = start + text.length
    lines.push({ text, start, end })
    offset = end + 1
  })

  const headings = lines
    .map((line) => ({ ...line, heading: parseScriptEpisodeHeading(line.text) }))
    .filter((line): line is { text: string, start: number, end: number, heading: { episodeNo: number, title: string } } => line.heading !== null)

  if (!headings.length) return []

  return headings.map((heading, index) => {
    const nextHeading = headings[index + 1]
    const start = heading.start
    const end = nextHeading?.start ?? source.length
    const block = source.slice(start, end).trim()
    const key = `episode-${heading.heading.episodeNo}-${start}`
    const synopsis = extractScriptSynopsis(block)
    const scenes = parseScriptScenes(block, key)
    const firstAction = scenes[0]?.lines.find((line) => line.type === 'action')?.text ?? ''
    const summary = synopsis || firstAction.replace(/^△\s*/, '') || scenes[0]?.title || '待补充剧情正文'

    return {
      key,
      episodeNo: heading.heading.episodeNo,
      title: heading.heading.title,
      summary,
      meta: buildEpisodeMeta(block, scenes),
      synopsis,
      scenes,
      start,
      end,
    }
  })
}

/** 用编辑后的单集文本替换全文中 [start, end) 区间，前后段以空行衔接。 */
export const replaceScriptEpisode = (content: string, episode: ScriptEpisodeCard, nextEpisodeText: string) => {
  const source = normalizeScriptContent(content)
  return `${source.slice(0, episode.start).trimEnd()}\n\n${nextEpisodeText.trim()}\n\n${source.slice(episode.end).trimStart()}`.trim()
}

/** 从全文中删除指定单集，前后段以空行衔接。 */
export const removeScriptEpisode = (content: string, episode: ScriptEpisodeCard) => {
  const source = normalizeScriptContent(content)
  return `${source.slice(0, episode.start).trimEnd()}\n\n${source.slice(episode.end).trimStart()}`.trim()
}