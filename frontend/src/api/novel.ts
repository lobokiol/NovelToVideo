import request from '@/request'

export type EventState = -1 | 0 | 1

export interface NovelChapterRecord {
  id: number
  publicId: string
  projectId: number
  chapterIndex: number
  reel: string
  chapter: string
  chapterData: string
  event: string
  eventState: EventState
  errorReason: string | null
  crawlSourceKey: string
  crawlNovelDirid: string
  crawlChapterId: number | null
  crawlTime: string
  crawlMd5: string
  sortOrder: number
  createdAt: string
  updatedAt: string
  disabledAt: string | null
}

export interface NovelChapterPage {
  data: NovelChapterRecord[]
  total: number
  page: number
  limit: number
}

export interface NovelChapterCleanStatus {
  id: number
  publicId: string
  chapterIndex: number
  reel: string
  chapter: string
  event: string
  eventState: EventState
  errorReason: string | null
  updatedAt: string
}

export interface NovelChapterListParams {
  page: number
  limit: number
  search?: string
}

export interface NovelChapterPayload {
  chapterIndex: number
  reel: string
  chapter: string
  chapterData: string
  event?: string
}

export interface NovelChapterBatchPayload {
  ids: number[]
}

export interface NovelChapterBatchResult {
  affected: number
}

export interface NovelChapterImportItemPayload {
  reel: string
  chapter: string
  chapterData: string
}

export interface NovelChapterImportPayload {
  rawText?: string
  chapters?: NovelChapterImportItemPayload[]
}

export interface NovelImportSplitRule {
  key: string
  label: string
  description: string
  chapterPattern: string
  chapterFlagsList: string[]
  reelPattern: string
  reelFlagsList: string[]
  builtin: boolean
}

export type CrawlSourceType = 'rule' | 'api'
export type CrawlSourceScope = 'public' | 'private'
export type CrawlHttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export const CRAWL_HTTP_METHODS: CrawlHttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
export const CRAWL_HTTP_METHODS_WITH_BODY: ReadonlyArray<CrawlHttpMethod> = ['POST', 'PUT', 'PATCH']

export interface CrawlSourcePayload {
  key: string
  name: string
  baseUrl: string
  desc: string
  sourceType: CrawlSourceType
  searchUrlTemplate: string
  apiSearchMethod: CrawlHttpMethod
  apiSearchHeaders: string
  apiSearchBody: string
  apiSearchBookUrlPath: string
  apiSearchBookIdPath: string
  apiSearchBookTitlePath: string
  apiSearchBookAuthorPath: string
  apiSearchBookIntroPath: string
  apiSearchBookCoverPath: string
  apiSearchBookCategoryPath: string
  apiSearchBookUpdateStatusPath: string
  apiSearchBookLastChapterPath: string
  apiSearchBookLastChapterIdPath: string
  apiSearchBookLastUpdatePath: string
  apiBookUrl: string
  apiBookMethod: CrawlHttpMethod
  apiBookHeaders: string
  apiBookBody: string
  apiBookTitlePath: string
  apiBookAuthorPath: string
  apiBookIntroPath: string
  apiBookLastChapterPath: string
  apiBookLastChapterIdPath: string
  apiBookLastUpdatePath: string
  apiBookCoverPath: string
  apiBookCategoryPath: string
  apiBookUpdateStatusPath: string
  apiBookIdPath: string
  apiChapterListUrl: string
  apiChapterListMethod: CrawlHttpMethod
  apiChapterListHeaders: string
  apiChapterListBody: string
  apiChapterListNamePath: string
  apiChapterListIdPath: string
  apiChapterListContentPath: string
  apiChapterListTimePath: string
  apiChapterListMd5Path: string
  apiChapterUrl: string
  apiChapterMethod: CrawlHttpMethod
  apiChapterHeaders: string
  apiChapterBody: string
  apiChapterNamePath: string
  apiChapterContentPath: string
  apiChapterTimePath: string
  apiChapterMd5Path: string
  builtin: boolean
  projectPublicId?: string | null
}

export type CrawlSourceUpdatePayload = Partial<Omit<CrawlSourcePayload, 'key' | 'projectPublicId' | 'builtin'>>

export interface CrawlSourceRecord extends CrawlSourcePayload {
  id: number
  publicId: string
  projectPublicId: string | null
  scope: CrawlSourceScope
  sortOrder: number
  createdAt: string
  updatedAt: string
  disabledAt: string | null
}

export interface CrawlSearchResult {
  dirid: string
  id: number
  full: string
  title: string
  author: string
  cover: string
  lastchapter: string
  lastchapterid: number
  lastupdate: string
  sortname: string
  intro: string
  sourceKey: string
}

export interface CrawlChapterDraft {
  key: number
  novelDirid: string
  chapterid: number
  chaptername: string
  time: string
  txt: string
  md5: string
  event: string
  eventState: EventState
  errorReason: string | null
}

export type CrawlChapterStreamEvent =
  | {
      type: 'start'
      total: number
      startChapter: number
      endChapter: number
    }
  | {
      type: 'chapter'
      completed: number
      total: number
      chapter: CrawlChapterDraft
    }
  | {
      type: 'done'
      completed: number
      total: number
    }
  | {
      type: 'error'
      detail: string
      completed: number
      total: number
    }

export interface CrawlSearchPayload {
  sourceKey: string
  query: string
}

export interface CrawlChapterFetchPayload {
  sourceKey: string
  book: CrawlSearchResult
  startChapter: number
  endChapter: number
}

export interface CrawlBookDetailPayload {
  sourceKey: string
  book: CrawlSearchResult
}

export interface CrawlBookDetailResult {
  book: CrawlSearchResult
}

export interface CrawlBookChapterCountResult extends CrawlBookDetailResult {
  lastchapterid: number
}

export interface CrawlImportPayload {
  sourceKey: string
  book: CrawlSearchResult
  chapters: CrawlChapterDraft[]
}

export interface CrawlImportResult {
  created: number
  updated: number
  skipped: number
  chapters: NovelChapterRecord[]
}

export interface CrawlAnalyzePayload {
  url: string
  sourceType: CrawlSourceType
}

export interface CrawlAnalyzeResult {
  status: 'pending'
  source: CrawlSourcePayload
  message: string
}

export const listNovelChaptersApi = (
  projectPublicId: string,
  params: NovelChapterListParams,
) => (
  request.get<NovelChapterPage>(`${projectNovelPath(projectPublicId)}`, { params })
)

export const listNovelChapterCleanStatusesApi = (
  projectPublicId: string,
  ids: number[],
) => (
  request.get<NovelChapterCleanStatus[]>(`${projectNovelPath(projectPublicId)}/clean/status`, {
    params: { ids: ids.join(',') },
  })
)

export interface ScreenwritingPreflightCheck {
  key: string
  label: string
  passed: boolean
  detail: string
}

export interface ScreenwritingPreflightResult {
  ready: boolean
  requiredEventCount: number
  eventReadyCount: number
  textModel: string
  checks: ScreenwritingPreflightCheck[]
}

export const getScreenwritingPreflightApi = (
  projectPublicId: string,
) => (
  request.get<ScreenwritingPreflightResult>(
    `${projectNovelPath(projectPublicId)}/screenwriting/preflight`,
  )
)

export const createNovelChapterApi = (
  projectPublicId: string,
  payload: NovelChapterPayload,
) => (
  request.post<NovelChapterRecord>(`${projectNovelPath(projectPublicId)}`, payload)
)

export const importNovelChaptersApi = (
  projectPublicId: string,
  payload: NovelChapterImportPayload,
) => (
  request.post<NovelChapterRecord[]>(`${projectNovelPath(projectPublicId)}/import`, payload, { timeout: 120000 })
)

export const listNovelImportSplitRulesApi = (
  projectPublicId: string,
) => (
  request.get<NovelImportSplitRule[]>(`${projectNovelPath(projectPublicId)}/import-split-rules`)
)

export const updateNovelChapterApi = (
  projectPublicId: string,
  chapterId: number,
  payload: Partial<NovelChapterPayload>,
) => (
  request.put<NovelChapterRecord>(`${projectNovelPath(projectPublicId)}/${chapterId}`, payload)
)

export const deleteNovelChapterApi = (
  projectPublicId: string,
  chapterId: number,
) => (
  request.delete<void>(`${projectNovelPath(projectPublicId)}/${chapterId}`)
)

export const batchDeleteNovelChaptersApi = (
  projectPublicId: string,
  payload: NovelChapterBatchPayload,
) => (
  request.post<NovelChapterBatchResult>(`${projectNovelPath(projectPublicId)}/batch-delete`, payload)
)

export const cleanNovelChapterApi = (
  projectPublicId: string,
  chapterId: number,
) => (
  request.post<NovelChapterRecord>(`${projectNovelPath(projectPublicId)}/${chapterId}/clean`, undefined, { timeout: 300000 })
)

export const batchCleanNovelChaptersApi = (
  projectPublicId: string,
  payload: NovelChapterBatchPayload,
) => (
  request.post<NovelChapterBatchCleanSubmitResult>(`${projectNovelPath(projectPublicId)}/batch-clean`, payload, { timeout: 600000 })
)

export const listCrawlSourcesApi = (
  projectPublicId: string,
) => (
  request.get<CrawlSourceRecord[]>(`${projectNovelPath(projectPublicId)}/crawl-sources`)
)

export const createCrawlSourceApi = (
  projectPublicId: string,
  payload: CrawlSourcePayload,
) => (
  request.post<CrawlSourceRecord>(`${projectNovelPath(projectPublicId)}/crawl-sources`, payload)
)

export const updateCrawlSourceApi = (
  projectPublicId: string,
  key: string,
  payload: CrawlSourceUpdatePayload,
) => (
  request.put<CrawlSourceRecord>(
    `${projectNovelPath(projectPublicId)}/crawl-sources/${encodeURIComponent(key.trim())}`,
    payload,
  )
)

export const deleteCrawlSourceApi = (
  projectPublicId: string,
  key: string,
) => (
  request.delete<void>(`${projectNovelPath(projectPublicId)}/crawl-sources/${encodeURIComponent(key.trim())}`)
)

export interface CrawlSourceDuplicatePayload {
  newKey: string
  name?: string
}

export const duplicateCrawlSourceApi = (
  projectPublicId: string,
  key: string,
  payload: CrawlSourceDuplicatePayload,
) => (
  request.post<CrawlSourceRecord>(
    `${projectNovelPath(projectPublicId)}/crawl-sources/${encodeURIComponent(key.trim())}/duplicate`,
    payload,
  )
)

export const analyzeCrawlSourceApi = (
  projectPublicId: string,
  payload: CrawlAnalyzePayload,
) => (
  request.post<CrawlAnalyzeResult>(`${projectNovelPath(projectPublicId)}/crawl-sources/analyze`, payload)
)

export const searchCrawlBooksApi = (
  projectPublicId: string,
  payload: CrawlSearchPayload,
) => (
  request.post<CrawlSearchResult[]>(`${projectNovelPath(projectPublicId)}/crawl/search`, payload, { timeout: 120000 })
)

export const fetchCrawlBookDetailApi = (
  projectPublicId: string,
  payload: CrawlBookDetailPayload,
) => (
  request.post<CrawlBookDetailResult>(`${projectNovelPath(projectPublicId)}/crawl/book-detail`, payload, { timeout: 120000 })
)

export const fetchCrawlBookChapterCountApi = (
  projectPublicId: string,
  payload: CrawlBookDetailPayload,
) => (
  request.post<CrawlBookChapterCountResult>(
    `${projectNovelPath(projectPublicId)}/crawl/book-chapter-count`,
    payload,
    { timeout: 120000 },
  )
)

export const fetchCrawlChaptersApi = (
  projectPublicId: string,
  payload: CrawlChapterFetchPayload,
) => (
  request.post<CrawlChapterDraft[]>(`${projectNovelPath(projectPublicId)}/crawl/chapters`, payload, { timeout: 120000 })
)

export const crawlChaptersStreamUrl = (projectPublicId: string) => (
  `/api${projectNovelPath(projectPublicId)}/crawl/chapters/stream`
)

export const importCrawlChaptersApi = (
  projectPublicId: string,
  payload: CrawlImportPayload,
) => (
  request.post<CrawlImportResult>(`${projectNovelPath(projectPublicId)}/crawl/import`, payload, { timeout: 120000 })
)

const projectNovelPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/novels`
)

export interface NovelChapterBatchCleanCancelResult {
  jobPublicId: string
  canceledCount: number
}

export interface NovelChapterBatchCleanItem {
  chapterId: number
  chapterPublicId: string
  chapterIndex: number
  chapterTitle: string
  reel: string
  itemPublicId: string
  itemStatus: 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled' | 'paused'
  eventState: number
  event: string
  errorReason: string | null
}

export interface NovelChapterBatchCleanProgress {
  jobPublicId: string
  jobStatus: string
  totalCount: number
  pendingCount: number
  runningCount: number
  succeededCount: number
  failedCount: number
  canceledCount: number
  pausedCount: number
  finishedCount: number
  isFinished: boolean
  items: NovelChapterBatchCleanItem[]
}

export type NovelChapterBatchCleanSubmitResult = NovelChapterBatchResult | NovelChapterBatchCleanProgress

export interface NovelChapterBatchCleanActiveJob {
  jobPublicId: string
  jobStatus: 'pending' | 'running' | 'paused'
  totalCount: number
  pendingCount: number
  runningCount: number
  pausedCount: number
  createdAt: string | null
}


export interface NovelChapterBatchCleanActiveJobList {
  items: NovelChapterBatchCleanActiveJob[]
}

export const cancelBatchCleanJobApi = (
  projectPublicId: string,
  jobPublicId: string,
) => (
  request.post<NovelChapterBatchCleanCancelResult>(
    `${projectNovelPath(projectPublicId)}/batch-clean/jobs/${encodeURIComponent(jobPublicId)}/cancel`,
  )
)


export const getBatchCleanJobProgressApi = (
  projectPublicId: string,
  jobPublicId: string,
) => (
  request.get<NovelChapterBatchCleanProgress>(
    `${projectNovelPath(projectPublicId)}/batch-clean/jobs/${encodeURIComponent(jobPublicId)}`,
  )
)

export const batchCleanJobEventsUrl = (
  projectPublicId: string,
  jobPublicId: string,
) => (
  `/api${projectNovelPath(projectPublicId)}/batch-clean/jobs/${encodeURIComponent(jobPublicId)}/events`
)

export const listActiveBatchCleanJobsApi = (
  projectPublicId: string,
) => (
  request.get<NovelChapterBatchCleanActiveJobList>(
    `${projectNovelPath(projectPublicId)}/batch-clean/jobs/active`,
  )
)
