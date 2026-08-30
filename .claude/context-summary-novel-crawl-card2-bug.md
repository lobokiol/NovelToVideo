## 项目上下文摘要（小说爬取卡片2点击无法获取数据 BUG）
生成时间：2026-05-23 11:00:00

### 1. 缺陷复现
- 入口：`NovelCrawlDialog.vue` 步骤 1 搜索小说
- 触发条件：后端搜索 API 对同一本书返回多条记录（如截图中两张"万相之王李洛姜青娥"卡片）
- 现象：左上卡片完整（玄幻 + 1836 章 + 更新时间），右上卡片仅显示作者；点击右上卡片无法获取类别、总章节

### 2. 根因分析（systematic-debugging Phase 1-2）

**A. `latestCrawlBook` 返回错误对象**（[NovelCrawlDialog.vue:1507-1512](frontend/src/components/NovelCrawlDialog.vue#L1507-L1512)）
- `crawlResults.value.find((item) => isSameCrawlBook(item, book))` 总是返回数组首个 dirid 相同项
- 点击 card2 时返回 card1，导致 `crawlSelectedBook` 被改成 card1

**B. `selectCrawlBook` 缓存短路误判**（[NovelCrawlDialog.vue:1614-1628](frontend/src/components/NovelCrawlDialog.vue#L1614-L1628)）
- `hasCrawlBookDetails(nextBook)` 用 `crawlBookIdentity(dirid)` 判断 → 两张同 dirid 卡片共享标识
- card1 已加载过 → card2 选中时 `hasCrawlBookDetails` 返回 true → 不发请求
- 同理 `nextBook.lastchapterid` 沿用 card1 数据，但用户期望对的是右上对象的数据流

**C. `:key="book.id"` v-for 冲突**（[NovelCrawlDialog.vue:548](frontend/src/components/NovelCrawlDialog.vue#L548)）
- 后端 `_parse_search_results` 用 `_to_int(raw_id, index+1)` 生成 id；若两条记录 raw_id 解析失败回退到不同 index，id 可能不同；但若 raw_id 是相同数字字符串，id 完全一致 → key 冲突

**D. fetchSelectedBookDetail/ChapterCount 硬短路**（[NovelCrawlDialog.vue:1547](frontend/src/components/NovelCrawlDialog.vue#L1547)、[NovelCrawlDialog.vue:1571](frontend/src/components/NovelCrawlDialog.vue#L1571)）
- `if (!book.dirid || !crawlSourceKey.value) return` 强制要求 dirid 非空
- 后端 `_book_context` 用 `book.dirid or book.id` 兜底（[novel_crawler.py:588-596](backend/app/services/novel_crawler.py#L588-L596)），完全可以接收 dirid 为空但 id > 0 的请求
- 前端短路掩盖了后端兜底能力，并且无任何 UI 反馈

### 3. 后端关键证据
- `_parse_search_results`（[novel_crawler.py:409-441](backend/app/services/novel_crawler.py#L409-L441)）：按 `count = max(len(ids), len(titles), ...)` 遍历所有索引，不去重；不同 index 的字段值独立提取，可能出现"同 dirid 不同字段完整度"
- `_merge_book_detail`（[novel_crawler.py:444-459](backend/app/services/novel_crawler.py#L444-L459)）：合并书籍详情时 `source_book_id or book.dirid` 兜底
- `_book_context`（[novel_crawler.py:588-596](backend/app/services/novel_crawler.py#L588-L596)）：URL 模板渲染时 `dirid: book.dirid or book.id`，支持 id 兜底

### 4. 修复策略（systematic-debugging Phase 4）

**修复 1**：`latestCrawlBook` 优先使用对象引用相等
- 若传入 book 本身就在 `crawlResults` 数组里 → 直接返回它
- 避免 find 错误命中前序匹配项

**修复 2**：在搜索结果落地前合并同书重复记录
- 添加 `mergeCrawlSearchResults` 工具：按 `isSameCrawlBook` 合并同书 card 的所有字段（非空/正整数优先）
- 在 [NovelCrawlDialog.vue:1421](frontend/src/components/NovelCrawlDialog.vue#L1421) 和 [NovelCrawlDialog.vue:1433](frontend/src/components/NovelCrawlDialog.vue#L1433) 两处赋值前应用

**修复 3**：放宽 `fetchSelectedBookDetail/ChapterCount` 短路条件
- 改为 `if ((!book.dirid && !book.id) || !crawlSourceKey.value) return`
- 让 dirid 为空但 id > 0 的卡片仍能发请求

**修复 4**：v-for key 使用稳定复合 key
- `:key` 从 `book.id` 改为 `crawlBookIdentity(book)` + index 复合
- 避免重复 id 导致 Vue 渲染异常

### 5. 可复用组件清单
- `crawlBookSourceKey`、`crawlBookIdentity`、`isSameCrawlBook`、`mergeCrawlBook`：已存在，可直接复用
- 后端 `_merge_book_detail`、`_book_context`：已有 id 兜底语义

### 6. 测试策略
- 类型检查：`npx vue-tsc --noEmit`
- 手动复现：mock 后端返回同书两条记录（dirid 相同、字段完整度不同），点击第二张卡片验证：
  - card2 视觉被独立选中（不会让 card1 也高亮）
  - selectedBook 实际是 card2 对象（或合并后的完整对象）
  - dirid 为空的卡片也能发请求获取数据
- 测试文件：暂无单元测试覆盖此场景，本次修复以类型检查 + 逻辑推演为主

### 7. 项目约定
- camelCase / snake_case 双向 schema（Pydantic alias_generator）
- 前端 ref 命名 `crawlXxx`，方法 `xxxCrawlBook`
- 中文注释，简体强制
- 复用 `pickText`/`mergeCrawlBook`/`isSameCrawlBook`等既有工具
