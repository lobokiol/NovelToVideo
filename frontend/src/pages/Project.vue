<template>
  <main class="project-page">
    <div class="app-shell">
      <aside class="sidebar">
        <div class="side-top">
          <div class="brand" @click="goHome">AF</div>

          <el-tooltip content="项目" placement="right">
            <button class="nav-btn active" aria-label="项目" @click="router.push('/project')">
              <el-icon><Folder /></el-icon>
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
          <div>
            <h1 class="title">我的项目</h1>
            <p class="desc">管理项目、生成模式、状态和协作成员</p>
          </div>

          <el-button class="create-button" type="primary" size="large" @click="openCreateDialog">
            <el-icon><Plus /></el-icon>
            &nbsp;新建项目
          </el-button>
        </header>

        <section class="toolbar">
          <el-input
            v-model="searchKeyword"
            class="search-input"
            clearable
            placeholder="按项目名称搜索"
            @clear="loadProjects"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-button :loading="loading" @click="handleSearch">搜索</el-button>
          <el-button :loading="loading" @click="loadProjects">刷新</el-button>
        </section>

        <section
          v-loading="loading"
          class="project-grid"
          element-loading-background="rgba(13, 17, 23, 0.55)"
        >
          <el-empty
            v-if="!loading && projects.length === 0"
            class="empty-state"
            description="暂无项目"
          />

          <el-card
            v-for="project in pagedProjects"
            v-else
            :key="project.public_id"
            class="project-card"
            shadow="never"
            @click="openProject(project)"
          >
            <template #header>
              <div class="card-head">
                <h2 class="project-name">{{ project.name }}</h2>
                <el-tag class="source-tag" effect="plain" round>{{ contentTypeLabel(project.project_type) }}</el-tag>
              </div>
            </template>

            <div class="tag-row">
              <el-tag class="model-tag" type="primary" effect="plain" round>
                {{ getArtStyleLabel(project.art_style) || project.art_style || '未设置风格' }}
              </el-tag>
              <el-tag class="ratio-tag" effect="plain" round>
                {{ project.video_ratio }}
              </el-tag>
              <el-tag :type="project.disabled_at ? 'danger' : 'success'" effect="plain" round>
                {{ project.disabled_at ? '已禁用' : '可用' }}
              </el-tag>
            </div>

            <p class="summary">{{ project.intro || '暂无简介' }}</p>

            <footer class="card-footer">
              <time class="time">{{ formatDate(project.created_at) }}</time>

              <div class="actions">
                <el-tooltip content="任务" placement="top">
                  <el-button text circle class="icon-action" @click.stop="openProjectTasks(project)">
                    <el-icon><List /></el-icon>
                  </el-button>
                </el-tooltip>

                <el-tooltip content="成员" placement="top">
                  <el-button text circle class="icon-action" @click.stop="openMemberDialog(project)">
                    <el-icon><UserFilled /></el-icon>
                  </el-button>
                </el-tooltip>

                <el-tooltip :content="project.disabled_at ? '启用' : '禁用'" placement="top">
                  <el-button text circle class="icon-action" @click.stop="toggleProjectStatus(project)">
                    <el-icon><SwitchButton /></el-icon>
                  </el-button>
                </el-tooltip>

                <el-tooltip content="编辑" placement="top">
                  <el-button text circle class="icon-action" @click.stop="openEditDialog(project)">
                    <el-icon><EditPen /></el-icon>
                  </el-button>
                </el-tooltip>

                <el-tooltip content="删除" placement="top">
                  <el-button text circle class="icon-action delete" @click.stop="handleDeleteProject(project)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </el-tooltip>
              </div>
            </footer>
          </el-card>
        </section>

        <div class="pagination-wrap">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="projects.length"
            layout="prev, pager, next, total"
            background
          />
        </div>
      </section>
    </div>

    <el-dialog
      v-model="projectDialogVisible"
      :title="projectDialogTitle"
      width="1080px"
      destroy-on-close
      class="project-dark-dialog"
    >
      <el-form
        ref="projectFormRef"
        :model="projectForm"
        :rules="projectRules"
        class="project-form"
        label-position="top"
      >
        <div class="dialog-grid-2col">
          <!-- 左栏：基础信息 -->
          <div class="form-col form-col--left">
            <el-form-item label="项目名称" prop="name">
              <el-input v-model="projectForm.name" maxlength="100" placeholder="请输入项目名称" show-word-limit />
            </el-form-item>

            <div class="form-grid">
              <el-form-item label="项目类型" prop="project_type">
                <el-select v-model="projectForm.project_type" popper-class="project-dark-select" placeholder="选择项目类型">
                  <el-option label="基于小说" value="novel" />
                  <el-option label="基于剧本" value="script" />
                  <el-option label="原创短剧" value="original" />
                </el-select>
              </el-form-item>

              <el-form-item label="内容类型" prop="content_type">
                <el-input v-model="projectForm.content_type" placeholder="如:玄幻、科幻、言情" />
              </el-form-item>

              <el-form-item label="选择文本模型" prop="text_model">
                <el-select
                  v-model="projectForm.text_model"
                  clearable
                  filterable
                  :loading="modelProvidersLoading"
                  popper-class="project-dark-select project-model-select"
                  placeholder="请选择文本模型"
                >
                  <el-option v-if="textModelGroups.length === 0" disabled label="暂无可用文本模型" value="" />
                  <el-option-group
                    v-for="group in textModelGroups"
                    :key="group.key"
                    :label="group.platform"
                  >
                    <el-option
                      v-for="item in group.models"
                      :key="`${group.key}:${item.value}`"
                      :label="item.label"
                      :value="item.value"
                    >
                      <span class="model-option">
                        <span class="model-option__main">
                          <img v-if="group.icon" class="model-option__icon" :src="group.icon" :alt="group.platform" />
                          <span v-else class="model-option__fallback">{{ group.platform.slice(0, 1).toUpperCase() }}</span>
                          <span class="model-option__name">{{ item.label }}</span>
                        </span>
                        <span class="model-option__category">{{ item.category }}</span>
                      </span>
                    </el-option>
                  </el-option-group>
                </el-select>
              </el-form-item>

              <el-form-item label="选择图像模型" prop="image_model">
                <el-select
                  v-model="projectForm.image_model"
                  clearable
                  filterable
                  :loading="modelProvidersLoading"
                  popper-class="project-dark-select project-model-select"
                  placeholder="请选择图像模型"
                >
                  <el-option v-if="imageModelGroups.length === 0" disabled label="暂无可用图像模型" value="" />
                  <el-option-group
                    v-for="group in imageModelGroups"
                    :key="group.key"
                    :label="group.platform"
                  >
                    <el-option
                      v-for="item in group.models"
                      :key="`${group.key}:${item.value}`"
                      :label="item.label"
                      :value="item.value"
                    >
                      <span class="model-option">
                        <span class="model-option__main">
                          <img v-if="group.icon" class="model-option__icon" :src="group.icon" :alt="group.platform" />
                          <span v-else class="model-option__fallback">{{ group.platform.slice(0, 1).toUpperCase() }}</span>
                          <span class="model-option__name">{{ item.label }}</span>
                        </span>
                        <span class="model-option__category">{{ item.category }}</span>
                      </span>
                    </el-option>
                  </el-option-group>
                </el-select>
              </el-form-item>

              <el-form-item label="生成图像质量" prop="image_quality">
                <el-select v-model="projectForm.image_quality" popper-class="project-dark-select" placeholder="质量">
                  <el-option label="1K" value="1K" />
                  <el-option label="2K" value="2K" />
                  <el-option label="4K" value="4K" />
                </el-select>
              </el-form-item>

              <el-form-item label="选择视频模型" prop="video_model">
                <el-select
                  v-model="projectForm.video_model"
                  clearable
                  filterable
                  :loading="modelProvidersLoading"
                  popper-class="project-dark-select project-model-select"
                  placeholder="请选择视频模型"
                >
                  <el-option v-if="videoModelGroups.length === 0" disabled label="暂无可用视频模型" value="" />
                  <el-option-group
                    v-for="group in videoModelGroups"
                    :key="group.key"
                    :label="group.platform"
                  >
                    <el-option
                      v-for="item in group.models"
                      :key="`${group.key}:${item.value}`"
                      :label="item.label"
                      :value="item.value"
                    >
                      <span class="model-option">
                        <span class="model-option__main">
                          <img v-if="group.icon" class="model-option__icon" :src="group.icon" :alt="group.platform" />
                          <span v-else class="model-option__fallback">{{ group.platform.slice(0, 1).toUpperCase() }}</span>
                          <span class="model-option__name">{{ item.label }}</span>
                        </span>
                        <span class="model-option__category">{{ item.category }}</span>
                      </span>
                    </el-option>
                  </el-option-group>
                </el-select>
              </el-form-item>

              <el-form-item label="选择语音模型" prop="tts_model">
                <el-select
                  v-model="projectForm.tts_model"
                  clearable
                  filterable
                  :loading="modelProvidersLoading"
                  popper-class="project-dark-select project-model-select"
                  placeholder="请选择语音模型"
                >
                  <el-option v-if="ttsModelGroups.length === 0" disabled label="暂无可用语音模型" value="" />
                  <el-option-group
                    v-for="group in ttsModelGroups"
                    :key="group.key"
                    :label="group.platform"
                  >
                    <el-option
                      v-for="item in group.models"
                      :key="`${group.key}:${item.value}`"
                      :label="item.label"
                      :value="item.value"
                    >
                      <span class="model-option">
                        <span class="model-option__main">
                          <img v-if="group.icon" class="model-option__icon" :src="group.icon" :alt="group.platform" />
                          <span v-else class="model-option__fallback">{{ group.platform.slice(0, 1).toUpperCase() }}</span>
                          <span class="model-option__name">{{ item.label }}</span>
                        </span>
                        <span class="model-option__category">{{ item.category }}</span>
                      </span>
                    </el-option>
                  </el-option-group>
                </el-select>
              </el-form-item>

              <el-form-item label="视频生成模式" prop="mode">
                <el-select v-model="projectForm.mode" popper-class="project-dark-select" placeholder="模式">
                  <el-option label="文生视频" value="text" />
                  <el-option label="单图参考" value="singleImage" />
                  <el-option label="多图参考" value="multiReference" />
                  <el-option label="必须首尾帧" value="startEndRequired" />
                  <el-option label="尾帧可选" value="endFrameOptional" />
                  <el-option label="首帧可选" value="startFrameOptional" />
                </el-select>
              </el-form-item>
            </div>

            <el-form-item label="画幅比例" prop="video_ratio">
              <el-select v-model="projectForm.video_ratio" popper-class="project-dark-select">
                <el-option label="9:16 竖屏" value="9:16" />
                <el-option label="16:9 横屏" value="16:9" />
              </el-select>
            </el-form-item>

            <el-form-item label="项目简介" prop="intro">
              <el-input v-model="projectForm.intro" maxlength="2000" :rows="4" placeholder="一句话描述项目主题、世界观或目标受众" show-word-limit type="textarea" />
            </el-form-item>
          </div>

          <!-- 右栏：视觉风格 + 导演风格 -->
          <div class="form-col form-col--right">
            <section class="panel-card">
              <header class="panel-card__head">
                <div class="panel-card__title-actions">
                  <h3 class="panel-card__title">视觉风格</h3>
                  <el-button
                    class="panel-card__add"
                    type="primary"
                    size="small"
                    @click="openCreateStyleDialog"
                  >
                    <el-icon><Plus /></el-icon>
                    添加视觉风格
                  </el-button>
                </div>
                <span class="panel-card__hint">{{ activeArtStyleLabel || '未选择' }}</span>
              </header>
              <el-form-item prop="art_style" class="panel-card__field">
                <div
                  v-loading="artStylesLoading"
                  class="style-grid"
                  element-loading-background="rgba(13, 17, 23, 0.55)"
                >
                  <el-empty
                    v-if="!artStylesLoading && artStylePresets.length === 0"
                    class="style-empty"
                    description="暂无视觉风格"
                  />
                  <button
                    v-for="preset in artStylePresets"
                    :key="preset.style_path"
                    type="button"
                    class="style-card"
                    :class="{ 'is-active': projectForm.art_style === preset.style_path }"
                    @click="projectForm.art_style = preset.style_path"
                  >
                    <span
                      class="style-card__image"
                      :style="{ backgroundImage: getArtStyleBackground(preset) }"
                    ></span>
                    <span class="style-card__overlay"></span>
                    <span
                      class="style-card__zoom"
                      role="button"
                      tabindex="0"
                      aria-label="预览图片"
                      title="预览图片"
                      @click.stop="openStylePreview(preset)"
                      @keydown.enter.stop.prevent="openStylePreview(preset)"
                      @keydown.space.stop.prevent="openStylePreview(preset)"
                    >
                      <el-icon><ZoomIn /></el-icon>
                    </span>
                    <span
                      class="style-card__edit"
                      role="button"
                      tabindex="0"
                      aria-label="编辑视觉风格"
                      title="编辑视觉风格"
                      @click.stop="openEditStyleDialog(preset)"
                      @keydown.enter.stop.prevent="openEditStyleDialog(preset)"
                      @keydown.space.stop.prevent="openEditStyleDialog(preset)"
                    >
                      <el-icon><EditPen /></el-icon>
                    </span>
                    <span class="style-card__text">
                      <strong class="style-card__title">{{ preset.style_path }}</strong>
                      <em class="style-card__subtitle">{{ preset.name }}</em>
                    </span>
                  </button>
                </div>
              </el-form-item>
            </section>

            <section class="panel-card">
              <header class="panel-card__head">
                <div class="panel-card__title-actions">
                  <h3 class="panel-card__title">导演风格</h3>
                  <el-button
                    class="panel-card__add"
                    type="primary"
                    size="small"
                    @click="openCreateDirectorStyleDialog"
                  >
                    <el-icon><Plus /></el-icon>
                    添加导演风格
                  </el-button>
                </div>
                <span class="panel-card__hint">{{ activeDirectorStyleLabel || '未选择' }}</span>
              </header>
              <el-form-item prop="director_manual" class="panel-card__field">
                <div
                  v-loading="directorStylesLoading"
                  class="director-grid"
                  element-loading-background="rgba(13, 17, 23, 0.55)"
                >
                  <el-empty
                    v-if="!directorStylesLoading && directorStylePresets.length === 0"
                    class="style-empty"
                    description="暂无导演风格"
                  />
                  <button
                    v-for="preset in directorStylePresets"
                    v-else
                    :key="preset.manual_path"
                    type="button"
                    class="director-card"
                    :class="{ 'is-active': projectForm.director_manual === preset.manual_path }"
                    @click="projectForm.director_manual = preset.manual_path"
                  >
                    <span
                      class="director-card__image"
                      :style="{ backgroundImage: getDirectorStyleBackground(preset) }"
                    ></span>
                    <span class="director-card__overlay"></span>
                    <span
                      class="director-card__zoom"
                      role="button"
                      tabindex="0"
                      aria-label="预览图片"
                      title="预览图片"
                      @click.stop="openDirectorPreview(preset)"
                      @keydown.enter.stop.prevent="openDirectorPreview(preset)"
                      @keydown.space.stop.prevent="openDirectorPreview(preset)"
                    >
                      <el-icon><ZoomIn /></el-icon>
                    </span>
                    <span
                      class="director-card__edit"
                      role="button"
                      tabindex="0"
                      aria-label="编辑导演风格"
                      title="编辑导演风格"
                      @click.stop="openEditDirectorStyleDialog(preset)"
                      @keydown.enter.stop.prevent="openEditDirectorStyleDialog(preset)"
                      @keydown.space.stop.prevent="openEditDirectorStyleDialog(preset)"
                    >
                      <el-icon><EditPen /></el-icon>
                    </span>
                    <span class="director-card__text">
                      <strong class="director-card__title">{{ preset.manual_path }}</strong>
                      <em class="director-card__subtitle">{{ preset.name }}</em>
                    </span>
                  </button>
                </div>
              </el-form-item>
            </section>
          </div>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="projectDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="projectSubmitting" @click="submitProject">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="memberDialogVisible"
      :title="memberDialogTitle"
      width="760px"
      destroy-on-close
      class="project-dark-dialog"
    >
      <section class="member-search">
        <el-input
          v-model="candidateKeyword"
          clearable
          placeholder="输入用户名或邮箱搜索可邀请成员"
          @keyup.enter="searchCandidates"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="inviteRole" class="role-select" popper-class="project-dark-select">
          <el-option label="管理员" value="admin" />
          <el-option label="管理者" value="manager" />
          <el-option label="编辑者" value="editor" />
          <el-option label="查看者" value="viewer" />
        </el-select>
        <el-button :loading="candidatesLoading" @click="searchCandidates">搜索</el-button>
      </section>

      <el-table
        v-if="candidates.length > 0"
        :data="candidates"
        class="candidate-table"
        size="small"
      >
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="nickname" label="昵称" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column label="操作" width="100" align="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="inviteCandidate(row)">邀请</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-divider />

      <el-table
        v-loading="membersLoading"
        :data="members"
        element-loading-background="rgba(13, 17, 23, 0.55)"
        size="small"
      >
        <el-table-column prop="user_email" label="成员 邮箱" min-width="240" />
        <el-table-column label="角色" width="160">
          <template #default="{ row }">
            <el-select
              v-model="row.role"
              :disabled="row.role === 'owner'"
              size="small"
              popper-class="project-dark-select"
              @change="updateMemberRole(row)"
            >
              <el-option label="所有者" value="owner" disabled />
              <el-option label="管理员" value="admin" />
              <el-option label="管理者" value="manager" />
              <el-option label="编辑者" value="editor" />
              <el-option label="查看者" value="viewer" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="加入时间" width="170">
          <template #default="{ row }">{{ formatDate(row.joined_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="right">
          <template #default="{ row }">
            <el-button
              :disabled="row.role === 'owner'"
              type="danger"
              link
              @click="removeMember(row)"
            >
              移除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <VisualStyleDialog
      v-model="visualStyleDialogVisible"
      :mode="visualStyleDialogMode"
      :style="editingVisualStyle"
      @saved="handleVisualStyleSaved"
    />

    <DirectorStyleDialog
      v-model="directorStyleDialogVisible"
      :mode="directorStyleDialogMode"
      :manual="editingDirectorStyle"
      @saved="handleDirectorStyleSaved"
    />

    <el-image-viewer
      v-if="previewVisible"
      :url-list="previewUrls"
      :initial-index="previewIndex"
      hide-on-click-modal
      teleported
      @close="previewVisible = false"
    />

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { AxiosError } from 'axios'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Connection,
  Delete,
  Document,
  EditPen,
  Folder,
  List,
  Plus,
  Search,
  Setting,
  SwitchButton,
  UserFilled,
  ZoomIn,
} from '@element-plus/icons-vue'
import {
  createProjectApi,
  deleteProjectApi,
  disableProjectApi,
  enableProjectApi,
  inviteProjectMemberApi,
  listDirectorManualsApi,
  listProjectMembersApi,
  listProjectsApi,
  listVisualStylesApi,
  removeProjectMemberApi,
  searchProjectMemberCandidatesApi,
  searchProjectsByNameApi,
  updateProjectApi,
  updateProjectMemberRoleApi,
  type DirectorManualRecord,
  type ProjectMemberRecord,
  type ProjectMemberRole,
  type ProjectPayload,
  type ProjectRecord,
  type ProjectVideoMode,
  type UserRecord,
  type VisualStyleImageRecord,
  type VisualStyleRecord,
} from '@/api/project'
import {
  listProvidersApi,
  type ProviderConfig,
  type ProviderModelType,
} from '@/api/modelProvider'
import Settings from '../components/Settings.vue'
import DirectorStyleDialog from '../components/DirectorStyleDialog.vue'
import VisualStyleDialog from '../components/VisualStyleDialog.vue'

type ProjectDialogMode = 'create' | 'edit'
type VisualStyleDialogMode = 'create' | 'edit'
type DirectorStyleDialogMode = 'create' | 'edit'

type ArtStylePreset = VisualStyleRecord
type DirectorStylePreset = DirectorManualRecord

interface ProviderModelOption {
  label: string
  value: string
  category: string
  description: string
}

interface ProviderModelGroup {
  key: string
  platform: string
  icon: string
  models: ProviderModelOption[]
}

const router = useRouter()
const projectFormRef = ref<FormInstance>()

const loading = ref(false)
const projectSubmitting = ref(false)
const projects = ref<ProjectRecord[]>([])
const currentPage = ref(1)
const pageSize = ref(4)
const searchKeyword = ref('')

const projectDialogVisible = ref(false)
const projectDialogMode = ref<ProjectDialogMode>('create')
const editingProjectPublicId = ref('')

const memberDialogVisible = ref(false)
const memberProject = ref<ProjectRecord | null>(null)
const members = ref<ProjectMemberRecord[]>([])
const membersLoading = ref(false)
const candidateKeyword = ref('')
const candidates = ref<UserRecord[]>([])
const candidatesLoading = ref(false)
const inviteRole = ref<ProjectMemberRole>('editor')
const artStylesLoading = ref(false)
const directorStylesLoading = ref(false)
const modelProvidersLoading = ref(false)
const modelProviders = ref<ProviderConfig[]>([])
const visualStyleDialogVisible = ref(false)
const visualStyleDialogMode = ref<VisualStyleDialogMode>('create')
const editingVisualStyle = ref<VisualStyleRecord | null>(null)
const directorStyleDialogVisible = ref(false)
const directorStyleDialogMode = ref<DirectorStyleDialogMode>('create')
const editingDirectorStyle = ref<DirectorManualRecord | null>(null)

const settingsVisible = ref(false)

const previewVisible = ref(false)
const previewUrls = ref<string[]>([])
const previewIndex = ref(0)

const projectForm = reactive<ProjectPayload>({
  name: '',
  intro: '',
  project_type: 'novel',
  content_type: '',
  art_style: '',
  director_manual: '',
  video_ratio: '9:16',
  text_model: '',
  image_model: '',
  video_model: '',
  tts_model: '',
  image_quality: '1K',
  mode: 'text',
})

const MODEL_TYPE_LABELS: Record<ProviderModelType, string> = {
  text: '文本',
  image: '图像',
  video: '视频',
  tts: '语音',
}

const createEmptyProviderGroups = (): Record<ProviderModelType, ProviderModelGroup[]> => ({
  text: [],
  image: [],
  video: [],
  tts: [],
})

const createEmptyModelBuckets = (): Record<ProviderModelType, ProviderModelOption[]> => ({
  text: [],
  image: [],
  video: [],
  tts: [],
})

const artStylePresets = ref<ArtStylePreset[]>([])

const providerModelGroups = computed<Record<ProviderModelType, ProviderModelGroup[]>>(() => {
  const groups = createEmptyProviderGroups()
  for (const provider of modelProviders.value) {
    if (!provider.enabled) continue

    const groupedModels = createEmptyModelBuckets()
    for (const model of provider.models) {
      groupedModels[model.model_type].push({
        label: model.name || model.model_id,
        value: model.model_id,
        category: MODEL_TYPE_LABELS[model.model_type],
        description: model.description || model.model_id,
      })
    }

    for (const modelType of Object.keys(groupedModels) as ProviderModelType[]) {
      if (groupedModels[modelType].length === 0) continue
      groups[modelType].push({
        key: provider.key,
        platform: provider.name || provider.key,
        icon: provider.icon,
        models: groupedModels[modelType],
      })
    }
  }
  return groups
})

const textModelGroups = computed(() => providerModelGroups.value.text)
const imageModelGroups = computed(() => providerModelGroups.value.image)
const videoModelGroups = computed(() => providerModelGroups.value.video)
const ttsModelGroups = computed(() => providerModelGroups.value.tts)
const directorStylePresets = ref<DirectorStylePreset[]>([])

const toArtStylePreset = (style: VisualStyleRecord): ArtStylePreset => ({
  style_path: style.style_path,
  name: style.name,
  files: style.files,
  images: style.images,
})

const toDirectorStylePreset = (manual: DirectorManualRecord): DirectorStylePreset => ({
  manual_path: manual.manual_path,
  name: manual.name,
  files: manual.files,
  images: manual.images,
})

const getArtStyleLabel = (value: string) => (
  artStylePresets.value.find((item) => item.style_path === value)?.style_path ?? ''
)

const getArtStyleImageUrl = (preset: ArtStylePreset) => {
  const imageUrl = preset.images[2]?.url ?? preset.images[2]?.path ?? ''
  return /^(?:https?:|data:|\/)/.test(imageUrl) ? imageUrl : ''
}

const getArtStyleBackground = (preset: ArtStylePreset) => {
  const imageUrl = getArtStyleImageUrl(preset)
  return imageUrl ? `url("${imageUrl}")` : 'linear-gradient(135deg, #475569, #1e293b)'
}

const getArtStyleAllImageUrls = (preset: ArtStylePreset): string[] => {
  return preset.images
    .map((image: VisualStyleImageRecord) => image.url ?? image.path ?? '')
    .filter((url: string) => /^(?:https?:|data:|\/)/.test(url))
}

const openStylePreview = (preset: ArtStylePreset) => {
  const urls = getArtStyleAllImageUrls(preset)
  if (urls.length === 0) {
    ElMessage.warning('暂无可预览的图片')
    return
  }
  previewUrls.value = urls
  previewIndex.value = 0
  previewVisible.value = true
}

const openCreateStyleDialog = () => {
  visualStyleDialogMode.value = 'create'
  editingVisualStyle.value = null
  visualStyleDialogVisible.value = true
}

const openEditStyleDialog = (preset: ArtStylePreset) => {
  visualStyleDialogMode.value = 'edit'
  editingVisualStyle.value = preset
  visualStyleDialogVisible.value = true
}

const handleVisualStyleSaved = async (style: VisualStyleRecord) => {
  await loadVisualStyles()
  projectForm.art_style = style.style_path
}

const getDirectorStyleLabel = (value: string) => (
  directorStylePresets.value.find((item) => item.manual_path === value)?.manual_path ?? ''
)

const getDirectorStyleImageUrl = (preset: DirectorStylePreset) => {
  const imageUrl = preset.images[0]?.url ?? preset.images[0]?.path ?? ''
  return /^(?:https?:|data:|\/)/.test(imageUrl) ? imageUrl : ''
}

const getDirectorStyleBackground = (preset: DirectorStylePreset) => {
  const imageUrl = getDirectorStyleImageUrl(preset)
  return imageUrl ? `url("${imageUrl}")` : 'linear-gradient(135deg, #475569, #1e293b)'
}

const getDirectorStyleAllImageUrls = (preset: DirectorStylePreset): string[] => {
  return preset.images
    .map((image: DirectorManualRecord['images'][number]) => image.url ?? image.path ?? '')
    .filter((url: string) => /^(?:https?:|data:|\/)/.test(url))
}

const openDirectorPreview = (preset: DirectorStylePreset) => {
  const urls = getDirectorStyleAllImageUrls(preset)
  if (urls.length === 0) {
    ElMessage.warning('暂无可预览的图片')
    return
  }
  previewUrls.value = urls
  previewIndex.value = 0
  previewVisible.value = true
}

const openCreateDirectorStyleDialog = () => {
  directorStyleDialogMode.value = 'create'
  editingDirectorStyle.value = null
  directorStyleDialogVisible.value = true
}

const openEditDirectorStyleDialog = (preset: DirectorStylePreset) => {
  directorStyleDialogMode.value = 'edit'
  editingDirectorStyle.value = preset
  directorStyleDialogVisible.value = true
}

const handleDirectorStyleSaved = async (manualPath: string) => {
  await loadDirectorManuals()
  projectForm.director_manual = manualPath
}

const activeArtStyleLabel = computed(
  () => getArtStyleLabel(projectForm.art_style),
)

const activeDirectorStyleLabel = computed(
  () => getDirectorStyleLabel(projectForm.director_manual),
)

const projectRules: FormRules<ProjectPayload> = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

const pagedProjects = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return projects.value.slice(start, start + pageSize.value)
})

const projectDialogTitle = computed(() => (projectDialogMode.value === 'create' ? '新建项目' : '编辑项目'))
const memberDialogTitle = computed(() => (memberProject.value ? `成员管理：${memberProject.value.name}` : '成员管理'))

const loadProjects = async () => {
  loading.value = true
  try {
    const { data } = await listProjectsApi()
    projects.value = data
    currentPage.value = 1
    searchKeyword.value = ''
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

const handleSearch = async () => {
  const keyword = searchKeyword.value.trim()
  if (!keyword) {
    await loadProjects()
    return
  }

  loading.value = true
  try {
    const { data } = await searchProjectsByNameApi(keyword)
    projects.value = data
    currentPage.value = 1
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

const loadVisualStyles = async () => {
  artStylesLoading.value = true
  try {
    const { data } = await listVisualStylesApi()
    artStylePresets.value = data.map(toArtStylePreset)
  } catch (error) {
    artStylePresets.value = []
    ElMessage.error(getErrorMessage(error))
  } finally {
    artStylesLoading.value = false
  }
}

const loadDirectorManuals = async () => {
  directorStylesLoading.value = true
  try {
    const { data } = await listDirectorManualsApi()
    directorStylePresets.value = data.map(toDirectorStylePreset)
  } catch (error) {
    directorStylePresets.value = []
    ElMessage.error(getErrorMessage(error))
  } finally {
    directorStylesLoading.value = false
  }
}

const loadModelProviders = async () => {
  modelProvidersLoading.value = true
  try {
    const { data } = await listProvidersApi()
    modelProviders.value = data
  } catch (error) {
    modelProviders.value = []
    ElMessage.error(getErrorMessage(error))
  } finally {
    modelProvidersLoading.value = false
  }
}

const ensureModelProvidersLoaded = () => {
  if (modelProvidersLoading.value || modelProviders.value.length > 0) return
  void loadModelProviders()
}

const openCreateDialog = () => {
  projectDialogMode.value = 'create'
  editingProjectPublicId.value = ''
  resetProjectForm()
  ensureModelProvidersLoaded()
  projectDialogVisible.value = true
}

const openEditDialog = (project: ProjectRecord) => {
  projectDialogMode.value = 'edit'
  editingProjectPublicId.value = project.public_id
  Object.assign(projectForm, pickProjectPayload(project))
  ensureModelProvidersLoaded()
  projectDialogVisible.value = true
}

const submitProject = async () => {
  if (!projectFormRef.value) return
  const valid = await projectFormRef.value.validate().catch(() => false)
  if (!valid) return

  projectSubmitting.value = true
  try {
    if (projectDialogMode.value === 'create') {
      await createProjectApi({ ...projectForm })
      ElMessage.success('项目已创建')
    } else {
      await updateProjectApi(editingProjectPublicId.value, { ...projectForm })
      ElMessage.success('项目已更新')
    }
    projectDialogVisible.value = false
    await refreshAfterMutation()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    projectSubmitting.value = false
  }
}

const toggleProjectStatus = async (project: ProjectRecord) => {
  try {
    if (project.disabled_at) {
      await enableProjectApi(project.public_id)
      ElMessage.success('项目已启用')
    } else {
      await disableProjectApi(project.public_id)
      ElMessage.success('项目已禁用')
    }
    await refreshAfterMutation()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

const handleDeleteProject = async (project: ProjectRecord) => {
  try {
    await ElMessageBox.confirm(`确定删除项目“${project.name}”吗？删除后不可恢复。`, '删除项目', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'project-dark-messagebox',
    })

    await deleteProjectApi(project.public_id)
    ElMessage.success('项目已删除')
    await refreshAfterMutation()
  } catch (error) {
    if (isCancelError(error)) return
    ElMessage.error(getErrorMessage(error))
  }
}

const openMemberDialog = async (project: ProjectRecord) => {
  memberProject.value = project
  members.value = []
  candidates.value = []
  candidateKeyword.value = ''
  inviteRole.value = 'editor'
  memberDialogVisible.value = true
  await loadMembers()
}

const loadMembers = async () => {
  if (!memberProject.value) return
  membersLoading.value = true
  try {
    const { data } = await listProjectMembersApi(memberProject.value.public_id)
    members.value = data
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    membersLoading.value = false
  }
}

const searchCandidates = async () => {
  if (!memberProject.value) return
  const keyword = candidateKeyword.value.trim()
  if (!keyword) {
    candidates.value = []
    return
  }

  candidatesLoading.value = true
  try {
    const { data } = await searchProjectMemberCandidatesApi(memberProject.value.public_id, keyword)
    candidates.value = data
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    candidatesLoading.value = false
  }
}

const inviteCandidate = async (candidate: UserRecord) => {
  if (!memberProject.value) return
  try {
    await inviteProjectMemberApi(memberProject.value.public_id, {
      user_public_id: candidate.public_id,
      role: inviteRole.value,
    })
    ElMessage.success('成员已邀请')
    candidates.value = candidates.value.filter((item) => item.public_id !== candidate.public_id)
    await loadMembers()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

const updateMemberRole = async (member: ProjectMemberRecord) => {
  if (!memberProject.value || member.role === 'owner') return
  try {
    await updateProjectMemberRoleApi(memberProject.value.public_id, member.user_public_id, member.role)
    ElMessage.success('成员角色已更新')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
    await loadMembers()
  }
}

const removeMember = async (member: ProjectMemberRecord) => {
  if (!memberProject.value || member.role === 'owner') return
  try {
    await ElMessageBox.confirm('确定移除该项目成员吗？', '移除成员', {
      confirmButtonText: '移除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'project-dark-messagebox',
    })
    await removeProjectMemberApi(memberProject.value.public_id, member.user_public_id)
    ElMessage.success('成员已移除')
    await loadMembers()
  } catch (error) {
    if (isCancelError(error)) return
    ElMessage.error(getErrorMessage(error))
  }
}

const refreshAfterMutation = async () => {
  if (searchKeyword.value.trim()) {
    await handleSearch()
  } else {
    await loadProjects()
  }
}

const resetProjectForm = () => {
  Object.assign(projectForm, {
    name: '',
    intro: '',
    project_type: 'novel',
    content_type: '',
    art_style: '',
    director_manual: '',
    video_ratio: '9:16',
    text_model: '',
    image_model: '',
    video_model: '',
    tts_model: '',
    image_quality: '1K',
    mode: 'text' as ProjectVideoMode,
  })
}

const pickProjectPayload = (project: ProjectRecord): ProjectPayload => ({
  name: project.name,
  intro: project.intro,
  project_type: project.project_type,
  content_type: project.content_type,
  art_style: project.art_style,
  director_manual: project.director_manual,
  video_ratio: project.video_ratio,
  text_model: project.text_model,
  image_model: project.image_model,
  video_model: project.video_model,
  tts_model: project.tts_model,
  image_quality: project.image_quality,
  mode: project.mode,
})

const contentTypeLabel = (contentType: string) => {
  const labels: Record<string, string> = {
    novel: '基于小说',
    script: '基于剧本',
    original: '原创短剧',
  }
  return labels[contentType] ?? contentType
}

const formatDate = (value: string) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const getErrorMessage = (error: unknown) => {
  const axiosError = error as AxiosError<{ detail?: string }>
  return axiosError.response?.data?.detail || axiosError.message || '请求失败'
}

const isCancelError = (error: unknown) => error === 'cancel' || error === 'close'

const goHome = () => {
  router.push('/project')
}

const openProject = (project: ProjectRecord) => {
  if (project.disabled_at) {
    ElMessage.warning('该项目已禁用，无法打开')
    return
  }
  const routeMap: Record<string, string> = {
    novel: '/novel',
    script: '/script',
    original: '/original',
  }
  const path = routeMap[project.project_type]
  if (!path) {
    ElMessage.info('该项目类型暂未开放')
    return
  }
  router.push({ path, query: { id: project.public_id } })
}

const openProjectTasks = (project: ProjectRecord) => {
  if (project.disabled_at) {
    ElMessage.warning('该项目已禁用，无法查看任务')
    return
  }
  router.push({ path: '/tasks', query: { id: project.public_id, type: project.project_type } })
}

const showComingSoon = () => {
  ElMessage.info('功能开发中')
}

onMounted(() => {
  void loadProjects()
  void loadVisualStyles()
  void loadDirectorManuals()
  void loadModelProviders()
})
</script>

<style scoped>
.project-page {
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
  border-radius: 22px;
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
  border-radius: 14px;
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
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 10px 24px rgba(243, 217, 107, 0.28);
}

.brand:active {
  transform: translateY(0) scale(0.97);
}

.nav-btn {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 16px;
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
  flex-direction: column;
  overflow: hidden;
  padding: 24px 28px 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
  flex-shrink: 0;
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

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.search-input {
  max-width: 420px;
}

.toolbar :deep(.el-input__wrapper) {
  background-color: rgba(255, 255, 255, 0.04);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
  border-radius: 10px;
  transition: box-shadow 0.18s ease, background-color 0.18s ease;
}

.toolbar :deep(.el-input__wrapper:hover) {
  background-color: rgba(255, 255, 255, 0.06);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset;
}

.toolbar :deep(.el-input__wrapper.is-focus) {
  background-color: rgba(37, 99, 235, 0.08);
  box-shadow: 0 0 0 1px #2563eb inset;
}

.toolbar :deep(.el-input__inner) {
  color: #e6edf3;
}

.toolbar :deep(.el-input__inner::placeholder) {
  color: #6e7681;
}

.toolbar :deep(.el-input__prefix-inner .el-icon),
.toolbar :deep(.el-input__suffix-inner .el-icon) {
  color: #8b949e;
}

.toolbar :deep(.el-button) {
  height: 38px;
  padding: 0 16px;
  border-radius: 10px;
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
  font-weight: 500;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.toolbar :deep(.el-button:hover),
.toolbar :deep(.el-button:focus) {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
  transform: translateY(-1px);
}

.toolbar :deep(.el-button:active) {
  transform: translateY(0);
}

.create-button {
  height: 38px;
  padding: 0 16px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  background: #2563eb;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.18);
  transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.create-button :deep(.el-icon) {
  margin-right: 0;
  font-size: 16px;
}

.create-button:hover,
.create-button:focus {
  background: #1d4ed8;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.28);
  transform: translateY(-1px);
}

.create-button:active {
  transform: translateY(0);
}

.project-grid {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(320px, 1fr));
  gap: 16px 18px;
  align-content: start;
  padding-right: 6px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.project-grid::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.project-grid::-webkit-scrollbar-track {
  background: transparent;
}

.project-grid::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  border: none;
  transition: background-color 0.18s ease;
}

.project-grid::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.project-grid::-webkit-scrollbar-corner {
  background: transparent;
}

.empty-state {
  grid-column: 1 / -1;
  align-self: center;
}

.project-card {
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.022), rgba(255, 255, 255, 0.012));
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.project-card:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.18);
  box-shadow: 0 18px 34px rgba(0, 0, 0, 0.24);
}

.project-card :deep(.el-card__header) {
  padding: 18px 22px 0;
  border-bottom: 0;
}

.project-card :deep(.el-card__body) {
  display: flex;
  flex: 1;
  flex-direction: column;
  padding: 10px 22px 16px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.project-name {
  margin: 0;
  color: #e6edf3;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.25;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.source-tag {
  height: 26px;
  padding: 0 10px;
  color: #d1d5db;
  font-size: 12px;
  font-weight: 500;
  border-color: rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.05);
  white-space: nowrap;
}

.model-tag,
.ratio-tag {
  width: fit-content;
  height: 24px;
  padding: 0 10px;
  font-size: 11px;
  font-weight: 500;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.model-tag {
  color: #c7d2fe;
  border-color: rgba(37, 99, 235, 0.22);
  background: rgba(37, 99, 235, 0.12);
}

.ratio-tag {
  color: #bae6fd;
  border-color: rgba(14, 165, 233, 0.22);
  background: rgba(14, 165, 233, 0.1);
}

.summary {
  flex: 1;
  margin: 10px 0 0;
  color: #b8c2cc;
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 14px;
}

.time {
  color: #8b949e;
  font-size: 12px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-action {
  width: 30px;
  height: 30px;
  font-size: 15px;
  color: #8b949e;
  border-radius: 8px;
  --el-fill-color-light: transparent;
  --el-fill-color: transparent;
  --el-color-info: #93c5fd;
  transition: color 0.2s ease, background-color 0.2s ease, transform 0.2s ease;
}

.icon-action :deep(.el-icon) {
  font-size: 15px;
}

.icon-action:hover,
.icon-action:focus {
  color: #93c5fd;
  background-color: rgba(59, 130, 246, 0.14);
  transform: translateY(-1px);
}

.icon-action.delete {
  --el-color-info: #fca5a5;
}

.icon-action.delete:hover,
.icon-action.delete:focus {
  color: #fca5a5;
  background-color: rgba(248, 113, 113, 0.16);
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 14px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.pagination-wrap :deep(.el-pagination.is-background .btn-prev),
.pagination-wrap :deep(.el-pagination.is-background .btn-next),
.pagination-wrap :deep(.el-pagination.is-background .el-pager li) {
  color: #8b949e;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.pagination-wrap :deep(.el-pagination.is-background .el-pager li:hover) {
  color: #e6edf3;
  border-color: rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.05);
}

.pagination-wrap :deep(.el-pagination.is-background .el-pager li.is-active) {
  color: #fff;
  border-color: #2563eb;
  background: #2563eb;
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.22);
}

.pagination-wrap :deep(.el-pagination__total) {
  color: #8b949e;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.project-form {
  padding-right: 8px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}

.member-search {
  display: grid;
  grid-template-columns: 1fr 140px auto;
  gap: 10px;
  align-items: center;
}

.candidate-table {
  margin-top: 12px;
}

.role-select {
  width: 140px;
}

@media (max-width: 860px) {
  .title {
    font-size: 28px;
  }

  .project-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 820px) {
  .project-page {
    padding: 14px;
  }

  .app-shell {
    grid-template-columns: 1fr;
    gap: 14px;
    height: calc(100vh - 28px);
    height: calc(100dvh - 28px);
  }

  .sidebar {
    flex-direction: row;
    padding: 12px 14px;
  }

  .side-top,
  .side-bottom {
    width: auto;
    flex-direction: row;
    gap: 10px;
  }

  .main-panel {
    padding: 18px 16px 16px;
  }

  .page-header,
  .toolbar,
  .card-head,
  .card-footer,
  .member-search {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar,
  .member-search {
    display: flex;
  }

  .title {
    font-size: 26px;
  }

  .desc {
    font-size: 13px;
  }

  .create-button {
    align-self: flex-start;
  }

  .search-input,
  .role-select {
    max-width: none;
    width: 100%;
  }

  .project-card :deep(.el-card__header) {
    padding: 16px 18px 0;
  }

  .project-card :deep(.el-card__body) {
    padding: 10px 18px 14px;
  }
}
</style>

<style>
/* 项目页面专用暗色弹窗样式（dialog 与 messagebox 由 element-plus teleport 到 body，需置于非 scoped 块） */
.project-dark-dialog {
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 24px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.project-dark-dialog .el-dialog__header {
  margin: 0;
  padding: 24px 30px 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: transparent;
}

.project-dark-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.project-dark-dialog .el-dialog__headerbtn {
  top: 18px;
  right: 22px;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.project-dark-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
  font-size: 20px;
  font-weight: 400;
}

.project-dark-dialog .el-dialog__headerbtn:hover,
.project-dark-dialog .el-dialog__headerbtn:focus {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.18);
}

.project-dark-dialog .el-dialog__headerbtn:hover .el-dialog__close,
.project-dark-dialog .el-dialog__headerbtn:focus .el-dialog__close {
  color: #ffffff;
}

.project-dark-dialog .el-dialog__body {
  padding: 22px 30px 8px;
  color: #b8c2cc;
  background: transparent;
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.project-dark-dialog .el-dialog__body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.project-dark-dialog .el-dialog__body::-webkit-scrollbar-track {
  background: transparent;
}

.project-dark-dialog .el-dialog__body::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.project-dark-dialog .el-dialog__body::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.project-dark-dialog .el-dialog__footer {
  padding: 18px 30px 24px;
  background: transparent;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.project-dark-dialog .el-form-item {
  margin-bottom: 18px;
}

.project-dark-dialog .el-form-item__label {
  color: #d5dce4;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  padding: 0 0 8px;
}

.project-dark-dialog .el-form-item.is-error .el-form-item__error {
  color: #fca5a5;
  padding-top: 4px;
}

.project-dark-dialog .el-input__wrapper,
.project-dark-dialog .el-select__wrapper {
  min-height: 46px;
  padding: 0 14px;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border-radius: 12px;
  color: #e6edf3;
  font-size: 14px;
  transition: box-shadow 0.18s ease, background-color 0.18s ease;
}

.project-dark-dialog .el-textarea__inner {
  min-height: 112px;
  padding: 12px 14px;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border: none;
  border-radius: 12px;
  color: #e6edf3;
  font-size: 14px;
  font-family: inherit;
  transition: box-shadow 0.18s ease, background-color 0.18s ease;
  resize: vertical;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.project-dark-dialog .el-textarea__inner::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.project-dark-dialog .el-textarea__inner::-webkit-scrollbar-track {
  background: transparent;
}

.project-dark-dialog .el-textarea__inner::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.project-dark-dialog .el-textarea__inner::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.project-dark-dialog .el-input__inner,
.project-dark-dialog .el-textarea__inner {
  color: #e6edf3;
}

.project-dark-dialog .el-input__inner::placeholder,
.project-dark-dialog .el-textarea__inner::placeholder,
.project-dark-dialog .el-select__placeholder {
  color: #7e8893;
}

.project-dark-dialog .el-input__wrapper:hover,
.project-dark-dialog .el-textarea__inner:hover,
.project-dark-dialog .el-select__wrapper:hover {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.project-dark-dialog .el-input__wrapper.is-focus,
.project-dark-dialog .el-textarea__inner:focus,
.project-dark-dialog .el-select__wrapper.is-focused {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.project-dark-dialog .el-input.is-disabled .el-input__wrapper,
.project-dark-dialog .el-select.is-disabled .el-select__wrapper {
  background-color: rgba(255, 255, 255, 0.02);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.04) inset;
  color: #6e7681;
}

.project-dark-dialog .el-input.is-disabled .el-input__inner,
.project-dark-dialog .el-select.is-disabled .el-select__placeholder {
  color: #6e7681;
  -webkit-text-fill-color: #6e7681;
}

.project-dark-dialog .el-input__count,
.project-dark-dialog .el-input__count-inner,
.project-dark-dialog .el-textarea .el-input__count,
.project-dark-dialog .el-input .el-input__count {
  color: #6e7681 !important;
  background: transparent !important;
  background-color: transparent !important;
  font-size: 12px;
}

.project-dark-dialog .el-textarea .el-input__count {
  bottom: 8px;
  right: 12px;
}

.project-dark-dialog .el-select__caret {
  color: #8b949e;
}

.project-dark-dialog .el-divider {
  background-color: rgba(255, 255, 255, 0.08);
  margin: 18px 0;
}

.project-dark-dialog .el-divider--horizontal {
  border-top: none;
  height: 1px;
}

/* 表格 */
.project-dark-dialog .el-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-border-color: rgba(255, 255, 255, 0.08);
  --el-table-header-text-color: #c5cdd6;
  --el-table-text-color: #c5cdd6;
  --el-table-row-hover-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-border: 1px solid rgba(255, 255, 255, 0.08);
  background: transparent;
  color: #e6edf3;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  overflow: hidden;
}

.project-dark-dialog .el-table::before,
.project-dark-dialog .el-table::after {
  background-color: rgba(255, 255, 255, 0.06);
}

.project-dark-dialog .el-table th.el-table__cell,
.project-dark-dialog .el-table td.el-table__cell {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: transparent;
}

.project-dark-dialog .el-table thead th.el-table__cell {
  background-color: rgba(255, 255, 255, 0.04);
  color: #c5cdd6;
  font-weight: 600;
}

.project-dark-dialog .el-table tr {
  background: transparent;
}

.project-dark-dialog .el-table tbody tr:hover > td.el-table__cell {
  background-color: rgba(255, 255, 255, 0.04);
}

.project-dark-dialog .el-table .cell {
  color: inherit;
}

.project-dark-dialog .el-table .el-table__empty-block {
  background: transparent;
}

.project-dark-dialog .el-table .el-table__empty-text {
  color: #6e7681;
}

/* dialog footer 内的按钮 */
.project-dark-dialog .el-dialog__footer .el-button {
  height: 42px;
  min-width: 88px;
  padding: 0 20px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 700;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.project-dark-dialog .el-button.is-text {
  border-radius: 8px;
}

.project-dark-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.12);
  color: #e6edf3;
}

.project-dark-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):hover,
.project-dark-dialog .el-dialog__footer .el-button:not(.el-button--primary):not(.el-button--danger):focus {
  background-color: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
  transform: translateY(-1px);
}

.project-dark-dialog .el-dialog__footer .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
}

.project-dark-dialog .el-dialog__footer .el-button--primary:hover,
.project-dark-dialog .el-dialog__footer .el-button--primary:focus {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
  box-shadow: 0 16px 30px rgba(37, 99, 235, 0.28);
  transform: translateY(-1px);
}

.project-dark-dialog .el-dialog__footer .el-button:active {
  transform: translateY(0);
}

/* 成员管理弹窗内的搜索/邀请按钮 */
.project-dark-dialog .member-search .el-button {
  border-radius: 10px;
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
}

.project-dark-dialog .member-search .el-button:hover {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}

/* 表格内 link 按钮 */
.project-dark-dialog .el-button.is-link.el-button--primary {
  color: #93c5fd;
}

.project-dark-dialog .el-button.is-link.el-button--primary:hover {
  color: #bfdbfe;
}

.project-dark-dialog .el-button.is-link.el-button--danger {
  color: #fca5a5;
}

.project-dark-dialog .el-button.is-link.el-button--danger:hover {
  color: #fecaca;
}

.project-dark-dialog .el-button.is-link.is-disabled {
  color: #4d5560;
}

.project-dark-dialog .dialog-grid-2col {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 24px;
}

.project-dark-dialog .form-col {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.project-dark-dialog .form-col--right {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.project-dark-dialog .panel-card {
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.022), rgba(255, 255, 255, 0.012));
  padding: 14px 14px 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.project-dark-dialog .panel-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 4px;
}

.project-dark-dialog .panel-card__title-actions {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.project-dark-dialog .panel-card__title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #f2f4f8;
  letter-spacing: -0.2px;
  flex-shrink: 0;
}

.project-dark-dialog .panel-card__add {
  min-height: 30px;
  border-radius: 999px;
  color: #bfdbfe;
  background: rgba(37, 99, 235, 0.12);
  border-color: rgba(96, 165, 250, 0.35);
}

.project-dark-dialog .panel-card__add:hover,
.project-dark-dialog .panel-card__add:focus {
  color: #ffffff;
  background: rgba(37, 99, 235, 0.26);
  border-color: rgba(147, 197, 253, 0.68);
}

.project-dark-dialog .panel-card__hint {
  font-size: 12px;
  color: #93c5fd;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.12);
  border: 1px solid rgba(37, 99, 235, 0.32);
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-dark-dialog .panel-card__field {
  margin-bottom: 0;
}

.project-dark-dialog .panel-card__field .el-form-item__content {
  display: block;
  line-height: normal;
}

/* 视觉风格卡片网格（紧凑化以适应右栏） */

.project-dark-dialog .style-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  width: 100%;
  max-height: 380px;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.project-dark-dialog .style-empty {
  grid-column: 1 / -1;
  padding: 16px 0;
}

.project-dark-dialog .style-grid::-webkit-scrollbar {
  width: 4px;
  height: 4px;
}

.project-dark-dialog .style-grid::-webkit-scrollbar-track {
  background: transparent;
}

.project-dark-dialog .style-grid::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.14);
  border-radius: 999px;
}

.project-dark-dialog .style-grid::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.28);
}

.project-dark-dialog .style-card {
  position: relative;
  height: 118px;
  padding: 0;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background-color: #1a1f29;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  isolation: isolate;
  transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
}

.project-dark-dialog .style-card__image {
  position: absolute;
  inset: 0;
  z-index: 0;
  background-position: center;
  background-size: cover;
  background-repeat: no-repeat;
  transform: scale(1.02);
  transition: transform 0.55s cubic-bezier(0.22, 0.61, 0.36, 1), filter 0.3s ease;
}

.project-dark-dialog .style-card__overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  background:
    linear-gradient(180deg, rgba(7, 10, 16, 0) 36%, rgba(7, 10, 16, 0.55) 72%, rgba(7, 10, 16, 0.94) 100%),
    radial-gradient(120% 80% at 50% 0%, rgba(255, 255, 255, 0.08) 0%, transparent 60%);
  transition: background 0.25s ease, opacity 0.25s ease;
}

.project-dark-dialog .style-card:hover {
  transform: translateY(-3px);
  border-color: rgba(255, 255, 255, 0.22);
  box-shadow: 0 22px 44px rgba(0, 0, 0, 0.36);
}

.project-dark-dialog .style-card:hover .style-card__image {
  transform: scale(1.08);
  filter: saturate(1.08) brightness(1.04);
}

.project-dark-dialog .style-card:focus-visible {
  outline: none;
  border-color: rgba(147, 197, 253, 0.7);
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55),
    0 0 0 4px rgba(37, 99, 235, 0.18);
}

.project-dark-dialog .style-card.is-active {
  border-color: rgba(96, 165, 250, 0.85);
  box-shadow:
    0 0 0 1px rgba(96, 165, 250, 0.5),
    0 0 0 4px rgba(37, 99, 235, 0.18),
    0 22px 44px rgba(37, 99, 235, 0.32);
}

.project-dark-dialog .style-card.is-active .style-card__overlay {
  background:
    linear-gradient(180deg, rgba(7, 10, 16, 0) 28%, rgba(7, 10, 16, 0.6) 72%, rgba(7, 10, 16, 0.94) 100%),
    linear-gradient(180deg, rgba(37, 99, 235, 0.22) 0%, rgba(37, 99, 235, 0) 60%);
}

.project-dark-dialog .style-card__zoom,
.project-dark-dialog .style-card__edit {
  position: absolute;
  top: 10px;
  z-index: 3;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #ffffff;
  background: rgba(15, 20, 28, 0.55);
  border: 1.5px solid rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.28);
  cursor: pointer;
  opacity: 0.85;
  transform: translateY(-2px);
  transition: opacity 0.2s ease, transform 0.2s ease, background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.project-dark-dialog .style-card__zoom { left: 10px; }
.project-dark-dialog .style-card__edit { right: 10px; }

.project-dark-dialog .style-card__zoom .el-icon,
.project-dark-dialog .style-card__edit .el-icon {
  font-size: 14px;
  line-height: 1;
}

.project-dark-dialog .style-card:hover .style-card__zoom,
.project-dark-dialog .style-card:hover .style-card__edit,
.project-dark-dialog .style-card:focus-within .style-card__zoom,
.project-dark-dialog .style-card:focus-within .style-card__edit {
  opacity: 1;
  transform: translateY(0);
}

.project-dark-dialog .style-card__zoom:hover,
.project-dark-dialog .style-card__zoom:focus-visible {
  outline: none;
  background: rgba(15, 20, 28, 0.78);
  border-color: rgba(255, 255, 255, 0.95);
  box-shadow:
    0 0 0 3px rgba(255, 255, 255, 0.18),
    0 6px 14px rgba(0, 0, 0, 0.4);
}

.project-dark-dialog .style-card__edit:hover,
.project-dark-dialog .style-card__edit:focus-visible {
  outline: none;
  color: #ffffff;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border-color: rgba(255, 255, 255, 0.95);
  box-shadow:
    0 0 0 3px rgba(37, 99, 235, 0.28),
    0 6px 14px rgba(37, 99, 235, 0.45);
}

.project-dark-dialog .style-card__text {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 11px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 3px;
  color: #ffffff;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.55);
}

.project-dark-dialog .style-card__title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.2px;
  line-height: 1.25;
  color: #ffffff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-dark-dialog .style-card__subtitle {
  font-style: normal;
  font-size: 11.5px;
  font-weight: 500;
  line-height: 1.35;
  color: rgba(229, 235, 244, 0.78);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.project-dark-dialog .style-card.is-active .style-card__subtitle {
  color: rgba(219, 234, 254, 0.9);
}

/* 导演风格 chip 网格（参考 chip-grid） */
.project-dark-dialog .director-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 10px;
  width: 100%;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.project-dark-dialog .director-grid::-webkit-scrollbar {
  width: 4px;
  height: 4px;
}

.project-dark-dialog .director-grid::-webkit-scrollbar-track {
  background: transparent;
}

.project-dark-dialog .director-grid::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.14);
  border-radius: 999px;
}

.project-dark-dialog .director-grid::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.28);
}

.project-dark-dialog .director-card {
  position: relative;
  height: 118px;
  padding: 0;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background-color: #1a1f29;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  isolation: isolate;
  transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
}

.project-dark-dialog .director-card__image {
  position: absolute;
  inset: 0;
  z-index: 0;
  display: grid;
  place-items: center;
  background-position: center;
  background-size: cover;
  background-repeat: no-repeat;
  transform: scale(1.02);
  transition: transform 0.55s cubic-bezier(0.22, 0.61, 0.36, 1), filter 0.3s ease;
}

.project-dark-dialog .director-card__overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  background:
    linear-gradient(180deg, rgba(7, 10, 16, 0) 36%, rgba(7, 10, 16, 0.55) 72%, rgba(7, 10, 16, 0.94) 100%),
    radial-gradient(120% 80% at 50% 0%, rgba(255, 255, 255, 0.08) 0%, transparent 60%);
  transition: background 0.25s ease, opacity 0.25s ease;
}

.project-dark-dialog .director-card:hover {
  transform: translateY(-3px);
  border-color: rgba(255, 255, 255, 0.22);
  box-shadow: 0 22px 44px rgba(0, 0, 0, 0.36);
}

.project-dark-dialog .director-card:hover .director-card__image {
  transform: scale(1.06);
  filter: saturate(1.08) brightness(1.04);
}

.project-dark-dialog .director-card:focus-visible {
  outline: none;
  border-color: rgba(147, 197, 253, 0.7);
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55),
    0 0 0 4px rgba(37, 99, 235, 0.18);
}

.project-dark-dialog .director-card.is-active {
  border-color: rgba(96, 165, 250, 0.85);
  box-shadow:
    0 0 0 1px rgba(96, 165, 250, 0.5),
    0 0 0 4px rgba(37, 99, 235, 0.18),
    0 22px 44px rgba(37, 99, 235, 0.32);
}

.project-dark-dialog .director-card.is-active .director-card__overlay {
  background:
    linear-gradient(180deg, rgba(7, 10, 16, 0) 28%, rgba(7, 10, 16, 0.6) 72%, rgba(7, 10, 16, 0.94) 100%),
    linear-gradient(180deg, rgba(37, 99, 235, 0.22) 0%, rgba(37, 99, 235, 0) 60%);
}

.project-dark-dialog .director-card__zoom,
.project-dark-dialog .director-card__edit {
  position: absolute;
  top: 10px;
  z-index: 3;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #ffffff;
  background: rgba(15, 20, 28, 0.55);
  border: 1.5px solid rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.28);
  cursor: pointer;
  opacity: 0.85;
  transform: translateY(-2px);
  transition: opacity 0.2s ease, transform 0.2s ease, background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.project-dark-dialog .director-card__zoom { left: 10px; }
.project-dark-dialog .director-card__edit { right: 10px; }

.project-dark-dialog .director-card__zoom .el-icon,
.project-dark-dialog .director-card__edit .el-icon {
  font-size: 14px;
  line-height: 1;
}

.project-dark-dialog .director-card:hover .director-card__zoom,
.project-dark-dialog .director-card:hover .director-card__edit,
.project-dark-dialog .director-card:focus-within .director-card__zoom,
.project-dark-dialog .director-card:focus-within .director-card__edit {
  opacity: 1;
  transform: translateY(0);
}

.project-dark-dialog .director-card__zoom:hover,
.project-dark-dialog .director-card__zoom:focus-visible {
  outline: none;
  background: rgba(15, 20, 28, 0.78);
  border-color: rgba(255, 255, 255, 0.95);
  box-shadow:
    0 0 0 3px rgba(255, 255, 255, 0.18),
    0 6px 14px rgba(0, 0, 0, 0.4);
}

.project-dark-dialog .director-card__edit:hover,
.project-dark-dialog .director-card__edit:focus-visible {
  outline: none;
  color: #ffffff;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border-color: rgba(255, 255, 255, 0.95);
  box-shadow:
    0 0 0 3px rgba(37, 99, 235, 0.28),
    0 6px 14px rgba(37, 99, 235, 0.45);
}

.project-dark-dialog .director-card__text {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 11px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 3px;
  color: #ffffff;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.55);
}

.project-dark-dialog .director-card__title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.2px;
  line-height: 1.25;
  color: #ffffff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-dark-dialog .director-card__subtitle {
  font-style: normal;
  font-size: 11.5px;
  font-weight: 500;
  line-height: 1.35;
  color: rgba(229, 235, 244, 0.78);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.project-dark-dialog .director-card.is-active .director-card__subtitle {
  color: rgba(219, 234, 254, 0.9);
}

@media (max-width: 1080px) {
  .project-dark-dialog .dialog-grid-2col {
    grid-template-columns: minmax(0, 1fr);
  }

  .project-dark-dialog .style-grid,
  .project-dark-dialog .director-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    max-height: none;
  }
}

@media (max-width: 720px) {
  .project-dark-dialog .style-grid,
  .project-dark-dialog .director-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* select 下拉浮层 */
.project-dark-select.el-popper {
  background-color: #14181f;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}

.project-dark-select.el-popper .el-select-dropdown__list {
  padding: 6px 4px;
}

.project-dark-select.el-popper .el-select-dropdown__item {
  color: #c5cdd6;
  border-radius: 8px;
  margin: 2px 4px;
  padding: 0 12px;
  height: 32px;
  line-height: 32px;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.project-dark-select.el-popper .el-select-dropdown__item:hover,
.project-dark-select.el-popper .el-select-dropdown__item.is-hovering {
  background-color: rgba(255, 255, 255, 0.06);
  color: #ffffff;
}

.project-dark-select.el-popper .el-select-dropdown__item.is-selected {
  color: #93c5fd;
  background-color: rgba(37, 99, 235, 0.16);
  font-weight: 600;
}

.project-dark-select.el-popper .el-select-dropdown__item.is-disabled {
  color: #4d5560;
  background: transparent;
}

.project-dark-select.el-popper .el-popper__arrow::before {
  background-color: #14181f;
  border-color: rgba(255, 255, 255, 0.08);
}

/* 模型选择下拉浮层（按平台分组） */
.project-model-select.el-popper {
  min-width: 360px !important;
}

.project-model-select.el-popper .el-select-group__title {
  padding: 8px 14px 4px;
  color: #6e7681;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
}

.project-model-select.el-popper .el-select-group__wrap:not(:last-of-type) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 4px;
  margin-bottom: 4px;
}

.project-model-select.el-popper .el-select-group__wrap:not(:last-of-type)::after {
  display: none;
}

.project-model-select.el-popper .el-select-dropdown__item {
  height: 38px;
  line-height: 38px;
  padding: 0 12px;
}

.project-model-select .model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.project-model-select .model-option__main {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.project-model-select .model-option__icon {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.18);
}

.project-model-select .model-option__fallback {
  width: 24px;
  height: 24px;
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  border-radius: 8px;
  color: #dbeafe;
  font-size: 11px;
  font-weight: 700;
  background: rgba(37, 99, 235, 0.18);
  border: 1px solid rgba(147, 197, 253, 0.28);
}

.project-model-select .model-option__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: inherit;
}

.project-model-select .model-option__category {
  margin-left: auto;
  text-align: right;
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.14);
  border: 1px solid rgba(37, 99, 235, 0.3);
  line-height: 1.6;
}

/* messagebox 暗色风格 */
.project-dark-messagebox {
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.project-dark-messagebox .el-message-box__header {
  padding: 18px 24px 8px;
}

.project-dark-messagebox .el-message-box__title {
  color: #e6edf3;
  font-weight: 700;
}

.project-dark-messagebox .el-message-box__headerbtn .el-message-box__close {
  color: #8b949e;
}

.project-dark-messagebox .el-message-box__headerbtn:hover .el-message-box__close,
.project-dark-messagebox .el-message-box__headerbtn:focus .el-message-box__close {
  color: #ffffff;
}

.project-dark-messagebox .el-message-box__content {
  padding: 8px 24px 18px;
  color: #b8c2cc;
}

.project-dark-messagebox .el-message-box__container {
  align-items: flex-start;
}

.project-dark-messagebox .el-message-box__message p {
  color: #b8c2cc;
}

.project-dark-messagebox .el-message-box__btns {
  padding: 12px 24px 18px;
  background: rgba(255, 255, 255, 0.015);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.project-dark-messagebox .el-message-box__btns .el-button {
  border-radius: 8px;
}

.project-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
}

.project-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger):hover {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}
</style>