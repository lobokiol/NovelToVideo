<template>
  <main class="production-page">
    <div class="app-shell">
      <aside class="sidebar">
        <div class="side-top">
          <div class="brand" @click="goProject">AF</div>

          <el-tooltip content="项目" placement="right">
            <button class="nav-btn" aria-label="项目" @click="goProject">
              <el-icon><Folder /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="剧本" placement="right">
            <button class="nav-btn" aria-label="剧本" @click="goScript">
              <el-icon><Tickets /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="制作" placement="right">
            <button class="nav-btn active" aria-label="制作">
              <el-icon><Film /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="任务" placement="right">
            <button class="nav-btn" aria-label="任务" @click="goTasks(activeJobId)">
              <el-icon><List /></el-icon>
            </button>
          </el-tooltip>
        </div>

        <div class="side-bottom">
          <el-tooltip content="文档" placement="right">
            <button class="nav-btn" aria-label="文档" @click="showComingSoon">
              <el-icon><Document /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="设置" placement="right">
            <button class="nav-btn" aria-label="设置" @click="settingsVisible = true">
              <el-icon><Setting /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="代码仓库" placement="right">
            <button class="nav-btn" aria-label="代码仓库" @click="showComingSoon">
              <el-icon><Connection /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </aside>

      <section class="main-panel">
        <header class="page-header">
          <div class="page-header__left">
            <h1 class="title">制作工作台</h1>
            <p class="desc">
              <template v-if="currentProject?.name">管理项目「{{ currentProject.name }}」的分镜生成与镜头编辑</template>
              <template v-else>正在加载项目信息…</template>
            </p>
          </div>

          <div class="page-header__right">
            <el-button class="header-action" size="large" @click="goScript">
              <el-icon><Back /></el-icon>
              返回剧本
            </el-button>
            <el-button class="header-action" size="large" @click="goEditor">
              <el-icon><Film /></el-icon>
              剪辑台
            </el-button>
            <el-button class="header-action" size="large" :loading="loading" @click="reloadAll">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </header>

        <section class="control-panel">
          <div class="control-grid">
            <label class="field">
              <span>文本模型</span>
              <ModelGroupSelect
                v-model="generateForm.modelId"
                :groups="textModelGroups"
                :loading="modelsLoading || projectFieldSaving"
                placeholder="选择文本模型"
                empty-label="暂无可用文本模型"
                @change="onTextModelChange"
              />
            </label>

            <label class="field">
              <span>生图模型</span>
              <ModelGroupSelect
                v-model="imageModelId"
                :groups="imageModelGroups"
                :loading="modelsLoading || projectFieldSaving"
                clearable
                placeholder="选择生图模型"
                empty-label="暂无可用生图模型"
                @change="onImageModelChange"
              />
            </label>

            <label class="field">
              <span>艺术风格</span>
              <el-select
                v-model="generateForm.artStyle"
                class="dark-select"
                popper-class="production-dark-select"
                filterable
                clearable
                placeholder="选择艺术风格"
                @change="onArtStyleChange"
              >
                <el-option
                  v-for="style in visualStyles"
                  :key="style.style_path"
                  :label="style.name || style.style_path"
                  :value="style.style_path"
                />
              </el-select>
            </label>

            <label class="field">
              <span>导演风格</span>
              <el-select
                v-model="generateForm.directorStyle"
                class="dark-select"
                popper-class="production-dark-select"
                filterable
                clearable
                placeholder="选择导演风格"
                @change="onDirectorStyleChange"
              >
                <el-option
                  v-for="manual in directorManuals"
                  :key="manual.manual_path"
                  :label="manual.name || manual.manual_path"
                  :value="manual.manual_path"
                />
              </el-select>
            </label>
          </div>

          <div class="control-actions">
            <div class="task-status" :class="{ active: hasActiveJob }">
              <span class="status-dot"></span>
              <span>{{ activeJobLabel }}</span>
            </div>
            <el-button class="ghost-button" @click="goTasks(activeJobId)">
              <el-icon><List /></el-icon>
              查看任务
            </el-button>
            <div class="grid-actions">
              <el-select
                v-model="gridImageSize"
                class="dark-select grid-resolution-select"
                popper-class="production-dark-select"
                :disabled="gridSubmitting"
              >
                <el-option
                  v-for="size in gridImageSizeOptions"
                  :key="size"
                  :label="size"
                  :value="size"
                />
              </el-select>
              <el-select
                v-model="gridSize"
                class="dark-select grid-size-select"
                popper-class="production-dark-select"
                :disabled="gridSubmitting"
              >
                <el-option
                  v-for="size in gridSizeOptions"
                  :key="size"
                  :label="`${size} 宫格`"
                  :value="size"
                />
              </el-select>
              <el-dropdown
                split-button
                type="primary"
                class="grid-generate-button"
                :disabled="gridSubmitting || !selectedEpisodeId"
                @click="submitGridImages(false)"
                @command="onGridImageCommand"
              >
                生成分镜图
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="missing">仅补缺图镜头</el-dropdown-item>
                    <el-dropdown-item command="all">重新生成本集全部</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <el-button
              class="primary-button"
              type="primary"
              :disabled="!selectedEpisodeId || !generateForm.modelId"
              :loading="submitting"
              @click="submitGenerate"
            >
              <el-icon><VideoPlay /></el-icon>
              生成分镜
            </el-button>
          </div>
        </section>

        <section class="workbench-grid">
          <aside class="episode-panel panel">
            <div class="panel-head">
              <h2>分集</h2>
              <span>{{ episodes.length }} 集</span>
            </div>
            <div v-loading="episodesLoading" class="episode-list" element-loading-background="rgba(7, 10, 16, 0.7)">
              <button
                v-for="episode in episodes"
                :key="episode.publicId"
                class="episode-item"
                :class="{ active: selectedEpisodeId === episode.publicId }"
                @click="selectEpisode(episode.publicId)"
              >
                <strong>EP{{ pad2(episode.episodeIndex) }}</strong>
                <span>{{ episode.title || '未命名分集' }}</span>
                <em>{{ shotCountByEpisode.get(episode.publicId) || 0 }} 镜</em>
              </button>
              <el-empty v-if="!episodesLoading && episodes.length === 0" description="暂无剧本分集" />
            </div>
          </aside>

          <section class="shot-panel panel">
            <div class="panel-head">
              <h2>分镜表</h2>
              <div class="panel-head__right">
                <el-button class="ghost-button panel-head-action" size="small" @click="openGridDialog">
                  <el-icon><Picture /></el-icon>
                  宫格图
                </el-button>
                <span>{{ currentShots.length }} 镜 · {{ totalDuration }} 秒</span>
              </div>
            </div>
            <div v-if="selectedShotRows.length > 0" class="batch-bar">
              <span class="batch-bar__count">已选 {{ selectedShotRows.length }} 镜</span>
              <el-button
                class="ghost-button"
                size="small"
                :loading="gridSubmitting"
                @click="submitGridImages(false, selectedShotRowIds)"
              >
                <el-icon><Picture /></el-icon>
                批量生成分镜图
              </el-button>
              <el-button
                class="ghost-button"
                size="small"
                :loading="submitting"
                :disabled="!generateForm.modelId"
                @click="submitBatchScripts"
              >
                <el-icon><VideoPlay /></el-icon>
                批量生成分镜脚本
              </el-button>
              <el-button
                class="ghost-button"
                size="small"
                :loading="videoSubmitting"
                @click="submitShotVideos(selectedShotRowIds, false)"
              >
                <el-icon><VideoCamera /></el-icon>
                批量生成镜头视频
              </el-button>
              <el-button
                class="danger-button"
                size="small"
                :loading="deletingShots"
                :disabled="deletingShots"
                @click="deleteSelectedShots"
              >
                <el-icon><Delete /></el-icon>
                批量删除
              </el-button>
              <el-button size="small" text class="batch-bar__clear" @click="clearShotSelection">清除选择</el-button>
            </div>
            <div v-loading="shotsLoading" class="shot-table-wrap" element-loading-background="rgba(7, 10, 16, 0.7)">
              <el-table
                ref="shotTableRef"
                :data="currentShots"
                class="shot-table"
                height="100%"
                highlight-current-row
                row-key="publicId"
                @row-click="selectShot"
                @selection-change="onShotSelectionChange"
              >
                <el-table-column type="selection" width="44" />
                <el-table-column label="#" width="64">
                  <template #default="{ row }">
                    <span>{{ row.shotIndex }}{{ row.status === 'locked' ? ' 🔒' : '' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="分镜图" width="92">
                  <template #default="{ row }">
                    <el-image
                      v-if="row.referenceMediaPublicId"
                      class="shot-frame-thumb"
                      fit="cover"
                      :src="mediaThumbnailUrl(projectPublicId, row.referenceMediaPublicId)"
                      :preview-src-list="[mediaContentUrl(projectPublicId, row.referenceMediaPublicId)]"
                      preview-teleported
                      hide-on-click-modal
                      @click.stop
                    />
                    <span v-else class="shot-frame-empty">待生成</span>
                  </template>
                </el-table-column>
                <el-table-column prop="sceneNumber" label="场号" width="90" />
                <el-table-column prop="shotSize" label="景别" width="90" />
                <el-table-column prop="camera" label="机位/运镜" min-width="160" show-overflow-tooltip />
                <el-table-column prop="action" label="画面动作" min-width="260" show-overflow-tooltip />
                <el-table-column prop="durationSeconds" label="秒" width="70" />
              </el-table>
              <el-empty v-if="!shotsLoading && currentShots.length === 0" description="当前分集暂无分镜" />
            </div>
          </section>

        </section>

        <el-drawer
          v-model="shotDrawerVisible"
          class="production-shot-drawer"
          direction="rtl"
          size="552px"
          :with-header="false"
        >
          <div v-if="selectedShot" class="shot-drawer-body">
            <header class="shot-drawer-head">
              <div class="shot-drawer-head__info">
                <span class="shot-drawer-badge">#{{ selectedShot.shotIndex }}</span>
                <div class="shot-drawer-title">
                  <h2>镜头详情</h2>
                  <p>场号 {{ selectedShot.sceneNumber || '—' }} · {{ selectedShot.durationSeconds }} 秒</p>
                </div>
              </div>
              <div class="shot-drawer-head__actions">
                <el-tag :type="selectedShot.status === 'locked' ? 'warning' : 'info'" effect="plain">
                  {{ selectedShot.status === 'locked' ? '已锁定' : '草稿' }}
                </el-tag>
                <button class="shot-drawer-close" aria-label="关闭" @click="shotDrawerVisible = false">
                  <el-icon><Close /></el-icon>
                </button>
              </div>
            </header>

            <div class="shot-drawer-scroll">
              <section class="shot-drawer-section">
                <h3>基础信息</h3>
                <div class="editor-row two">
                  <label>
                    <span>场号</span>
                    <el-input v-model="editForm.sceneNumber" />
                  </label>
                  <label>
                    <span>景别</span>
                    <el-input v-model="editForm.shotSize" />
                  </label>
                </div>
                <label>
                  <span>时长（秒）</span>
                  <el-input-number
                    v-model="editForm.durationSeconds"
                    class="duration-input"
                    :min="0"
                    :max="600"
                    controls-position="right"
                  />
                </label>
              </section>

              <section class="shot-drawer-section">
                <h3>画面调度</h3>
                <label>
                  <span>机位与运镜</span>
                  <el-input v-model="editForm.camera" />
                </label>
                <label>
                  <span>画面动作</span>
                  <el-input v-model="editForm.action" type="textarea" :rows="5" />
                </label>
              </section>

              <section class="shot-drawer-section">
                <h3>台词</h3>
                <label>
                  <span>对白/旁白</span>
                  <el-input v-model="editForm.dialogue" type="textarea" :rows="3" />
                </label>
              </section>

              <section class="shot-drawer-section">
                <h3>生图设定</h3>
                <label>
                  <span>生图提示词（键入 @ 引用资产）</span>
                  <AssetPromptEditor
                    v-model="editForm.prompt"
                    :assets="assetOptions"
                    placeholder="输入提示词，键入 @ 从资产库选择引用"
                  />
                </label>
                <div v-if="selectedShot.referenceMediaPublicId" class="shot-frame-preview">
                  <el-image
                    class="shot-frame-preview__image"
                    :src="mediaContentUrl(projectPublicId, selectedShot.referenceMediaPublicId)"
                    :preview-src-list="[mediaContentUrl(projectPublicId, selectedShot.referenceMediaPublicId)]"
                    preview-teleported
                    hide-on-click-modal
                  />
                  <span class="shot-frame-preview__hint">当前分镜图，点击查看原图</span>
                </div>
                <div class="shot-frame-tools">
                  <input
                    ref="shotImageUploadInput"
                    class="shot-image-upload-input"
                    type="file"
                    accept="image/png,image/jpeg,image/jpg,image/webp"
                    @change="onShotImageFileChange"
                  />
                  <el-button
                    class="ghost-button"
                    :loading="uploadingShotImage"
                    :disabled="selectedShot.status === 'locked' || uploadingShotImage || deletingShotImage"
                    @click="triggerShotImageUpload"
                  >
                    <el-icon><Upload /></el-icon>
                    上传分镜图
                  </el-button>
                  <el-button
                    v-if="selectedShot.referenceMediaPublicId"
                    class="danger-button"
                    :loading="deletingShotImage"
                    :disabled="selectedShot.status === 'locked' || uploadingShotImage || deletingShotImage"
                    @click="deleteShotImage"
                  >
                    <el-icon><Delete /></el-icon>
                    删除分镜图
                  </el-button>
                  <span class="shot-frame-tools__hint">支持 PNG/JPEG/WebP，最大 20MB</span>
                </div>
              </section>

              <section class="shot-drawer-section">
                <h3>镜头视频</h3>
                <div v-if="supportsTailFrame" class="tail-frame-control">
                  <div class="tail-frame-control__header">
                    <span>尾帧图</span>
                    <el-tag size="small" effect="plain" :type="tailFrameRequired ? 'warning' : 'info'">
                      {{ tailFrameRequired ? '必需' : '可选' }}
                    </el-tag>
                  </div>
                  <div v-if="selectedShot.lastFrameMediaPublicId" class="tail-frame-preview">
                    <el-image
                      class="tail-frame-preview__image"
                      :src="mediaContentUrl(projectPublicId, selectedShot.lastFrameMediaPublicId)"
                      :preview-src-list="[mediaContentUrl(projectPublicId, selectedShot.lastFrameMediaPublicId)]"
                      preview-teleported
                      hide-on-click-modal
                      fit="cover"
                    />
                    <span class="tail-frame-preview__meta">独立尾帧</span>
                  </div>
                  <div class="shot-frame-tools">
                    <input
                      ref="lastFrameUploadInput"
                      class="shot-image-upload-input"
                      type="file"
                      accept="image/png,image/jpeg,image/jpg,image/webp"
                      @change="onLastFrameFileChange"
                    />
                    <el-button
                      class="ghost-button"
                      :loading="uploadingLastFrame"
                      :disabled="selectedShot.status === 'locked' || uploadingLastFrame || deletingLastFrame"
                      @click="triggerLastFrameUpload"
                    >
                      <el-icon><Upload /></el-icon>
                      {{ selectedShot.lastFrameMediaPublicId ? '替换尾帧' : '上传尾帧' }}
                    </el-button>
                    <el-button
                      v-if="selectedShot.lastFrameMediaPublicId"
                      class="danger-button"
                      :loading="deletingLastFrame"
                      :disabled="selectedShot.status === 'locked' || uploadingLastFrame || deletingLastFrame"
                      @click="deleteLastFrame"
                    >
                      <el-icon><Delete /></el-icon>
                      清除尾帧
                    </el-button>
                  </div>
                </div>
                <div class="video-settings-panel">
                  <div class="video-setting-group">
                    <span class="video-setting-label">视频比例</span>
                    <div class="video-ratio-options" role="radiogroup" aria-label="视频比例">
                      <button
                        v-for="ratioOption in VIDEO_RATIO_OPTIONS"
                        :key="ratioOption"
                        type="button"
                        class="video-option-button video-ratio-option"
                        :class="{ selected: effectiveVideoRatio === ratioOption }"
                        :aria-checked="effectiveVideoRatio === ratioOption"
                        role="radio"
                        @click="selectVideoRatio(ratioOption)"
                      >
                        <span class="video-ratio-glyph" :data-ratio="ratioOption" aria-hidden="true" />
                        <span>{{ ratioOption }}</span>
                      </button>
                    </div>
                  </div>

                  <div class="video-setting-group">
                    <span class="video-setting-label">分辨率</span>
                    <div class="video-resolution-options" role="radiogroup" aria-label="视频分辨率">
                      <button
                        v-for="option in VIDEO_RESOLUTION_OPTIONS"
                        :key="option.value"
                        type="button"
                        class="video-option-button"
                        :class="{ selected: effectiveVideoResolution === option.value }"
                        :disabled="!supportedVideoResolutions.has(option.value)"
                        :aria-checked="effectiveVideoResolution === option.value"
                        :aria-disabled="!supportedVideoResolutions.has(option.value)"
                        role="radio"
                        @click="selectVideoResolution(option.value)"
                      >
                        {{ option.label }}
                      </button>
                    </div>
                  </div>

                  <div class="video-setting-group">
                    <span class="video-setting-label">视频时长</span>
                    <div class="video-duration-mode" role="group" aria-label="视频时长模式">
                      <button
                        type="button"
                        :class="{ selected: videoDurationMode === 'seconds' }"
                        :aria-pressed="videoDurationMode === 'seconds'"
                        @click="videoDurationMode = 'seconds'"
                      >
                        按秒数
                      </button>
                      <button
                        type="button"
                        :class="{ selected: videoDurationMode === 'smart' }"
                        :aria-pressed="videoDurationMode === 'smart'"
                        @click="videoDurationMode = 'smart'"
                      >
                        智能时长
                      </button>
                    </div>
                    <div class="video-setting-range">
                      <el-slider
                        v-model="videoDurationSeconds"
                        :min="4"
                        :max="15"
                        :step="1"
                        :show-tooltip="false"
                        :disabled="videoSubmitting"
                        aria-label="视频时长秒数"
                      />
                      <div class="video-setting-value" aria-live="polite">
                        <strong>{{ videoDurationSeconds }}</strong>
                        <span>秒</span>
                      </div>
                    </div>
                  </div>

                  <div class="video-setting-group">
                    <span class="video-setting-label">选择生成数量</span>
                    <div class="video-setting-range">
                      <el-slider
                        v-model="videoQuantity"
                        :min="1"
                        :max="4"
                        :step="1"
                        :show-tooltip="false"
                        :disabled="videoSubmitting"
                        aria-label="候选视频生成数量"
                      />
                      <div class="video-setting-value" aria-live="polite">
                        <strong>{{ videoQuantity }}</strong>
                        <span>条</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="video-gen-controls">
                  <div class="video-inherited-spec" aria-label="继承的分镜视频规格">
                    <span>输出规格</span>
                    <strong>{{ inheritedVideoSpec }}</strong>
                  </div>
                  <el-checkbox v-model="videoGenerateAudio" :disabled="videoSubmitting">音画同生</el-checkbox>
                  <el-button
                    class="ghost-button"
                    :loading="videoSubmitting"
                    :disabled="Boolean(videoGenerationBlockReason) || selectedShot.status === 'locked' || videoSubmitting"
                    :title="videoGenerationBlockReason"
                    @click="submitShotVideos([selectedShot.publicId], false, {
                      durationSeconds: videoDurationSeconds,
                      quantity: videoQuantity,
                      ratio: videoRatioOverride,
                      resolution: videoResolutionOverride,
                    })"
                  >
                    <el-icon><VideoCamera /></el-icon>
                    生成候选视频
                  </el-button>
                </div>
                <p v-if="videoGenerationBlockReason" class="video-hint" role="status">
                  {{ videoGenerationBlockReason }}
                </p>
                <div v-loading="shotVideosLoading" class="shot-video-list" element-loading-background="rgba(7, 10, 16, 0.7)">
                  <div
                    v-for="media in shotVideos"
                    :key="media.publicId"
                    class="shot-video-item"
                    :class="{ selected: media.mediaRole === 'final' }"
                  >
                    <video
                      class="shot-video-item__player"
                      controls
                      preload="metadata"
                      :src="mediaContentUrl(projectPublicId, media.publicId)"
                    />
                    <div class="shot-video-item__meta">
                      <el-tag v-if="media.mediaRole === 'final'" type="success" effect="dark" size="small">已选定</el-tag>
                      <span class="shot-video-item__time">{{ new Date(media.createdAt).toLocaleString() }}</span>
                      <div class="shot-video-item__actions">
                        <el-button
                          v-if="media.mediaRole !== 'final'"
                          size="small"
                          text
                          class="shot-video-item__select"
                          :loading="selectingVideoId === media.publicId"
                          @click="selectShotVideo(media.publicId)"
                        >
                          设为选定
                        </el-button>
                        <el-button
                          text
                          circle
                          class="shot-video-item__delete"
                          :loading="deletingVideoId === media.publicId"
                          :disabled="Boolean(deletingVideoId)"
                          title="删除视频"
                          aria-label="删除视频"
                          @click="deleteShotVideo(media)"
                        >
                          <el-icon><Delete /></el-icon>
                        </el-button>
                      </div>
                    </div>
                  </div>
                  <p v-if="!shotVideosLoading && shotVideos.length === 0" class="video-hint">暂无候选视频，生成后可在此择优</p>
                </div>
              </section>
            </div>

            <footer class="shot-drawer-footer">
              <el-button class="ghost-button" :loading="lockingShot" @click="toggleShotLock">
                <el-icon><Lock v-if="selectedShot.status !== 'locked'" /><Unlock v-else /></el-icon>
                {{ selectedShot.status === 'locked' ? '解锁' : '锁定' }}
              </el-button>
              <el-button class="danger-button" :disabled="selectedShot.status === 'locked'" @click="deleteShot">
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
              <el-button
                class="primary-button"
                type="primary"
                :loading="savingShot"
                :disabled="selectedShot.status === 'locked'"
                @click="saveShot"
              >
                <el-icon><Check /></el-icon>
                保存修改
              </el-button>
            </footer>
          </div>
        </el-drawer>

        <el-dialog
          v-model="gridDialogVisible"
          class="production-grid-dialog"
          title="宫格分镜图"
          width="720px"
          align-center
        >
          <div v-loading="gridMediaLoading" class="grid-media-list" element-loading-background="rgba(7, 10, 16, 0.7)">
            <div v-for="media in gridMediaList" :key="media.publicId" class="grid-media-item">
              <el-image
                class="grid-media-item__image"
                fit="contain"
                :src="mediaThumbnailUrl(projectPublicId, media.publicId)"
                :preview-src-list="gridMediaList.map((item) => mediaContentUrl(projectPublicId, item.publicId))"
                :initial-index="gridMediaList.indexOf(media)"
                preview-teleported
                hide-on-click-modal
              />
              <div class="grid-media-item__meta">
                <strong>{{ gridMediaLabel(media) }}</strong>
                <span>{{ new Date(media.createdAt).toLocaleString() }}</span>
              </div>
            </div>
            <el-empty
              v-if="!gridMediaLoading && gridMediaList.length === 0"
              description="当前分集尚未生成宫格分镜图"
            />
          </div>
        </el-dialog>
      </section>
    </div>

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Back,
  Check,
  Close,
  Connection,
  Delete,
  Document,
  Film,
  Folder,
  List,
  Lock,
  Picture,
  Refresh,
  Setting,
  Tickets,
  Unlock,
  Upload,
  VideoCamera,
  VideoPlay,
} from '@element-plus/icons-vue'
import { listProjectEpisodesApi, type ScriptEpisodeListItem } from '@/api/script'
import {
  deleteStoryboardShotApi,
  generateStoryboardGridImagesApi,
  generateStoryboardShotVideosApi,
  generateStoryboardsApi,
  listStoryboardShotsApi,
  lockStoryboardShotApi,
  unlockStoryboardShotApi,
  updateStoryboardShotApi,
  type StoryboardShot,
  type StoryboardShotUpdatePayload,
} from '@/api/storyboard'
import {
  deleteProjectMediaApi,
  listProjectMediaApi,
  mediaContentUrl,
  mediaThumbnailUrl,
  selectProjectMediaApi,
  uploadProjectMediaApi,
  type MediaAssetRecord,
} from '@/api/media'
import { listManagedAssetsApi, type AssetManageItem, type AssetType } from '@/api/asset'
import { getTaskJobApi, listTaskJobsApi, type TaskJobResponse, type TaskJobStatus } from '@/api/task'
import {
  listDirectorManualsApi,
  listProjectsApi,
  listVisualStylesApi,
  updateProjectApi,
  type DirectorManualRecord,
  type ProjectPayload,
  type ProjectRecord,
  type VisualStyleRecord,
} from '@/api/project'
import { useProviderModels } from '@/composables/useProviderModels'
import ModelGroupSelect from '@/components/ModelGroupSelect.vue'
import Settings from '@/components/Settings.vue'
import AssetPromptEditor from '@/components/production/AssetPromptEditor.vue'

const ACTIVE_JOB_STATUSES: TaskJobStatus[] = ['pending', 'running', 'paused']
const POLL_ACTIVE_INTERVAL_MS = 2500
const STORYBOARD_TASK_TYPE = 'storyboard.generate'
const STORYBOARD_GRID_IMAGE_TASK_TYPE = 'storyboard.grid_image'
const STORYBOARD_SHOT_VIDEO_TASK_TYPE = 'storyboard.shot_video'
const STORYBOARD_TASK_TYPES = [
  STORYBOARD_TASK_TYPE,
  STORYBOARD_GRID_IMAGE_TASK_TYPE,
  STORYBOARD_SHOT_VIDEO_TASK_TYPE,
]
const SHOT_IMAGE_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
const SHOT_IMAGE_UPLOAD_MIME_TYPES = new Set(['image/png', 'image/jpeg', 'image/jpg', 'image/webp'])
type VideoDurationMode = 'seconds' | 'smart'

const VIDEO_RATIO_OPTIONS = ['21:9', '16:9', '4:3', '1:1', '3:4', '9:16'] as const
const VIDEO_RESOLUTION_OPTIONS = [
  { label: '480P', value: '480p' },
  { label: '720P', value: '720p' },
  { label: '1080P', value: '1080p' },
  { label: '4K', value: '4k' },
] as const
const SEEDANCE_IMAGE_SIZE_RESOLUTION: Record<string, string> = {
  '1K': '720p',
  '2K': '1080p',
  '4K': '4k',
}

const router = useRouter()
const route = useRoute()

const resolveQueryString = (value: unknown) => {
  if (Array.isArray(value)) return String(value[0] ?? '')
  return typeof value === 'string' ? value : ''
}

const projectPublicId = ref(
  (resolveQueryString(route.query.id) || resolveQueryString(route.query.projectId)).trim(),
)
const currentProject = ref<ProjectRecord | null>(null)
const settingsVisible = ref(false)
const loading = ref(false)
const episodesLoading = ref(false)
const shotsLoading = ref(false)
const submitting = ref(false)
const savingShot = ref(false)
const lockingShot = ref(false)
const deletingShots = ref(false)
const uploadingShotImage = ref(false)
const deletingShotImage = ref(false)
const uploadingLastFrame = ref(false)
const deletingLastFrame = ref(false)

const episodes = ref<ScriptEpisodeListItem[]>([])
const shots = ref<StoryboardShot[]>([])
const visualStyles = ref<VisualStyleRecord[]>([])
const directorManuals = ref<DirectorManualRecord[]>([])
const selectedEpisodeId = ref('')
const selectedShotId = ref('')
const shotDrawerVisible = ref(false)
const activeJob = ref<TaskJobResponse | null>(null)
const activeJobTimer = ref<ReturnType<typeof setTimeout> | null>(null)

// 分镜表多选：批量生成分镜图/分镜脚本的目标镜头。
const shotTableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedShotRows = ref<StoryboardShot[]>([])
const shotImageUploadInput = ref<HTMLInputElement | null>(null)
const lastFrameUploadInput = ref<HTMLInputElement | null>(null)

// 项目资产选项：供引用资产选择器与提示词 @ 引用使用（配图 + 名称）。
interface AssetOption {
  publicId: string
  name: string
  assetType: AssetType | ''
  variantLabel: string
  thumbnailUrl: string
}
const assetOptions = ref<AssetOption[]>([])

// 分辨率档位 → 允许的宫格规格：与后端校验规则保持一致；1 宫格为单帧首帧图，各档位可用。
const GRID_SIZES_BY_IMAGE_SIZE: Record<'1K' | '2K' | '4K', number[]> = {
  '1K': [1, 4],
  '2K': [1, 4, 9, 16],
  '4K': [1, 4, 9, 16, 25],
}

const gridImageSize = ref<'1K' | '2K' | '4K'>('4K')
const gridSize = ref(1)
const gridImageSizeOptions = computed<Array<'1K' | '2K' | '4K'>>(() => {
  const modelId = (currentProject.value?.video_model || '').trim().toLowerCase()
  if (!modelId.startsWith('doubao-seedance-2-0-')) return ['1K', '2K', '4K']
  if (modelId.includes('-fast-') || modelId.includes('-mini-')) return ['1K']
  return ['1K', '2K', '4K']
})
const gridSizeOptions = computed(() => GRID_SIZES_BY_IMAGE_SIZE[gridImageSize.value])
const gridSubmitting = ref(false)
const gridDialogVisible = ref(false)
const gridMediaLoading = ref(false)
const gridMediaList = ref<MediaAssetRecord[]>([])

const {
  loading: modelsLoading,
  load: loadProviderModels,
  textModelGroups,
  imageModelGroups,
} = useProviderModels()

const imageModelId = ref('')
const projectFieldSaving = ref(false)

const generateForm = reactive({
  modelId: '',
  artStyle: '',
  directorStyle: '',
})

const editForm = reactive({
  sceneNumber: '',
  shotSize: '',
  camera: '',
  action: '',
  dialogue: '',
  durationSeconds: 0,
  assetSelection: [] as string[],
  prompt: '',
  negativePrompt: '',
})

const assetByPublicId = computed(() => new Map(assetOptions.value.map((asset) => [asset.publicId, asset])))
const assetByName = computed(() => new Map(assetOptions.value.map((asset) => [asset.name, asset])))

// 资产选项缺失（已删除/未加载）时，用镜头上存储的名称兜底展示。
const assetChipFor = (assetPublicId: string): AssetOption => {
  const known = assetByPublicId.value.get(assetPublicId)
  if (known) return known
  const shot = selectedShot.value
  const ids = (shot?.assetPublicIds || '').split(',').map((item) => item.trim())
  const names = (shot?.assetNames || '').split(',').map((item) => item.trim())
  const index = ids.indexOf(assetPublicId)
  return {
    publicId: assetPublicId,
    name: (index >= 0 && names[index]) || assetPublicId,
    assetType: '',
    variantLabel: '',
    thumbnailUrl: '',
  }
}

const SYNCED_ASSET_PROMPT_PREFIX = '引用资产：'

/** 剥离旧版同步机制在提示词末尾追加的「引用资产：@…」行（历史数据清洗）。 */
const promptWithoutSyncedAssetLine = (prompt: string) => {
  const lines = prompt.trimEnd().split(/\r?\n/)
  if (lines.length === 0) return ''
  const lastLine = lines[lines.length - 1]?.trim() || ''
  if (lastLine.startsWith(SYNCED_ASSET_PROMPT_PREFIX)) lines.pop()
  return lines.join('\n').trimEnd()
}

// 与后端 _MENTION_RE 保持一致：@资产名 到空白或常见标点为止。
const MENTION_RE = /@([^\s@，。；、！？…,;.!?()（）【】[\]{}<>：:"'`]{1,60})/g

const promptMentionedAssets = computed(() => {
  const seen = new Set<string>()
  const result: AssetOption[] = []
  const pattern = new RegExp(MENTION_RE.source, 'g')
  let match = pattern.exec(editForm.prompt)
  while (match) {
    const asset = assetByName.value.get(match[1].trim())
    if (asset && !seen.has(asset.publicId)) {
      seen.add(asset.publicId)
      result.push(asset)
    }
    match = pattern.exec(editForm.prompt)
  }
  return result
})

// 提示词文本是引用的唯一来源：正文 @ 芯片变化时反向同步下拉选中态。
watch(promptMentionedAssets, (assets) => {
  const ids = assets.map((asset) => asset.publicId)
  if (ids.join(',') !== editForm.assetSelection.join(',')) {
    editForm.assetSelection = ids
  }
})

const currentShots = computed(() =>
  shots.value
    .filter((shot) => !selectedEpisodeId.value || shot.episodePublicId === selectedEpisodeId.value)
    .sort((a, b) => a.shotIndex - b.shotIndex),
)

const selectedShot = computed(() =>
  currentShots.value.find((shot) => shot.publicId === selectedShotId.value) ?? null,
)

const supportsTailFrame = computed(() => (
  currentProject.value?.mode === 'startEndRequired'
  || currentProject.value?.mode === 'endFrameOptional'
  || currentProject.value?.mode === 'startFrameOptional'
))

const tailFrameRequired = computed(() => (
  currentProject.value?.mode === 'startEndRequired'
  || currentProject.value?.mode === 'startFrameOptional'
))

const shotImageMedia = ref<MediaAssetRecord[]>([])
const videoGenerateAudio = ref(false)
const videoSubmitting = ref(false)
const shotVideos = ref<MediaAssetRecord[]>([])
const shotVideosLoading = ref(false)
const selectingVideoId = ref('')
const deletingVideoId = ref('')
const videoDurationMode = ref<VideoDurationMode>('seconds')
const videoDurationSeconds = ref(5)
const videoQuantity = ref(1)
/** 比例/分辨率覆写：空串表示沿用继承规格（比例来自项目、分辨率来自分镜图）。 */
const videoRatioOverride = ref('')
const videoResolutionOverride = ref('')

const clampVideoDuration = (value: number) => Math.max(4, Math.min(15, Math.round(value || 5)))

const selectedStoryboardFrameMedia = computed(() => {
  const mediaPublicId = selectedShot.value?.referenceMediaPublicId?.trim() || ''
  return shotImageMedia.value.find((media) => media.publicId === mediaPublicId) ?? null
})

const storyboardFrameSpec = computed(() => {
  const frame = selectedStoryboardFrameMedia.value
  const videoModelId = (currentProject.value?.video_model || '').trim().toLowerCase()
  let resolution = ''
  let ratio = currentProject.value?.video_ratio || ''
  if (frame) {
    try {
      const params = JSON.parse(frame.params || '{}') as {
        image_size?: string
        video_resolution?: string
        video_ratio?: string
      }
      const legacyResolution = videoModelId.startsWith('doubao-seedance-2-0-')
        ? SEEDANCE_IMAGE_SIZE_RESOLUTION[String(params.image_size || '').trim().toUpperCase()] || ''
        : ''
      resolution = String(params.video_resolution || legacyResolution).trim().toLowerCase()
      ratio = String(params.video_ratio || ratio).trim()
    } catch {
      // 历史媒体参数缺失时仍使用项目比例和真实像素。
    }
  }
  return {
    resolution,
    ratio,
    width: Number(frame?.width || 0),
    height: Number(frame?.height || 0),
  }
})

const supportedVideoResolutions = computed<Set<string>>(() => {
  const modelId = (currentProject.value?.video_model || '').trim().toLowerCase()
  if (!modelId.startsWith('doubao-seedance-2-0-')) {
    return new Set(VIDEO_RESOLUTION_OPTIONS.map((option) => option.value))
  }
  return modelId.includes('-fast-') || modelId.includes('-mini-')
    ? new Set(['480p', '720p'])
    : new Set(['480p', '720p', '1080p', '4k'])
})

/** 生效比例/分辨率：优先用户覆写，否则取继承规格。 */
const effectiveVideoRatio = computed(() => videoRatioOverride.value || storyboardFrameSpec.value.ratio)
const effectiveVideoResolution = computed(() => (
  videoResolutionOverride.value || storyboardFrameSpec.value.resolution
))

const selectVideoRatio = (value: string) => {
  videoRatioOverride.value = value === storyboardFrameSpec.value.ratio ? '' : value
}

const selectVideoResolution = (value: string) => {
  if (!supportedVideoResolutions.value.has(value)) return
  videoResolutionOverride.value = value === storyboardFrameSpec.value.resolution ? '' : value
}

const inheritedVideoSpec = computed(() => {
  if (!selectedShot.value?.referenceMediaPublicId) return '等待分镜图'
  if (!selectedStoryboardFrameMedia.value) return '读取中'
  const spec = storyboardFrameSpec.value
  const dimensions = spec.width > 0 && spec.height > 0 ? `${spec.width}×${spec.height}` : ''
  return [spec.resolution, dimensions, spec.ratio].filter(Boolean).join(' · ') || '等待规格校验'
})

const videoGenerationBlockReason = computed(() => {
  const shot = selectedShot.value
  if (!shot?.referenceMediaPublicId) return '该镜头尚无分镜图，请先生成或上传分镜图'
  if (!currentProject.value?.video_model) return '项目尚未绑定视频模型'
  if (currentProject.value.mode === 'text') return '当前项目为纯文本视频模式，不能使用分镜图生成视频'
  if (tailFrameRequired.value && !shot.lastFrameMediaPublicId) return '当前视频模式要求先上传独立尾帧'
  if (
    storyboardFrameSpec.value.resolution
    && !supportedVideoResolutions.value.has(storyboardFrameSpec.value.resolution)
  ) return '当前正式分镜图分辨率不受项目绑定的视频模型支持'
  return ''
})

const totalDuration = computed(() =>
  currentShots.value.reduce((sum, shot) => sum + (Number(shot.durationSeconds) || 0), 0),
)

const shotCountByEpisode = computed(() => {
  const counts = new Map<string, number>()
  for (const shot of shots.value) {
    counts.set(shot.episodePublicId, (counts.get(shot.episodePublicId) || 0) + 1)
  }
  return counts
})

const hasActiveJob = computed(() =>
  Boolean(activeJob.value && ACTIVE_JOB_STATUSES.includes(activeJob.value.status)),
)

const activeJobId = computed(() => activeJob.value?.publicId || '')

const activeJobLabel = computed(() => {
  const job = activeJob.value
  if (!job) return '暂无分镜任务'
  const done = job.succeededCount + job.failedCount + job.canceledCount
  if (ACTIVE_JOB_STATUSES.includes(job.status)) return `生成中 ${done}/${job.totalCount}`
  if (job.status === 'succeeded') return `已完成 ${job.succeededCount}/${job.totalCount}`
  if (job.status === 'partial_failed') return `部分失败 ${job.failedCount}/${job.totalCount}`
  if (job.status === 'failed') return '生成失败'
  return job.name
})

const pad2 = (value: number) => String(value).padStart(2, '0')

const errorDetail = (error: unknown, fallback: string) => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) return detail.map((item) => String((item as { msg?: string }).msg || '')).filter(Boolean).join('；') || fallback
  if (error instanceof Error && error.message) return error.message
  return fallback
}

// 控制栏取值与项目配置强绑定：加载与回滚时均以项目字段为准。
const syncFormFromProject = () => {
  const project = currentProject.value
  generateForm.modelId = project?.text_model || ''
  generateForm.artStyle = project?.art_style || ''
  generateForm.directorStyle = project?.director_manual || ''
  imageModelId.value = project?.image_model || ''
}

const loadProject = async () => {
  const { data } = await listProjectsApi()
  currentProject.value = data.find((item) => item.public_id === projectPublicId.value) ?? null
  syncFormFromProject()
}

const loadStyles = async () => {
  const [styleResult, directorResult] = await Promise.all([
    listVisualStylesApi(),
    listDirectorManualsApi(),
  ])
  visualStyles.value = styleResult.data
  directorManuals.value = directorResult.data
}

const loadModels = async () => {
  await loadProviderModels()
}

const loadEpisodes = async () => {
  if (!projectPublicId.value) return
  episodesLoading.value = true
  try {
    const { data } = await listProjectEpisodesApi(projectPublicId.value)
    episodes.value = data
    if (!selectedEpisodeId.value && data.length > 0) {
      selectedEpisodeId.value = data[0].publicId
    }
  } finally {
    episodesLoading.value = false
  }
}

const loadShots = async () => {
  if (!projectPublicId.value) return
  shotsLoading.value = true
  try {
    const { data } = await listStoryboardShotsApi(projectPublicId.value)
    shots.value = data
    if (selectedShotId.value && !data.some((shot) => shot.publicId === selectedShotId.value)) {
      selectedShotId.value = ''
      shotDrawerVisible.value = false
    }
  } finally {
    shotsLoading.value = false
  }
}

// 资产选项分页拉取（manage 接口才带封面缩略图），拍平主资产与子资产。
const loadAssets = async () => {
  if (!projectPublicId.value) return
  const collected: AssetOption[] = []
  const toOption = (item: AssetManageItem): AssetOption => ({
    publicId: item.publicId,
    name: item.name,
    assetType: item.assetType,
    variantLabel: item.variantLabel || '',
    thumbnailUrl: item.thumbnailUrl || '',
  })
  let page = 1
  for (;;) {
    const { data } = await listManagedAssetsApi(projectPublicId.value, { page, pageSize: 100 })
    for (const item of data.items ?? []) {
      collected.push(toOption(item))
      for (const child of item.children ?? []) collected.push(toOption(child))
    }
    if (page >= (data.pages || 1)) break
    page += 1
  }
  assetOptions.value = collected
}

// 刷新后从任务列表恢复最近的分镜相关任务状态（分镜表/宫格分镜图），运行中的任务同时恢复轮询。
const restoreActiveJob = async () => {
  if (!projectPublicId.value || activeJob.value) return
  const { data } = await listTaskJobsApi(projectPublicId.value, { page: 1, pageSize: 50 })
  const storyboardJobs = (data.items ?? [])
    .filter((job) => STORYBOARD_TASK_TYPES.includes(job.taskType))
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
  if (storyboardJobs.length === 0) return
  const runningJob = storyboardJobs.find((job) => ACTIVE_JOB_STATUSES.includes(job.status))
  activeJob.value = runningJob ?? storyboardJobs[0]
  if (runningJob) startJobPolling(runningJob.publicId)
}

const reloadAll = async () => {
  loading.value = true
  try {
    await Promise.all([loadProject(), loadStyles(), loadModels(), loadEpisodes(), loadAssets(), restoreActiveJob()])
    await loadShots()
  } catch (error) {
    ElMessage.error(errorDetail(error, '加载制作工作台失败'))
  } finally {
    loading.value = false
  }
}

const selectEpisode = (episodeId: string) => {
  selectedEpisodeId.value = episodeId
  selectedShotId.value = ''
  shotDrawerVisible.value = false
}

const selectShot = (shot: StoryboardShot) => {
  selectedShotId.value = shot.publicId
  shotDrawerVisible.value = true
}

const onShotSelectionChange = (rows: StoryboardShot[]) => {
  selectedShotRows.value = rows
}

const selectedShotRowIds = computed(() => selectedShotRows.value.map((row) => row.publicId))

const clearShotSelection = () => {
  shotTableRef.value?.clearSelection()
  selectedShotRows.value = []
}

const deleteSelectedShots = async () => {
  if (!projectPublicId.value) return
  const deletableShots = selectedShotRows.value.filter((shot) => shot.status !== 'locked')
  const lockedCount = selectedShotRows.value.length - deletableShots.length
  if (deletableShots.length === 0) {
    ElMessage.warning('所选镜头均已锁定，无法删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${deletableShots.length} 个分镜镜头吗？${lockedCount > 0 ? ` 已锁定的 ${lockedCount} 个会跳过。` : ''}`,
      '批量删除分镜',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        customClass: 'production-dark-messagebox',
      },
    )
  } catch {
    return
  }

  deletingShots.value = true
  try {
    const results = await Promise.allSettled(
      deletableShots.map((shot) => deleteStoryboardShotApi(projectPublicId.value, shot.publicId)),
    )
    const deletedIds = new Set<string>()
    const failedResults: PromiseRejectedResult[] = []
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        deletedIds.add(deletableShots[index].publicId)
      } else {
        failedResults.push(result)
      }
    })

    if (deletedIds.size > 0) {
      shots.value = shots.value.filter((shot) => !deletedIds.has(shot.publicId))
      if (selectedShotId.value && deletedIds.has(selectedShotId.value)) {
        selectedShotId.value = ''
        shotDrawerVisible.value = false
      }
      clearShotSelection()
    }

    if (failedResults.length > 0) {
      ElMessage.error(errorDetail(failedResults[0].reason, `已删除 ${deletedIds.size} 个分镜，${failedResults.length} 个删除失败`))
      return
    }

    ElMessage.success(
      lockedCount > 0
        ? `已删除 ${deletedIds.size} 个分镜，跳过 ${lockedCount} 个已锁定镜头`
        : `已删除 ${deletedIds.size} 个分镜`,
    )
  } finally {
    deletingShots.value = false
  }
}

// 批量重生成勾选镜头的分镜脚本字段；模型按整集上下文重写，仅落库选中行。
const submitBatchScripts = async () => {
  if (!projectPublicId.value || !selectedEpisodeId.value || !generateForm.modelId) {
    ElMessage.warning('请先在左侧选择分集并设置文本模型')
    return
  }
  const shotIds = selectedShotRowIds.value
  if (shotIds.length === 0) {
    ElMessage.warning('请先勾选要重生成的镜头')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将重新生成选中 ${shotIds.length} 个镜头的分镜脚本（景别/运镜/画面动作/台词/提示词等），已锁定镜头会自动跳过。确认提交？`,
      '批量生成分镜脚本',
      {
        confirmButtonText: '提交',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'production-dark-messagebox',
      },
    )
  } catch {
    return
  }
  submitting.value = true
  try {
    const { data } = await generateStoryboardsApi(projectPublicId.value, {
      modelId: generateForm.modelId,
      episodePublicIds: [selectedEpisodeId.value],
      shotPublicIds: shotIds,
      artStyle: generateForm.artStyle,
      directorStyle: generateForm.directorStyle,
    })
    activeJob.value = data
    ElMessage.success('分镜脚本重生成任务已提交')
    startJobPolling(data.publicId)
  } catch (error) {
    ElMessage.error(errorDetail(error, '分镜脚本重生成任务提交失败'))
  } finally {
    submitting.value = false
  }
}

const syncEditForm = () => {
  const shot = selectedShot.value
  if (!shot) return
  editForm.sceneNumber = shot.sceneNumber
  editForm.shotSize = shot.shotSize
  editForm.camera = shot.camera
  editForm.action = shot.action
  editForm.dialogue = shot.dialogue
  editForm.durationSeconds = shot.durationSeconds
  editForm.assetSelection = (shot.assetPublicIds || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  // 历史数据清洗：剥离旧版同步产生的「引用资产：@…」尾行；
  // 引用列表里有而正文未 @ 的资产补写到末尾，此后提示词文本即引用的唯一来源。
  let prompt = promptWithoutSyncedAssetLine(shot.prompt)
  const missingTokens = editForm.assetSelection
    .map((assetPublicId) => assetChipFor(assetPublicId).name.trim())
    .filter((name) => name && !prompt.includes(`@${name}`))
    .map((name) => `@${name}`)
  if (missingTokens.length > 0) {
    prompt = `${prompt ? `${prompt}\n` : ''}${missingTokens.join(' ')}`
  }
  editForm.prompt = prompt
  editForm.negativePrompt = shot.negativePrompt
}

const submitGenerate = async () => {
  if (!projectPublicId.value || !selectedEpisodeId.value || !generateForm.modelId) {
    ElMessage.warning('请先在左侧选择分集并设置文本模型')
    return
  }
  submitting.value = true
  try {
    const { data } = await generateStoryboardsApi(projectPublicId.value, {
      modelId: generateForm.modelId,
      episodePublicIds: [selectedEpisodeId.value],
      artStyle: generateForm.artStyle,
      directorStyle: generateForm.directorStyle,
    })
    activeJob.value = data
    ElMessage.success('分镜生成任务已提交')
    startJobPolling(data.publicId)
  } catch (error) {
    ElMessage.error(errorDetail(error, '分镜生成任务提交失败'))
  } finally {
    submitting.value = false
  }
}

const startJobPolling = (jobId: string) => {
  stopJobPolling()
  const tick = async () => {
    if (!projectPublicId.value || !jobId) return
    try {
      const { data } = await getTaskJobApi(projectPublicId.value, jobId)
      activeJob.value = data
      if (ACTIVE_JOB_STATUSES.includes(data.status)) {
        activeJobTimer.value = setTimeout(tick, POLL_ACTIVE_INTERVAL_MS)
        return
      }
      await loadShots()
      if (data.taskType === STORYBOARD_SHOT_VIDEO_TASK_TYPE) void loadShotVideos()
      const jobName = data.taskType === STORYBOARD_SHOT_VIDEO_TASK_TYPE
        ? '镜头视频生成'
        : data.taskType === STORYBOARD_GRID_IMAGE_TASK_TYPE
          ? '分镜图生成'
          : '分镜生成'
      if (data.status === 'succeeded') ElMessage.success(`${jobName}完成`)
      else if (data.status === 'failed') ElMessage.error(`${jobName}失败，请查看任务详情`)
      else if (data.status === 'partial_failed') ElMessage.warning(`${jobName}部分失败，请查看任务详情`)
    } catch (error) {
      console.error('轮询分镜任务失败', error)
      activeJobTimer.value = setTimeout(tick, POLL_ACTIVE_INTERVAL_MS)
    }
  }
  activeJobTimer.value = setTimeout(tick, POLL_ACTIVE_INTERVAL_MS)
}

// 提交宫格分镜图生成：每个镜头一张宫格图；给定 shotIds 时仅生成勾选镜头。
const submitGridImages = async (onlyMissing: boolean, shotIds: string[] = []) => {
  if (!projectPublicId.value || !selectedEpisodeId.value) {
    ElMessage.warning('请先在左侧选择分集')
    return
  }
  if (currentShots.value.length === 0) {
    ElMessage.warning('当前分集暂无分镜，请先生成分镜表')
    return
  }
  gridSubmitting.value = true
  try {
    const { data } = await generateStoryboardGridImagesApi(projectPublicId.value, {
      gridSize: gridSize.value,
      imageSize: gridImageSize.value,
      episodePublicIds: [selectedEpisodeId.value],
      ...(shotIds.length > 0 ? { shotPublicIds: shotIds } : {}),
      onlyMissing,
      modelId: imageModelId.value,
    })
    activeJob.value = data
    ElMessage.success('分镜图生成任务已提交')
    startJobPolling(data.publicId)
  } catch (error) {
    ElMessage.error(errorDetail(error, '分镜图生成任务提交失败'))
  } finally {
    gridSubmitting.value = false
  }
}

const onGridImageCommand = (command: string | number | object) => {
  void submitGridImages(String(command) === 'missing')
}

// 宫格图现挂在镜头（scope=shot）上；拉取项目宫格图后按当前分集的镜头过滤。
const openGridDialog = async () => {
  if (!projectPublicId.value || !selectedEpisodeId.value) {
    ElMessage.warning('请先在左侧选择分集')
    return
  }
  gridDialogVisible.value = true
  gridMediaLoading.value = true
  try {
    const { data } = await listProjectMediaApi(projectPublicId.value, {
      mediaType: 'image',
      status: 'ready',
      scopeType: 'shot',
      mediaRole: 'grid',
      limit: 200,
    })
    const episodeShotIds = new Set(currentShots.value.map((shot) => shot.publicId))
    gridMediaList.value = data.filter((media) => episodeShotIds.has(media.scopePublicId))
  } catch (error) {
    ElMessage.error(errorDetail(error, '加载宫格分镜图失败'))
  } finally {
    gridMediaLoading.value = false
  }
}

const gridMediaLabel = (media: MediaAssetRecord) => {
  try {
    const params = JSON.parse(media.params || '{}') as {
      grid_size?: number
      image_size?: string
      shot_index?: number
    }
    const bits: string[] = []
    if (Number(params.grid_size)) {
      bits.push(Number(params.grid_size) === 1 ? '单帧' : `${Number(params.grid_size)} 宫格`)
    }
    if (params.image_size) bits.push(String(params.image_size))
    if (Number(params.shot_index)) bits.push(`镜头 #${Number(params.shot_index)}`)
    if (bits.length > 0) return bits.join(' · ')
  } catch {
    // params 非法时退回默认标签
  }
  return '分镜图'
}

const triggerShotImageUpload = () => {
  const shot = selectedShot.value
  if (!shot) return
  if (shot.status === 'locked') {
    ElMessage.warning('已锁定镜头不能上传分镜图')
    return
  }
  shotImageUploadInput.value?.click()
}

const onShotImageFileChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const shot = selectedShot.value
  if (!file || !shot || !projectPublicId.value) return
  if (shot.status === 'locked') {
    ElMessage.warning('已锁定镜头不能上传分镜图')
    return
  }

  const mimeType = (file.type || '').toLowerCase()
  if (!SHOT_IMAGE_UPLOAD_MIME_TYPES.has(mimeType)) {
    ElMessage.warning('分镜图仅支持 PNG/JPEG/WebP')
    return
  }
  if (file.size > SHOT_IMAGE_UPLOAD_MAX_BYTES) {
    ElMessage.warning('分镜图不能超过 20MB')
    return
  }

  const shotPublicId = shot.publicId
  uploadingShotImage.value = true
  try {
    const { data: media } = await uploadProjectMediaApi(projectPublicId.value, file, {
      scopeType: 'shot',
      scopePublicId: shotPublicId,
      mediaRole: 'final',
    })
    const { data } = await updateStoryboardShotApi(projectPublicId.value, shotPublicId, {
      referenceMediaPublicId: media.publicId,
    })
    replaceShot(data)
    await loadShotVideos()
    ElMessage.success('分镜图已上传')
  } catch (error) {
    ElMessage.error(errorDetail(error, '上传分镜图失败'))
  } finally {
    uploadingShotImage.value = false
  }
}

const deleteShotImage = async () => {
  const shot = selectedShot.value
  const mediaPublicId = shot?.referenceMediaPublicId?.trim() || ''
  if (!shot || !mediaPublicId || !projectPublicId.value) return
  if (shot.status === 'locked') {
    ElMessage.warning('已锁定镜头不能删除分镜图')
    return
  }

  try {
    await ElMessageBox.confirm('确定删除当前分镜图吗？镜头本身会保留。', '删除分镜图', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'production-dark-messagebox',
    })
  } catch {
    return
  }

  deletingShotImage.value = true
  try {
    const { data } = await updateStoryboardShotApi(projectPublicId.value, shot.publicId, {
      referenceMediaPublicId: '',
    })
    replaceShot(data)
    await loadShotVideos()
    try {
      await deleteProjectMediaApi(projectPublicId.value, mediaPublicId)
      ElMessage.success('分镜图已删除')
    } catch (error) {
      ElMessage.warning(errorDetail(error, '已解除分镜图引用，但媒体文件删除失败'))
    }
  } catch (error) {
    ElMessage.error(errorDetail(error, '删除分镜图失败'))
  } finally {
    deletingShotImage.value = false
  }
}

const triggerLastFrameUpload = () => {
  const shot = selectedShot.value
  if (!shot || !supportsTailFrame.value) return
  if (shot.status === 'locked') {
    ElMessage.warning('已锁定镜头不能上传尾帧')
    return
  }
  lastFrameUploadInput.value?.click()
}

const onLastFrameFileChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const shot = selectedShot.value
  if (!file || !shot || !projectPublicId.value || !supportsTailFrame.value) return
  if (shot.status === 'locked') {
    ElMessage.warning('已锁定镜头不能上传尾帧')
    return
  }
  const mimeType = (file.type || '').toLowerCase()
  if (!SHOT_IMAGE_UPLOAD_MIME_TYPES.has(mimeType)) {
    ElMessage.warning('尾帧仅支持 PNG/JPEG/WebP')
    return
  }
  if (file.size > SHOT_IMAGE_UPLOAD_MAX_BYTES) {
    ElMessage.warning('尾帧不能超过 20MB')
    return
  }

  const previousMediaPublicId = shot.lastFrameMediaPublicId?.trim() || ''
  uploadingLastFrame.value = true
  try {
    const { data: media } = await uploadProjectMediaApi(projectPublicId.value, file, {
      scopeType: 'shot',
      scopePublicId: shot.publicId,
      mediaRole: 'reference',
    })
    try {
      const { data } = await updateStoryboardShotApi(projectPublicId.value, shot.publicId, {
        lastFrameMediaPublicId: media.publicId,
      })
      replaceShot(data)
    } catch (error) {
      await deleteProjectMediaApi(projectPublicId.value, media.publicId).catch(() => undefined)
      throw error
    }
    if (previousMediaPublicId && previousMediaPublicId !== media.publicId) {
      await deleteProjectMediaApi(projectPublicId.value, previousMediaPublicId).catch(() => undefined)
    }
    await loadShotVideos()
    ElMessage.success(previousMediaPublicId ? '尾帧已替换' : '尾帧已上传')
  } catch (error) {
    ElMessage.error(errorDetail(error, '上传尾帧失败'))
  } finally {
    uploadingLastFrame.value = false
  }
}

const deleteLastFrame = async () => {
  const shot = selectedShot.value
  const mediaPublicId = shot?.lastFrameMediaPublicId?.trim() || ''
  if (!shot || !mediaPublicId || !projectPublicId.value) return
  if (shot.status === 'locked') {
    ElMessage.warning('已锁定镜头不能清除尾帧')
    return
  }
  try {
    await ElMessageBox.confirm('确定清除当前尾帧吗？', '清除尾帧', {
      confirmButtonText: '清除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'production-dark-messagebox',
    })
  } catch {
    return
  }

  deletingLastFrame.value = true
  try {
    const { data } = await updateStoryboardShotApi(projectPublicId.value, shot.publicId, {
      lastFrameMediaPublicId: '',
    })
    replaceShot(data)
    try {
      await deleteProjectMediaApi(projectPublicId.value, mediaPublicId)
      ElMessage.success('尾帧已清除')
    } catch (error) {
      ElMessage.warning(errorDetail(error, '已解除尾帧引用，但媒体文件删除失败'))
    }
    await loadShotVideos()
  } catch (error) {
    ElMessage.error(errorDetail(error, '清除尾帧失败'))
  } finally {
    deletingLastFrame.value = false
  }
}

const stopJobPolling = () => {
  if (activeJobTimer.value) {
    clearTimeout(activeJobTimer.value)
    activeJobTimer.value = null
  }
}

const saveShot = async () => {
  const shot = selectedShot.value
  if (!shot) return
  // 提示词文本中的 @ 引用即最终引用列表（芯片增删与手动键入均已收敛到文本）。
  const mergedAssetIds = promptMentionedAssets.value.map((asset) => asset.publicId)
  editForm.assetSelection = mergedAssetIds
  const payload: StoryboardShotUpdatePayload = {
    sceneNumber: editForm.sceneNumber,
    shotSize: editForm.shotSize,
    camera: editForm.camera,
    action: editForm.action,
    dialogue: editForm.dialogue,
    durationSeconds: editForm.durationSeconds,
    assetPublicIds: mergedAssetIds.join(','),
    assetNames: mergedAssetIds.map((assetPublicId) => assetChipFor(assetPublicId).name).join(','),
    prompt: editForm.prompt,
    negativePrompt: editForm.negativePrompt,
  }
  savingShot.value = true
  try {
    const { data } = await updateStoryboardShotApi(projectPublicId.value, shot.publicId, payload)
    replaceShot(data)
    ElMessage.success('分镜已保存')
  } catch (error) {
    ElMessage.error(errorDetail(error, '保存分镜失败'))
  } finally {
    savingShot.value = false
  }
}

const toggleShotLock = async () => {
  const shot = selectedShot.value
  if (!shot) return
  lockingShot.value = true
  try {
    const request = shot.status === 'locked' ? unlockStoryboardShotApi : lockStoryboardShotApi
    const { data } = await request(projectPublicId.value, shot.publicId)
    replaceShot(data)
  } catch (error) {
    ElMessage.error(errorDetail(error, '更新锁定状态失败'))
  } finally {
    lockingShot.value = false
  }
}

const deleteShot = async () => {
  const shot = selectedShot.value
  if (!shot) return
  try {
    await ElMessageBox.confirm('确定删除当前分镜镜头吗？', '删除分镜', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'production-dark-messagebox',
    })
    await deleteStoryboardShotApi(projectPublicId.value, shot.publicId)
    shots.value = shots.value.filter((item) => item.publicId !== shot.publicId)
    selectedShotId.value = ''
    shotDrawerVisible.value = false
    ElMessage.success('分镜已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorDetail(error, '删除分镜失败'))
  }
}

const replaceShot = (shot: StoryboardShot) => {
  const index = shots.value.findIndex((item) => item.publicId === shot.publicId)
  if (index >= 0) shots.value.splice(index, 1, shot)
  else shots.value.push(shot)
  selectedShotId.value = shot.publicId
}

type ProjectBoundField = 'text_model' | 'image_model' | 'art_style' | 'director_manual'

// 控制栏的模型与风格均为项目级配置，切换后立即持久化到当前项目；失败时回滚为项目当前值。
const persistProjectField = async (field: ProjectBoundField, value: string, label: string) => {
  const previous = currentProject.value?.[field] || ''
  if (!projectPublicId.value || value === previous) return
  projectFieldSaving.value = true
  try {
    const payload: Partial<ProjectPayload> = {}
    payload[field] = value
    const { data } = await updateProjectApi(projectPublicId.value, payload)
    currentProject.value = data
    syncFormFromProject()
    ElMessage.success(`${label}已更新`)
  } catch (error) {
    syncFormFromProject()
    ElMessage.error(errorDetail(error, `${label}更新失败`))
  } finally {
    projectFieldSaving.value = false
  }
}

const onTextModelChange = (value: string) => persistProjectField('text_model', value, '文本模型')
const onImageModelChange = (value: string) => persistProjectField('image_model', value, '生图模型')
const onArtStyleChange = (value: string) => persistProjectField('art_style', value, '艺术风格')
const onDirectorStyleChange = (value: string) => persistProjectField('director_manual', value, '导演风格')

const goProject = () => router.push('/project')

const goEditor = () => {
  if (!projectPublicId.value) return
  router.push({ path: '/editor', query: { id: projectPublicId.value } })
}

const goScript = () => {
  if (!projectPublicId.value) return router.push('/script')
  return router.push({ path: '/script', query: { id: projectPublicId.value } })
}

const goTasks = (jobPublicId: string | null | undefined = '') => {
  if (!projectPublicId.value) return
  const resolvedJobPublicId = String(jobPublicId || '').trim()
  router.push({
    path: '/tasks',
    query: {
      id: projectPublicId.value,
      type: 'storyboard',
      from: route.fullPath,
      ...(resolvedJobPublicId ? { job: resolvedJobPublicId } : {}),
    },
  })
}

const showComingSoon = () => {
  ElMessage.info('功能开发中')
}

const loadShotVideos = async () => {
  const shot = selectedShot.value
  if (!projectPublicId.value || !shot) {
    shotVideos.value = []
    shotImageMedia.value = []
    return
  }
  shotVideosLoading.value = true
  try {
    const [videoResult, imageResult] = await Promise.all([
      listProjectMediaApi(projectPublicId.value, {
        mediaType: 'video',
        status: 'ready',
        scopeType: 'shot',
        scopePublicId: shot.publicId,
        limit: 50,
      }),
      listProjectMediaApi(projectPublicId.value, {
        mediaType: 'image',
        status: 'ready',
        scopeType: 'shot',
        scopePublicId: shot.publicId,
        limit: 50,
      }),
    ])
    shotVideos.value = videoResult.data
    shotImageMedia.value = imageResult.data
  } catch (error) {
    ElMessage.error(errorDetail(error, '加载候选视频失败'))
  } finally {
    shotVideosLoading.value = false
  }
}

// 提交镜头视频生成：抽屉内单镜追加候选；批量条按勾选镜头提交。
const submitShotVideos = async (
  shotIds: string[],
  onlyMissing: boolean,
  options: { durationSeconds?: number; quantity?: number; ratio?: string; resolution?: string } = {},
) => {
  if (!projectPublicId.value || shotIds.length === 0) return
  videoSubmitting.value = true
  try {
    // 覆写为空串时省略，交由后端沿用继承规格。
    const { ratio, resolution, ...rest } = options
    const { data } = await generateStoryboardShotVideosApi(projectPublicId.value, {
      shotPublicIds: shotIds,
      onlyMissing,
      generateAudio: videoGenerateAudio.value,
      ...rest,
      ...(ratio ? { ratio } : {}),
      ...(resolution ? { resolution } : {}),
    })
    activeJob.value = data
    ElMessage.success('镜头视频生成任务已提交')
    startJobPolling(data.publicId)
  } catch (error) {
    ElMessage.error(errorDetail(error, '镜头视频任务提交失败'))
  } finally {
    videoSubmitting.value = false
  }
}

const selectShotVideo = async (mediaPublicId: string) => {
  if (!projectPublicId.value) return
  selectingVideoId.value = mediaPublicId
  try {
    await selectProjectMediaApi(projectPublicId.value, mediaPublicId)
    await loadShotVideos()
    ElMessage.success('已设为选定视频')
  } catch (error) {
    ElMessage.error(errorDetail(error, '设为选定失败'))
  } finally {
    selectingVideoId.value = ''
  }
}

const deleteShotVideo = async (media: MediaAssetRecord) => {
  if (!projectPublicId.value || deletingVideoId.value) return
  const isSelected = media.mediaRole === 'final'
  try {
    await ElMessageBox.confirm(
      isSelected
        ? '删除后该镜头将回到暂无选定视频状态，且无法恢复。'
        : '删除该候选视频后无法恢复。',
      '删除视频',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        customClass: 'production-dark-messagebox',
      },
    )
  } catch {
    return
  }

  deletingVideoId.value = media.publicId
  try {
    await deleteProjectMediaApi(projectPublicId.value, media.publicId)
    await loadShotVideos()
    ElMessage.success(isSelected ? '已删除选定视频' : '候选视频已删除')
  } catch (error) {
    ElMessage.error(errorDetail(error, '删除视频失败'))
  } finally {
    deletingVideoId.value = ''
  }
}

watch(selectedShot, () => {
  syncEditForm()
  videoDurationMode.value = 'seconds'
  videoDurationSeconds.value = clampVideoDuration(selectedShot.value?.durationSeconds || 5)
  videoQuantity.value = 1
  void loadShotVideos()
})

// 切换分辨率后若当前宫格规格不再可用，回落到该档位允许的最大规格。
watch(gridImageSize, () => {
  if (!gridSizeOptions.value.includes(gridSize.value)) {
    gridSize.value = gridSizeOptions.value[gridSizeOptions.value.length - 1]
  }
})

watch(gridImageSizeOptions, (options) => {
  if (!options.includes(gridImageSize.value)) {
    gridImageSize.value = options[0]
  }
}, { immediate: true })

onMounted(() => {
  void reloadAll()
})

onBeforeUnmount(stopJobPolling)
</script>

<style scoped>
.production-page {
  box-sizing: border-box;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  padding: 16px;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  background:
    radial-gradient(circle at top, rgba(100, 116, 139, 0.18) 0%, rgba(11, 13, 16, 0) 32%),
    linear-gradient(180deg, #0d1117 0%, #0b0d10 100%);
}

.app-shell {
  height: calc(100vh - 32px);
  height: calc(100dvh - 32px);
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 16px;
}

.sidebar {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.side-top,
.side-bottom {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.brand {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #0a0a0a;
  font-size: 20px;
  font-weight: 800;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, #f3d96b, #c4b5fd);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 6px 18px rgba(243, 217, 107, 0.18);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.brand:hover {
  transform: translateY(-1px);
}

.nav-btn {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 12px;
  color: #8b949e;
  background: transparent;
  cursor: pointer;
  font-size: 22px;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.nav-btn :deep(.el-icon) {
  font-size: 22px;
}

.nav-btn:hover {
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.05);
  transform: translateY(-1px);
}

.nav-btn.active {
  color: #dbeafe;
  border-color: rgba(37, 99, 235, 0.32);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.22), rgba(37, 99, 235, 0.12));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.main-panel {
  display: flex;
  min-width: 0;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.34) transparent;
  padding: 24px 28px 20px;
  gap: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.main-panel::-webkit-scrollbar {
  width: 8px;
}

.main-panel::-webkit-scrollbar-track {
  background: transparent;
}

.main-panel::-webkit-scrollbar-thumb {
  min-height: 48px;
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.32);
  background-clip: padding-box;
}

.main-panel::-webkit-scrollbar-thumb:hover {
  background: rgba(203, 213, 225, 0.46);
  background-clip: padding-box;
}

.page-header {
  display: flex;
  flex-shrink: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.page-header__left {
  min-width: 0;
}

.page-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  margin: 0;
  font-size: 32px;
  line-height: 1.1;
  font-weight: 800;
  background: linear-gradient(180deg, #ffffff 0%, #93a1b3 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.desc {
  margin: 6px 0 0;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.4;
}

.header-action {
  height: 38px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 10px;
  color: #c5cdd6;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 14px;
  font-weight: 500;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.header-action :deep(.el-icon) {
  font-size: 16px;
}

.header-action:hover,
.header-action:focus {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  transform: translateY(-1px);
}

.header-action:active {
  transform: translateY(0);
}

.control-panel,
.panel {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(13, 17, 23, 0.86);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.28);
}

.control-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.control-panel {
  flex-shrink: 0;
  border-radius: 12px;
  padding: 16px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: end;
}

.control-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.control-grid .field {
  width: 134px;
}

.field,
.shot-drawer-section label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.field > span,
.shot-drawer-section label > span {
  font-size: 12px;
  color: #8b949e;
  font-weight: 700;
}

.task-status {
  height: 36px;
  padding: 0 12px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #8b949e;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  white-space: nowrap;
}

.task-status.active {
  color: #bfdbfe;
  border-color: rgba(96, 165, 250, 0.35);
  background: rgba(37, 99, 235, 0.14);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #6b7280;
}

.task-status.active .status-dot {
  background: #60a5fa;
  box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.16);
}

.workbench-grid {
  flex: 1 1 auto;
  min-height: 560px;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  gap: 16px;
}

.panel {
  min-height: 0;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-head {
  min-height: 54px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.panel-head h2 {
  margin: 0;
  font-size: 15px;
}

.panel-head span {
  color: #8b949e;
  font-size: 12px;
}

.episode-list,
.shot-table-wrap {
  min-height: 0;
  flex: 1;
}

.episode-list {
  overflow: auto;
  padding: 10px;
}

.episode-item {
  width: 100%;
  min-height: 74px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  color: #c5cdd6;
  text-align: left;
  cursor: pointer;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 10px;
  align-items: baseline;
}

.episode-item:hover,
.episode-item.active {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(96, 165, 250, 0.34);
}

.episode-item strong {
  color: #93c5fd;
  font-size: 12px;
}

.episode-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.episode-item em {
  grid-column: 2;
  font-style: normal;
  color: #6e7681;
  font-size: 12px;
}

.shot-table-wrap {
  position: relative;
}

.editor-row.two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

:deep(.production-shot-drawer) {
  background: #0d1117;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: -24px 0 70px rgba(0, 0, 0, 0.5);
}

:deep(.production-shot-drawer .el-drawer__body) {
  padding: 0;
  overflow: hidden;
}

.shot-drawer-body {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.shot-drawer-head {
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.shot-drawer-head__info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.shot-drawer-badge {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #93c5fd;
  font-weight: 800;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  background: rgba(37, 99, 235, 0.16);
  border: 1px solid rgba(37, 99, 235, 0.32);
}

.shot-drawer-title h2 {
  margin: 0;
  font-size: 16px;
}

.shot-drawer-title p {
  margin: 4px 0 0;
  color: #8b949e;
  font-size: 12px;
}

.shot-drawer-head__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.shot-drawer-close {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: #8b949e;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease;
}

.shot-drawer-close:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}

.shot-drawer-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.shot-drawer-section {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}

.shot-drawer-section h3 {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #93c5fd;
}

.duration-input {
  width: 100%;
}

.shot-drawer-footer {
  padding: 14px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(13, 17, 23, 0.92);
}

.ghost-button,
.danger-button,
.primary-button {
  border-radius: 10px;
}

.ghost-button {
  color: #c5cdd6;
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
}

.ghost-button:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
}

.danger-button {
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.24);
}

.primary-button {
  background: #2563eb;
  border-color: #2563eb;
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner),
:deep(.el-input-number .el-input__wrapper),
:deep(.el-select__wrapper) {
  background-color: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: none;
}

:deep(.el-input__inner),
:deep(.el-textarea__inner),
:deep(.el-select__placeholder),
:deep(.el-select__selected-item) {
  color: #e6edf3;
}

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.035);
  --el-table-row-hover-bg-color: rgba(37, 99, 235, 0.12);
  --el-table-current-row-bg-color: rgba(37, 99, 235, 0.18);
  --el-table-text-color: #c5cdd6;
  --el-table-header-text-color: #8b949e;
  --el-table-border-color: rgba(255, 255, 255, 0.08);
  font-size: 12.5px;
}

/* 多选框暗黑适配：组件默认白底在暗色界面过亮。 */
:deep(.el-checkbox__inner) {
  background-color: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.28);
}

:deep(.el-checkbox__input.is-checked .el-checkbox__inner),
:deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner) {
  background-color: #2563eb;
  border-color: #2563eb;
}

:deep(.el-checkbox__input.is-disabled .el-checkbox__inner) {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
}

/* 非主色按钮的悬停/激活/文字态统一暗色，避免组件默认浅色背景露白。 */
:deep(.el-button:not(.el-button--primary):not(.el-button--danger)) {
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.08);
  --el-button-hover-border-color: rgba(255, 255, 255, 0.2);
  --el-button-hover-text-color: #fff;
  --el-button-active-bg-color: rgba(255, 255, 255, 0.12);
  --el-button-active-border-color: rgba(255, 255, 255, 0.24);
}

:deep(.el-button.is-text) {
  --el-fill-color-light: rgba(255, 255, 255, 0.08);
  --el-fill-color: rgba(255, 255, 255, 0.12);
}

.danger-button:hover {
  color: #fecaca;
  background: rgba(239, 68, 68, 0.16);
  border-color: rgba(239, 68, 68, 0.4);
}

/* 数字输入器增减按钮暗黑适配。 */
:deep(.el-input-number__increase),
:deep(.el-input-number__decrease) {
  background: rgba(255, 255, 255, 0.05);
  color: #8b949e;
}

:deep(.el-input-number__increase:hover),
:deep(.el-input-number__decrease:hover) {
  color: #e6edf3;
}

/* 多选选择器输入框内的已选标签暗黑适配。 */
:deep(.el-select__wrapper .el-tag) {
  background: rgba(37, 99, 235, 0.16);
  border-color: rgba(37, 99, 235, 0.3);
  color: #bfdbfe;
}

:deep(.el-select__wrapper .el-tag .el-tag__close) {
  color: #93c5fd;
}

:deep(.el-select__wrapper .el-tag .el-tag__close:hover) {
  color: #fff;
  background: rgba(37, 99, 235, 0.4);
}

.grid-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.grid-resolution-select {
  width: 80px;
}

.grid-size-select {
  width: 104px;
}

.grid-generate-button :deep(.el-button) {
  border: none;
}

.panel-head__right {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.panel-head-action {
  height: 28px;
  padding: 0 10px;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(37, 99, 235, 0.08);
}

.batch-bar__count {
  color: #bfdbfe;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.batch-bar__clear {
  margin-left: auto;
  color: #8b949e;
}

.asset-option {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.asset-option__thumb,
.asset-chip__thumb {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

.asset-option__thumb--empty,
.asset-chip__thumb--empty {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #6e7681;
  font-size: 11px;
}

.asset-option__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-option__meta {
  margin-left: auto;
  color: #6e7681;
  font-size: 12px;
  white-space: nowrap;
}

.asset-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.asset-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px 4px 4px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.asset-chip__thumb {
  cursor: zoom-in;
}

.asset-chip__name {
  color: #c5cdd6;
  font-size: 12px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shot-frame-thumb {
  width: 64px;
  height: 40px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  cursor: zoom-in;
  display: block;
  background: rgba(255, 255, 255, 0.04);
}

.shot-frame-empty {
  color: #6e7681;
  font-size: 12px;
}

.shot-frame-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 4px;
}

/* 分镜图按源图比例展示，占满抽屉内容区宽度。 */
.shot-frame-preview__image {
  width: 100%;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  cursor: zoom-in;
  background: rgba(255, 255, 255, 0.04);
}

.shot-frame-preview__image :deep(img) {
  display: block;
  width: 100%;
  height: auto;
}

.shot-frame-preview__hint {
  color: #6e7681;
  font-size: 12px;
}

/* 镜头视频：生成控件与候选列表暗色卡片。 */
.tail-frame-control {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 4px;
}

.tail-frame-control__header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #c9d1d9;
  font-size: 13px;
  font-weight: 600;
}

.tail-frame-preview {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tail-frame-preview__image {
  width: min(180px, 48%);
  aspect-ratio: 16 / 9;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  cursor: zoom-in;
}

.tail-frame-preview__meta {
  color: #8b949e;
  font-size: 12px;
}

.video-settings-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  background: #0b0e14;
}

.video-setting-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.video-setting-label {
  color: #c9d1d9;
  font-size: 13px;
  font-weight: 600;
}

.video-ratio-options,
.video-resolution-options,
.video-duration-mode {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.video-ratio-options {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.video-resolution-options {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.video-option-button,
.video-duration-mode button {
  min-width: 0;
  min-height: 40px;
  padding: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  background: #151a22;
  color: #9ba7b5;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color 180ms ease, background-color 180ms ease, color 180ms ease;
}

.video-option-button:hover:not(:disabled),
.video-duration-mode button:hover {
  border-color: rgba(96, 165, 250, 0.45);
  color: #dbeafe;
}

.video-option-button.selected,
.video-duration-mode button.selected {
  border-color: rgba(96, 165, 250, 0.7);
  background: rgba(59, 130, 246, 0.16);
  color: #eff6ff;
}

.video-option-button:disabled:not(.selected) {
  opacity: 0.38;
  cursor: not-allowed;
}

.video-option-button:focus-visible,
.video-duration-mode button:focus-visible {
  outline: 2px solid #60a5fa;
  outline-offset: 2px;
}

.video-ratio-option {
  min-height: 58px;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
}

.video-ratio-glyph {
  display: block;
  width: 18px;
  height: 10px;
  border: 1.5px solid currentColor;
  border-radius: 2px;
}

.video-ratio-glyph[data-ratio='21:9'] { width: 22px; height: 8px; }
.video-ratio-glyph[data-ratio='16:9'] { width: 20px; height: 11px; }
.video-ratio-glyph[data-ratio='4:3'] { width: 18px; height: 13px; }
.video-ratio-glyph[data-ratio='1:1'] { width: 13px; height: 13px; }
.video-ratio-glyph[data-ratio='3:4'] { width: 11px; height: 15px; }
.video-ratio-glyph[data-ratio='9:16'] { width: 8px; height: 16px; }

.video-duration-mode {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 3px;
  border-radius: 6px;
  background: #151a22;
}

.video-duration-mode button {
  border-color: transparent;
  background: transparent;
}

.video-setting-range {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 74px;
  align-items: center;
  gap: 14px;
  min-width: 0;
  padding-top: 2px;
}

.video-setting-range :deep(.el-slider) {
  --el-slider-main-bg-color: #60a5fa;
  --el-slider-runway-bg-color: rgba(148, 163, 184, 0.28);
  --el-slider-stop-bg-color: rgba(148, 163, 184, 0.28);
  min-width: 0;
}

.video-setting-range :deep(.el-slider__button) {
  width: 16px;
  height: 16px;
  border-color: #bfdbfe;
  background: #f8fafc;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
}

.video-setting-value {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 6px;
  background: #11161e;
  color: #94a3b8;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.video-setting-value strong {
  color: #f8fafc;
  font-size: 14px;
  font-weight: 600;
}

.video-gen-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.video-inherited-spec {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.035);
  color: #8b949e;
  font-size: 12px;
}

.video-inherited-spec strong {
  color: #d8dee9;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.video-hint {
  margin: 0;
  color: #6e7681;
  font-size: 12px;
}

.shot-video-list {
  min-height: 32px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.shot-video-item {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.03);
}

.shot-video-item.selected {
  border-color: rgba(34, 197, 94, 0.45);
}

.shot-video-item__player {
  display: block;
  width: 100%;
  max-height: 300px;
  background: #000;
}

.shot-video-item__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
}

.shot-video-item__time {
  min-width: 0;
  color: #6e7681;
  font-size: 12px;
}

.shot-video-item__actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.shot-video-item__select {
  color: #93c5fd;
}

.shot-video-item__delete {
  width: 40px;
  height: 40px;
  color: #f87171;
}

.shot-video-item__delete:hover:not(:disabled) {
  color: #fecaca;
  background: rgba(239, 68, 68, 0.12);
}

:deep(.el-checkbox__label) {
  color: #c5cdd6;
}

.shot-frame-tools {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 10px;
  margin-bottom: 4px;
}

.shot-frame-tools__hint {
  color: #6e7681;
  font-size: 12px;
}

.shot-image-upload-input {
  display: none;
}

.grid-media-list {
  min-height: 240px;
  max-height: 62vh;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  padding: 4px;
}

.grid-media-item {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  flex-direction: column;
}

.grid-media-item__image {
  width: 100%;
  height: 300px;
  cursor: zoom-in;
  background: rgba(0, 0, 0, 0.35);
}

.grid-media-item__meta {
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.grid-media-item__meta strong {
  color: #e6edf3;
  font-size: 13px;
}

.grid-media-item__meta span {
  color: #6e7681;
  font-size: 12px;
}

@media (max-width: 1280px) {
  .control-panel {
    grid-template-columns: minmax(0, 1fr);
  }

  .workbench-grid {
    flex: 0 0 auto;
    min-height: 0;
    grid-template-rows: auto;
    grid-template-columns: 220px minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  :deep(.production-shot-drawer) {
    width: 100% !important;
    max-width: 100vw;
  }

  .shot-drawer-head,
  .shot-drawer-footer {
    padding-inline: 16px;
  }

  .shot-drawer-scroll {
    padding-inline: 12px;
  }

  .editor-row.two {
    grid-template-columns: minmax(0, 1fr);
  }

  .video-settings-panel {
    gap: 18px;
    padding: 12px;
  }

  .video-ratio-options {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .video-setting-range {
    grid-template-columns: minmax(0, 1fr) 68px;
    gap: 12px;
  }

  .shot-video-item__meta {
    flex-wrap: wrap;
  }

  .shot-video-item__actions {
    margin-left: auto;
  }

  .shot-video-item__delete {
    width: 44px;
    height: 44px;
  }
}
</style>

<style>
.production-dark-select.el-popper {
  background-color: #14181f;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #e6edf3;
}

.production-dark-select.el-popper .el-select-dropdown__item {
  color: #c5cdd6;
}

.production-dark-select.el-popper .el-select-dropdown__item.is-hovering,
.production-dark-select.el-popper .el-select-dropdown__item:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.06);
}

.production-dark-select.el-popper .el-select-dropdown__item.is-selected {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.16);
}

.production-dark-select.el-popper .el-popper__arrow::before {
  background: #14181f;
  border-color: rgba(255, 255, 255, 0.08);
}

.production-dark-messagebox {
  background: #14181f;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
}

.production-dark-messagebox .el-message-box__title,
.production-dark-messagebox .el-message-box__message {
  color: #e6edf3;
}

.production-grid-dialog {
  background: #0d1117;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
}

.production-grid-dialog .el-dialog__title {
  color: #e6edf3;
}

.production-grid-dialog .el-dialog__body {
  padding-top: 8px;
}

</style>