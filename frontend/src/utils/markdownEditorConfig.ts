import type { Themes, ToolbarNames } from 'md-editor-v3'

export type MarkdownEditorTheme = Themes | 'auto'

/* markdown的工具栏定制 */
export const MARKDOWN_EDITOR_TOOLBARS: ToolbarNames[] = [
  'bold',
  'underline',
  'italic',
  'strikeThrough',
  '-',
  'title',
  'sub',
  'sup',
  'quote',
  'unorderedList',
  'orderedList',
  'task',
  '-',
  'codeRow',
  'code',
  'table',
  '-',
  'revoke',
  'next',
  '=',
  'preview',
  'fullscreen',
]

export const normalizeMarkdownEditorTheme = (theme: MarkdownEditorTheme = 'dark'): Themes => (
  theme === 'light' ? 'light' : 'dark'
)
