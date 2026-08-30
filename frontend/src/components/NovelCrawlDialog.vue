<template>
  <el-dialog
    v-model="sourceManageVisible"
    :title="sourceManagerTitle"
    width="90vw"
    destroy-on-close
    append-to-body
    class="novel-dark-dialog novel-source-dialog"
  >
    <!-- 列表 -->
    <div v-if="sourceMode === 'list'" class="source-list">
      <div class="source-list__head">
        <span class="source-list__count">共 {{ crawlSources.length }} 个来源</span>
        <el-button type="primary" @click="startCreateSource">
          <el-icon><Plus /></el-icon>
          新增来源
        </el-button>
      </div>

      <el-table
        :data="crawlSources"
        class="novel-table source-list__table"
        :tooltip-options="{ effect: 'dark', popperClass: 'novel-cell-tooltip' }"
      >
        <el-table-column prop="name" label="名称" width="140" show-overflow-tooltip />
        <el-table-column prop="key" label="标识" width="100" show-overflow-tooltip />
        <el-table-column prop="baseUrl" label="站点" min-width="200" show-overflow-tooltip />
        <el-table-column prop="desc" label="说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="row.builtin ? 'info' : 'success'" effect="plain">
              {{ row.builtin ? '内置' : '自定义' }}
            </el-tag>
            <el-tag size="small" type="warning" effect="plain" style="margin-left: 4px">
              {{ row.sourceType === 'rule' ? '规则' : 'API' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="right" fixed="right">
          <template #default="{ row }">
            <template v-if="row.builtin && row.scope === 'public'">
              <el-button text size="small" type="primary" @click="openDuplicateDialog(row)">复制</el-button>
              <el-button v-if="isSuperuser" text size="small" @click="startEditSource(row)">编辑</el-button>
              <el-button v-if="isSuperuser" text size="small" type="danger" @click="removeSource(row)">禁用</el-button>
            </template>
            <template v-else>
              <el-button text size="small" type="primary" @click="openDuplicateDialog(row)">复制</el-button>
              <el-button text size="small" type="primary" @click="startEditSource(row)">编辑</el-button>
              <el-button text size="small" type="danger" @click="removeSource(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 复制为自定义来源 -->
    <div v-else-if="sourceMode === 'duplicate'" class="source-form">
      <div class="source-form__banner source-form__banner--create">
        <span class="source-form__banner-tag">复制</span>
        <span class="source-form__banner-text">
          从 <strong>{{ duplicateForm.originName || duplicateForm.originKey }}</strong> 复制为自定义来源；请填写新的来源标识与名称，保存后可继续编辑接入字段。
        </span>
      </div>

      <section class="source-form__section">
        <header class="source-form__section-head">
          <h4>基础信息</h4>
        </header>
        <div class="source-form__grid">
          <div class="source-form__field">
            <label>来源标识 <span class="required">*</span></label>
            <el-input
              v-model="duplicateForm.newKey"
              size="default"
              placeholder="字母 / 数字 / 下划线 / 短横线，且全局唯一"
            />
          </div>
          <div class="source-form__field">
            <label>来源名称 <span class="required">*</span></label>
            <el-input v-model="duplicateForm.newName" size="default" placeholder="如 我的笔趣阁" />
          </div>
        </div>
      </section>
    </div>

    <!-- 表单（新增 / 编辑 / 查看） -->
    <div v-else-if="sourceMode === 'create' || sourceMode === 'edit'" class="source-form">
      <div
        class="source-form__banner"
        :class="{
          'source-form__banner--edit': sourceMode === 'edit',
          'source-form__banner--create': sourceMode === 'create',
        }"
      >
        <span class="source-form__banner-tag">
          {{ sourceMode === 'edit' ? '编辑' : '新建' }}
        </span>
        <span class="source-form__banner-text">
          <template v-if="sourceMode === 'edit'">
            正在编辑 <strong>{{ sourceForm.name || sourceForm.key }}</strong>{{ sourceForm.builtin ? '（内置来源，名称、接口配置均可修改）' : '（自定义来源）' }}。仅「来源标识」不可改。
          </template>
          <template v-else>
            新建来源：填写完整后点击「保存」加入来源列表。
          </template>
        </span>
      </div>

      <section class="source-form__section">
        <header class="source-form__section-head">
          <h4>基础信息</h4>
          <el-button size="small" plain @click="aiAnalyzeSource">
            <el-icon><MagicStick /></el-icon>
            AI 分析（开发中）
          </el-button>
        </header>
        <div class="source-form__grid">
          <div class="source-form__field">
            <label>来源标识 <span class="required">*</span></label>
            <el-input
              v-model="sourceForm.key"
              size="default"
              placeholder="如 biquge（字母/数字/_/-）"
              :disabled="sourceMode !== 'create'"
            />
          </div>
          <div class="source-form__field">
            <label>名称 <span class="required">*</span></label>
            <el-input v-model="sourceForm.name" size="default" placeholder="如 笔趣阁" />
          </div>
          <div class="source-form__field">
            <label>来源类型 <span class="required">*</span></label>
            <el-select
              v-model="sourceForm.sourceType"
              size="default"
              class="source-form__type-select"
              popper-class="novel-dark-select"
            >
              <el-option label="API 接口（JSON）" value="api" />
              <el-option label="规则解析（HTML / CSS）" value="rule" />
            </el-select>
          </div>
          <div class="source-form__field source-form__field--full">
            <label>站点 URL</label>
            <el-input v-model="sourceForm.baseUrl" size="default" placeholder="https://www.example.com" />
          </div>
          <div class="source-form__field source-form__field--full">
            <label>站点描述</label>
            <el-input v-model="sourceForm.desc" size="default" placeholder="一句话描述该来源" />
          </div>
        </div>
      </section>

      <section class="source-form__section">
        <header class="source-form__section-head">
          <h4>{{ isRuleSource ? '规则解析（HTML）' : 'API 接口' }}</h4>
          <span class="source-form__section-hint">
            {{ isRuleSource
              ? '填写页面 URL 与 CSS 选择器；选择器支持 ::text 取文本、::attr(name) 取属性'
              : '填写接口 URL、请求参数与字段选择器' }}
          </span>
        </header>

        <div class="source-form__subgroup">
          <div class="source-form__subgroup-head">
            <span class="source-form__subgroup-tag">小说搜索页</span>
            <span class="source-form__subgroup-hint">搜索小说页面的条目抽取</span>
          </div>
          <div class="source-form__grid">
            <div class="source-form__field source-form__field--full">
              <label>小说搜索页 URL</label>
              <div class="source-form__inline">
                <el-input
                  v-model="sourceForm.searchUrlTemplate"
                  size="default"
                  placeholder="https://xxx.com/api/search?q={q}"
                  class="source-form__inline-input"
                />
                <el-select
                  v-model="sourceForm.apiSearchMethod"
                  size="default"
                  class="source-form__method-select"
                  popper-class="novel-dark-select"
                >
                  <el-option v-for="method in crawlHttpMethods" :key="method" :label="method" :value="method" />
                </el-select>
              </div>
            </div>
            <div class="source-form__field source-form__field--full">
              <label>搜索请求头（JSON，可选）</label>
              <el-input
                v-model="sourceForm.apiSearchHeaders"
                type="textarea"
                :rows="3"
                placeholder='{"User-Agent": "Mozilla/5.0", "Referer": "https://xxx.com/"}'
              />
            </div>
            <div v-if="needsRequestBody(sourceForm.apiSearchMethod)" class="source-form__field source-form__field--full">
              <label>搜索请求体（JSON）</label>
              <el-input
                v-model="sourceForm.apiSearchBody"
                type="textarea"
                :rows="3"
                placeholder='{"keyword": "{q}", "page": 1}'
              />
            </div>
            <div class="source-form__field source-form__field--full">
              <label>小说详情页 URL 选择器</label>
              <el-input v-model="sourceForm.apiSearchBookUrlPath" size="default" placeholder="$.data.items[*].url / $.url" />
            </div>
            <div class="source-form__field">
              <label>搜索结果小说 ID 选择器</label>
              <el-input v-model="sourceForm.apiSearchBookIdPath" size="default" placeholder="$.data[*].id / $.items[*].bookId" />
            </div>
            <div class="source-form__field">
              <label>搜索结果标题选择器</label>
              <el-input v-model="sourceForm.apiSearchBookTitlePath" size="default" placeholder="$.data[*].title / $.items[*].name" />
            </div>
            <div class="source-form__field">
              <label>搜索结果作者选择器</label>
              <el-input v-model="sourceForm.apiSearchBookAuthorPath" size="default" placeholder="$.data[*].author" />
            </div>
            <div class="source-form__field">
              <label>搜索结果封面图选择器</label>
              <el-input v-model="sourceForm.apiSearchBookCoverPath" size="default" placeholder="$.data[*].cover / $.items[*].coverUrl" />
            </div>
            <div class="source-form__field">
              <label>搜索结果类别选择器</label>
              <el-input v-model="sourceForm.apiSearchBookCategoryPath" size="default" placeholder="$.data[*].sortname / $.items[*].category" />
            </div>
            <div class="source-form__field">
              <label>搜索结果更新状态选择器</label>
              <el-input v-model="sourceForm.apiSearchBookUpdateStatusPath" size="default" placeholder="$.data[*].full / $.items[*].status" />
            </div>
            <div class="source-form__field">
              <label>搜索结果最新章节选择器</label>
              <el-input v-model="sourceForm.apiSearchBookLastChapterPath" size="default" placeholder="$.data[*].lastchapter" />
            </div>
            <div class="source-form__field">
              <label>搜索结果最新章节 ID 选择器</label>
              <el-input v-model="sourceForm.apiSearchBookLastChapterIdPath" size="default" placeholder="$.data[*].lastchapterid" />
            </div>
            <div class="source-form__field">
              <label>搜索结果最新更新时间选择器</label>
              <el-input v-model="sourceForm.apiSearchBookLastUpdatePath" size="default" placeholder="$.data[*].lastupdate" />
            </div>
            <div class="source-form__field source-form__field--full">
              <label>搜索结果简介选择器</label>
              <el-input v-model="sourceForm.apiSearchBookIntroPath" size="default" placeholder="$.data[*].intro" />
            </div>
          </div>
        </div>

        <div class="source-form__subgroup">
          <div class="source-form__subgroup-head">
            <span class="source-form__subgroup-tag">小说详情页</span>
            <span class="source-form__subgroup-hint">{{ isRuleSource ? '获取单本小说信息；返回 HTML 用 CSS 选择器抽取字段' : '获取单本小说信息；返回 JSON 用 JSONPath 抽取字段' }}</span>
          </div>
          <div class="source-form__grid">
            <div class="source-form__field source-form__field--full">
              <label>小说详情页 URL</label>
              <div class="source-form__inline">
                <el-input
                  v-model="sourceForm.apiBookUrl"
                  size="default"
                  placeholder="https://xxx.com/api/book?id={id}"
                  class="source-form__inline-input"
                />
                <el-select
                  v-model="sourceForm.apiBookMethod"
                  size="default"
                  class="source-form__method-select"
                  popper-class="novel-dark-select"
                >
                  <el-option v-for="method in crawlHttpMethods" :key="method" :label="method" :value="method" />
                </el-select>
              </div>
            </div>
            <div class="source-form__field source-form__field--full">
              <label>详情请求头（JSON，可选）</label>
              <el-input
                v-model="sourceForm.apiBookHeaders"
                type="textarea"
                :rows="3"
                placeholder='{"User-Agent": "Mozilla/5.0", "Cookie": "session=..."}'
              />
            </div>
            <div v-if="needsRequestBody(sourceForm.apiBookMethod)" class="source-form__field source-form__field--full">
              <label>详情请求体（JSON）</label>
              <el-input
                v-model="sourceForm.apiBookBody"
                type="textarea"
                :rows="3"
                placeholder='{"id": "{id}"}'
              />
            </div>
            <div class="source-form__field">
              <label>作者选择器</label>
              <el-input v-model="sourceForm.apiBookAuthorPath" size="default" placeholder="$.author" />
            </div>
            <div class="source-form__field">
              <label>标题选择器</label>
              <el-input v-model="sourceForm.apiBookTitlePath" size="default" placeholder="$.title" />
            </div>
            <div class="source-form__field">
              <label>封面图选择器</label>
              <el-input v-model="sourceForm.apiBookCoverPath" size="default" placeholder="$.img_url" />
            </div>
            <div class="source-form__field">
              <label>小说类别选择器</label>
              <el-input v-model="sourceForm.apiBookCategoryPath" size="default" placeholder="$.category" />
            </div>
            <div class="source-form__field">
              <label>更新状态选择器</label>
              <el-input v-model="sourceForm.apiBookUpdateStatusPath" size="default" placeholder="$.status / $.serialStatus" />
            </div>
            <div class="source-form__field">
              <label>最新章节选择器</label>
              <el-input v-model="sourceForm.apiBookLastChapterPath" size="default" placeholder="$.lastchapter" />
            </div>
            <div class="source-form__field">
              <label>最新章节 ID 选择器</label>
              <el-input v-model="sourceForm.apiBookLastChapterIdPath" size="default" placeholder="$.lastchapterid" />
            </div>
            <div class="source-form__field">
              <label>最近更新时间选择器</label>
              <el-input v-model="sourceForm.apiBookLastUpdatePath" size="default" placeholder="$.lastupdate" />
            </div>
            <div class="source-form__field">
              <label>小说 ID 选择器</label>
              <el-input v-model="sourceForm.apiBookIdPath" size="default" placeholder="$.id / $.bookId" />
            </div>
            <div class="source-form__field source-form__field--full">
              <label>小说简介选择器</label>
              <el-input v-model="sourceForm.apiBookIntroPath" size="default" placeholder="$.intro" />
            </div>
          </div>
        </div>

        <div class="source-form__subgroup">
          <div class="source-form__subgroup-head">
            <span class="source-form__subgroup-tag">章节列表页</span>
            <span class="source-form__subgroup-hint">获取章节列表，并抽取章节 ID、标题、时间与可选正文信息</span>
          </div>
          <div class="source-form__grid">
            <div class="source-form__field source-form__field--full">
              <label>章节列表页 URL</label>
              <div class="source-form__inline">
                <el-input
                  v-model="sourceForm.apiChapterListUrl"
                  size="default"
                  placeholder="https://xxx.com/api/chapters?id={id}"
                  class="source-form__inline-input"
                />
                <el-select
                  v-model="sourceForm.apiChapterListMethod"
                  size="default"
                  class="source-form__method-select"
                  popper-class="novel-dark-select"
                >
                  <el-option v-for="method in crawlHttpMethods" :key="method" :label="method" :value="method" />
                </el-select>
              </div>
            </div>
            <div class="source-form__field source-form__field--full">
              <label>章节列表请求头（JSON，可选）</label>
              <el-input
                v-model="sourceForm.apiChapterListHeaders"
                type="textarea"
                :rows="3"
                placeholder='{"User-Agent": "Mozilla/5.0", "Cookie": "session=..."}'
              />
            </div>
            <div v-if="needsRequestBody(sourceForm.apiChapterListMethod)" class="source-form__field source-form__field--full">
              <label>章节列表请求体（JSON）</label>
              <el-input
                v-model="sourceForm.apiChapterListBody"
                type="textarea"
                :rows="3"
                placeholder='{"id": "{id}"}'
              />
            </div>
            <div class="source-form__field">
              <label>章节 ID 选择器</label>
              <el-input v-model="sourceForm.apiChapterListIdPath" size="default" placeholder="$.chapters[*].chapterid" />
            </div>
            <div class="source-form__field">
              <label>章节标题选择器</label>
              <el-input v-model="sourceForm.apiChapterListNamePath" size="default" placeholder="$.chapters[*].chaptername" />
            </div>
            <div class="source-form__field">
              <label>章节更新时间选择器</label>
              <el-input v-model="sourceForm.apiChapterListTimePath" size="default" placeholder="$.chapters[*].time" />
            </div>
            <div class="source-form__field">
              <label>章节正文选择器</label>
              <el-input v-model="sourceForm.apiChapterListContentPath" size="default" placeholder="$.chapters[*].txt" />
            </div>
            <div class="source-form__field source-form__field--full">
              <label>章节正文 md5 选择器</label>
              <el-input v-model="sourceForm.apiChapterListMd5Path" size="default" placeholder="$.chapters[*].md5" />
            </div>
          </div>
        </div>

        <div class="source-form__subgroup">
          <div class="source-form__subgroup-head">
            <span class="source-form__subgroup-tag">章节正文页</span>
            <span class="source-form__subgroup-hint">通过 {{ '{' }}id{{ '}' }} + {{ '{' }}chapterid{{ '}' }} 拉单章正文</span>
          </div>
          <div class="source-form__grid">
            <div class="source-form__field source-form__field--full">
              <label>章节正文页 URL</label>
              <div class="source-form__inline">
                <el-input
                  v-model="sourceForm.apiChapterUrl"
                  size="default"
                  placeholder="https://xxx.com/api/chapter?id={id}&chapterid={chapterid}"
                  class="source-form__inline-input"
                />
                <el-select
                  v-model="sourceForm.apiChapterMethod"
                  size="default"
                  class="source-form__method-select"
                  popper-class="novel-dark-select"
                >
                  <el-option v-for="method in crawlHttpMethods" :key="method" :label="method" :value="method" />
                </el-select>
              </div>
            </div>
            <div class="source-form__field source-form__field--full">
              <label>章节正文请求头（JSON，可选）</label>
              <el-input
                v-model="sourceForm.apiChapterHeaders"
                type="textarea"
                :rows="3"
                placeholder='{"User-Agent": "Mozilla/5.0", "Cookie": "session=..."}'
              />
            </div>
            <div v-if="needsRequestBody(sourceForm.apiChapterMethod)" class="source-form__field source-form__field--full">
              <label>章节正文请求体（JSON）</label>
              <el-input
                v-model="sourceForm.apiChapterBody"
                type="textarea"
                :rows="3"
                placeholder='{"id": "{id}", "chapterid": "{chapterid}"}'
              />
            </div>
            <div class="source-form__field">
              <label>章节标题选择器</label>
              <el-input v-model="sourceForm.apiChapterNamePath" size="default" placeholder="$.chaptername" />
            </div>
            <div class="source-form__field">
              <label>章节更新时间选择器</label>
              <el-input v-model="sourceForm.apiChapterTimePath" size="default" placeholder="$.time（对应 chapters.time）" />
            </div>
            <div class="source-form__field">
              <label>章节正文选择器</label>
              <el-input v-model="sourceForm.apiChapterContentPath" size="default" placeholder="$.txt" />
            </div>
            <div class="source-form__field">
              <label>章节正文 md5 选择器</label>
              <el-input v-model="sourceForm.apiChapterMd5Path" size="default" placeholder="$.md5（若 API 提供则用，否则前端本地计算）" />
            </div>
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <template v-if="sourceMode === 'list'">
        <el-button @click="sourceManageVisible = false">关闭</el-button>
      </template>
      <template v-else-if="sourceMode === 'duplicate'">
        <el-button @click="backToSourceList">返回列表</el-button>
        <el-button type="primary" @click="submitDuplicateForm">复制并编辑</el-button>
      </template>
      <template v-else>
        <el-button @click="backToSourceList">返回列表</el-button>
        <el-button type="primary" @click="saveSourceForm">保存</el-button>
      </template>
    </template>
  </el-dialog>

  <!-- 小说爬取 -->
  <el-dialog
    :model-value="modelValue"
    :title="crawlDialogTitle"
    width="90vw"
    height="80vh"
    destroy-on-close
    class="novel-dark-dialog novel-crawl-dialog"
    @update:model-value="(val: boolean) => emit('update:modelValue', val)"
    @close="resetCrawlState"
  >
    <el-steps :active="crawlStep - 1" finish-status="success" align-center class="import-steps">
      <el-step title="搜索小说" />
      <el-step title="爬取章节" />
      <el-step title="预览入库" />
    </el-steps>

    <!-- 步骤 1：搜索 -->
    <div v-show="crawlStep === 1" class="crawl-step">
      <section class="crawl-search">
        <div class="crawl-search__row">
          <el-button type="primary" plain size="default" @click="openSourceManager">
            <el-icon><Setting /></el-icon>
            添加来源
          </el-button>
          <el-select
            v-model="crawlSourceKey"
            class="crawl-search__source"
            popper-class="novel-dark-select"
            placeholder="选择来源"
          >
            <el-option
              v-for="src in crawlSources"
              :key="src.key"
              :label="src.name"
              :value="src.key"
            >
              <div class="crawl-source-opt">
                <span class="crawl-source-opt__name">{{ src.name }}</span>
                <span class="crawl-source-opt__desc">{{ src.desc }}</span>
              </div>
            </el-option>
          </el-select>
          <el-input
            v-model="crawlSearchQuery"
            size="default"
            placeholder="按书名 / 作者搜索"
            class="crawl-search__keyword"
            @keyup.enter="searchCrawlBooks"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button
            type="primary"
            :loading="crawlSearching"
            @click="searchCrawlBooks"
          >搜索</el-button>
            <el-button
              :disabled="crawlSearching || !crawlSourceKey || !crawlSearchQuery.trim()"
              @click="clearCrawlSearchCache"
              title="清空当前来源+关键字的本地搜索/章节缓存"
            >清空缓存</el-button>
        </div>
        <p class="crawl-search__hint" v-if="currentCrawlSource">
          {{ currentCrawlSource.name }}：{{ currentCrawlSource.desc }}
        </p>
      </section>

      <section
        v-loading="crawlSearching"
        element-loading-background="rgba(13, 17, 23, 0.55)"
        class="crawl-results"
      >
        <el-empty
          v-if="!crawlSearching && crawlResults.length === 0"
          description="尚无搜索结果，输入关键词后点击搜索"
        />
        <div
          v-for="(book, bookIndex) in crawlResults"
          :key="`${crawlBookIdentity(book)}#${bookIndex}`"
          class="crawl-book-card"
          :class="{ 'is-active': isSelectedCrawlBook(book) }"
          @click="selectCrawlBook(book)"
        >
          <div class="crawl-book-card__head">
            <h4 class="crawl-book-card__title">{{ book.title }}</h4>
            <el-tag
              v-if="hasCrawlBookDetails(book) && book.sortname"
              size="small"
              effect="plain"
              round
              class="crawl-book-card__tag"
            >
              {{ book.sortname }}
            </el-tag>
          </div>
          <div class="crawl-book-card__meta">
            <span><el-icon><User /></el-icon>{{ book.author }}</span>
            <span v-if="book.lastchapterid > 0"><el-icon><Reading /></el-icon>{{ book.lastchapterid }} 章</span>
            <span class="crawl-book-card__time">{{ book.lastupdate }}</span>
          </div>
          <p class="crawl-book-card__intro">{{ book.intro }}</p>
        </div>
      </section>
    </div>

    <!-- 步骤 2：配置 + 爬取 -->
    <div v-show="crawlStep === 2" class="crawl-step">
      <section v-if="crawlSelectedBook" class="crawl-info">
        <div class="crawl-info__title">{{ crawlSelectedBook.title }}</div>
        <div class="crawl-info__meta">
          <span>来源：{{ currentCrawlSource.name }}</span>
          <span>dirid：{{ crawlSelectedBook.dirid }}</span>
          <span>作者：{{ crawlSelectedBook.author }}</span>
          <span>题材：{{ crawlSelectedBook.sortname }}</span>
          <span>规模：{{ crawlSelectedBook.full }}</span>
          <span v-if="crawlSelectedBook.lastchapterid > 0">总章节：{{ crawlSelectedBook.lastchapterid }}</span>
          <span v-else-if="crawlBookCountLoading">正在获取章节数…</span>
          <span v-else-if="crawlBookDetailLoading">正在获取详情…</span>
          <span>最近更新：{{ crawlSelectedBook.lastupdate }}</span>
        </div>
        <p class="crawl-info__intro">{{ crawlSelectedBook.intro }}</p>
      </section>

      <section class="crawl-config">
        <div class="crawl-config__row">
          <label>章节范围</label>
          <el-input-number
            v-model="crawlStartChapter"
            :min="1"
            :max="crawlSelectedBook?.lastchapterid || 9999"
            :disabled="crawling"
            controls-position="right"
          />
          <span class="crawl-config__dash">—</span>
          <el-input-number
            v-model="crawlEndChapter"
            :min="1"
            :max="crawlSelectedBook?.lastchapterid || 9999"
            :disabled="crawling"
            controls-position="right"
          />
          <span class="crawl-config__sum">
            共 {{ Math.max(crawlEndChapter - crawlStartChapter + 1, 0) }} 章
          </span>
        </div>
      </section>

      <section class="crawl-progress">
        <div class="crawl-progress__bar">
          <div
            class="crawl-progress-meter"
            :class="{
              'is-active': !crawlProgressStatus,
              'is-success': crawlProgressStatus === 'success',
              'is-exception': crawlProgressStatus === 'exception',
              'is-warning': crawlProgressStatus === 'warning',
            }"
            role="progressbar"
            :aria-valuenow="crawlProgress"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <div class="crawl-progress-meter__dots">
              <span
                v-for="chapterKey in crawlProgressDotChapters"
                :key="chapterKey"
                class="crawl-progress-meter__dot"
                :class="{
                  'is-complete': isCrawlChapterFetched(chapterKey),
                  'is-error': isCrawlChapterFailed(chapterKey),
                }"
                :title="getCrawlProgressDotTitle(chapterKey)"
              />
            </div>
            <span class="crawl-progress-meter__value">{{ crawlProgress }}%</span>
          </div>
        </div>
        <p class="crawl-progress__text">{{ crawlProgressText || '点击下方“开始爬取”按钮启动抓取' }}</p>

        <div v-if="crawling && recentCrawledChapters.length > 0" class="crawl-progress__list">
          <div
            v-for="item in recentCrawledChapters"
            :key="item.key"
            class="crawl-progress__item"
          >
            <el-icon><Check /></el-icon>
            <span>{{ item.chaptername }}</span>
          </div>
          <div v-if="crawledChapterCount > recentCrawledChapters.length" class="crawl-progress__more">
            … 已抓取 {{ crawledChapterCount }} 章，仅显示最新 {{ recentCrawledChapters.length }} 条
          </div>
        </div>
      </section>
    </div>

    <!-- 步骤 3：预览 + 入库 -->
    <div v-show="crawlStep === 3" class="crawl-step">
      <div class="import-preview__head">
        <div class="import-preview__summary">
          共爬取 <strong>{{ crawledChapterCount }}</strong> 章，已选 <strong>{{ crawlImportSelectedRows.length }}</strong> 章入库
        </div>
        <div class="import-preview__tools">
          <el-popover
            v-model:visible="crawlFilterPopoverVisible"
            placement="bottom-end"
            trigger="click"
            width="775"
            popper-class="novel-filter-popover"
          >
            <template #reference>
              <el-button size="small" plain>
                <el-icon><Setting /></el-icon>
                过滤规则
              </el-button>
            </template>

            <div class="crawl-filter" @click.stop @mousedown.stop>
              <header class="crawl-filter__head">
                <div>
                  <h4 class="crawl-filter__title">过滤正文</h4>
                  <p class="crawl-filter__hint">勾选规则后可对单章或已选章节应用过滤。</p>
                </div>
                <el-button size="small" type="primary" @click="applyCrawlFilterToSelected">
                  应用到已选
                </el-button>
              </header>

              <ul class="crawl-filter__list">
                <li
                  v-for="rule in crawlFilterRules"
                  :key="rule.id"
                  class="crawl-filter__item"
                >
                  <el-checkbox v-model="rule.enabled" class="crawl-filter__check">
                    <div class="crawl-filter__item-info">
                      <span class="crawl-filter__item-name">{{ rule.name }}</span>
                      <code
                        class="crawl-filter__item-regex"
                        :title="`/${rule.pattern}/${rule.flags}`"
                      >/{{ rule.pattern }}/{{ rule.flags }}</code>
                    </div>
                  </el-checkbox>
                  <el-tag v-if="rule.builtin" size="small" effect="plain" class="crawl-filter__badge">内置</el-tag>
                  <el-button
                    v-else
                    link
                    type="danger"
                    size="small"
                    @click="removeCrawlFilterRule(rule.id)"
                  >移除</el-button>
                </li>
              </ul>

              <div class="crawl-filter__custom">
                <el-input
                  v-model="crawlCustomRuleName"
                  size="small"
                  placeholder="规则名称（可选）"
                  class="crawl-filter__custom-input crawl-filter__custom-input--name"
                />
                <el-input
                  v-model="crawlCustomRulePattern"
                  size="small"
                  placeholder="匹配正则（必填）"
                  class="crawl-filter__custom-input crawl-filter__custom-input--pattern"
                />
                <el-select
                  v-model="crawlCustomRuleFlagsList"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  size="small"
                  placeholder="匹配方式"
                  :teleported="false"
                  popper-class="novel-dark-select"
                  class="crawl-filter__custom-input crawl-filter__custom-input--flags"
                >
                  <el-option
                    v-for="opt in CRAWL_FILTER_FLAG_OPTIONS"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
                <el-input
                  v-model="crawlCustomRuleReplacement"
                  size="small"
                  placeholder="替换为（默认空）"
                  class="crawl-filter__custom-input crawl-filter__custom-input--repl"
                />
                <el-button size="small" type="primary" plain @click="addCrawlCustomFilterRule">
                  <el-icon><Plus /></el-icon>
                  添加
                </el-button>
              </div>
            </div>
          </el-popover>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="crawlImportSelectedRows.length === 0"
            @click="applyCrawlFilterToSelected"
          >
            <el-icon><Filter /></el-icon>
            过滤已选
          </el-button>
        </div>
      </div>

      <el-table
        ref="crawlImportTableRef"
        :data="crawlPreviewChapters"
        class="novel-table import-preview__table"
        height="380"
        row-key="key"
        :tooltip-options="{ effect: 'dark', popperClass: 'novel-cell-tooltip' }"
        @selection-change="onCrawlSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="key" label="章节号" width="96" sortable />
        <el-table-column prop="chaptername" label="章节标题" min-width="220" sortable>
          <template #default="{ row }">
            <span
              class="crawl-chapter-title"
              :class="{ 'is-warning': hasCrawlChapterLengthWarning(row) }"
              :title="getCrawlChapterLengthWarning(row) || row.chaptername"
            >
              <el-icon
                v-if="hasCrawlChapterLengthWarning(row)"
                class="crawl-chapter-title__warning"
                aria-hidden="true"
              >
                <WarningFilled />
              </el-icon>
              <span class="crawl-chapter-title__text">{{ row.chaptername }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="字数" width="100" sortable :sort-method="sortCrawlByTextLength">
          <template #default="{ row }">
            <span
              class="row-count"
              :class="{ 'is-warning': hasCrawlChapterLengthWarning(row) }"
              :title="getCrawlChapterLengthWarning(row) || undefined"
            >
              {{ row.txt.length }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="事件状态" width="120" sortable :sort-method="sortCrawlByEventState">
          <template #default="{ row }">
            <el-tooltip
              :content="row.errorReason || crawlEventStateLabel(row.eventState)"
              placement="top"
              :disabled="!row.errorReason"
            >
              <span class="crawl-event-chip" :class="`crawl-event-chip--${crawlEventStateKey(row.eventState)}`">
                {{ crawlEventStateLabel(row.eventState) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="204" align="right" fixed="right">
          <template #default="{ row }">
            <div class="import-preview__actions">
              <el-tooltip content="预览正文" placement="top">
                <el-button text circle class="icon-action" @click="openCrawlChapterPreview(row)">
                  <el-icon><View /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="过滤正文" placement="top">
                <el-button text circle class="icon-action" @click="filterCrawlChapter(row)">
                  <el-icon><Filter /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="清洗事件" placement="top">
                <el-button text circle class="icon-action" @click="cleanCrawlChapterEvent(row)">
                  <el-icon><MagicStick /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="移除" placement="top">
                <el-button text circle class="icon-action delete" @click="removeCrawlChapter(row)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <template #footer>
      <!-- 步骤 1 footer -->
      <template v-if="crawlStep === 1">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button
          type="primary"
          :disabled="!crawlSelectedBook || crawlBookDetailLoading || crawlBookCountLoading"
          @click="goCrawlConfig"
        >下一步</el-button>
      </template>
      <!-- 步骤 2 footer -->
      <template v-else-if="crawlStep === 2">
        <el-button @click="crawlStep = 1" :disabled="crawling">上一步</el-button>
        <el-button v-if="!crawling" @click="emit('update:modelValue', false)">取消</el-button>
        <el-button v-else type="danger" @click="cancelCrawl">取消爬取</el-button>
        <el-button
          v-if="!crawling && crawlSelectedBook"
          :disabled="crawling"
          @click="clearCrawlChaptersCache"
          title="清空当前小说的本地章节缓存"
        >清空缓存</el-button>
        <el-button
          v-if="!crawling && crawledChapterCount === 0"
          type="primary"
          @click="startCrawl"
        >开始爬取</el-button>
        <el-button
          v-if="canContinueCrawl"
          type="primary"
          @click="continueCrawl"
        >
          <el-icon><RefreshRight /></el-icon>
          继续爬取 ({{ nextCrawlStartChapter }}-{{ crawlEndChapter }})
        </el-button>
        <el-button
          v-if="!crawling && crawledChapterCount > 0"
          type="primary"
          :plain="canContinueCrawl"
          @click="goCrawlPreview"
        >预览并入库 ({{ crawledChapterCount }})</el-button>
      </template>
      <!-- 步骤 3 footer -->
      <template v-else>
        <el-button @click="crawlStep = 2">上一步</el-button>
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button
          type="primary"
          :loading="crawlSubmitting"
          :disabled="crawlImportSelectedRows.length === 0"
          @click="submitCrawlImport"
        >确认导入 ({{ crawlImportSelectedRows.length }})</el-button>
      </template>
    </template>
  </el-dialog>

  <el-dialog
    v-model="crawlPreviewVisible"
    :title="crawlPreviewChapter?.chaptername || '预览正文'"
    width="760px"
    append-to-body
    destroy-on-close
    class="novel-dark-dialog crawl-preview-dialog"
  >
    <div v-if="crawlPreviewChapter" class="crawl-preview">
      <div class="crawl-preview__top">
        <div class="crawl-preview__meta">
          <span>章节号：{{ crawlPreviewChapter.key }}</span>
          <span>字数：{{ crawlPreviewChapter.txt.length }}</span>
          <span>事件状态：{{ crawlEventStateLabel(crawlPreviewChapter.eventState) }}</span>
        </div>
        <div class="crawl-preview__actions">
          <el-button size="small" plain @click="filterPreviewChapter">
            <el-icon><Filter /></el-icon>
            过滤正文
          </el-button>
          <el-button size="small" type="primary" plain @click="cleanPreviewChapterEvent">
            <el-icon><MagicStick /></el-icon>
            清洗事件
          </el-button>
        </div>
      </div>
      <div class="crawl-preview__content">
        <p
          v-for="(paragraph, idx) in splitCrawlParagraphs(crawlPreviewChapter.txt)"
          :key="idx"
        >
          {{ paragraph }}
        </p>
      </div>
    </div>

    <template #footer>
      <el-button @click="crawlPreviewVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { AxiosError } from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Check,
  Delete,
  Filter,
  MagicStick,
  Plus,
  Reading,
  RefreshRight,
  Search,
  Setting,
  User,
  View,
  WarningFilled,
} from '@element-plus/icons-vue'
import {
  analyzeCrawlSourceApi,
  createCrawlSourceApi,
  crawlChaptersStreamUrl,
  deleteCrawlSourceApi,
  duplicateCrawlSourceApi,
  fetchCrawlBookChapterCountApi,
  fetchCrawlBookDetailApi,
  listCrawlSourcesApi,
  searchCrawlBooksApi,
  updateCrawlSourceApi,
  CRAWL_HTTP_METHODS,
  CRAWL_HTTP_METHODS_WITH_BODY,
  type CrawlChapterStreamEvent,
  type CrawlChapterDraft as ApiCrawlChapterDraft,
  type CrawlHttpMethod,
  type CrawlSearchResult as ApiCrawlSearchResult,
  type CrawlSourcePayload,
  type EventState,
} from '@/api/novel'
import { getCurrentUserApi } from '@/api/user'
import { fetchWithAuthRetry } from '@/request'

export type CrawlSource = CrawlSourcePayload
export type CrawlSearchResult = ApiCrawlSearchResult
export type CrawlChapterDraft = ApiCrawlChapterDraft

interface CrawlFilterRule {
  id: string
  name: string
  pattern: string
  flags: string
  replacement: string
  enabled: boolean
  builtin: boolean
}

type CompiledCrawlFilterRule = {
  rule: CrawlFilterRule
  regex: RegExp
}

const props = defineProps<{
  modelValue: boolean
  projectPublicId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'submit', drafts: CrawlChapterDraft[], book: CrawlSearchResult): void
}>()

const DEFAULT_CRAWL_END_CHAPTER = 20

const createEmptySource = (): CrawlSource => ({
  key: '',
  name: '',
  baseUrl: '',
  desc: '',
  sourceType: 'api',
  searchUrlTemplate: '',
  apiSearchBookUrlPath: '',
  apiSearchBookIdPath: '',
  apiSearchBookTitlePath: '',
  apiSearchBookAuthorPath: '',
  apiSearchBookIntroPath: '',
  apiSearchBookCoverPath: '',
  apiSearchBookCategoryPath: '',
  apiSearchBookUpdateStatusPath: '',
  apiSearchBookLastChapterPath: '',
  apiSearchBookLastChapterIdPath: '',
  apiSearchBookLastUpdatePath: '',
  apiBookUrl: '',
  apiBookTitlePath: '',
  apiBookAuthorPath: '',
  apiBookIntroPath: '',
  apiBookLastChapterPath: '',
  apiBookLastChapterIdPath: '',
  apiBookLastUpdatePath: '',
  apiBookCoverPath: '',
  apiBookCategoryPath: '',
  apiBookUpdateStatusPath: '',
  apiBookIdPath: '',
  apiChapterListUrl: '',
  apiChapterListNamePath: '',
  apiChapterListIdPath: '',
  apiChapterListContentPath: '',
  apiChapterListTimePath: '',
  apiChapterListMd5Path: '',
  apiChapterUrl: '',
  apiChapterNamePath: '',
  apiChapterContentPath: '',
  apiChapterTimePath: '',
  apiChapterMd5Path: '',
  apiSearchMethod: 'GET',
  apiSearchHeaders: '',
  apiSearchBody: '',
  apiBookMethod: 'GET',
  apiBookHeaders: '',
  apiBookBody: '',
  apiChapterListMethod: 'GET',
  apiChapterListHeaders: '',
  apiChapterListBody: '',
  apiChapterMethod: 'GET',
  apiChapterHeaders: '',
  apiChapterBody: '',
  builtin: false,
})

const normalizeCrawlSource = (source: Partial<CrawlSource>): CrawlSource => ({
  ...createEmptySource(),
  ...source,
  sourceType: source.sourceType ?? 'api',
})

const crawlSources = ref<CrawlSource[]>([])

const crawlHttpMethods = CRAWL_HTTP_METHODS

const needsRequestBody = (method: CrawlHttpMethod | string | undefined): boolean => {
  if (!method) return false
  return (CRAWL_HTTP_METHODS_WITH_BODY as ReadonlyArray<string>).includes(method)
}

const crawlStep = ref<1 | 2 | 3>(1)
const crawlSourceKey = ref<string>('')
const crawlSearchQuery = ref('')
const crawlSearching = ref(false)
const crawlResults = ref<CrawlSearchResult[]>([])
const crawlSelectedBook = ref<CrawlSearchResult | null>(null)
const crawlDetailedBookKeys = ref<Set<string>>(new Set())
const crawlBookDetailLoading = ref(false)
const crawlBookCountLoading = ref(false)
const crawlStartChapter = ref(1)
const crawlEndChapter = ref(DEFAULT_CRAWL_END_CHAPTER)
const crawling = ref(false)
const crawlAborted = ref(false)
const crawlChapterSlots = ref<Array<CrawlChapterDraft | null>>([])
const crawlChapterSlotStart = ref(0)
const crawlChapterSlotEnd = ref(0)
const crawledChapterCount = ref(0)
const recentCrawledChapters = ref<CrawlChapterDraft[]>([])
const crawlProgressText = ref('')
let crawlAbortController: AbortController | null = null
const crawlImportTableRef = ref()
const crawlImportSelectedRows = ref<CrawlChapterDraft[]>([])
const crawlSubmitting = ref(false)
const crawlPreviewVisible = ref(false)
const crawlPreviewChapter = ref<CrawlChapterDraft | null>(null)
const crawlFilterPopoverVisible = ref(false)
let crawlBookCountRequestId = 0
let crawlBookDetailRequestId = 0

const crawlFilterRules = ref<CrawlFilterRule[]>([
  {
    id: 'cf-url',
    name: '移除 http(s) 网址',
    pattern: 'https?:\\/\\/[^\\s\\u4e00-\\u9fa5]+',
    flags: 'gi',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'cf-www',
    name: '移除 www.xxx 域名',
    pattern: 'www\\.[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}',
    flags: 'gi',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'cf-ads',
    name: '移除常见广告 / 水印行',
    pattern: '^.*(笔趣阁|起点中文|纵横中文|17K小说|顶点小说|百度搜索|本站|本书首发|手打|更新最快|VIP章节|微信公众号|加群|本作品).*$',
    flags: 'gm',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'cf-tips',
    name: '移除章节尾提示',
    pattern: '^\\s*(?:本章未完.*|请收藏本站.*|最新网址.*|手机用户请浏览.*|喜欢.*请收藏.*)$',
    flags: 'gm',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'cf-email',
    name: '移除邮箱',
    pattern: '[\\w.+-]+@[\\w-]+\\.[\\w.-]+',
    flags: 'gi',
    replacement: '',
    enabled: false,
    builtin: true,
  },
  {
    id: 'cf-garbled',
    name: '移除乱码字符（�、控制符）',
    pattern: '[\\uFFFD\\u0000-\\u0008\\u000B-\\u001F]',
    flags: 'g',
    replacement: '',
    enabled: true,
    builtin: true,
  },
  {
    id: 'cf-empty',
    name: '合并多余空行（≥3 行 → 1 行）',
    pattern: '\\n{3,}',
    flags: 'g',
    replacement: '\\n\\n',
    enabled: true,
    builtin: true,
  },
  {
    id: 'cf-unicode',
    name: '移除ubicode特殊符号',
    pattern: '[¤§©®™°±×÷•·※★☆♠♣♥♦¤⊕♟◇●c♜◆•Θ★mó◇ Θī♜]',
    flags: 'g',
    replacement: '',
    enabled: true,
    builtin: true,
  },
])

const crawlCustomRuleName = ref('')
const crawlCustomRulePattern = ref('')
const crawlCustomRuleFlagsList = ref<string[]>(['g'])
const crawlCustomRuleReplacement = ref('')
const CHAPTER_SHORT_WARNING_LENGTH = 1000
const CHAPTER_LONG_WARNING_LENGTH = 20000

const CRAWL_FILTER_FLAG_OPTIONS = [
  { value: 'g', label: '全局匹配（所有出现处都替换）' },
  { value: 'i', label: '忽略大小写' },
  { value: 'm', label: '多行模式（^ $ 匹配每一行）' },
  { value: 's', label: '点号匹配换行' },
]

const CRAWL_CACHE_PREFIX = 'novel-crawl-cache:v1'

const buildCrawlCacheKey = (...parts: Array<string | number>) => (
  [CRAWL_CACHE_PREFIX, ...parts.map((part) => encodeURIComponent(String(part)))].join(':')
)

const readCrawlCache = <T,>(key: string): T | null => {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

const writeCrawlCache = (key: string, value: unknown) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 本地存储不可用或空间不足时，不影响爬取流程。
  }
}

const removeCrawlCache = (key: string) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(key)
  } catch {
    // 忽略本地存储错误。
  }
}

const removeCrawlCachePrefix = (prefix: string) => {
  if (typeof window === 'undefined') return
  try {
    const keys = Array.from({ length: window.localStorage.length }, (_, index) => window.localStorage.key(index))
      .filter((key): key is string => Boolean(key && key.startsWith(prefix)))
    keys.forEach((key) => window.localStorage.removeItem(key))
  } catch {
    // 忽略本地存储错误。
  }
}

const crawlCache = {
  readSearch(projectPublicId: string, sourceKey: string, query: string) {
    return readCrawlCache<CrawlSearchResult[]>(
      buildCrawlCacheKey('search', projectPublicId, sourceKey, query),
    )
  },
  writeSearch(projectPublicId: string, sourceKey: string, query: string, books: CrawlSearchResult[]) {
    writeCrawlCache(buildCrawlCacheKey('search', projectPublicId, sourceKey, query), books)
  },
  clearSearch(projectPublicId: string, sourceKey: string, query: string) {
    removeCrawlCache(buildCrawlCacheKey('search', projectPublicId, sourceKey, query))
  },
  readChapters(projectPublicId: string, sourceKey: string, dirid: string, startChapter: number, endChapter: number) {
    return readCrawlCache<CrawlChapterDraft[]>(
      buildCrawlCacheKey('chapters', projectPublicId, sourceKey, dirid, startChapter, endChapter),
    )
  },
  writeChapters(
    projectPublicId: string,
    sourceKey: string,
    dirid: string,
    startChapter: number,
    endChapter: number,
    chapters: CrawlChapterDraft[],
  ) {
    writeCrawlCache(
      buildCrawlCacheKey('chapters', projectPublicId, sourceKey, dirid, startChapter, endChapter),
      chapters,
    )
  },
  clearChapters(projectPublicId: string, sourceKey: string, dirid: string) {
    removeCrawlCachePrefix(buildCrawlCacheKey('chapters', projectPublicId, sourceKey, dirid))
  },
}

const crawlTargetTotal = computed(() => Math.max(crawlEndChapter.value - crawlStartChapter.value + 1, 1))

const crawledChapters = computed(() => (
  crawlChapterSlots.value.filter((item): item is CrawlChapterDraft => Boolean(item))
))

const crawlPreviewChapters = computed(() => (crawlStep.value === 3 ? crawledChapters.value : []))

const crawlProgressDotChapters = computed(() => (
  Array.from({ length: crawlTargetTotal.value }, (_, index) => crawlStartChapter.value + index)
))

const crawlProgress = computed(() => {
  if (!crawlSelectedBook.value) return 0
  return Math.min(Math.round((crawledChapterCount.value / crawlTargetTotal.value) * 100), 100)
})

const crawlCompleted = computed(
  () => crawledChapterCount.value > 0 && crawledChapterCount.value >= crawlTargetTotal.value,
)

const nextCrawlStartChapter = computed(() => {
  if (
    crawlChapterSlotStart.value !== crawlStartChapter.value
    || crawlChapterSlotEnd.value !== crawlEndChapter.value
  ) return crawlStartChapter.value
  const slots = crawlChapterSlots.value
  for (let index = 0; index < crawlTargetTotal.value; index += 1) {
    if (!slots[index]) return crawlStartChapter.value + index
  }
  return crawlEndChapter.value + 1
})

const canContinueCrawl = computed(
  () => Boolean(
    !crawling.value
    && crawlSelectedBook.value
    && crawledChapterCount.value > 0
    && nextCrawlStartChapter.value <= crawlEndChapter.value,
  ),
)

const crawlProgressStatus = computed<'' | 'success' | 'exception' | 'warning'>(() => {
  if (crawling.value) return ''
  if (crawlAborted.value) return 'exception'
  if (crawlCompleted.value) return 'success'
  if (crawledChapterCount.value > 0) return 'warning'
  return ''
})

const getCrawlSlotIndex = (chapterKey: number) => chapterKey - crawlStartChapter.value

const getCrawlSlotChapter = (chapterKey: number) => {
  if (
    crawlChapterSlotStart.value !== crawlStartChapter.value
    || crawlChapterSlotEnd.value !== crawlEndChapter.value
  ) return null
  const index = getCrawlSlotIndex(chapterKey)
  if (index < 0 || index >= crawlChapterSlots.value.length) return null
  return crawlChapterSlots.value[index]
}

const isCrawlChapterFetched = (chapterKey: number) => Boolean(getCrawlSlotChapter(chapterKey))

const isCrawlChapterFailed = (chapterKey: number) => getCrawlSlotChapter(chapterKey)?.eventState === -1

const getCrawlProgressDotTitle = (chapterKey: number) => {
  const chapter = getCrawlSlotChapter(chapterKey)
  return chapter ? `第 ${chapterKey} 章：${chapter.chaptername}` : `第 ${chapterKey} 章：未抓取`
}

const rebuildCrawlChapterSlots = (chapters: CrawlChapterDraft[] = []) => {
  const slots: Array<CrawlChapterDraft | null> = Array.from({ length: crawlTargetTotal.value }, () => null)
  let completed = 0
  for (const chapter of chapters) {
    const index = chapter.key - crawlStartChapter.value
    if (index < 0 || index >= slots.length) continue
    if (!slots[index]) completed += 1
    slots[index] = chapter
  }
  crawlChapterSlots.value = slots
  crawlChapterSlotStart.value = crawlStartChapter.value
  crawlChapterSlotEnd.value = crawlEndChapter.value
  crawledChapterCount.value = completed
  recentCrawledChapters.value = chapters
    .filter((chapter) => chapter.key >= crawlStartChapter.value && chapter.key <= crawlEndChapter.value)
    .slice(-6)
    .reverse()
}

const resetCrawlChapterSlots = () => {
  crawlChapterSlots.value = []
  crawlChapterSlotStart.value = 0
  crawlChapterSlotEnd.value = 0
  crawledChapterCount.value = 0
  recentCrawledChapters.value = []
}

const ensureCrawlChapterSlots = () => {
  if (
    crawlChapterSlots.value.length === crawlTargetTotal.value
    && crawlChapterSlotStart.value === crawlStartChapter.value
    && crawlChapterSlotEnd.value === crawlEndChapter.value
  ) return
  rebuildCrawlChapterSlots(crawledChapters.value)
}

const rememberRecentCrawledChapter = (draft: CrawlChapterDraft) => {
  recentCrawledChapters.value = [
    draft,
    ...recentCrawledChapters.value.filter((item) => item.key !== draft.key),
  ].slice(0, 6)
}

const currentCrawlSource = computed(
  () => crawlSources.value.find((s) => s.key === crawlSourceKey.value) || crawlSources.value[0],
)

const crawlDialogTitle = computed(() => (crawlStep.value === 3 ? '预览入库' : '小说爬取'))

const sourceManagerTitle = computed(() => {
  switch (sourceMode.value) {
    case 'create':
      return '新增来源'
    case 'edit':
      return '编辑来源'
    case 'duplicate':
      return '复制为自定义来源'
    default:
      return '来源管理'
  }
})

const ensureProjectReady = () => {
  if (props.projectPublicId.trim()) return true
  ElMessage.warning('未指定项目，无法使用小说爬取')
  return false
}

const selectAvailableSource = (preferredKey = crawlSourceKey.value) => {
  const preferred = crawlSources.value.find((source) => source.key === preferredKey)
  crawlSourceKey.value = preferred?.key || crawlSources.value[0]?.key || ''
}

const loadCrawlSources = async (preferredKey = crawlSourceKey.value) => {
  if (!ensureProjectReady()) return
  try {
    const { data } = await listCrawlSourcesApi(props.projectPublicId)
    crawlSources.value = data.map((source) => normalizeCrawlSource(source))
    selectAvailableSource(preferredKey)
  } catch (error) {
    ElMessage.error(`来源加载失败：${getErrorMessage(error)}`)
  }
}

const resetCrawlState = () => {
  crawlAbortController?.abort()
  crawlAbortController = null
  crawlStep.value = 1
  selectAvailableSource()
  crawlSearchQuery.value = ''
  crawlSearching.value = false
  crawlResults.value = []
  crawlSelectedBook.value = null
  crawlDetailedBookKeys.value = new Set()
  crawlBookDetailRequestId += 1
  crawlBookDetailLoading.value = false
  crawlBookCountRequestId += 1
  crawlBookCountLoading.value = false
  crawlStartChapter.value = 1
  crawlEndChapter.value = DEFAULT_CRAWL_END_CHAPTER
  crawling.value = false
  crawlAborted.value = false
  resetCrawlChapterSlots()
  crawlProgressText.value = ''
  crawlImportSelectedRows.value = []
  crawlSubmitting.value = false
  crawlPreviewVisible.value = false
  crawlPreviewChapter.value = null
  crawlFilterPopoverVisible.value = false
}

const searchCrawlBooks = async (options: { skipCache?: boolean } = {}) => {
  if (!crawlSearchQuery.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  if (!ensureProjectReady()) return
  if (!crawlSourceKey.value) {
    ElMessage.warning('请先选择爬取来源')
    return
  }
  const sourceKey = crawlSourceKey.value
  const query = crawlSearchQuery.value.trim()
  crawlSearching.value = true
  crawlResults.value = []
  crawlSelectedBook.value = null
  resetCrawlChapterSlots()
  crawlImportSelectedRows.value = []
  crawlDetailedBookKeys.value = new Set()
  crawlBookDetailRequestId += 1
  crawlBookDetailLoading.value = false
  crawlBookCountRequestId += 1
  crawlBookCountLoading.value = false
  try {
    if (!options.skipCache) {
      const cached = crawlCache.readSearch(props.projectPublicId, sourceKey, query)
      if (cached && cached.length > 0) {
        crawlResults.value = mergeCrawlSearchResults(cached, sourceKey)
        ElMessage.success(`已使用本地缓存（共 ${crawlResults.value.length} 条），点「清空缓存」可重新搜索`)
        return
      }
    }
    const { data } = await searchCrawlBooksApi(props.projectPublicId, {
      sourceKey,
      query,
    })
    crawlResults.value = mergeCrawlSearchResults(data, sourceKey)
    if (crawlResults.value.length === 0) {
      ElMessage.info('未搜索到可爬取小说')
    } else {
      crawlCache.writeSearch(props.projectPublicId, sourceKey, query, crawlResults.value)
    }
  } catch (error) {
    ElMessage.error(`搜索失败：${getErrorMessage(error)}`)
  } finally {
    crawlSearching.value = false
  }
}

const clearCrawlSearchCache = () => {
  const sourceKey = crawlSourceKey.value
  const query = crawlSearchQuery.value.trim()
  if (!sourceKey || !query) {
    ElMessage.warning('请先选择来源并输入关键词')
    return
  }
  crawlCache.clearSearch(props.projectPublicId, sourceKey, query)
  for (const book of crawlResults.value) {
    crawlCache.clearChapters(props.projectPublicId, sourceKey, book.dirid)
  }
  ElMessage.success('已清空当前搜索缓存，可手动点击搜索重新请求')
}

const clearCrawlChaptersCache = () => {
  if (!crawlSelectedBook.value) {
    ElMessage.warning('未选中小说，无法清空章节缓存')
    return
  }
  const sourceKey = crawlSelectedBook.value.sourceKey || crawlSourceKey.value
  crawlCache.clearChapters(props.projectPublicId, sourceKey, crawlSelectedBook.value.dirid)
  resetCrawlChapterSlots()
  crawlImportSelectedRows.value = []
  crawlProgressText.value = '已清空本地章节缓存，可重新开始爬取'
  ElMessage.success(`已清空《${crawlSelectedBook.value.title}》的本地章节缓存`)
}

const writeCurrentSearchCache = () => {
  const sourceKey = crawlSourceKey.value
  const query = crawlSearchQuery.value.trim()
  if (!sourceKey || !query) return
  crawlCache.writeSearch(props.projectPublicId, sourceKey, query, crawlResults.value)
}

const crawlBookSourceKey = (book: CrawlSearchResult) => book.sourceKey || crawlSourceKey.value

const crawlBookIdentity = (book: CrawlSearchResult) => (
  `${crawlBookSourceKey(book)}:${book.dirid || book.id}`
)

const isSameCrawlBook = (left: CrawlSearchResult, right: CrawlSearchResult) => {
  if (crawlBookSourceKey(left) !== crawlBookSourceKey(right)) return false
  if (left.dirid && right.dirid && left.dirid === right.dirid) return true
  return left.id > 0 && right.id > 0 && left.id === right.id
}

const isSelectedCrawlBook = (book: CrawlSearchResult) => (
  Boolean(crawlSelectedBook.value && isSameCrawlBook(crawlSelectedBook.value, book))
)

const hasCrawlBookDetails = (book: CrawlSearchResult) => crawlDetailedBookKeys.value.has(crawlBookIdentity(book))

const markCrawlBookDetailsLoaded = (book: CrawlSearchResult) => {
  const nextKeys = new Set(crawlDetailedBookKeys.value)
  nextKeys.add(crawlBookIdentity(book))
  crawlDetailedBookKeys.value = nextKeys
}

const latestCrawlBook = (book: CrawlSearchResult) => {
  // 优先对象引用：用户点击哪张卡片就锁定哪张，避免 find 误命中前序同书项
  if (crawlResults.value.includes(book)) {
    return book
  }
  if (crawlSelectedBook.value && isSameCrawlBook(crawlSelectedBook.value, book)) {
    return crawlSelectedBook.value
  }
  return crawlResults.value.find((item) => isSameCrawlBook(item, book)) || book
}

// 同 sourceKey + dirid（或 id）的搜索记录合并为单条，保留各字段最佳值
const mergeCrawlSearchResults = (
  books: CrawlSearchResult[],
  fallbackSourceKey: string,
): CrawlSearchResult[] => {
  const merged: CrawlSearchResult[] = []
  for (const book of books) {
    const normalized = normalizeCrawlBook({
      ...book,
      sourceKey: book.sourceKey || fallbackSourceKey,
    })
    const existing = merged.find((item) => isSameCrawlBook(item, normalized))
    if (existing) {
      Object.assign(existing, mergeCrawlBook(existing, normalized, fallbackSourceKey))
      continue
    }
    merged.push(normalized)
  }
  return merged
}

const mergeCrawlBook = (
  base: CrawlSearchResult,
  incoming: CrawlSearchResult,
  fallbackSourceKey: string,
): CrawlSearchResult => {
  const pickText = (next: string, current: string) => next.trim() || current
  return normalizeCrawlBook({
    dirid: pickText(incoming.dirid, base.dirid),
    id: incoming.id > 0 ? incoming.id : base.id,
    full: pickText(incoming.full, base.full),
    title: pickText(incoming.title, base.title),
    author: pickText(incoming.author, base.author),
    cover: pickText(incoming.cover, base.cover),
    lastchapter: pickText(incoming.lastchapter, base.lastchapter),
    lastchapterid: incoming.lastchapterid > 0 ? incoming.lastchapterid : base.lastchapterid,
    lastupdate: pickText(incoming.lastupdate, base.lastupdate),
    sortname: pickText(incoming.sortname, base.sortname),
    intro: pickText(incoming.intro, base.intro),
    sourceKey: incoming.sourceKey || base.sourceKey || fallbackSourceKey,
  })
}

const normalizeCrawlBook = (book: CrawlSearchResult): CrawlSearchResult => {
  const diridAsNumber = Number.parseInt(book.dirid, 10)
  const chapterCountLooksLikeBookId = (
    book.lastchapterid > 0
    && (
      book.lastchapterid === book.id
      || (!Number.isNaN(diridAsNumber) && book.lastchapterid === diridAsNumber)
    )
  )
  return {
    ...book,
    lastchapterid: chapterCountLooksLikeBookId ? 0 : book.lastchapterid,
  }
}

const syncCrawlEndChapterFromBook = (book: CrawlSearchResult) => {
  if (
    !crawling.value
    && book.lastchapterid > 0
    && crawlEndChapter.value === DEFAULT_CRAWL_END_CHAPTER
  ) {
    crawlEndChapter.value = book.lastchapterid
  }
}

const updateCrawlBookInResults = (book: CrawlSearchResult, options: { select?: boolean } = {}) => {
  crawlResults.value = crawlResults.value.map((item) => (
    isSameCrawlBook(item, book) ? book : item
  ))
  const shouldSelect = options.select ?? isSelectedCrawlBook(book)
  if (shouldSelect) {
    crawlSelectedBook.value = book
    syncCrawlEndChapterFromBook(book)
  }
  writeCurrentSearchCache()
}

const fetchSelectedBookDetail = async (
  book: CrawlSearchResult,
  options: { fetchChapterCountIfMissing?: boolean } = {},
) => {
  if ((!book.dirid && !(book.id > 0)) || !crawlSourceKey.value) return
  const requestId = ++crawlBookDetailRequestId
  crawlBookDetailLoading.value = true
  try {
    const { data } = await fetchCrawlBookDetailApi(props.projectPublicId, {
      sourceKey: book.sourceKey || crawlSourceKey.value,
      book,
    })
    if (!crawlResults.value.some((item) => isSameCrawlBook(item, book))) return
    const nextBook = mergeCrawlBook(latestCrawlBook(book), data.book, crawlSourceKey.value)
    const shouldUpdateSelection = isSelectedCrawlBook(book)
    markCrawlBookDetailsLoaded(nextBook)
    updateCrawlBookInResults(nextBook, { select: shouldUpdateSelection })
    if (options.fetchChapterCountIfMissing && shouldUpdateSelection && nextBook.lastchapterid <= 0) {
      void fetchSelectedBookChapterCount(nextBook)
    }
  } catch (error) {
    if (requestId !== crawlBookDetailRequestId) return
    if (options.fetchChapterCountIfMissing && isSelectedCrawlBook(book) && latestCrawlBook(book).lastchapterid <= 0) {
      void fetchSelectedBookChapterCount(book)
    }
    ElMessage.warning(`详情获取失败：${getErrorMessage(error)}`)
  } finally {
    if (requestId === crawlBookDetailRequestId) {
      crawlBookDetailLoading.value = false
    }
  }
}

const fetchSelectedBookChapterCount = async (book: CrawlSearchResult) => {
  if ((!book.dirid && !(book.id > 0)) || !crawlSourceKey.value) return
  const requestId = ++crawlBookCountRequestId
  crawlBookCountLoading.value = true
  try {
    const { data } = await fetchCrawlBookChapterCountApi(props.projectPublicId, {
      sourceKey: book.sourceKey || crawlSourceKey.value,
      book,
    })
    if (!crawlResults.value.some((item) => isSameCrawlBook(item, book))) return
    const baseBook = latestCrawlBook(book)
    const nextBook = {
      ...mergeCrawlBook(baseBook, data.book, crawlSourceKey.value),
      lastchapterid: data.lastchapterid > 0 ? data.lastchapterid : baseBook.lastchapterid,
    }
    const shouldUpdateSelection = isSelectedCrawlBook(book)
    updateCrawlBookInResults(nextBook, { select: shouldUpdateSelection })
  } catch (error) {
    if (requestId !== crawlBookCountRequestId) return
    ElMessage.warning(`章节数获取失败：${getErrorMessage(error)}`)
  } finally {
    if (requestId === crawlBookCountRequestId) {
      crawlBookCountLoading.value = false
    }
  }
}

const selectCrawlBook = (book: CrawlSearchResult) => {
  const isSwitchingBook = Boolean(crawlSelectedBook.value && !isSameCrawlBook(crawlSelectedBook.value, book))
  const nextBook = latestCrawlBook(book)
  crawlSelectedBook.value = nextBook
  crawlStartChapter.value = 1
  crawlEndChapter.value = DEFAULT_CRAWL_END_CHAPTER
  if (isSwitchingBook) {
    resetCrawlChapterSlots()
    crawlImportSelectedRows.value = []
    crawlProgressText.value = ''
    crawlAborted.value = false
    crawlPreviewVisible.value = false
    crawlPreviewChapter.value = null
  }
  const detailsLoaded = hasCrawlBookDetails(nextBook)
  if (detailsLoaded) {
    crawlBookDetailRequestId += 1
    crawlBookDetailLoading.value = false
  } else {
    void fetchSelectedBookDetail(nextBook, { fetchChapterCountIfMissing: true })
  }
  if (nextBook.lastchapterid > 0) {
    crawlBookCountRequestId += 1
    crawlBookCountLoading.value = false
    syncCrawlEndChapterFromBook(nextBook)
  } else if (detailsLoaded) {
    void fetchSelectedBookChapterCount(nextBook)
  } else {
    crawlBookCountRequestId += 1
    crawlBookCountLoading.value = false
  }
}

const goCrawlConfig = async () => {
  if (!crawlSelectedBook.value) {
    ElMessage.warning('请先选中一本要爬取的小说')
    return
  }
  if (crawlSelectedBook.value.lastchapterid <= 0) {
    await fetchSelectedBookChapterCount(crawlSelectedBook.value)
  }
  crawlStep.value = 2
}

const validateCrawlBeforeRequest = () => {
  if (!crawlSelectedBook.value) return
  if (!ensureProjectReady()) return
  if (!crawlSourceKey.value) {
    ElMessage.warning('请先选择爬取来源')
    return
  }
  if (crawlEndChapter.value < crawlStartChapter.value) {
    ElMessage.error('结束章节不能小于起始章节')
    return
  }
  const max = crawlSelectedBook.value.lastchapterid
  if (max > 0 && crawlEndChapter.value > max) {
    ElMessage.error(`结束章节超过该书总章节数（${max}）`)
    return
  }
  return true
}

const startCrawl = async () => {
  if (!validateCrawlBeforeRequest()) return
  await requestCrawlRange(crawlStartChapter.value, { append: false })
}

const continueCrawl = async () => {
  if (!validateCrawlBeforeRequest()) return
  if (!canContinueCrawl.value) {
    ElMessage.info('当前章节范围已爬取完成')
    return
  }
  await requestCrawlRange(nextCrawlStartChapter.value, { append: true })
}

const requestCrawlRange = async (
  startChapter: number,
  options: { append: boolean },
) => {
  if (!crawlSelectedBook.value) return
  crawling.value = true
  crawlAborted.value = false
  if (!options.append) {
    rebuildCrawlChapterSlots()
    crawlImportSelectedRows.value = []
  } else {
    ensureCrawlChapterSlots()
  }
  const controller = new AbortController()
  crawlAbortController = controller

  const book = {
    ...crawlSelectedBook.value,
    sourceKey: crawlSelectedBook.value.sourceKey || crawlSourceKey.value,
  }
  const overallTotal = crawlTargetTotal.value
  const endChapter = crawlEndChapter.value
  const fetchedChapters: CrawlChapterDraft[] = []
  const previousCount = crawledChapterCount.value

  const cachedChapters = crawlCache.readChapters(
    props.projectPublicId,
    book.sourceKey,
    book.dirid,
    startChapter,
    endChapter,
  )
  if (cachedChapters && cachedChapters.length > 0) {
    for (const chapter of cachedChapters) {
      upsertCrawledChapter(normalizeCrawlDraft(chapter, chapter.key - crawlStartChapter.value, book))
    }
    crawlProgressText.value = `已使用本地缓存，共 ${crawledChapterCount.value}/${overallTotal} 章`
    ElMessage.success(`本段命中本地缓存（共 ${cachedChapters.length} 章），点「清空缓存」可重新爬取`)
    crawling.value = false
    if (crawlAbortController === controller) {
      crawlAbortController = null
    }
    return
  }

  crawlProgressText.value = options.append
    ? `正在从第 ${startChapter} 章继续连接服务端爬取通道…`
    : '正在连接服务端爬取通道…'
  try {
    const response = await fetchWithAuthRetry(crawlChaptersStreamUrl(props.projectPublicId), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        sourceKey: crawlSourceKey.value,
        book,
        startChapter,
        endChapter,
      }),
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new Error(await readFetchError(response))
    }
    if (!response.body) {
      throw new Error('当前浏览器不支持读取爬取进度流')
    }
    await readCrawlStream(response.body, book, {
      overallTotal,
      previousCount,
      requestStart: startChapter,
      requestEnd: endChapter,
      fetchedChapters,
    })
    if (crawlAborted.value) {
      crawlProgressText.value = `已取消，共爬取 ${crawledChapterCount.value}/${overallTotal} 章`
      return
    }
    crawlProgressText.value = crawlCompleted.value
      ? `爬取完成，共 ${crawledChapterCount.value}/${overallTotal} 章`
      : `本次爬取结束，已获取 ${crawledChapterCount.value}/${overallTotal} 章，可继续爬取`
    if (fetchedChapters.length > 0) {
      crawlCache.writeChapters(
        props.projectPublicId,
        book.sourceKey,
        book.dirid,
        startChapter,
        endChapter,
        fetchedChapters,
      )
    }
  } catch (error) {
    if (isAbortError(error)) {
      crawlProgressText.value = `已取消，共爬取 ${crawledChapterCount.value}/${overallTotal} 章`
      return
    }
    crawlAborted.value = true
    crawlProgressText.value = `爬取失败，已获取 ${crawledChapterCount.value}/${overallTotal} 章`
    ElMessage.error(`爬取失败：${getErrorMessage(error)}`)
  } finally {
    crawling.value = false
    if (crawlAbortController === controller) {
      crawlAbortController = null
    }
  }
}

const cancelCrawl = () => {
  if (!crawling.value) return
  crawlAborted.value = true
  crawlAbortController?.abort()
  crawlAbortController = null
  crawling.value = false
  crawlProgressText.value = `已取消，共爬取 ${crawledChapterCount.value}/${crawlTargetTotal.value} 章`
  ElMessage.info('已取消爬取')
}

interface CrawlProgressContext {
  overallTotal: number
  previousCount: number
  requestStart: number
  requestEnd: number
  fetchedChapters: CrawlChapterDraft[]
}

const readCrawlStream = async (
  body: ReadableStream<Uint8Array>,
  book: CrawlSearchResult,
  progress: CrawlProgressContext,
) => {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      handleCrawlStreamLine(line, book, progress)
    }
  }

  buffer += decoder.decode()
  if (buffer.trim()) {
    handleCrawlStreamLine(buffer, book, progress)
  }
}

const handleCrawlStreamLine = (
  line: string,
  book: CrawlSearchResult,
  progress: CrawlProgressContext,
) => {
  const trimmed = line.trim()
  if (!trimmed) return
  const event = JSON.parse(trimmed) as CrawlChapterStreamEvent
  if (event.type === 'start') {
    crawlProgressText.value = progress.previousCount > 0
      ? `继续爬取 ${progress.requestStart}-${progress.requestEnd}，已获取 ${progress.previousCount}/${progress.overallTotal} 章`
      : `开始爬取，共 ${progress.overallTotal} 章`
    return
  }
  if (event.type === 'chapter') {
    const draft = normalizeCrawlDraft(event.chapter, crawledChapterCount.value, book)
    if (upsertCrawledChapter(draft)) {
      progress.fetchedChapters.push(draft)
    }
    crawlProgressText.value = `正在爬取 ${crawledChapterCount.value}/${progress.overallTotal}：${draft.chaptername}`
    return
  }
  if (event.type === 'done') {
    crawlProgressText.value = `本段完成，已获取 ${crawledChapterCount.value}/${progress.overallTotal} 章`
    return
  }
  if (event.type === 'error') {
    throw new Error(event.detail || '服务端爬取失败')
  }
}

const normalizeCrawlDraft = (
  draft: CrawlChapterDraft,
  index: number,
  book: CrawlSearchResult,
): CrawlChapterDraft => ({
  ...draft,
  key: draft.key || crawlStartChapter.value + index,
  novelDirid: draft.novelDirid || book.dirid,
  event: draft.event || '',
  eventState: draft.eventState ?? 0,
  errorReason: draft.errorReason || null,
})

const upsertCrawledChapter = (draft: CrawlChapterDraft) => {
  ensureCrawlChapterSlots()
  const index = getCrawlSlotIndex(draft.key)
  if (index < 0 || index >= crawlChapterSlots.value.length) return false
  const hadChapter = Boolean(crawlChapterSlots.value[index])
  crawlChapterSlots.value[index] = draft
  if (!hadChapter) {
    crawledChapterCount.value += 1
  }
  rememberRecentCrawledChapter(draft)
  return true
}

const readFetchError = async (response: Response) => {
  try {
    const data = await response.json()
    return formatErrorDetail(data?.detail) || formatErrorDetail(data?.message) || response.statusText
  } catch {
    return response.statusText || `HTTP ${response.status}`
  }
}

const isAbortError = (error: unknown) => (
  error instanceof DOMException && error.name === 'AbortError'
)

const goCrawlPreview = () => {
  if (crawling.value) {
    ElMessage.warning('请先等待爬取完成或取消')
    return
  }
  if (crawledChapterCount.value === 0) {
    ElMessage.warning('暂无可预览的章节，请先开始爬取')
    return
  }
  crawlStep.value = 3
  nextTick(() => {
    crawlImportTableRef.value?.toggleAllSelection?.()
  })
}

const onCrawlSelectionChange = (rows: CrawlChapterDraft[]) => {
  crawlImportSelectedRows.value = rows
}

const unescapeCrawlReplacement = (str: string) => (
  str.replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\r/g, '\r')
)

const compileEnabledCrawlFilterRules = (): CompiledCrawlFilterRule[] | null => {
  const enabledRules = crawlFilterRules.value.filter((rule) => rule.enabled)
  if (enabledRules.length === 0) {
    ElMessage.warning('请先勾选至少一条过滤规则')
    return null
  }

  const compiled: CompiledCrawlFilterRule[] = []
  for (const rule of enabledRules) {
    try {
      compiled.push({ rule, regex: new RegExp(rule.pattern, rule.flags) })
    } catch (error) {
      ElMessage.error(`规则「${rule.name}」执行失败：${(error as Error).message}`)
      return null
    }
  }
  return compiled
}

const normalizeFilteredCrawlText = (content: string) => (
  content
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .join('\n\n')
    .trim()
)

const applyCompiledCrawlFilters = (
  content: string,
  compiledRules: CompiledCrawlFilterRule[],
) => {
  let result = content.replace(/\r\n?/g, '\n')
  for (const { rule, regex } of compiledRules) {
    result = result.replace(regex, unescapeCrawlReplacement(rule.replacement))
  }
  return normalizeFilteredCrawlText(result)
}

const updateCrawlChapterText = (row: CrawlChapterDraft, txt: string) => {
  row.txt = txt
  row.md5 = ''
  row.event = ''
  row.eventState = 0
  row.errorReason = null
}

const filterCrawlChapter = (row: CrawlChapterDraft) => {
  const before = row.txt.length
  const compiledRules = compileEnabledCrawlFilterRules()
  if (!compiledRules) return
  const filtered = applyCompiledCrawlFilters(row.txt, compiledRules)
  if (!filtered) {
    ElMessage.warning('过滤后正文为空，已保留原文')
    return
  }
  if (filtered === row.txt) {
    ElMessage.info('当前章节未匹配到可过滤内容')
    return
  }
  updateCrawlChapterText(row, filtered)
  ElMessage.success(`已过滤《${row.chaptername}》：${before} → ${filtered.length} 字`)
}

const applyCrawlFilterToSelected = () => {
  if (crawlImportSelectedRows.value.length === 0) {
    ElMessage.warning('请先选择要过滤的章节')
    return
  }
  const compiledRules = compileEnabledCrawlFilterRules()
  if (!compiledRules) return

  let changed = 0
  let emptied = 0
  for (const row of crawlImportSelectedRows.value) {
    const filtered = applyCompiledCrawlFilters(row.txt, compiledRules)
    if (!filtered) {
      emptied += 1
      continue
    }
    if (filtered === row.txt) continue
    updateCrawlChapterText(row, filtered)
    changed += 1
  }

  if (changed > 0) {
    ElMessage.success(`已过滤 ${changed} 章${emptied ? `，${emptied} 章过滤后为空已跳过` : ''}`)
  } else if (emptied > 0) {
    ElMessage.warning(`${emptied} 章过滤后为空，已保留原文`)
  } else {
    ElMessage.info('已选章节未匹配到可过滤内容')
  }
  crawlFilterPopoverVisible.value = false
}

const addCrawlCustomFilterRule = () => {
  const pattern = crawlCustomRulePattern.value.trim()
  if (!pattern) {
    ElMessage.warning('请输入匹配规则')
    return
  }
  const flags = Array.from(new Set(crawlCustomRuleFlagsList.value)).join('') || 'g'
  try {
    new RegExp(pattern, flags)
  } catch (error) {
    ElMessage.error(`正则无效：${(error as Error).message}`)
    return
  }

  crawlFilterRules.value.push({
    id: `cf-${Date.now()}`,
    name: crawlCustomRuleName.value.trim() || `自定义规则 #${crawlFilterRules.value.length + 1}`,
    pattern,
    flags,
    replacement: crawlCustomRuleReplacement.value,
    enabled: true,
    builtin: false,
  })
  crawlCustomRuleName.value = ''
  crawlCustomRulePattern.value = ''
  crawlCustomRuleFlagsList.value = ['g']
  crawlCustomRuleReplacement.value = ''
  ElMessage.success('已添加自定义规则')
}

const removeCrawlFilterRule = (id: string) => {
  crawlFilterRules.value = crawlFilterRules.value.filter((rule) => rule.id !== id)
}

const openCrawlChapterPreview = (row: CrawlChapterDraft) => {
  crawlPreviewChapter.value = row
  crawlPreviewVisible.value = true
}

const filterPreviewChapter = () => {
  if (!crawlPreviewChapter.value) return
  filterCrawlChapter(crawlPreviewChapter.value)
}

const cleanPreviewChapterEvent = () => {
  if (!crawlPreviewChapter.value) return
  cleanCrawlChapterEvent(crawlPreviewChapter.value)
}

const splitCrawlParagraphs = (raw: string) => (
  (raw || '')
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
)

const cleanCrawlChapterEvent = (row: CrawlChapterDraft) => {
  const content = row.txt.trim()
  if (content.length < 80) {
    row.event = ''
    row.eventState = -1
    row.errorReason = '正文字数过少，无法提取有效事件'
    ElMessage.warning(row.errorReason)
    return
  }

  row.event = [
    '## 主要事件',
    `- 由《${row.chaptername}》预览清洗生成`,
    `- 正文共 ${content.length} 字`,
    '',
    '## 关键人物',
    '- 待入库后继续精修',
    '',
    '## 场景',
    '- 自动识别中...',
  ].join('\n')
  row.eventState = 1
  row.errorReason = null
  ElMessage.success(`《${row.chaptername}》事件已生成`)
}

const removeCrawlChapter = (row: CrawlChapterDraft) => {
  const index = getCrawlSlotIndex(row.key)
  if (index >= 0 && index < crawlChapterSlots.value.length && crawlChapterSlots.value[index]) {
    crawlChapterSlots.value[index] = null
    crawledChapterCount.value = Math.max(crawledChapterCount.value - 1, 0)
  }
  recentCrawledChapters.value = recentCrawledChapters.value.filter((item) => item.key !== row.key)
  crawlImportSelectedRows.value = crawlImportSelectedRows.value.filter((item) => item.key !== row.key)
  ElMessage.info(`已移除《${row.chaptername}》`)
}

const crawlEventStateLabel = (state: EventState = 0) => {
  if (state === 1) return '已清洗'
  if (state === -1) return '失败'
  return '未清洗'
}

const crawlEventStateKey = (state: EventState = 0) => {
  if (state === 1) return 'success'
  if (state === -1) return 'error'
  return 'pending'
}

const getCrawlChapterLengthWarning = (draft: CrawlChapterDraft) => {
  const length = draft.txt.length
  if (length < CHAPTER_SHORT_WARNING_LENGTH) {
    return `本章字数 ${length}，低于 ${CHAPTER_SHORT_WARNING_LENGTH} 字`
  }
  if (length > CHAPTER_LONG_WARNING_LENGTH) {
    return `本章字数 ${length}，高于 ${CHAPTER_LONG_WARNING_LENGTH} 字`
  }
  return ''
}

const hasCrawlChapterLengthWarning = (draft: CrawlChapterDraft) => Boolean(getCrawlChapterLengthWarning(draft))

const sortCrawlByTextLength = (a: CrawlChapterDraft, b: CrawlChapterDraft) => a.txt.length - b.txt.length

const sortCrawlByEventState = (a: CrawlChapterDraft, b: CrawlChapterDraft) => a.eventState - b.eventState

const submitCrawlImport = async () => {
  if (crawlImportSelectedRows.value.length === 0) {
    ElMessage.warning('请选择要导入的章节')
    return
  }
  if (!crawlSelectedBook.value) {
    ElMessage.warning('当前没有选中的小说，无法导入')
    return
  }
  crawlSubmitting.value = true
  await new Promise((resolve) => setTimeout(resolve, 200))
  emit('submit', [...crawlImportSelectedRows.value], crawlSelectedBook.value)
  emit('update:modelValue', false)
  crawlSubmitting.value = false
}

// ============== 来源管理 ==============

type SourceMode = 'list' | 'create' | 'edit' | 'duplicate'

const isSuperuser = ref(false)
const duplicateForm = ref<{ originKey: string; originName: string; newKey: string; newName: string }>({
  originKey: '',
  originName: '',
  newKey: '',
  newName: '',
})

const sourceManageVisible = ref(false)
const sourceMode = ref<SourceMode>('list')
const sourceForm = ref<CrawlSource>(createEmptySource())
const sourceEditingKey = ref('')

const isRuleSource = computed(() => sourceForm.value.sourceType === 'rule')

const openSourceManager = () => {
  sourceMode.value = 'list'
  sourceForm.value = createEmptySource()
  sourceEditingKey.value = ''
  sourceManageVisible.value = true
  void loadCrawlSources()
  void refreshSuperuserFlag()
}

const refreshSuperuserFlag = async () => {
  try {
    const { data } = await getCurrentUserApi()
    isSuperuser.value = Boolean(data?.is_superuser)
  } catch {
    isSuperuser.value = false
  }
}

const openDuplicateDialog = (source: CrawlSource) => {
  duplicateForm.value = {
    originKey: source.key,
    originName: source.name,
    newKey: `${source.key}_copy`,
    newName: `${source.name} 副本`,
  }
  sourceMode.value = 'duplicate'
}

const submitDuplicateForm = async () => {
  const payload = duplicateForm.value
  const newKey = payload.newKey.trim()
  const newName = payload.newName.trim()
  if (!newKey) {
    ElMessage.warning('请输入新的来源标识')
    return
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(newKey)) {
    ElMessage.warning('来源标识只能包含字母、数字、下划线、短横线')
    return
  }
  if (!newName) {
    ElMessage.warning('请输入新的来源名称')
    return
  }
  if (!ensureProjectReady()) return
  try {
    const { data } = await duplicateCrawlSourceApi(props.projectPublicId, payload.originKey, {
      newKey,
      name: newName,
    })
    await loadCrawlSources(data.key)
    ElMessage.success('已复制为自定义来源')
    const created = crawlSources.value.find((item) => item.key === data.key)
    if (created) {
      startEditSource(created)
    } else {
      sourceMode.value = 'list'
    }
  } catch (err) {
    ElMessage.error(`复制失败：${getErrorMessage(err)}`)
  }
}

const startCreateSource = () => {
  sourceForm.value = { ...createEmptySource(), builtin: false }
  sourceEditingKey.value = ''
  sourceMode.value = 'create'
}

const startEditSource = (source: CrawlSource) => {
  sourceForm.value = normalizeCrawlSource(source)
  sourceEditingKey.value = source.key
  sourceMode.value = 'edit'
}

const backToSourceList = () => {
  sourceMode.value = 'list'
  sourceForm.value = createEmptySource()
  sourceEditingKey.value = ''
}

const removeSource = async (source: CrawlSource) => {
  if (!ensureProjectReady()) return
  try {
    await ElMessageBox.confirm(
      `确定删除来源「${source.name}」？此操作不可恢复。`,
      '删除来源',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        customClass: 'novel-dark-messagebox',
      },
    )
    await deleteCrawlSourceApi(props.projectPublicId, source.key)
    await loadCrawlSources(crawlSourceKey.value === source.key ? '' : crawlSourceKey.value)
    ElMessage.success('来源已删除')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(`删除失败：${getErrorMessage(err)}`)
  }
}

const saveSourceForm = async () => {
  const form = sourceForm.value
  if (!form.key.trim()) {
    ElMessage.warning('请填写来源标识（key）')
    return
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(form.key)) {
    ElMessage.warning('来源标识只能包含字母、数字、下划线、短横线')
    return
  }
  if (!form.name.trim()) {
    ElMessage.warning('请填写来源名称')
    return
  }
  if (
    form.searchUrlTemplate.trim()
    && !/\{(?:q|keyword|sort)\}/.test(`${form.searchUrlTemplate}\n${form.apiSearchBody}`)
  ) {
    ElMessage.warning('搜索 URL 或 Body 需包含 {q}、{keyword} 或 {sort} 占位符')
    return
  }
  const specError = validateRequestSpecJson(form)
  if (specError) {
    ElMessage.warning(specError)
    return
  }
  if (!ensureProjectReady()) return
  try {
    if (sourceMode.value === 'create') {
      await createCrawlSourceApi(props.projectPublicId, buildSourceCreatePayload(form))
      await loadCrawlSources(form.key.trim())
      ElMessage.success('已添加来源')
    } else if (sourceMode.value === 'edit') {
      await updateCrawlSourceApi(props.projectPublicId, sourceEditingKey.value, buildSourceUpdatePayload(form))
      await loadCrawlSources(sourceEditingKey.value)
      ElMessage.success('已更新来源')
    }
    backToSourceList()
  } catch (error) {
    ElMessage.error(`保存失败：${getErrorMessage(error)}`)
  }
}

const aiAnalyzeSource = async () => {
  if (!ensureProjectReady()) return
  const url = sourceForm.value.apiBookUrl.trim() || sourceForm.value.searchUrlTemplate.trim() || sourceForm.value.baseUrl.trim()
  if (!url) {
    ElMessage.warning('请先填写站点根 URL、搜索 URL 模板或详情 API URL 模板')
    return
  }
  try {
    const { data } = await analyzeCrawlSourceApi(props.projectPublicId, {
      url,
      sourceType: 'api',
    })
    sourceForm.value = normalizeCrawlSource({
      ...data.source,
      builtin: false,
    })
    ElMessage.info(data.message || 'AI 分析入口已调用，请继续手动补全接口配置')
  } catch (error) {
    ElMessage.error(`AI 分析失败：${getErrorMessage(error)}`)
  }
}

const buildSourceCreatePayload = (source: CrawlSource): CrawlSourcePayload => {
  const payload = buildSourceUpdatePayload(source)
  return {
    ...payload,
    key: source.key.trim(),
    builtin: false,
    projectPublicId: props.projectPublicId,
  }
}

const buildSourceUpdatePayload = (source: CrawlSource): Omit<CrawlSourcePayload, 'key' | 'projectPublicId' | 'builtin'> => ({
  name: source.name.trim(),
  baseUrl: source.baseUrl.trim(),
  desc: source.desc.trim(),
  sourceType: source.sourceType,
  searchUrlTemplate: source.searchUrlTemplate.trim(),
  apiBookUrl: source.apiBookUrl.trim(),
  apiBookTitlePath: source.apiBookTitlePath.trim(),
  apiBookAuthorPath: source.apiBookAuthorPath.trim(),
  apiBookIntroPath: source.apiBookIntroPath.trim(),
  apiBookLastChapterPath: source.apiBookLastChapterPath.trim(),
  apiBookLastChapterIdPath: source.apiBookLastChapterIdPath.trim(),
  apiBookLastUpdatePath: source.apiBookLastUpdatePath.trim(),
  apiBookCoverPath: source.apiBookCoverPath.trim(),
  apiBookCategoryPath: source.apiBookCategoryPath.trim(),
  apiBookUpdateStatusPath: source.apiBookUpdateStatusPath.trim(),
  apiBookIdPath: source.apiBookIdPath.trim(),
  apiChapterListUrl: source.apiChapterListUrl.trim(),
  apiChapterListNamePath: source.apiChapterListNamePath.trim(),
  apiChapterListIdPath: source.apiChapterListIdPath.trim(),
  apiChapterListContentPath: source.apiChapterListContentPath.trim(),
  apiChapterListTimePath: source.apiChapterListTimePath.trim(),
  apiChapterListMd5Path: source.apiChapterListMd5Path.trim(),
  apiChapterUrl: source.apiChapterUrl.trim(),
  apiChapterNamePath: source.apiChapterNamePath.trim(),
  apiChapterContentPath: source.apiChapterContentPath.trim(),
  apiChapterTimePath: source.apiChapterTimePath.trim(),
  apiChapterMd5Path: source.apiChapterMd5Path.trim(),
  apiSearchMethod: normalizeHttpMethod(source.apiSearchMethod),
  apiSearchHeaders: source.apiSearchHeaders.trim(),
  apiSearchBody: needsRequestBody(source.apiSearchMethod) ? source.apiSearchBody.trim() : '',
  apiSearchBookUrlPath: source.apiSearchBookUrlPath.trim(),
  apiSearchBookIdPath: source.apiSearchBookIdPath.trim(),
  apiSearchBookTitlePath: source.apiSearchBookTitlePath.trim(),
  apiSearchBookAuthorPath: source.apiSearchBookAuthorPath.trim(),
  apiSearchBookIntroPath: source.apiSearchBookIntroPath.trim(),
  apiSearchBookCoverPath: source.apiSearchBookCoverPath.trim(),
  apiSearchBookCategoryPath: source.apiSearchBookCategoryPath.trim(),
  apiSearchBookUpdateStatusPath: source.apiSearchBookUpdateStatusPath.trim(),
  apiSearchBookLastChapterPath: source.apiSearchBookLastChapterPath.trim(),
  apiSearchBookLastChapterIdPath: source.apiSearchBookLastChapterIdPath.trim(),
  apiSearchBookLastUpdatePath: source.apiSearchBookLastUpdatePath.trim(),
  apiBookMethod: normalizeHttpMethod(source.apiBookMethod),
  apiBookHeaders: source.apiBookHeaders.trim(),
  apiBookBody: needsRequestBody(source.apiBookMethod) ? source.apiBookBody.trim() : '',
  apiChapterListMethod: normalizeHttpMethod(source.apiChapterListMethod),
  apiChapterListHeaders: source.apiChapterListHeaders.trim(),
  apiChapterListBody: needsRequestBody(source.apiChapterListMethod) ? source.apiChapterListBody.trim() : '',
  apiChapterMethod: normalizeHttpMethod(source.apiChapterMethod),
  apiChapterHeaders: source.apiChapterHeaders.trim(),
  apiChapterBody: needsRequestBody(source.apiChapterMethod) ? source.apiChapterBody.trim() : '',
})

const normalizeHttpMethod = (value: CrawlHttpMethod | string | undefined): CrawlHttpMethod => {
  const upper = (value ?? '').toString().trim().toUpperCase()
  return (CRAWL_HTTP_METHODS as ReadonlyArray<string>).includes(upper) ? (upper as CrawlHttpMethod) : 'GET'
}

const validateRequestSpecJson = (source: CrawlSource): string => {
  const checks: Array<{ label: string; value: string; expectObject: boolean }> = [
    { label: '搜索请求头', value: source.apiSearchHeaders.trim(), expectObject: true },
    { label: '详情请求头', value: source.apiBookHeaders.trim(), expectObject: true },
    { label: '章节列表请求头', value: source.apiChapterListHeaders.trim(), expectObject: true },
    { label: '章节请求头', value: source.apiChapterHeaders.trim(), expectObject: true },
  ]
  if (needsRequestBody(source.apiSearchMethod)) {
    checks.push({ label: '搜索请求体', value: source.apiSearchBody.trim(), expectObject: false })
  }
  if (needsRequestBody(source.apiBookMethod)) {
    checks.push({ label: '详情请求体', value: source.apiBookBody.trim(), expectObject: false })
  }
  if (needsRequestBody(source.apiChapterListMethod)) {
    checks.push({ label: '章节列表请求体', value: source.apiChapterListBody.trim(), expectObject: false })
  }
  if (needsRequestBody(source.apiChapterMethod)) {
    checks.push({ label: '章节正文请求体', value: source.apiChapterBody.trim(), expectObject: false })
  }
  for (const item of checks) {
    if (!item.value) continue
    let parsed: unknown
    try {
      parsed = JSON.parse(item.value)
    } catch (error) {
      return `${item.label} 不是合法的 JSON：${(error as Error).message}`
    }
    if (item.expectObject) {
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        return `${item.label} 必须是 JSON 对象`
      }
    }
  }
  return ''
}

const getErrorMessage = (error: unknown) => {
  const axiosError = isRecord(error) ? (error as unknown as AxiosError<{ detail?: unknown; message?: unknown }>) : null
  const responseMessage =
    formatErrorDetail(axiosError?.response?.data?.detail) ||
    formatErrorDetail(axiosError?.response?.data?.message)
  if (responseMessage) return responseMessage
  if (error instanceof Error && error.message) return error.message
  return formatErrorDetail(error) || '请求失败'
}

const formatErrorDetail = (detail: unknown): string => {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(formatErrorDetail).filter(Boolean).join('；')
  }
  if (isRecord(detail)) {
    const record = detail as Record<string, unknown>
    const message = formatErrorDetail(record.msg) || formatErrorDetail(record.message) || formatErrorDetail(record.detail)
    const location = Array.isArray(record.loc) ? record.loc.map(String).join('.') : ''
    if (message) return location ? `${location}: ${message}` : message
    try {
      return JSON.stringify(detail)
    } catch {
      return String(detail)
    }
  }
  return String(detail)
}

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null
)

watch([crawlStartChapter, crawlEndChapter], () => {
  if (crawling.value || crawlChapterSlots.value.length === 0) return
  rebuildCrawlChapterSlots(crawledChapters.value)
  crawlImportSelectedRows.value = crawlImportSelectedRows.value.filter(
    (item) => item.key >= crawlStartChapter.value && item.key <= crawlEndChapter.value,
  )
})

watch(() => props.modelValue, (visible) => {
  if (visible) {
    void loadCrawlSources()
  }
})

watch(() => props.projectPublicId, () => {
  crawlSources.value = []
  resetCrawlState()
  if (props.modelValue) {
    void loadCrawlSources()
  }
})
</script>

<style>
/* 小说爬取对话框 */
.novel-crawl-dialog {
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 24px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.novel-crawl-dialog .el-dialog__header {
  margin: 0;
  padding: 11px 14px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-crawl-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.novel-crawl-dialog .el-dialog__headerbtn {
  top: 16px;
  right: 20px;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
}

.novel-crawl-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
  font-size: 20px;
}

.novel-crawl-dialog .el-dialog__headerbtn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.18);
}

.novel-crawl-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #ffffff;
}

.novel-crawl-dialog .el-dialog__body {
  padding: 11px 14px 4px;
  color: #b8c2cc;
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-crawl-dialog .el-dialog__body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.novel-crawl-dialog .el-dialog__body::-webkit-scrollbar-track {
  background: transparent;
}

.novel-crawl-dialog .el-dialog__body::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.novel-crawl-dialog .el-dialog__body::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.novel-crawl-dialog .el-dialog__footer {
  padding: 8px 14px 11px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.01);
}

.novel-crawl-dialog .import-steps {
  --crawl-step-icon-radius: 12px;
  padding: 4px 12px 18px;
}

.novel-crawl-dialog .import-steps .el-step__title {
  color: #8b949e;
  font-size: 13px;
  font-weight: 500;
}

.novel-crawl-dialog .import-steps .el-step__head.is-process .el-step__icon,
.novel-crawl-dialog .import-steps .el-step__head.is-finish .el-step__icon {
  background-color: rgba(37, 99, 235, 0.18);
  border-color: rgba(37, 99, 235, 0.55);
  color: #93c5fd;
}

.novel-crawl-dialog .import-steps .el-step__head.is-success .el-step__icon {
  background-color: rgba(34, 197, 94, 0.16);
  border-color: rgba(34, 197, 94, 0.55);
  color: #86efac;
}

.novel-crawl-dialog .import-steps .el-step__title.is-process,
.novel-crawl-dialog .import-steps .el-step__title.is-success {
  color: #e6edf3;
  font-weight: 600;
}

.novel-crawl-dialog .import-steps .el-step__line {
  left: calc(50% + var(--crawl-step-icon-radius));
  right: calc(-50% + var(--crawl-step-icon-radius));
  background-color: rgba(255, 255, 255, 0.08);
}

.novel-crawl-dialog .crawl-step {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 6px;
}

.novel-crawl-dialog .crawl-search {
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.025);
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.novel-crawl-dialog .crawl-search:focus-within {
  border-color: rgba(96, 165, 250, 0.35);
  background: rgba(37, 99, 235, 0.05);
}

.novel-crawl-dialog .crawl-search__row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.novel-crawl-dialog .crawl-search__label {
  font-size: 12px;
  font-weight: 600;
  color: #c5cdd6;
  flex-shrink: 0;
  width: 40px;
}

.novel-crawl-dialog .crawl-search__source {
  width: 200px;
  flex-shrink: 0;
}

.novel-crawl-dialog .crawl-search__keyword {
  flex: 1;
  min-width: 240px;
}

.novel-crawl-dialog .crawl-search__hint {
  margin: 0;
  font-size: 12px;
  color: #6e7681;
}

.novel-crawl-dialog .el-input__wrapper,
.novel-crawl-dialog .el-select__wrapper,
.novel-crawl-dialog .el-input-number .el-input__wrapper {
  min-height: 38px;
  padding: 0 14px;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border-radius: 10px;
  color: #e6edf3;
  font-size: 14px;
  transition: background-color 0.18s ease, box-shadow 0.18s ease;
}

.novel-crawl-dialog .el-input__wrapper:hover,
.novel-crawl-dialog .el-select__wrapper:hover,
.novel-crawl-dialog .el-input-number .el-input__wrapper:hover {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.novel-crawl-dialog .el-input__wrapper.is-focus,
.novel-crawl-dialog .el-select__wrapper.is-focused,
.novel-crawl-dialog .el-input-number .el-input__wrapper.is-focus {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.novel-crawl-dialog .el-input__inner,
.novel-crawl-dialog .el-select__selected-item,
.novel-crawl-dialog .el-input-number .el-input__inner {
  color: #e6edf3;
}

.novel-crawl-dialog .el-input__inner::placeholder,
.novel-crawl-dialog .el-select__placeholder {
  color: #7e8893;
}

.novel-crawl-dialog .el-input-number__decrease,
.novel-crawl-dialog .el-input-number__increase {
  color: #8b949e;
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.08);
}

.novel-crawl-dialog .el-input-number__decrease:hover,
.novel-crawl-dialog .el-input-number__increase:hover {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.12);
}

.novel-crawl-dialog .crawl-source-opt {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.novel-crawl-dialog .crawl-source-opt__name {
  font-size: 13px;
  font-weight: 600;
}

.novel-crawl-dialog .crawl-source-opt__desc {
  font-size: 11px;
  color: #6e7681;
}

.novel-crawl-dialog .crawl-results {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  min-height: 200px;
}

.novel-crawl-dialog .crawl-results > .el-empty {
  grid-column: 1 / -1;
}

.novel-crawl-dialog .el-empty__description p {
  color: #8b949e;
  font-size: 13px;
}

.novel-crawl-dialog .crawl-book-card {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.014));
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.12);
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.novel-crawl-dialog .crawl-book-card:hover,
.novel-crawl-dialog .crawl-book-card:focus-within {
  border-color: rgba(96, 165, 250, 0.45);
  background: rgba(37, 99, 235, 0.06);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.22);
  transform: translateY(-1px);
}

.novel-crawl-dialog .crawl-book-card.is-active {
  border-color: rgba(96, 165, 250, 0.65);
  background: rgba(37, 99, 235, 0.08);
  box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.4), 0 6px 16px rgba(37, 99, 235, 0.18);
}

.novel-crawl-dialog .crawl-book-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.novel-crawl-dialog .crawl-book-card__title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #f2f4f8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-crawl-dialog .crawl-book-card__tag {
  flex-shrink: 0;
  color: #93c5fd;
  background-color: rgba(37, 99, 235, 0.12);
  border-color: rgba(37, 99, 235, 0.3);
}

.novel-crawl-dialog .crawl-book-card__meta {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: #8b949e;
  align-items: center;
}

.novel-crawl-dialog .crawl-book-card__meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.novel-crawl-dialog .crawl-book-card__time {
  margin-left: auto;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 11px;
  color: #6e7681;
}

.novel-crawl-dialog .crawl-book-card__intro {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: #b8c2cc;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.novel-crawl-dialog .crawl-info {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.025);
}

.novel-crawl-dialog .crawl-info__title {
  font-size: 17px;
  font-weight: 700;
  color: #f2f4f8;
  margin-bottom: 6px;
}

.novel-crawl-dialog .crawl-info__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 8px;
}

.novel-crawl-dialog .crawl-info__intro {
  margin: 0;
  color: #b8c2cc;
  font-size: 12px;
  line-height: 1.6;
}

.novel-crawl-dialog .crawl-config {
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.025);
}

.novel-crawl-dialog .crawl-config__row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.novel-crawl-dialog .crawl-config__row label {
  font-size: 13px;
  font-weight: 600;
  color: #c5cdd6;
  flex-shrink: 0;
}

.novel-crawl-dialog .crawl-config__dash {
  color: #6e7681;
}

.novel-crawl-dialog .crawl-config__sum {
  color: #93c5fd;
  font-size: 12px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.novel-crawl-dialog .crawl-progress {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.025);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.novel-crawl-dialog .crawl-progress__bar {
  width: 100%;
  min-width: 0;
}

.novel-crawl-dialog .crawl-progress-meter {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 52px;
  align-items: start;
  gap: 10px;
  width: 100%;
  min-width: 0;
}

.novel-crawl-dialog .crawl-progress-meter__dots {
  display: grid;
  grid-template-columns: repeat(auto-fill, 5px);
  grid-auto-rows: 5px;
  justify-content: start;
  align-content: start;
  gap: 2px;
  max-height: 112px;
  min-width: 0;
  overflow-y: auto;
  padding: 8px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.06);
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-crawl-dialog .crawl-progress-meter__dots::-webkit-scrollbar {
  width: 6px;
}

.novel-crawl-dialog .crawl-progress-meter__dots::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.novel-crawl-dialog .crawl-progress-meter__dot {
  display: block;
  width: 5px;
  height: 5px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.08);
}

.novel-crawl-dialog .crawl-progress-meter__dot.is-complete {
  background: #2563eb;
}

.novel-crawl-dialog .crawl-progress-meter__dot.is-error {
  background: #ef4444;
}

.novel-crawl-dialog .crawl-progress-meter__value {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  text-align: right;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.novel-crawl-dialog .crawl-progress-meter.is-success .crawl-progress-meter__dot.is-complete {
  background-color: #22c55e;
}

.novel-crawl-dialog .crawl-progress-meter.is-success .crawl-progress-meter__value {
  color: #86efac;
}

.novel-crawl-dialog .crawl-progress-meter.is-exception .crawl-progress-meter__value {
  color: #fca5a5;
}

.novel-crawl-dialog .crawl-progress-meter.is-warning .crawl-progress-meter__dot.is-complete {
  background-color: #f59e0b;
}

.novel-crawl-dialog .crawl-progress-meter.is-warning .crawl-progress-meter__value {
  color: #fbbf24;
}

.novel-crawl-dialog .crawl-progress__text {
  margin: 0;
  font-size: 12px;
  color: #c5cdd6;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.novel-crawl-dialog .crawl-progress__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 168px;
  overflow-y: auto;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.06);
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-crawl-dialog .crawl-progress__list::-webkit-scrollbar {
  width: 6px;
}

.novel-crawl-dialog .crawl-progress__list::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.novel-crawl-dialog .crawl-progress__list::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.novel-crawl-dialog .crawl-progress__item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #86efac;
}

.novel-crawl-dialog .crawl-progress__item span {
  color: #c5cdd6;
}

.novel-crawl-dialog .crawl-progress__more {
  font-size: 11px;
  color: #6e7681;
  padding-top: 4px;
  border-top: 1px dashed rgba(255, 255, 255, 0.06);
}

.novel-crawl-dialog .import-preview__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  color: #c5cdd6;
  font-size: 13px;
  padding: 4px 4px 8px;
}

.novel-crawl-dialog .import-preview__head strong {
  color: #93c5fd;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  margin: 0 2px;
}

.novel-crawl-dialog .import-preview__summary {
  min-width: 0;
  line-height: 1.5;
}

.novel-crawl-dialog .import-preview__tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.novel-filter-popover {
  max-width: calc(100vw - 32px);
  padding: 0 !important;
  background: #11161d !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  border-radius: 14px !important;
  box-shadow: 0 18px 54px rgba(0, 0, 0, 0.48) !important;
  color: #d5dce4;
}

.novel-filter-popover .el-popper__arrow::before {
  background: #11161d !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
}

.crawl-filter {
  height: min(75vh, 500px);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}

.crawl-filter__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.crawl-filter__title {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 700;
  color: #f2f4f8;
}

.crawl-filter__hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #8b949e;
}

.crawl-filter__list {
  flex: 1;
  min-height: 0;
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.16) transparent;
}

.crawl-filter__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.025);
}

.crawl-filter__check {
  flex: 1;
  min-width: 0;
}

.crawl-filter__check .el-checkbox__label {
  width: 100%;
  min-width: 0;
  padding-left: 8px;
  line-height: 1.4;
}

.crawl-filter__item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.crawl-filter__item-name {
  overflow: hidden;
  color: #d5dce4;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.crawl-filter__item-regex {
  display: block;
  max-width: 420px;
  overflow: hidden;
  color: #6e7681;
  cursor: help;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.crawl-filter__badge {
  flex-shrink: 0;
  height: 20px;
  padding: 0 6px;
  color: #93c5fd;
  background-color: rgba(37, 99, 235, 0.12);
  border-color: rgba(37, 99, 235, 0.3);
  font-size: 11px;
  line-height: 18px;
}

.crawl-filter__custom {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.crawl-filter__custom-input {
  flex-shrink: 0;
}

.crawl-filter__custom-input--name {
  width: 132px;
}

.crawl-filter__custom-input--pattern {
  flex: 1;
  min-width: 180px;
}

.crawl-filter__custom-input--flags {
  width: 150px;
}

.crawl-filter__custom-input--repl {
  width: 128px;
}

.novel-filter-popover .el-input__wrapper,
.novel-filter-popover .el-select__wrapper {
  min-height: 34px;
  padding: 0 12px;
  background-color: #0c1015;
  border-radius: 9px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  color: #e6edf3;
  transition: background-color 0.18s ease, box-shadow 0.18s ease;
}

.novel-filter-popover .el-input__wrapper:hover,
.novel-filter-popover .el-select__wrapper:hover {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.novel-filter-popover .el-input__wrapper.is-focus,
.novel-filter-popover .el-select__wrapper.is-focused {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.novel-filter-popover .el-input__inner,
.novel-filter-popover .el-select__selected-item {
  color: #e6edf3;
}

.novel-filter-popover .el-input__inner::placeholder,
.novel-filter-popover .el-select__placeholder {
  color: #7e8893;
}

.novel-filter-popover .novel-dark-select.el-popper {
  background: #11161d;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.42);
}

.novel-filter-popover .novel-dark-select.el-popper .el-select-dropdown__list {
  padding: 6px;
}

.novel-filter-popover .novel-dark-select.el-popper .el-select-dropdown__item {
  height: 32px;
  border-radius: 8px;
  color: #c5cdd6;
  font-size: 12px;
}

.novel-filter-popover .novel-dark-select.el-popper .el-select-dropdown__item:hover,
.novel-filter-popover .novel-dark-select.el-popper .el-select-dropdown__item.is-hovering {
  background-color: rgba(37, 99, 235, 0.14);
  color: #ffffff;
}

.novel-filter-popover .novel-dark-select.el-popper .el-select-dropdown__item.is-selected {
  background-color: rgba(37, 99, 235, 0.2);
  color: #93c5fd;
  font-weight: 700;
}

.novel-filter-popover .novel-dark-select.el-popper .el-popper__arrow::before {
  background: #11161d;
  border-color: rgba(255, 255, 255, 0.12);
}

.novel-crawl-dialog .row-count {
  color: #8b949e;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px;
}

.novel-crawl-dialog .row-count.is-warning {
  color: #f87171;
  font-weight: 700;
}

.novel-crawl-dialog .crawl-chapter-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
  color: #d5dce4;
  line-height: 1.5;
}

.novel-crawl-dialog .crawl-chapter-title.is-warning {
  color: #f87171;
  font-weight: 600;
}

.novel-crawl-dialog .crawl-chapter-title__warning {
  flex-shrink: 0;
  color: currentColor;
  font-size: 14px;
}

.novel-crawl-dialog .crawl-chapter-title__text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-crawl-dialog .crawl-event-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
}

.novel-crawl-dialog .crawl-event-chip--success {
  color: #86efac;
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.32);
}

.novel-crawl-dialog .crawl-event-chip--pending {
  color: #fde68a;
  background: rgba(234, 179, 8, 0.1);
  border-color: rgba(234, 179, 8, 0.32);
}

.novel-crawl-dialog .crawl-event-chip--error {
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.1);
  border-color: rgba(248, 113, 113, 0.32);
}

.novel-crawl-dialog .import-preview__actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}

.novel-crawl-dialog .icon-action {
  width: 30px !important;
  min-width: 30px;
  height: 30px !important;
  padding: 0 !important;
  border-radius: 8px;
  color: #8b949e;
  --el-fill-color-light: transparent;
  --el-fill-color: transparent;
  --el-color-info: #93c5fd;
}

.novel-crawl-dialog .icon-action .el-icon {
  font-size: 15px;
}

.novel-crawl-dialog .icon-action:hover,
.novel-crawl-dialog .icon-action:focus {
  color: #93c5fd;
  background-color: rgba(59, 130, 246, 0.14);
}

.novel-crawl-dialog .icon-action.delete {
  --el-color-info: #fca5a5;
}

.novel-crawl-dialog .icon-action.delete:hover,
.novel-crawl-dialog .icon-action.delete:focus {
  color: #fca5a5;
  background-color: rgba(248, 113, 113, 0.16);
}

.novel-crawl-dialog .import-preview__table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-border-color: rgba(255, 255, 255, 0.06);
  --el-table-border: 1px solid rgba(255, 255, 255, 0.06);
  --el-table-header-text-color: #c5cdd6;
  --el-table-text-color: #c5cdd6;
  --el-table-row-hover-bg-color: rgba(37, 99, 235, 0.08);
  background: transparent;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.novel-crawl-dialog .import-preview__table.el-table,
.novel-crawl-dialog .import-preview__table .el-table__inner-wrapper,
.novel-crawl-dialog .import-preview__table .el-table__header-wrapper,
.novel-crawl-dialog .import-preview__table .el-table__body-wrapper,
.novel-crawl-dialog .import-preview__table .el-table__fixed-right,
.novel-crawl-dialog .import-preview__table .el-table__fixed,
.novel-crawl-dialog .import-preview__table .el-table__empty-block {
  background: transparent;
}

.novel-crawl-dialog .import-preview__table .el-table__inner-wrapper::before,
.novel-crawl-dialog .import-preview__table .el-table__border-left-patch {
  background-color: rgba(255, 255, 255, 0.06);
}

.novel-crawl-dialog .import-preview__table thead th.el-table__cell {
  background-color: rgba(255, 255, 255, 0.04);
  color: #c5cdd6;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-crawl-dialog .import-preview__table td.el-table__cell,
.novel-crawl-dialog .import-preview__table th.el-table__cell {
  background: transparent;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.novel-crawl-dialog .import-preview__table tr.el-table__row {
  background: transparent;
  color: #c5cdd6;
}

.novel-crawl-dialog .import-preview__table tr.el-table__row--striped td.el-table__cell {
  background: rgba(255, 255, 255, 0.012);
}

.novel-crawl-dialog .import-preview__table tbody tr:hover > td.el-table__cell {
  background-color: rgba(37, 99, 235, 0.08) !important;
}

.novel-crawl-dialog .import-preview__table .el-table__empty-text {
  color: #8b949e;
}

.novel-crawl-dialog .import-preview__table .el-checkbox__inner {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.18);
}

.novel-crawl-dialog .import-preview__table .el-checkbox__input.is-checked .el-checkbox__inner,
.novel-crawl-dialog .import-preview__table .el-checkbox__input.is-indeterminate .el-checkbox__inner {
  background-color: #2563eb;
  border-color: #2563eb;
}

.novel-crawl-dialog .import-preview__table .el-scrollbar__thumb {
  background-color: rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.novel-crawl-dialog .import-preview__table .el-scrollbar__thumb:hover {
  background-color: rgba(255, 255, 255, 0.32);
}

.novel-crawl-dialog .import-preview__table .el-scrollbar__wrap {
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-crawl-dialog .el-dialog__body .el-button {
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
  color: #c5cdd6;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.novel-crawl-dialog .el-dialog__body .el-button:hover,
.novel-crawl-dialog .el-dialog__body .el-button:focus {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
  transform: translateY(-1px);
}

.novel-crawl-dialog .el-dialog__body .el-button:active {
  transform: translateY(0);
}

.novel-crawl-dialog .el-dialog__body .el-button.is-disabled,
.novel-crawl-dialog .el-dialog__body .el-button.is-disabled:hover,
.novel-crawl-dialog .el-dialog__body .el-button.is-disabled:focus {
  background-color: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.06);
  color: #4d5560;
  transform: none;
  cursor: not-allowed;
}

.novel-crawl-dialog .el-dialog__body .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.22);
}

.novel-crawl-dialog .el-dialog__body .el-button--primary:hover,
.novel-crawl-dialog .el-dialog__body .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
  color: #ffffff;
}

.novel-crawl-dialog .el-dialog__body .el-button--primary.is-plain {
  background-color: rgba(37, 99, 235, 0.1);
  border-color: rgba(37, 99, 235, 0.45);
  color: #93c5fd;
  box-shadow: none;
}

.novel-crawl-dialog .el-dialog__body .el-button--primary.is-plain:hover,
.novel-crawl-dialog .el-dialog__body .el-button--primary.is-plain:focus {
  background-color: rgba(37, 99, 235, 0.2);
  border-color: rgba(37, 99, 235, 0.65);
  color: #ffffff;
}

.novel-crawl-dialog .el-dialog__body .el-button--danger {
  background-color: rgba(248, 113, 113, 0.12);
  border-color: rgba(248, 113, 113, 0.42);
  color: #fca5a5;
}

.novel-crawl-dialog .el-dialog__body .el-button--danger:hover,
.novel-crawl-dialog .el-dialog__body .el-button--danger:focus {
  background-color: rgba(248, 113, 113, 0.2);
  border-color: rgba(248, 113, 113, 0.58);
  color: #fecaca;
}

.novel-crawl-dialog .el-dialog__body .el-input-number {
  background-color: #0c1015;
  border-radius: 10px;
}

.novel-crawl-dialog .el-dialog__footer .el-button {
  height: 40px;
  min-width: 88px;
  padding: 0 20px;
  border-radius: 10px;
  font-weight: 700;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.novel-crawl-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.12);
  color: #e6edf3;
}

.novel-crawl-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):hover,
.novel-crawl-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):focus {
  background-color: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
  transform: translateY(-1px);
}

.novel-crawl-dialog .el-dialog__footer .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
}

.novel-crawl-dialog .el-dialog__footer .el-button--primary:hover,
.novel-crawl-dialog .el-dialog__footer .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
  color: #ffffff;
  transform: translateY(-1px);
}

.novel-crawl-dialog .el-dialog__footer .el-button--danger {
  background-color: rgba(248, 113, 113, 0.12);
  border-color: rgba(248, 113, 113, 0.42);
  color: #fca5a5;
}

.novel-crawl-dialog .el-dialog__footer .el-button--danger:hover,
.novel-crawl-dialog .el-dialog__footer .el-button--danger:focus {
  background-color: rgba(248, 113, 113, 0.2);
  border-color: rgba(248, 113, 113, 0.58);
  color: #fecaca;
  transform: translateY(-1px);
}

.novel-crawl-dialog .el-dialog__footer .el-button.is-disabled,
.novel-crawl-dialog .el-dialog__footer .el-button.is-disabled:hover,
.novel-crawl-dialog .el-dialog__footer .el-button.is-disabled:focus {
  background-color: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.06);
  color: #4d5560;
  box-shadow: none;
  transform: none;
  cursor: not-allowed;
}

.novel-crawl-dialog .el-dialog__footer .el-button:active {
  transform: translateY(0);
}

.crawl-preview-dialog {
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 20px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.crawl-preview-dialog .el-dialog__header {
  margin: 0;
  padding: 20px 24px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.crawl-preview-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 18px;
  font-weight: 800;
}

.crawl-preview-dialog .el-dialog__body {
  padding: 18px 24px 8px;
  color: #b8c2cc;
}

.crawl-preview-dialog .el-dialog__footer {
  padding: 14px 24px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.crawl-preview-dialog .el-dialog__footer .el-button {
  height: 36px;
  min-width: 86px;
  border-radius: 10px;
  font-weight: 700;
}

.crawl-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.crawl-preview__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.crawl-preview__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
  color: #8b949e;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px;
}

.crawl-preview__meta span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(148, 163, 184, 0.08);
}

.crawl-preview__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.crawl-preview__actions .el-button {
  height: 32px;
  padding: 0 12px;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 700;
}

.crawl-preview__content {
  max-height: min(58vh, 560px);
  overflow-y: auto;
  padding: 16px 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.24);
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.16) transparent;
}

.crawl-preview__content p {
  margin: 0 0 12px;
  color: #d5dce4;
  font-size: 14px;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-word;
}

.crawl-preview__content p:last-child {
  margin-bottom: 0;
}

/* 来源管理对话框 */
.novel-source-dialog {
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 24px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  max-width: calc(100vw - 32px);
}

.novel-source-dialog .el-dialog__header {
  margin: 0;
  padding: 22px 28px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-source-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.novel-source-dialog .el-dialog__headerbtn {
  top: 16px;
  right: 20px;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
}

.novel-source-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
  font-size: 20px;
}

.novel-source-dialog .el-dialog__headerbtn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.18);
}

.novel-source-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #ffffff;
}

.novel-source-dialog .el-dialog__body {
  padding: 22px 28px 8px;
  color: #b8c2cc;
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-source-dialog .el-dialog__body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.novel-source-dialog .el-dialog__body::-webkit-scrollbar-track {
  background: transparent;
}

.novel-source-dialog .el-dialog__body::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.novel-source-dialog .el-dialog__body::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.novel-source-dialog .el-dialog__footer {
  padding: 16px 28px 22px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.01);
}

.novel-source-dialog .el-input__wrapper,
.novel-source-dialog .el-select__wrapper,
.novel-source-dialog .el-input-number .el-input__wrapper {
  min-height: 38px;
  padding: 0 14px;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border-radius: 10px;
  color: #e6edf3;
  font-size: 14px;
  transition: background-color 0.18s ease, box-shadow 0.18s ease;
}

.novel-source-dialog .el-input__wrapper:hover,
.novel-source-dialog .el-select__wrapper:hover {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.novel-source-dialog .el-input__wrapper.is-focus,
.novel-source-dialog .el-select__wrapper.is-focused {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.novel-source-dialog .el-input__inner,
.novel-source-dialog .el-select__selected-item {
  color: #e6edf3;
}

.novel-source-dialog .el-input__inner::placeholder,
.novel-source-dialog .el-select__placeholder {
  color: #7e8893;
}

.novel-source-dialog .el-input.is-disabled .el-input__wrapper,
.novel-source-dialog .el-select .el-select__wrapper.is-disabled {
  background-color: rgba(255, 255, 255, 0.02);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.06) inset;
  cursor: not-allowed;
}

.novel-source-dialog .el-input.is-disabled .el-input__inner,
.novel-source-dialog .el-select .el-select__wrapper.is-disabled .el-select__selected-item {
  color: #6e7681;
  -webkit-text-fill-color: #6e7681;
}

.novel-source-dialog .source-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.novel-source-dialog .source-list__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.018));
}

.novel-source-dialog .source-list__count {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 11px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.08);
  color: #c5cdd6;
  font-size: 12px;
  font-weight: 600;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.novel-source-dialog .source-list__table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-border-color: rgba(255, 255, 255, 0.06);
  --el-table-border: 1px solid rgba(255, 255, 255, 0.06);
  --el-table-header-text-color: #c5cdd6;
  --el-table-text-color: #c5cdd6;
  --el-table-row-hover-bg-color: rgba(37, 99, 235, 0.08);
  background: transparent;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.novel-source-dialog .source-list__table.el-table,
.novel-source-dialog .source-list__table .el-table__inner-wrapper,
.novel-source-dialog .source-list__table .el-table__header-wrapper,
.novel-source-dialog .source-list__table .el-table__body-wrapper,
.novel-source-dialog .source-list__table .el-table__fixed-right,
.novel-source-dialog .source-list__table .el-table__fixed,
.novel-source-dialog .source-list__table .el-table__empty-block {
  background: transparent;
}

.novel-source-dialog .source-list__table .el-table__inner-wrapper::before,
.novel-source-dialog .source-list__table .el-table__border-left-patch {
  background-color: rgba(255, 255, 255, 0.06);
}

.novel-source-dialog .source-list__table thead th.el-table__cell {
  background-color: rgba(255, 255, 255, 0.04);
  color: #c5cdd6;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-source-dialog .source-list__table td.el-table__cell,
.novel-source-dialog .source-list__table th.el-table__cell {
  background: transparent;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.novel-source-dialog .source-list__table tr.el-table__row {
  background: transparent;
  color: #c5cdd6;
}

.novel-source-dialog .source-list__table tr.el-table__row--striped td.el-table__cell {
  background: rgba(255, 255, 255, 0.012);
}

.novel-source-dialog .source-list__table tbody tr:hover > td.el-table__cell {
  background-color: rgba(37, 99, 235, 0.08) !important;
}

.novel-source-dialog .source-list__table .el-table__empty-text {
  color: #8b949e;
}

.novel-source-dialog .source-list__table .el-table__fixed-right,
.novel-source-dialog .source-list__table .el-table__fixed-right-patch {
  background-color: #0d1117;
}

.novel-source-dialog .source-list__table .el-table__fixed-right {
  box-shadow: -8px 0 12px rgba(0, 0, 0, 0.35);
}

.novel-source-dialog .source-list__table .el-table__fixed-right td.el-table__cell,
.novel-source-dialog .source-list__table .el-table__fixed-right th.el-table__cell {
  background-color: #0d1117;
}

.novel-source-dialog .source-list__table .el-table__fixed-right tbody tr:hover > td.el-table__cell {
  background-color: rgba(37, 99, 235, 0.08) !important;
}

.novel-source-dialog .source-list__table .el-checkbox__inner {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.18);
}

.novel-source-dialog .source-list__table .el-checkbox__input.is-checked .el-checkbox__inner,
.novel-source-dialog .source-list__table .el-checkbox__input.is-indeterminate .el-checkbox__inner {
  background-color: #2563eb;
  border-color: #2563eb;
}

.novel-source-dialog .source-list__table .el-scrollbar__thumb {
  background-color: rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.novel-source-dialog .source-list__table .el-scrollbar__thumb:hover {
  background-color: rgba(255, 255, 255, 0.32);
}

.novel-source-dialog .source-list__table .el-scrollbar__wrap {
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-source-dialog .source-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.novel-source-dialog .source-form__banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.018));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  font-size: 12px;
  line-height: 1.6;
  color: #c5cdd6;
}

.novel-source-dialog .source-form__banner--edit {
  border-color: rgba(96, 165, 250, 0.45);
  background:
    linear-gradient(180deg, rgba(37, 99, 235, 0.12), rgba(37, 99, 235, 0.045)),
    #10151d;
}

.novel-source-dialog .source-form__banner--create {
  border-color: rgba(74, 222, 128, 0.45);
  background:
    linear-gradient(180deg, rgba(34, 197, 94, 0.12), rgba(34, 197, 94, 0.045)),
    #10151a;
}

.novel-source-dialog .source-form__banner-tag {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.08);
}

.novel-source-dialog .source-form__banner--edit .source-form__banner-tag {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.2);
}

.novel-source-dialog .source-form__banner--create .source-form__banner-tag {
  color: #86efac;
  background: rgba(34, 197, 94, 0.2);
}

.novel-source-dialog .source-form__banner-text {
  flex: 1;
  min-width: 260px;
}

.novel-source-dialog .source-form__banner-text strong {
  color: #f2f4f8;
  font-weight: 700;
}

.novel-source-dialog .source-form__section {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.012));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
  transition: background-color 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.novel-source-dialog .source-form__section:hover,
.novel-source-dialog .source-form__section:focus-within {
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(37, 99, 235, 0.035);
}

.novel-source-dialog .source-form__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.novel-source-dialog .source-form__section-head h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #f2f4f8;
}

.novel-source-dialog .source-form__section-hint {
  max-width: 620px;
  font-size: 11px;
  line-height: 1.55;
  color: #6e7681;
  text-align: right;
}

.novel-source-dialog .source-form__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}

.novel-source-dialog .source-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.novel-source-dialog .source-form__field--full {
  grid-column: 1 / -1;
}

.novel-source-dialog .source-form__field label {
  font-size: 12px;
  line-height: 1.35;
  font-weight: 600;
  color: #c5cdd6;
}

.novel-source-dialog .source-form__field label .required {
  color: #fca5a5;
  margin-left: 2px;
}

.novel-source-dialog .source-form__inline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.novel-source-dialog .source-form__inline .source-form__inline-input {
  flex: 1;
  min-width: 0;
}

.novel-source-dialog .source-form__method-select {
  width: 110px;
  flex: 0 0 110px;
}

/* 接口分组 */
.novel-source-dialog .source-form__subgroup {
  padding: 12px 14px;
  border-radius: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.018), rgba(255, 255, 255, 0.006)),
    rgba(0, 0, 0, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.06);
  margin-bottom: 12px;
  transition: background-color 0.18s ease, border-color 0.18s ease;
}

.novel-source-dialog .source-form__subgroup:hover,
.novel-source-dialog .source-form__subgroup:focus-within {
  border-color: rgba(96, 165, 250, 0.22);
  background-color: rgba(37, 99, 235, 0.03);
}

.novel-source-dialog .source-form__subgroup:last-child {
  margin-bottom: 0;
}

.novel-source-dialog .source-form__subgroup-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.novel-source-dialog .source-form__subgroup-tag {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  font-size: 11px;
  font-weight: 700;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.14);
  border: 1px solid rgba(37, 99, 235, 0.32);
  padding: 0 10px;
  border-radius: 999px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.novel-source-dialog .source-form__subgroup-hint {
  flex: 1;
  min-width: 220px;
  text-align: right;
  font-size: 11px;
  line-height: 1.5;
  color: #6e7681;
}

/* 来源管理 — 表格 / footer 按钮统一为雅黑风格 */
.novel-source-dialog .el-tag--info {
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background-color: rgba(148, 163, 184, 0.14);
  border-color: rgba(148, 163, 184, 0.35);
  color: #cbd5e1;
}

.novel-source-dialog .el-tag--success {
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background-color: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.4);
  color: #86efac;
}

.novel-source-dialog .el-dialog__body .el-button--primary.is-plain {
  background-color: rgba(37, 99, 235, 0.1);
  border-color: rgba(37, 99, 235, 0.45);
  color: #93c5fd;
  box-shadow: none;
}

.novel-source-dialog .el-dialog__body .el-button--primary.is-plain:hover,
.novel-source-dialog .el-dialog__body .el-button--primary.is-plain:focus {
  background-color: rgba(37, 99, 235, 0.2);
  border-color: rgba(37, 99, 235, 0.65);
  color: #ffffff;
}

.novel-source-dialog .el-dialog__body .el-button {
  height: 32px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
  color: #c5cdd6;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.novel-source-dialog .el-dialog__body .el-button .el-icon {
  margin-right: 0;
}

.novel-source-dialog .el-dialog__body .el-button:hover,
.novel-source-dialog .el-dialog__body .el-button:focus {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
  transform: translateY(-1px);
}

.novel-source-dialog .el-dialog__body .el-button:active {
  transform: translateY(0);
}

.novel-source-dialog .el-dialog__body .el-button.is-disabled,
.novel-source-dialog .el-dialog__body .el-button.is-disabled:hover,
.novel-source-dialog .el-dialog__body .el-button.is-disabled:focus {
  background-color: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.06);
  color: #4d5560;
  transform: none;
  cursor: not-allowed;
}

.novel-source-dialog .el-dialog__body .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
}

.novel-source-dialog .el-dialog__body .el-button--primary:hover,
.novel-source-dialog .el-dialog__body .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
}

.novel-source-dialog .el-dialog__body .el-button--danger {
  background-color: rgba(248, 113, 113, 0.1);
  border-color: rgba(248, 113, 113, 0.35);
  color: #fca5a5;
}

.novel-source-dialog .el-dialog__body .el-button--danger:hover,
.novel-source-dialog .el-dialog__body .el-button--danger:focus {
  background-color: rgba(248, 113, 113, 0.18);
  border-color: rgba(248, 113, 113, 0.52);
  color: #fecaca;
}

.novel-source-dialog .el-dialog__body .el-button.is-text {
  height: 28px;
  background: transparent;
  border-color: transparent;
  padding: 0 8px;
  font-weight: 600;
}

.novel-source-dialog .el-dialog__body .el-button.is-text.el-button--primary {
  color: #93c5fd;
}

.novel-source-dialog .el-dialog__body .el-button.is-text.el-button--danger {
  color: #fca5a5;
}

.novel-source-dialog .el-dialog__body .el-button.is-text:hover,
.novel-source-dialog .el-dialog__body .el-button.is-text:focus {
  border-color: transparent;
  transform: none;
}

.novel-source-dialog .el-dialog__body .el-button.is-text.el-button--primary:hover,
.novel-source-dialog .el-dialog__body .el-button.is-text.el-button--primary:focus {
  background: rgba(37, 99, 235, 0.12);
  color: #bfdbfe;
}

.novel-source-dialog .el-dialog__body .el-button.is-text.el-button--danger:hover,
.novel-source-dialog .el-dialog__body .el-button.is-text.el-button--danger:focus {
  background: rgba(248, 113, 113, 0.14);
  color: #fecaca;
}

.novel-source-dialog .el-dialog__footer .el-button {
  height: 40px;
  min-width: 88px;
  padding: 0 20px;
  border-radius: 10px;
  font-weight: 700;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.novel-source-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.12);
  color: #e6edf3;
}

.novel-source-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):hover,
.novel-source-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):focus {
  background-color: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
  transform: translateY(-1px);
}

.novel-source-dialog .el-dialog__footer .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
}

.novel-source-dialog .el-dialog__footer .el-button--primary:hover,
.novel-source-dialog .el-dialog__footer .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
  color: #ffffff;
  transform: translateY(-1px);
}

.novel-source-dialog .el-dialog__footer .el-button--danger {
  background-color: rgba(248, 113, 113, 0.12);
  border-color: rgba(248, 113, 113, 0.42);
  color: #fca5a5;
}

.novel-source-dialog .el-dialog__footer .el-button--danger:hover,
.novel-source-dialog .el-dialog__footer .el-button--danger:focus {
  background-color: rgba(248, 113, 113, 0.2);
  border-color: rgba(248, 113, 113, 0.58);
  color: #fecaca;
  transform: translateY(-1px);
}

.novel-source-dialog .el-dialog__footer .el-button.is-disabled,
.novel-source-dialog .el-dialog__footer .el-button.is-disabled:hover,
.novel-source-dialog .el-dialog__footer .el-button.is-disabled:focus {
  background-color: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.06);
  color: #4d5560;
  box-shadow: none;
  transform: none;
  cursor: not-allowed;
}

.novel-source-dialog .el-dialog__footer .el-button:active {
  transform: translateY(0);
}

/* 覆盖可能在爬取流程中暴露浅色背景的 Element Plus 默认样式。 */
.novel-crawl-dialog,
.novel-source-dialog,
.crawl-preview-dialog,
.novel-filter-popover {
  --el-bg-color: #0d1117;
  --el-bg-color-overlay: #11161d;
  --el-fill-color-blank: transparent;
  --el-fill-color-light: rgba(255, 255, 255, 0.04);
  --el-fill-color-lighter: rgba(255, 255, 255, 0.025);
  --el-fill-color-extra-light: rgba(255, 255, 255, 0.018);
  --el-border-color: rgba(255, 255, 255, 0.1);
  --el-border-color-light: rgba(255, 255, 255, 0.08);
  --el-border-color-lighter: rgba(255, 255, 255, 0.06);
  --el-text-color-primary: #e6edf3;
  --el-text-color-regular: #c5cdd6;
  --el-text-color-secondary: #8b949e;
  --el-disabled-bg-color: rgba(255, 255, 255, 0.02);
  --el-disabled-border-color: rgba(255, 255, 255, 0.06);
  --el-disabled-text-color: #4d5560;
  color-scheme: dark;
}

.novel-crawl-dialog .el-textarea__inner,
.novel-source-dialog .el-textarea__inner {
  min-height: 92px;
  padding: 12px 14px;
  background-color: #0c1015;
  border: none;
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  color: #e6edf3;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  transition: background-color 0.18s ease, box-shadow 0.18s ease;
}

.novel-crawl-dialog .el-textarea__inner:hover,
.novel-source-dialog .el-textarea__inner:hover {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.novel-crawl-dialog .el-textarea__inner:focus,
.novel-source-dialog .el-textarea__inner:focus {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.novel-crawl-dialog .el-textarea__inner::placeholder,
.novel-source-dialog .el-textarea__inner::placeholder {
  color: #7e8893;
}

.novel-crawl-dialog .el-textarea.is-disabled .el-textarea__inner,
.novel-source-dialog .el-textarea.is-disabled .el-textarea__inner {
  background-color: rgba(255, 255, 255, 0.02);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.06) inset;
  color: #6e7681;
  -webkit-text-fill-color: #6e7681;
}

.novel-crawl-dialog .el-input-number__decrease,
.novel-crawl-dialog .el-input-number__increase,
.novel-source-dialog .el-input-number__decrease,
.novel-source-dialog .el-input-number__increase {
  background-color: rgba(255, 255, 255, 0.035);
  border-color: rgba(255, 255, 255, 0.08);
  color: #8b949e;
}

.novel-crawl-dialog .el-input-number__decrease:hover,
.novel-crawl-dialog .el-input-number__increase:hover,
.novel-source-dialog .el-input-number__decrease:hover,
.novel-source-dialog .el-input-number__increase:hover {
  background-color: rgba(37, 99, 235, 0.12);
  color: #93c5fd;
}

.novel-crawl-dialog .el-input-number.is-disabled .el-input-number__decrease,
.novel-crawl-dialog .el-input-number.is-disabled .el-input-number__increase,
.novel-source-dialog .el-input-number.is-disabled .el-input-number__decrease,
.novel-source-dialog .el-input-number.is-disabled .el-input-number__increase {
  background-color: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.05);
  color: #4d5560;
}

.novel-crawl-dialog .el-loading-mask,
.novel-source-dialog .el-loading-mask,
.crawl-preview-dialog .el-loading-mask {
  background-color: rgba(13, 17, 23, 0.72) !important;
  backdrop-filter: blur(2px);
}

.novel-crawl-dialog .el-loading-spinner .path,
.novel-source-dialog .el-loading-spinner .path,
.crawl-preview-dialog .el-loading-spinner .path {
  stroke: #60a5fa;
}

.novel-crawl-dialog .el-loading-spinner .el-loading-text,
.novel-source-dialog .el-loading-spinner .el-loading-text,
.crawl-preview-dialog .el-loading-spinner .el-loading-text {
  color: #c5cdd6;
}

.novel-crawl-dialog .el-empty,
.novel-source-dialog .el-empty,
.crawl-preview-dialog .el-empty {
  --el-empty-padding: 28px 0;
  --el-empty-description-margin-top: 10px;
}

.novel-crawl-dialog .el-empty__image svg,
.novel-source-dialog .el-empty__image svg,
.crawl-preview-dialog .el-empty__image svg {
  opacity: 0.58;
  filter: saturate(0.75) brightness(0.72);
}

.novel-crawl-dialog .el-empty__description p,
.novel-source-dialog .el-empty__description p,
.crawl-preview-dialog .el-empty__description p {
  color: #8b949e;
}

.novel-crawl-dialog .import-preview__table .el-table__body,
.novel-crawl-dialog .import-preview__table .el-table__header,
.novel-crawl-dialog .import-preview__table .el-table__footer,
.novel-crawl-dialog .import-preview__table .el-table__fixed-right-patch,
.novel-source-dialog .source-list__table .el-table__body,
.novel-source-dialog .source-list__table .el-table__header,
.novel-source-dialog .source-list__table .el-table__footer,
.novel-source-dialog .source-list__table .el-table__fixed-right-patch {
  background-color: transparent !important;
}

.novel-crawl-dialog .import-preview__table::before,
.novel-crawl-dialog .import-preview__table::after,
.novel-source-dialog .source-list__table::before,
.novel-source-dialog .source-list__table::after {
  background-color: rgba(255, 255, 255, 0.06);
}

.novel-filter-popover .el-checkbox__label {
  color: #d5dce4;
}

.novel-filter-popover .el-checkbox__inner {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.18);
}

.novel-filter-popover .el-checkbox__input.is-checked .el-checkbox__inner,
.novel-filter-popover .el-checkbox__input.is-indeterminate .el-checkbox__inner {
  background-color: #2563eb;
  border-color: #2563eb;
}

.novel-filter-popover .el-button {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
  color: #c5cdd6;
}

.novel-filter-popover .el-button:hover,
.novel-filter-popover .el-button:focus {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
}

.novel-filter-popover .el-button--primary,
.novel-filter-popover .el-button--primary.is-plain {
  background-color: rgba(37, 99, 235, 0.16);
  border-color: rgba(37, 99, 235, 0.46);
  color: #93c5fd;
}

.novel-filter-popover .el-button--primary:hover,
.novel-filter-popover .el-button--primary:focus,
.novel-filter-popover .el-button--primary.is-plain:hover,
.novel-filter-popover .el-button--primary.is-plain:focus {
  background-color: rgba(37, 99, 235, 0.24);
  border-color: rgba(37, 99, 235, 0.66);
  color: #ffffff;
}

.crawl-preview-dialog .el-dialog__headerbtn {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
}

.crawl-preview-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
}

.crawl-preview-dialog .el-dialog__headerbtn:hover {
  background: rgba(255, 255, 255, 0.06);
}

.crawl-preview-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #ffffff;
}

.crawl-preview-dialog .el-dialog__body .el-button,
.crawl-preview-dialog .el-dialog__footer .el-button {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
  color: #c5cdd6;
}

.crawl-preview-dialog .el-dialog__body .el-button:hover,
.crawl-preview-dialog .el-dialog__body .el-button:focus,
.crawl-preview-dialog .el-dialog__footer .el-button:hover,
.crawl-preview-dialog .el-dialog__footer .el-button:focus {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
}

.crawl-preview-dialog .el-dialog__body .el-button--primary,
.crawl-preview-dialog .el-dialog__body .el-button--primary.is-plain,
.crawl-preview-dialog .el-dialog__footer .el-button--primary {
  background-color: rgba(37, 99, 235, 0.16);
  border-color: rgba(37, 99, 235, 0.46);
  color: #93c5fd;
}

.crawl-preview-dialog .el-dialog__body .el-button--primary:hover,
.crawl-preview-dialog .el-dialog__body .el-button--primary:focus,
.crawl-preview-dialog .el-dialog__body .el-button--primary.is-plain:hover,
.crawl-preview-dialog .el-dialog__body .el-button--primary.is-plain:focus,
.crawl-preview-dialog .el-dialog__footer .el-button--primary:hover,
.crawl-preview-dialog .el-dialog__footer .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
  color: #ffffff;
}

.crawl-preview__content::-webkit-scrollbar,
.novel-source-dialog .el-textarea__inner::-webkit-scrollbar {
  width: 6px;
}

.crawl-preview__content::-webkit-scrollbar-track,
.novel-source-dialog .el-textarea__inner::-webkit-scrollbar-track {
  background: transparent;
}

.crawl-preview__content::-webkit-scrollbar-thumb,
.novel-source-dialog .el-textarea__inner::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.14);
  border-radius: 999px;
}

.crawl-preview__content::-webkit-scrollbar-thumb:hover,
.novel-source-dialog .el-textarea__inner::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.26);
}

.novel-dark-select.el-popper {
  --el-bg-color-overlay: #11161d;
  --el-border-color-light: rgba(255, 255, 255, 0.12);
  background: #11161d !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  border-radius: 10px !important;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.46) !important;
  color: #c5cdd6;
}

.novel-dark-select.el-popper .el-select-dropdown,
.novel-dark-select.el-popper .el-scrollbar,
.novel-dark-select.el-popper .el-select-dropdown__wrap {
  background: #11161d;
}

.novel-dark-select.el-popper .el-select-dropdown__list {
  padding: 6px;
}

.novel-dark-select.el-popper .el-select-dropdown__item {
  height: 32px;
  margin: 2px 0;
  border-radius: 8px;
  color: #c5cdd6;
  font-size: 13px;
  line-height: 32px;
}

.novel-dark-select.el-popper .el-select-dropdown__item:hover,
.novel-dark-select.el-popper .el-select-dropdown__item.is-hovering {
  background-color: rgba(37, 99, 235, 0.14);
  color: #ffffff;
}

.novel-dark-select.el-popper .el-select-dropdown__item.is-selected {
  background-color: rgba(37, 99, 235, 0.2);
  color: #93c5fd;
  font-weight: 700;
}

.novel-dark-select.el-popper .el-select-dropdown__item.is-disabled {
  color: #4d5560;
}

.novel-dark-select.el-popper .el-select-dropdown__empty {
  color: #8b949e;
}

.novel-dark-select.el-popper .el-popper__arrow::before {
  background: #11161d !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
}

.novel-cell-tooltip.el-popper,
.el-popper.is-dark[role="tooltip"] {
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  border-radius: 10px !important;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45) !important;
  color: #e6edf3 !important;
}

.novel-cell-tooltip.el-popper .el-popper__arrow::before,
.el-popper.is-dark[role="tooltip"] .el-popper__arrow::before {
  background: #14181f !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
}

@media (max-width: 820px) {
  .novel-crawl-dialog .import-preview__head,
  .crawl-filter__head,
  .crawl-filter__custom,
  .crawl-preview__top {
    flex-direction: column;
    align-items: stretch;
  }

  .novel-crawl-dialog .import-preview__tools {
    width: 100%;
    justify-content: stretch;
  }

  .novel-crawl-dialog .import-preview__tools .el-button {
    flex: 1;
    justify-content: center;
  }

  .crawl-filter__custom-input,
  .crawl-filter__custom-input--name,
  .crawl-filter__custom-input--pattern,
  .crawl-filter__custom-input--flags,
  .crawl-filter__custom-input--repl {
    width: 100%;
    min-width: 0;
  }

  .crawl-preview-dialog {
    width: calc(100vw - 28px) !important;
  }

  .crawl-filter {
    height: min(75vh, 560px);
  }

  .crawl-preview__actions {
    justify-content: stretch;
  }

  .crawl-preview__actions .el-button {
    flex: 1;
    justify-content: center;
  }

  .novel-source-dialog .el-dialog__body {
    padding: 18px 18px 8px;
  }

  .novel-source-dialog .source-list__head,
  .novel-source-dialog .source-form__section-head {
    flex-direction: column;
    align-items: stretch;
  }

  .novel-source-dialog .source-list__head .el-button {
    width: 100%;
    justify-content: center;
  }

  .novel-source-dialog .source-form__grid {
    grid-template-columns: 1fr;
  }

  .novel-source-dialog .source-form__section-hint,
  .novel-source-dialog .source-form__subgroup-hint {
    max-width: none;
    text-align: left;
  }

  .novel-source-dialog .source-form__banner-text {
    min-width: 0;
  }
}
</style>
