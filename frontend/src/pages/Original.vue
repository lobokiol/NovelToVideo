<template>
  <main class="original-page">
    <div class="app-shell">
      <aside class="sidebar">
        <div class="side-top">
          <div class="brand" @click="goProject">AF</div>

          <el-tooltip content="项目" placement="right">
            <button class="nav-btn" aria-label="项目" @click="goProject">
              <el-icon><Folder /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="短剧" placement="right">
            <button class="nav-btn active" aria-label="短剧">
              <el-icon><VideoCamera /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="任务" placement="right">
            <button class="nav-btn" aria-label="任务" @click="goTasks">
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
            <h1 class="title">我的短剧</h1>
            <p class="desc">一句话创意生成短剧方向、分集节奏与资产列表</p>
          </div>

          <div class="page-header__right">
            <el-popover
              trigger="hover"
              placement="bottom-end"
              popper-class="template-popover"
              :width="440"
              :show-after="120"
              :hide-after="180"
              :teleported="true"
            >
              <template #reference>
                <el-button class="header-action" size="large" @click="rotateTemplate">
                  <el-icon><Refresh /></el-icon>
                  &nbsp;刷新模板
                </el-button>
              </template>

              <div class="template-popover-panel">
                <div class="template-popover__head">
                  <strong>灵感模板</strong>
                  <div class="template-popover__tools">
                    <span>{{ templates.length }} 个</span>
                    <el-button size="small" type="primary" @click.stop="openTemplateDialog">
                      <el-icon><Plus /></el-icon>
                      添加模板
                    </el-button>
                  </div>
                </div>

                <div class="template-popover-list">
                  <button
                    v-for="template in templates"
                    :key="template.id"
                    type="button"
                    class="template-card"
                    :class="{ 'is-active': activeTemplate === template.id }"
                    @click="selectTemplate(template.id)"
                  >
                    <span>{{ template.genre }}</span>
                    <strong>{{ template.title }}</strong>
                    <em>{{ template.hook }}</em>
                    <p>{{ template.topic }}</p>
                    <small>{{ template.sellingPoint }}</small>
                  </button>
                </div>

              </div>
            </el-popover>

            <el-button class="header-action" size="large" @click="exportConcept">
              <el-icon><Download /></el-icon>
              &nbsp;导出草案
            </el-button>

            <el-popover
              trigger="hover"
              placement="bottom-end"
              popper-class="generation-popover"
              :width="340"
              :show-after="120"
              :hide-after="180"
              :teleported="true"
            >
              <template #reference>
                <el-button
                  class="primary-button"
                  type="primary"
                  size="large"
                  :loading="generating"
                  @click="generateConcept"
                >
                  <el-icon><MagicStick /></el-icon>
                  &nbsp;生成短剧方案
                </el-button>
              </template>

              <div class="generation-popover-panel">
                <article
                  v-for="task in nextTasks"
                  :key="task.title"
                  class="generation-task-card"
                >
                  <el-icon><component :is="task.icon" /></el-icon>
                  <div>
                    <strong>{{ task.title }}</strong>
                    <span>{{ task.desc }}</span>
                  </div>
                </article>
              </div>
            </el-popover>

            <el-button class="header-action stage-button" size="large" @click="goStoryboardStage">
              <el-icon><Picture /></el-icon>
              &nbsp;剧本管理
            </el-button>
          </div>
        </header>

        <section class="workspace" @scroll="closeConstraintPopover">
          <aside class="ai-chat-panel">
            <section class="assistant-shell">
              <header class="assistant-header">
                <div class="assistant-heading">
                  <span class="assistant-status-dot"></span>
                  <div>
                    <h2>AI 助手</h2>
                    <p>OpenAI · gpt-5.5</p>
                  </div>
                </div>
                <span class="assistant-message-count">{{ chatMessages.length }} 条</span>
              </header>

              <div class="assistant-thread-wrap">
                <div
                  ref="assistantThreadRef"
                  class="assistant-thread"
                  aria-label="对话记录"
                  @scroll="onAssistantThreadScroll"
                >
                  <article
                    v-for="message in chatMessages"
                    :key="message.id"
                    class="assistant-message"
                    :class="`assistant-message--${message.role}`"
                  >
                    <div class="assistant-bubble">
                      <p>{{ message.content }}</p>
                      <time class="assistant-bubble__time">{{ message.time }}</time>
                    </div>
                  </article>
                </div>

                <button
                  v-if="showAssistantScrollBottom"
                  type="button"
                  class="assistant-scroll-bottom-btn"
                  aria-label="回到最新消息"
                  @click="scrollToAssistantBottom()"
                >
                  <el-icon><CaretBottom /></el-icon>
                </button>
              </div>

              <footer class="assistant-composer">
                <el-input
                  v-model="chatInput"
                  type="textarea"
                  :rows="4"
                  resize="none"
                  maxlength="240"
                  show-word-limit
                  placeholder="输入想调整的创作问题，例如：把前三集反转压得更强。"
                  @keydown.ctrl.enter.prevent="sendChatMessage"
                />
                <div class="assistant-composer__actions">
                  <span></span>
                  <el-button
                    class="assistant-send-btn"
                    type="primary"
                    :disabled="!chatInput.trim()"
                    @click="sendChatMessage"
                  >
                    <el-icon><MagicStick /></el-icon>
                    &nbsp;发送（Ctrl+Enter）
                  </el-button>
                </div>
              </footer>
            </section>
          </aside>

          <section class="workspace-main">
            <section class="concept-hero">
              <div>
                <div class="hero-taxonomy">
                  <div
                    v-for="item in heroTaxonomyCards"
                    :key="item.key"
                    class="hero-taxonomy-card"
                  >
                    <span class="hero-taxonomy-label">{{ item.label }}</span>
                    <el-select
                      v-model="heroTaxonomyValues[item.key]"
                      class="hero-taxonomy-select"
                      popper-class="original-taxonomy-select"
                      size="small"
                      :teleported="true"
                      :aria-label="`选择${item.label}`"
                    >
                      <el-option
                        v-for="option in item.values"
                        :key="option"
                        :label="option"
                        :value="option"
                      />
                    </el-select>
                  </div>
                </div>
                <h2>{{ draft.title }}</h2>
                <div class="project-content-type">
                  <strong>{{ projectContentType }}</strong>
                </div>
                <p>{{ draft.logline }}</p>
              </div>
              <div class="hero-meta">
                <div class="hero-meta-card">
                  <div class="hero-meta-card__main">
                    <strong>{{ idea.episodeCount }}</strong>
                    <span>集数</span>
                  </div>
                  <div
                    class="hero-meta-control-rail"
                    role="group"
                    aria-label="调整集数"
                  >
                    <button
                      type="button"
                      class="hero-meta-control"
                      aria-label="增加集数"
                      :disabled="idea.episodeCount >= EPISODE_MAX"
                      @click="adjustEpisodeCount(1)"
                    >
                      <el-icon><CaretTop /></el-icon>
                    </button>
                    <button
                      type="button"
                      class="hero-meta-control"
                      aria-label="减少集数"
                      :disabled="idea.episodeCount <= EPISODE_MIN"
                      @click="adjustEpisodeCount(-1)"
                    >
                      <el-icon><CaretBottom /></el-icon>
                    </button>
                  </div>
                </div>

                <div class="hero-meta-card hero-meta-card--duration">
                  <span class="hero-meta-card__label">单集时长</span>
                  <el-select
                    ref="durationSelectRef"
                    v-model="durationSelectValue"
                    class="duration-select"
                    popper-class="original-duration-select"
                    :teleported="true"
                    @change="applyDurationOption"
                  >
                    <el-option
                      v-for="option in durationSelectOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />

                    <el-option
                      :value="CUSTOM_DURATION_VALUE"
                      label="自定义时长"
                      class="duration-custom-option"
                    >
                      <div class="duration-custom" @click.stop @mousedown.stop>
                        <span class="duration-custom__label">自定义时长</span>
                        <el-input-number
                          v-model="durationDraft.amount"
                          class="duration-custom__amount"
                          size="small"
                          controls-position="right"
                          :min="1"
                          :max="999"
                          :step="1"
                        />
                        <select
                          v-model="durationDraft.unit"
                          class="duration-custom__unit"
                          aria-label="选择时间单位"
                          @click.stop
                          @mousedown.stop
                        >
                          <option
                            v-for="unit in durationUnitOptions"
                            :key="unit"
                            :value="unit"
                          >
                            {{ unit }}
                          </option>
                        </select>
                        <el-button
                          class="duration-custom__apply"
                          size="small"
                          type="primary"
                          @click.stop="applyCustomDuration"
                        >
                          应用
                        </el-button>
                      </div>
                    </el-option>
                  </el-select>
                </div>
              </div>
            </section>

            <section class="result-panel" @scroll="closeConstraintPopover">
            <section class="content-grid">
              <article class="block-card">
                <div class="section-title">
                  <strong>黄金三秒钩子</strong>
                  <el-popover
                    v-model:visible="constraintPopoverVisible"
                    placement="bottom-end"
                    trigger="click"
                    width="260"
                    popper-class="original-constraint-popover"
                    transition="el-zoom-in-top"
                  >
                    <template #reference>
                      <button type="button" class="constraint-trigger">
                        生成约束
                        <span>{{ draft.constraints.length }}</span>
                      </button>
                    </template>
                    <div class="constraint-popover">
                      <div class="constraint-popover-list">
                        <span v-for="item in draft.constraints" :key="item">{{ item }}</span>
                      </div>
                    </div>
                  </el-popover>
                </div>
                <p class="hook-text">{{ draft.openingHook }}</p>
              </article>
            </section>

            <section class="episode-board">
              <div class="section-title">
                <strong>剧本草稿</strong>
                <span>{{ draft.episodes.length }} 集草稿</span>
              </div>

              <div class="episode-list">
                <article v-for="episode in draft.episodes" :key="episode.index" class="episode-card">
                  <span class="episode-index">EP{{ String(episode.index).padStart(2, '0') }}</span>
                  <div>
                    <h3>{{ episode.title }}</h3>
                    <p>{{ episode.beat }}</p>
                    <strong>{{ episode.cliffhanger }}</strong>
                  </div>
                </article>
              </div>
            </section>

            <aside class="resource-panel">
            <div class="resource-stack">
              <section class="panel-section">
                <div class="section-title">
                  <strong>一句话创意</strong>
                </div>

                <el-form class="idea-form" label-position="top">
                  <el-form-item>
                    <el-input
                      v-model="idea.topic"
                      class="idea-topic-input"
                      type="textarea"
                      :rows="4"
                      maxlength="300"
                      show-word-limit
                      placeholder="例如：被裁员的外卖员意外继承一家濒临倒闭的AI影像公司，用短剧逆袭资本局。"
                    />
                  </el-form-item>

                  <el-form-item label="核心卖点">
                    <el-input
                      v-model="idea.sellingPoint"
                      class="selling-point-input"
                      type="textarea"
                      :rows="3"
                      maxlength="80"
                      placeholder="例如：强反转、低成本场景、每集结尾留钩子"
                      show-word-limit
                    />
                  </el-form-item>
                </el-form>
              </section>

              <section class="panel-section asset-panel">
                <div class="section-title asset-section-title">
                  <div class="asset-title-copy">
                    <strong>资产管理</strong>
                    <span>{{ totalAssetCount }} 个</span>
                  </div>

                  <el-button size="small" class="asset-manage-btn" @click="openAssetManager">
                    <el-icon><Picture /></el-icon>
                    &nbsp;资产管理
                  </el-button>
                </div>

                <el-collapse v-model="activeAssetGroup" accordion class="asset-accordion">
                  <el-collapse-item
                    v-for="group in assetGroups"
                    :key="group.type"
                    :name="group.type"
                  >
                    <template #title>
                      <span class="asset-group__head">
                        <span>{{ group.label }}</span>
                        <em>{{ group.items.length }}</em>
                      </span>
                    </template>

                    <div class="asset-list">
                      <article
                        v-for="asset in group.items"
                        :key="`${group.type}-${asset.name}`"
                        class="asset-item"
                        :class="`asset-item--${asset.type}`"
                      >
                        <div class="asset-item__mark">{{ group.label.slice(0, 1) }}</div>
                        <div class="asset-item__body">
                          <strong>{{ asset.name }}</strong>
                          <p v-if="asset.desc">{{ asset.desc }}</p>
                        </div>
                      </article>

                      <p v-if="group.items.length === 0" class="asset-empty">
                        暂无{{ group.label }}资产
                      </p>
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </section>

            </div>
            </aside>
            </section>
          </section>
        </section>
      </section>
    </div>

    <Settings v-model="settingsVisible" />

    <el-dialog
      v-model="templateAddDialogVisible"
      title="添加灵感模板"
      width="min(560px, calc(100vw - 32px))"
      append-to-body
      destroy-on-close
      class="template-add-dialog"
    >
      <el-form class="template-add-form" label-position="top" @submit.prevent>
        <div class="template-add-form__grid">
          <el-form-item label="题材">
            <el-input
              v-model="templateDraft.genre"
              maxlength="20"
              placeholder="如：都市逆袭"
            />
          </el-form-item>
          <el-form-item label="模板标题">
            <el-input
              v-model="templateDraft.title"
              maxlength="40"
              placeholder="如：雨夜继承者"
            />
          </el-form-item>
        </div>

        <el-form-item label="黄金三秒钩子">
          <el-input
            v-model="templateDraft.hook"
            maxlength="40"
            placeholder="一句话概括开场反差"
          />
        </el-form-item>

        <el-form-item label="一句话创意">
          <el-input
            v-model="templateDraft.topic"
            type="textarea"
            :rows="3"
            maxlength="160"
            resize="none"
            placeholder="写清主角、冲突和反转方向"
          />
        </el-form-item>

        <el-form-item label="核心卖点">
          <el-input
            v-model="templateDraft.sellingPoint"
            type="textarea"
            row="3"
            maxlength="80"
            placeholder="如：低成本场景、强反转、系列化"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="resetTemplateDraft">清空</el-button>
        <el-button type="primary" @click="addInspirationTemplate">保存</el-button>
      </template>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  CaretBottom,
  CaretTop,
  Connection,
  Document,
  Download,
  Folder,
  List,
  MagicStick,
  Picture,
  Plus,
  Refresh,
  Setting,
  Tickets,
  VideoCamera,
} from '@element-plus/icons-vue'
import Settings from '../components/Settings.vue'

type AssetSeedType = 'role' | 'scene' | 'prop'
type DurationUnit = '秒' | '分钟'
type HeroTaxonomyKey = 'visualStyle' | 'directorStyle' | 'videoRatio'

interface TemplatePreset {
  id: string
  title: string
  genre: string
  hook: string
  topic: string
  sellingPoint: string
}

type TemplateDraft = Omit<TemplatePreset, 'id'>

interface EpisodeBeat {
  index: number
  title: string
  beat: string
  cliffhanger: string
}

interface CharacterSeed {
  name: string
  role: string
  visual: string
}

interface AssetSeed {
  name: string
  type: AssetSeedType
  desc?: string
}

interface AssetGroup {
  type: AssetSeedType
  label: string
  items: AssetSeed[]
}

interface ChatMessage {
  id: number
  role: 'assistant' | 'user'
  content: string
  time: string
}

interface DramaProjectProfile {
  title: string
  contentType: string
  logline: string
}

interface DramaStoryStructure {
  openingHook: string
  episodes: EpisodeBeat[]
}

interface DramaProductionPlan {
  constraints: string[]
}

interface DramaAssetLibrary {
  characters: CharacterSeed[]
  assets: AssetSeed[]
}

interface DramaDraft {
  title: string
  genre: string
  logline: string
  openingHook: string
  constraints: string[]
  episodes: EpisodeBeat[]
  characters: CharacterSeed[]
  assets: AssetSeed[]
}

interface DurationSelectExpose {
  blur?: () => void
  handleClickOutside?: (event: Event) => void
  dropdownMenuVisible?: boolean | { value: boolean }
}

const router = useRouter()
const route = useRoute()

const ASSET_TYPE_LABELS: Record<AssetSeedType, string> = {
  role: '角色',
  scene: '场景',
  prop: '道具',
}

const ASSET_TYPE_ORDER: AssetSeedType[] = ['role', 'scene', 'prop']

const heroTaxonomyOptions: { key: HeroTaxonomyKey; label: string; values: string[] }[] = [
  { key: 'visualStyle', label: '视觉风格', values: ['都市写实', '3D 国风', '赛博霓虹', '轻喜剧暖调'] },
  { key: 'directorStyle', label: '导演风格', values: ['快节奏反转', '冷峻悬疑', '情绪特写', '手持纪实'] },
  { key: 'videoRatio', label: '画幅比例', values: ['16:9 横屏', '9:16 竖屏', '1:1 方屏'] },
]
const durationPresetOptions = [
  { label: '45 秒', value: '45|秒', amount: 45, unit: '秒' as DurationUnit },
  { label: '60 秒', value: '60|秒', amount: 60, unit: '秒' as DurationUnit },
  { label: '90 秒', value: '90|秒', amount: 90, unit: '秒' as DurationUnit },
  { label: '1 分钟', value: '1|分钟', amount: 1, unit: '分钟' as DurationUnit },
  { label: '2 分钟', value: '2|分钟', amount: 2, unit: '分钟' as DurationUnit },
  { label: '3 分钟', value: '3|分钟', amount: 3, unit: '分钟' as DurationUnit },
  { label: '5 分钟', value: '5|分钟', amount: 5, unit: '分钟' as DurationUnit },
  { label: '8 分钟', value: '8|分钟', amount: 8, unit: '分钟' as DurationUnit },
  { label: '10 分钟', value: '10|分钟', amount: 10, unit: '分钟' as DurationUnit },
]
const durationUnitOptions: DurationUnit[] = ['秒', '分钟']
const CUSTOM_DURATION_VALUE = '__custom_duration__'
const EPISODE_MIN = 3
const EPISODE_MAX = 24

const templates = reactive<TemplatePreset[]>([
  {
    id: 'revenge',
    title: '离婚当天继承公司',
    genre: '都市逆袭',
    hook: '弱者被羞辱后立刻翻盘',
    topic: '被净身出户的女主在离婚当天继承濒临破产的影像公司，靠AI短剧项目反杀前夫和投资人。',
    sellingPoint: '低成本办公室场景、强反转、每集结尾留钩子',
  },
  {
    id: 'mystery',
    title: '匿名账号预告死亡',
    genre: '悬疑反转',
    hook: '手机弹出下一位遇害者名字',
    topic: '一个匿名账号每天发布一条短视频，预告城市里下一位将出事的人，剪辑师发现所有视频都来自自己的素材库。',
    sellingPoint: '手机屏幕、办公室、楼道即可完成主要场景',
  },
  {
    id: 'workplace',
    title: '实习生改写爆款规则',
    genre: '职场爽剧',
    hook: '实习生一句话推翻老板方案',
    topic: '短剧公司濒临倒闭，最不起眼的实习生用一套反常识选题法连续做出爆款，却发现流量背后有人操盘。',
    sellingPoint: '短剧行业题材、强代入、适合系列化',
  },
])

const activeTemplate = ref('revenge')
const activeAssetGroup = ref<AssetSeedType | ''>('')
const generating = ref(false)
const settingsVisible = ref(false)
const templateAddDialogVisible = ref(false)
const constraintPopoverVisible = ref(false)
const chatInput = ref('')
const assistantThreadRef = ref<HTMLElement | null>(null)
const showAssistantScrollBottom = ref(false)
let chatSeq = 4
let customTemplateSeq = templates.length + 1

const templateDraft = reactive<TemplateDraft>({
  genre: '',
  title: '',
  hook: '',
  topic: '',
  sellingPoint: '',
})

const idea = reactive({
  topic: templates[0].topic,
  episodeCount: 8,
  duration: '90 秒',
  sellingPoint: templates[0].sellingPoint,
})

const heroTaxonomyValues = reactive<Record<HeroTaxonomyKey, string>>({
  visualStyle: '都市写实',
  directorStyle: '快节奏反转',
  videoRatio: '16:9 横屏',
})

const durationDraft = reactive({
  amount: 90,
  unit: '秒' as DurationUnit,
})
const durationSelectValue = ref('90|秒')
const durationSelectRef = ref<DurationSelectExpose | null>(null)

const projectProfile = reactive<DramaProjectProfile>({
  title: '古相思曲',
  contentType: '穿越、爱情、架空、古装',
  logline: '《古相思曲》是由哔哩哔哩出品，知竹执导，张雅钦、郭迦南领衔主演，朱林雨、全伊伦、庄翰、黄靖洲主演，淳于珊珊特别出演的古装奇幻爱情剧。',
})

const storyStructure = reactive<DramaStoryStructure>({
  openingHook: '离婚协议刚签完，前夫把她的行李扔进雨里；下一秒，律师递来文件：“这家公司，现在归你。”',
  episodes: [
    {
      index: 1,
      title: '雨夜接手',
      beat: '女主被羞辱离婚，意外继承公司，第一次看到公司债务和未完成短剧项目。',
      cliffhanger: '她发现项目署名竟然是前夫。',
    },
    {
      index: 2,
      title: '爆款赌局',
      beat: '女主决定用 48 小时做出样片，拉拢被边缘化的剪辑师和编剧。',
      cliffhanger: '投资人要求她签下对赌协议。',
    },
    {
      index: 3,
      title: '素材失窃',
      beat: '样片上线前素材库被清空，团队只能用残片重组剧情。',
      cliffhanger: '爆款数据异常上涨。',
    },
  ],
})

const productionPlan = reactive<DramaProductionPlan>({
  constraints: ['2 个场景', '4 名角色', '1 个道具'],
})

const assetLibrary = reactive<DramaAssetLibrary>({
  characters: [
    {
      name: '林夏',
      role: '女主 / 新任老板',
      visual: '短发、浅色风衣、克制表情，适合雨夜和办公室场景。',
    },
    {
      name: '顾远',
      role: '剪辑师 / 盟友',
      visual: '黑色卫衣、眼下疲态，常出现在剪辑台和楼梯间。',
    },
    {
      name: '周启明',
      role: '前夫 / 对手',
      visual: '深色西装、金属腕表，办公室冷光下压迫感强。',
    },
  ],
  assets: [
    { name: '雨夜公司门口', type: 'scene', desc: '低成本外景，适合开场反差' },
    { name: '旧剪辑台', type: 'scene', desc: '核心工作区，可跨集复用' },
    { name: '离婚协议', type: 'prop', desc: '推动继承反转的关键文件' },
    { name: '林夏主视觉', type: 'role', desc: '用于后续角色定妆和海报参考' },
  ],
})

const projectContentType = computed(() => projectProfile.contentType)

const draft = computed<DramaDraft>(() => ({
  title: projectProfile.title,
  genre: projectProfile.contentType,
  logline: projectProfile.logline,
  openingHook: storyStructure.openingHook,
  constraints: productionPlan.constraints,
  episodes: storyStructure.episodes,
  characters: assetLibrary.characters,
  assets: assetLibrary.assets,
}))

const assetGroups = computed<AssetGroup[]>(() => {
  const roleAssets: AssetSeed[] = assetLibrary.characters.map((character) => ({
    name: character.name,
    type: 'role',
    desc: `${character.role} · ${character.visual}`,
  }))
  const allAssets = [...roleAssets, ...assetLibrary.assets]

  return ASSET_TYPE_ORDER.map((type) => ({
    type,
    label: ASSET_TYPE_LABELS[type],
    items: allAssets.filter((asset) => asset.type === type),
  }))
})

const totalAssetCount = computed(() =>
  assetGroups.value.reduce((total, group) => total + group.items.length, 0),
)

const heroTaxonomyCards = computed(() =>
  heroTaxonomyOptions.map((item) => ({
    key: item.key,
    label: item.label,
    values: item.values,
  })),
)

const durationSelectOptions = computed(() => {
  const hasCurrent = durationPresetOptions.some((option) => option.value === durationSelectValue.value)
  if (hasCurrent) return durationPresetOptions
  return [
    {
      label: idea.duration,
      value: durationSelectValue.value,
      amount: durationDraft.amount,
      unit: durationDraft.unit,
    },
    ...durationPresetOptions,
  ]
})

const formatChatTime = (date = new Date()) =>
  date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

const chatMessages = ref<ChatMessage[]>([
  {
    id: 1,
    role: 'assistant',
    content: '我已经读取当前创意、题材、集数和资产列表。你可以继续让我压缩钩子、增强反转，或者把分集节奏改成更适合短视频平台的版本。',
    time: '09:30',
  },
  {
    id: 2,
    role: 'user',
    content: '先帮我判断前三集是不是有足够强的反转。',
    time: '09:31',
  },
  {
    id: 3,
    role: 'assistant',
    content: '前三集结构可用，但第二集的对赌压力可以提前到第一集末尾，第三集素材失窃再叠加“内鬼嫌疑”，这样每集结尾都会有更明确的追看理由。',
    time: '09:32',
  },
])

const nextTasks = computed(() => [
  { title: '故事大纲生成', desc: '把创意扩展成完整剧情骨架', icon: Tickets },
  { title: '分集剧本拆分', desc: '每集生成冲突、对白和结尾钩子', icon: Document },
  { title: '关联资产生成', desc: '关联资产（角色、场景、道具）自动生成', icon: Picture },
])

const applyTemplate = (template: TemplatePreset) => {
  activeTemplate.value = template.id
  idea.topic = template.topic
  idea.sellingPoint = template.sellingPoint
}

const selectTemplate = (id: string) => {
  const template = templates.find((item) => item.id === id)
  if (!template) return
  applyTemplate(template)
  ElMessage.success(`已选择「${template.title}」模板`)
}

const rotateTemplate = () => {
  const candidates = templates.filter((item) => item.id !== activeTemplate.value)
  const pool = candidates.length > 0 ? candidates : templates
  const nextTemplate = pool[Math.floor(Math.random() * pool.length)]
  if (!nextTemplate) return
  applyTemplate(nextTemplate)
  ElMessage.success(`已切换到「${nextTemplate.title}」模板`)
}

const resetTemplateDraft = () => {
  templateDraft.genre = ''
  templateDraft.title = ''
  templateDraft.hook = ''
  templateDraft.topic = ''
  templateDraft.sellingPoint = ''
}

const openTemplateDialog = () => {
  resetTemplateDraft()
  templateAddDialogVisible.value = true
}

const addInspirationTemplate = () => {
  const title = templateDraft.title.trim()
  const topic = templateDraft.topic.trim()
  if (!title || !topic) {
    ElMessage.warning('请填写模板标题和一句话创意')
    return
  }

  const template: TemplatePreset = {
    id: `custom-${Date.now()}-${customTemplateSeq++}`,
    title,
    genre: templateDraft.genre.trim() || '自定义',
    hook: templateDraft.hook.trim() || title,
    topic,
    sellingPoint: templateDraft.sellingPoint.trim() || '强冲突、强反转、适合短剧化',
  }

  templates.push(template)
  applyTemplate(template)
  resetTemplateDraft()
  templateAddDialogVisible.value = false
  ElMessage.success(`已添加「${template.title}」模板`)
}

const adjustEpisodeCount = (delta: number) => {
  idea.episodeCount = Math.min(EPISODE_MAX, Math.max(EPISODE_MIN, idea.episodeCount + delta))
}

const formatDuration = (amount: number, unit: DurationUnit) => `${amount} ${unit}`

const normalizeDurationAmount = (amount: number | undefined) => {
  if (!Number.isFinite(amount)) return 1
  return Math.min(999, Math.max(1, Math.round(amount ?? 1)))
}

const syncDuration = () => {
  durationDraft.amount = normalizeDurationAmount(durationDraft.amount)
  durationSelectValue.value = `${durationDraft.amount}|${durationDraft.unit}`
  idea.duration = formatDuration(durationDraft.amount, durationDraft.unit)
}

const closeDurationSelect = () => {
  nextTick(() => {
    const select = durationSelectRef.value
    select?.handleClickOutside?.(new Event('click'))
    if (select?.dropdownMenuVisible && typeof select.dropdownMenuVisible === 'object') {
      select.dropdownMenuVisible.value = false
    } else if (select && 'dropdownMenuVisible' in select) {
      select.dropdownMenuVisible = false
    }
    select?.blur?.()
  })
}

const applyDurationOption = (value: string) => {
  if (value === CUSTOM_DURATION_VALUE) {
    durationSelectValue.value = `${durationDraft.amount}|${durationDraft.unit}`
    return
  }

  const [amountText, unitText] = value.split('|')
  const unit = durationUnitOptions.includes(unitText as DurationUnit) ? (unitText as DurationUnit) : '秒'
  durationDraft.amount = normalizeDurationAmount(Number(amountText))
  durationDraft.unit = unit
  syncDuration()
}

const applyCustomDuration = () => {
  syncDuration()
  closeDurationSelect()
}

const generateConcept = async () => {
  if (!idea.topic.trim()) {
    ElMessage.warning('请先输入一句话创意')
    return
  }

  generating.value = true
  await new Promise((resolve) => setTimeout(resolve, 500))

  const topicText = idea.topic.trim()
  projectProfile.title = buildTitle(topicText)
  projectProfile.logline = `${topicText} 核心卖点是${idea.sellingPoint || '强冲突、强反转、低成本可拍'}，适合做成 ${idea.episodeCount} 集原创短剧，画幅 ${heroTaxonomyValues.videoRatio}。`
  storyStructure.openingHook = `前三秒直接给出反差：${topicText.slice(0, 38)}……随后用一句台词把主角推入无法回头的选择。`
  productionPlan.constraints = [
    projectContentType.value,
    heroTaxonomyValues.visualStyle,
    heroTaxonomyValues.directorStyle,
    heroTaxonomyValues.videoRatio,
    `${idea.episodeCount} 集`,
    `单集 ${idea.duration}`,
  ]
  storyStructure.episodes = Array.from({ length: idea.episodeCount }, (_, index) => ({
    index: index + 1,
    title: buildEpisodeTitle(index),
    beat: buildEpisodeBeat(index),
    cliffhanger: buildCliffhanger(index),
  }))
  assetLibrary.characters = buildCharacters()
  assetLibrary.assets = buildAssets()
  generating.value = false
  ElMessage.success('原创短剧方案已生成')
}


const isAssistantThreadAtBottom = () => {
  const el = assistantThreadRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= 24
}

const updateAssistantScrollState = () => {
  const el = assistantThreadRef.value
  if (!el) {
    showAssistantScrollBottom.value = false
    return
  }
  showAssistantScrollBottom.value = el.scrollHeight > el.clientHeight && !isAssistantThreadAtBottom()
}

const scrollToAssistantBottom = (behavior: ScrollBehavior = 'smooth') => {
  const el = assistantThreadRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior })
  showAssistantScrollBottom.value = false
}

const onAssistantThreadScroll = () => {
  updateAssistantScrollState()
}

const closeConstraintPopover = () => {
  constraintPopoverVisible.value = false
}

const sendChatMessage = () => {
  const content = chatInput.value.trim()
  if (!content) {
    ElMessage.warning('请输入对话内容')
    return
  }

  chatMessages.value.push({
    id: chatSeq++,
    role: 'user',
    content,
    time: formatChatTime(),
  })
  chatInput.value = ''

  chatMessages.value.push({
    id: chatSeq++,
    role: 'assistant',
    content: `已收到“${content}”。正式接入 AI 后，这里会结合当前《${draft.value.title}》草案继续多轮推演，并同步更新右侧创意输入与中间方案。`,
    time: formatChatTime(),
  })
  nextTick(() => scrollToAssistantBottom())
}

onMounted(() => {
  window.addEventListener('scroll', closeConstraintPopover, true)
  nextTick(() => scrollToAssistantBottom('auto'))
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', closeConstraintPopover, true)
})

const openAssetManager = () => {
  ElMessage.info('资产管理功能待接入')
}

const buildTitle = (text: string) => {
  if (text.includes('离婚')) return '离婚当天继承公司'
  if (text.includes('死亡') || text.includes('匿名')) return '匿名账号预告死亡'
  if (text.includes('实习')) return '实习生改写爆款规则'
  return `${projectContentType.value}短剧方案`
}

const buildEpisodeTitle = (index: number) => {
  const titles = ['强钩子开场', '第一次反转', '关系结盟', '中段危机', '真相逼近', '结尾爆点']
  return titles[index] ?? `第 ${index + 1} 集推进`
}

const buildEpisodeBeat = (index: number) => {
  const beats = [
    '主角遭遇羞辱或意外事件，观众在第一集看清目标和代价。',
    '主角尝试反击却发现局面更复杂，反派掌握关键资源。',
    '主角找到临时盟友，建立可执行的低成本行动方案。',
    '计划被破坏，核心道具或素材丢失，关系出现裂痕。',
    '主角发现真正操盘者，前面的异常数据开始回收。',
    '主角用对手的规则反制对手，留下下一季或后续悬念。',
  ]
  return beats[index] ?? '推进主线冲突并回收前一集钩子。'
}

const buildCliffhanger = (index: number) => {
  const hooks = [
    '主角收到一份本不该存在的合同。',
    '对手提前发布了同款内容。',
    '盟友手机里出现关键录音。',
    '监控画面显示内鬼就在团队里。',
    '投资人背后的真正身份曝光。',
    '胜利后，主角发现项目还有隐藏债务。',
  ]
  return hooks[index] ?? '新的敌人出现。'
}

const buildCharacters = (): CharacterSeed[] => [
  {
    name: '主角',
    role: '被迫入局的人',
    visual: '干净轮廓、情绪克制，服装方便跨集复用。',
  },
  {
    name: '盟友',
    role: '提供技能或资源',
    visual: '深色休闲装，常在工作台、车内或楼道出现。',
  },
  {
    name: '对手',
    role: '掌握资源的人',
    visual: '西装或精致商务装，冷色灯光下更有压迫感。',
  },
]

const buildAssets = (): AssetSeed[] => [
  { name: '主角标准照', type: 'role', desc: '用于定妆和一致性参考' },
  { name: '对手标准照', type: 'role', desc: '用于定妆和冲突海报参考' },
  { name: '办公室主场景', type: 'scene', desc: '主要对话和反转发生地' },
  { name: '手机聊天截图', type: 'prop', desc: '适合承载线索和反转信息' },
  { name: '关键合同', type: 'prop', desc: '推动剧情转折的核心文件' },
]

const exportConcept = () => {
  ElMessage.info('已整理原创短剧草案，可进入故事大纲或剧本生成')
}

const goStoryboardStage = () => {
  const projectId = route.query.id
  const id = Array.isArray(projectId) ? projectId[0] : projectId

  if (id) {
    router.push({ path: '/script', query: { id } })
    return
  }

  router.push('/script')
}

const goProject = () => {
  router.push('/project')
}

const resolveProjectPublicId = () => {
  const projectId = route.query.id
  if (Array.isArray(projectId)) return projectId[0] || ''
  return typeof projectId === 'string' ? projectId : ''
}

const goTasks = () => {
  const projectId = resolveProjectPublicId()
  if (!projectId) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  router.push({
    path: '/tasks',
    query: {
      id: projectId,
      type: 'original',
      from: route.fullPath,
    },
  })
}

const showComingSoon = () => {
  ElMessage.info('功能开发中')
}
</script>

<style scoped>
.original-page {
  height: 100vh;
  height: 100dvh;
  min-height: 760px;
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
  transition: transform 0.2s ease;
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
  min-width: 0;
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

.primary-button {
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

.primary-button :deep(.el-icon) {
  margin-right: 0;
  font-size: 16px;
}

.primary-button:hover,
.primary-button:focus {
  background: #1d4ed8;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.28);
  transform: translateY(-1px);
}

.header-action {
  height: 38px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #c5cdd6;
  background-color: rgba(255, 255, 255, 0.04);
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.header-action :deep(.el-icon) {
  margin-right: 0;
  font-size: 16px;
}

.header-action:hover,
.header-action:focus {
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.18);
  background-color: rgba(255, 255, 255, 0.08);
  transform: translateY(-1px);
}

.stage-button {
  border-color: rgba(96, 165, 250, 0.28);
  color: #bfdbfe;
  background-color: rgba(37, 99, 235, 0.12);
}

.stage-button:hover,
.stage-button:focus {
  border-color: rgba(147, 197, 253, 0.42);
  color: #ffffff;
  background-color: rgba(37, 99, 235, 0.20);
}

.workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: clamp(368px, 24vw, 432px) minmax(0, 1fr);
  gap: 8px;
  overflow: hidden;
}

.ai-chat-panel,
.workspace-main {
  min-height: 0;
}

.workspace-main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.result-panel {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.42fr);
  gap: 7px;
  align-content: start;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.resource-panel {
  min-height: 0;
  grid-column: 2;
  grid-row: 1 / span 2;
}

.ai-chat-panel {
  overflow: hidden;
}

.assistant-shell {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background:
    radial-gradient(circle at 20% 0%, rgba(37, 99, 235, 0.14), transparent 34%),
    linear-gradient(180deg, rgba(15, 22, 32, 0.92), rgba(7, 11, 17, 0.96));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 22px 52px rgba(0, 0, 0, 0.42);
  overflow: hidden;
}

.assistant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 58px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.01)),
    rgba(9, 14, 22, 0.86);
}

.assistant-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.assistant-status-dot {
  position: relative;
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow:
    0 0 0 4px rgba(34, 197, 94, 0.12),
    0 0 18px rgba(34, 197, 94, 0.32);
}

.assistant-heading h2 {
  margin: 0;
  color: #f2f4f8;
  font-size: 16px;
  line-height: 1.25;
  font-weight: 750;
}

.assistant-heading p {
  margin: 3px 0 0;
  color: #7e8893;
  font-size: 12px;
  line-height: 1.35;
}

.assistant-message-count {
  flex-shrink: 0;
  min-width: 54px;
  padding: 5px 9px;
  border-radius: 999px;
  color: #93c5fd;
  border: 1px solid rgba(96, 165, 250, 0.22);
  background: rgba(37, 99, 235, 0.12);
  text-align: center;
  font-size: 12px;
  font-weight: 700;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.assistant-thread-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  background: rgba(4, 8, 14, 0.24);
}

.assistant-thread {
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 14px 18px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.assistant-thread::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.assistant-thread::-webkit-scrollbar-track {
  background: transparent;
}

.assistant-thread::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.assistant-thread::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.assistant-scroll-bottom-btn {
  position: absolute;
  right: 16px;
  bottom: 14px;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(96, 165, 250, 0.38);
  border-radius: 50%;
  color: #dbeafe;
  background: rgba(13, 18, 27, 0.92);
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.34);
  cursor: pointer;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.assistant-scroll-bottom-btn :deep(.el-icon) {
  font-size: 18px;
}

.assistant-scroll-bottom-btn:hover,
.assistant-scroll-bottom-btn:focus {
  color: #ffffff;
  border-color: rgba(96, 165, 250, 0.65);
  background: rgba(37, 99, 235, 0.72);
  transform: translateY(-1px);
}

.assistant-scroll-bottom-btn:active {
  transform: translateY(0);
}

.assistant-message {
  display: flex;
  align-items: flex-start;
}

.assistant-message--user {
  justify-content: flex-end;
}

.assistant-message--user .assistant-bubble {
  max-width: 82%;
  border-color: rgba(96, 165, 250, 0.36);
  background:
    linear-gradient(180deg, rgba(37, 99, 235, 0.28), rgba(37, 99, 235, 0.16)),
    rgba(13, 18, 27, 0.86);
}

.assistant-bubble {
  min-width: 0;
  max-width: 88%;
  display: grid;
  gap: 6px;
  padding: 11px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.012)),
    rgba(15, 22, 32, 0.88);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.18);
}

.assistant-bubble__time {
  justify-self: end;
  color: #7e8893;
  font-size: 11px;
  line-height: 1;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.assistant-bubble p {
  margin: 0;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.68;
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-composer {
  display: grid;
  gap: 10px;
  padding: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent),
    rgba(9, 14, 22, 0.92);
}

.assistant-composer :deep(.el-textarea__inner) {
  min-height: 104px !important;
  padding: 12px 13px 24px;
  border: none;
  border-radius: 10px;
  color: #e6edf3;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  font-size: 13px;
  line-height: 1.6;
}

.assistant-composer :deep(.el-textarea__inner:hover) {
  background-color: #0f151d;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.2) inset;
}

.assistant-composer :deep(.el-textarea__inner:focus) {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.assistant-composer :deep(.el-textarea__inner::placeholder) {
  color: #7e8893;
}

.assistant-composer :deep(.el-input__count) {
  color: #6e7681 !important;
  background: transparent !important;
  background-color: transparent !important;
}

.assistant-composer__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.assistant-composer__actions span {
  min-width: 0;
  color: #6e7681;
  font-size: 12px;
  line-height: 1.45;
}

.assistant-send-btn {
  --el-button-disabled-bg-color: rgba(255, 255, 255, 0.04);
  --el-button-disabled-border-color: rgba(255, 255, 255, 0.08);
  --el-button-disabled-text-color: #4d5560;
  flex-shrink: 0;
  height: 36px;
  min-width: 86px;
  padding: 0 16px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
}

.assistant-send-btn:hover,
.assistant-send-btn:focus {
  transform: translateY(-1px);
}

.assistant-send-btn :deep(.el-icon) {
  margin-right: 0;
  font-size: 15px;
}

.resource-stack {
  display: grid;
  gap: 7px;
}

.panel-section,
.concept-hero,
.block-card,
.episode-board {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(8, 12, 18, 0.62);
}

.panel-section {
  padding: 16px;
  margin-bottom: 7px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.section-title strong {
  color: #d5dce4;
  font-size: 14px;
}

.section-title > span {
  color: #6e7681;
  font-size: 12px;
}

.ai-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.ai-action-btn {
  height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  color: #c5cdd6;
  border-color: rgba(255, 255, 255, 0.08);
  background-color: rgba(255, 255, 255, 0.04);
  font-size: 12px;
  font-weight: 600;
}

.ai-action-btn :deep(.el-icon) {
  margin-right: 0;
  font-size: 13px;
}

.ai-action-btn:hover,
.ai-action-btn:focus {
  color: #ffffff;
  border-color: rgba(96, 165, 250, 0.42);
  background-color: rgba(37, 99, 235, 0.14);
}

.idea-form :deep(.el-form-item__label) {
  color: #c5cdd6;
  font-weight: 600;
}

.idea-form :deep(.el-textarea__inner),
.idea-form :deep(.el-input__wrapper) {
  border: none;
  border-radius: 10px;
  color: #e6edf3;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
}

.idea-form :deep(.el-textarea__inner:hover),
.idea-form :deep(.el-input__wrapper:hover) {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.idea-form :deep(.el-textarea__inner:focus),
.idea-form :deep(.el-input__wrapper.is-focus) {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.idea-form :deep(.el-input__inner),
.idea-form :deep(.el-textarea__inner) {
  color: #e6edf3;
}

.idea-form :deep(.el-input__inner::placeholder),
.idea-form :deep(.el-textarea__inner::placeholder) {
  color: #7e8893;
}

.idea-form :deep(.el-input__count),
.idea-form :deep(.el-input__count-inner),
.idea-form :deep(.el-textarea .el-input__count) {
  color: #6e7681 !important;
  background: transparent !important;
  background-color: transparent !important;
}

.idea-topic-input :deep(.el-textarea__inner) {
  min-height: 80px !important;
}

.selling-point-input :deep(.el-textarea__inner) {
  min-height: 96px !important;
}

.template-popover-panel {
  display: grid;
  gap: 12px;
}

.template-popover__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.template-popover__head strong {
  color: #f2f4f8;
  font-size: 14px;
  font-weight: 750;
}

.template-popover__head span {
  color: #8b949e;
  font-size: 12px;
}

.template-popover__tools {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.template-popover-list {
  display: flex;
  padding-top: 10px;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 2px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.template-card {
  width: 100%;
  display: grid;
  gap: 5px;
  padding: 10px 11px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #c5cdd6;
  background: rgba(255, 255, 255, 0.025);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.template-card:hover,
.template-card.is-active {
  border-color: rgba(96, 165, 250, 0.4);
  background: rgba(37, 99, 235, 0.1);
  transform: translateY(-1px);
}

.template-card span {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 700;
}

.template-card strong {
  color: #e6edf3;
  font-size: 14px;
}

.template-card em {
  color: #8b949e;
  font-size: 12px;
  font-style: normal;
}

.template-card p,
.template-card small {
  margin: 0;
  color: #7e8893;
  font-size: 12px;
  line-height: 1.45;
}

.template-card small {
  color: #6e7681;
}

.template-add-form {
  display: grid;
  gap: 8px;
}

.template-add-form__grid {
  display: grid;
  grid-template-columns: 0.8fr 1fr;
  gap: 8px;
}

.template-add-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.template-add-form :deep(.el-form-item__label) {
  color: #8b949e;
  font-size: 12px;
  font-weight: 600;
  padding-bottom: 5px;
}

.template-add-form :deep(.el-input__wrapper),
.template-add-form :deep(.el-textarea__inner) {
  background-color: #0c1015;
  border: none;
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.10) inset;
  color: #e6edf3;
  font-size: 12px;
}

.template-add-form :deep(.el-input__wrapper:hover),
.template-add-form :deep(.el-textarea__inner:hover) {
  background-color: #0f151d;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.20) inset;
}

.template-add-form :deep(.el-input__wrapper.is-focus),
.template-add-form :deep(.el-textarea__inner:focus) {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.template-add-form :deep(.el-input__inner),
.template-add-form :deep(.el-textarea__inner) {
  color: #e6edf3;
}

.template-add-form :deep(.el-input__inner::placeholder),
.template-add-form :deep(.el-textarea__inner::placeholder) {
  color: #6e7681;
}

.result-panel {
  gap: 7px;
}

.concept-hero {
  flex-shrink: 0;
  margin-bottom: 6px;
  min-height: 120px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background:
    radial-gradient(circle at 80% 0%, rgba(37, 99, 235, 0.2), transparent 34%),
    rgba(8, 12, 18, 0.62);
}

.concept-hero > div:first-child {
  flex: 1;
  min-width: 0;
}

.hero-taxonomy {
  display: grid;
  grid-template-columns: repeat(3, minmax(124px, max-content));
  gap: 6px;
  max-width: 720px;
}

.hero-taxonomy-card {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 124px;
  padding: 0 9px;
  border: 1px solid rgba(96, 165, 250, 0.22);
  border-radius: 8px;
  color: inherit;
  background: rgba(37, 99, 235, 0.09);
  font: inherit;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.hero-taxonomy-card:hover,
.hero-taxonomy-card:focus-within {
  border-color: rgba(96, 165, 250, 0.42);
  background: rgba(37, 99, 235, 0.18);
}

.hero-taxonomy-label {
  flex-shrink: 0;
  color: #8b949e;
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
}

.hero-taxonomy-card :deep(.el-icon) {
  color: #8b949e;
  font-size: 12px;
}

.hero-taxonomy-select {
  width: 96px;
}

.hero-taxonomy-select :deep(.el-select__wrapper) {
  min-height: 28px;
  padding: 0 6px 0 8px;
  border-radius: 7px;
  background-color: rgba(4, 8, 14, 0.45);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
}

.hero-taxonomy-select :deep(.el-select__wrapper:hover),
.hero-taxonomy-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.38) inset;
}

.hero-taxonomy-select :deep(.el-select__placeholder),
.hero-taxonomy-select :deep(.el-select__selected-item) {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 700;
}

.concept-hero h2 {
  margin: 5px 0;
  color: #f2f4f8;
  font-size: 22px;
  line-height: 1.2;
}

.project-content-type {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 7px;
  padding: 4px 10px;
  border: 1px solid rgba(96, 165, 250, 0.22);
  border-radius: 8px;
  background: rgba(37, 99, 235, 0.09);
}

.project-content-type strong {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.25;
  white-space: nowrap;
}

.concept-hero p {
  max-width: 680px;
  margin: 0;
  color: #9ca3af;
  font-size: 13px;
  line-height: 1.55;
}

.hero-meta {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 128px;
}

.hero-meta-card {
  min-width: 104px;
  min-height: 52px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px;
  align-items: stretch;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  color: inherit;
  background: rgba(255, 255, 255, 0.035);
  font: inherit;
  overflow: hidden;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.hero-meta-card:hover {
  border-color: rgba(96, 165, 250, 0.42);
  background: rgba(37, 99, 235, 0.12);
}

.hero-meta-card__main {
  display: grid;
  place-content: center;
  padding: 7px 8px 7px 10px;
  text-align: center;
}

.hero-meta-card__main strong,
.hero-meta-card__main span {
  display: block;
}

.hero-meta-card__main strong {
  color: #fff;
  font-size: 18px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  line-height: 1.25;
}

.hero-meta-card__main span {
  margin-top: 2px;
  color: #8b949e;
  font-size: 12px;
  white-space: nowrap;
}

.hero-meta-card--duration {
  min-width: 128px;
  grid-template-columns: 1fr;
  gap: 5px;
  padding: 8px 9px 9px;
}

.hero-meta-card__label {
  color: #8b949e;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  text-align: center;
  white-space: nowrap;
}

.duration-select {
  width: 100%;
}

.duration-select :deep(.el-select__wrapper) {
  min-height: 28px;
  padding: 0 8px;
  border-radius: 8px;
  background-color: rgba(4, 8, 14, 0.55);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
}

.duration-select :deep(.el-select__wrapper:hover),
.duration-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.38) inset;
}

.duration-select :deep(.el-select__placeholder),
.duration-select :deep(.el-select__selected-item) {
  color: #f2f4f8;
  font-size: 13px;
  font-weight: 700;
}

.hero-meta-control-rail {
  display: grid;
  grid-template-rows: 1fr 1fr;
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(4, 8, 14, 0.5);
}

.hero-meta-control {
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: #8b949e;
  background: transparent;
  cursor: pointer;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.hero-meta-control:last-child {
  border-bottom: 0;
}

.hero-meta-control:hover:not(:disabled),
.hero-meta-control:focus-visible:not(:disabled) {
  color: #dbeafe;
  background: rgba(37, 99, 235, 0.18);
}

.hero-meta-control:disabled {
  color: #3f4752;
  cursor: not-allowed;
}

.hero-meta-control :deep(.el-icon) {
  font-size: 12px;
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 7px;
}

.block-card,
.episode-board {
  padding: 16px;
}

.hook-text {
  min-height: 72px;
  margin: 0;
  color: #e6edf3;
  font-size: 14px;
  line-height: 1.8;
}

.constraint-trigger {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  border: 1px solid rgba(96, 165, 250, 0.28);
  border-radius: 999px;
  color: #c5cdd6;
  background: rgba(37, 99, 235, 0.09);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.constraint-trigger span {
  min-width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #dbeafe;
  background: rgba(37, 99, 235, 0.24);
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 11px;
}

.constraint-trigger:hover,
.constraint-trigger:focus {
  color: #ffffff;
  border-color: rgba(96, 165, 250, 0.55);
  background: rgba(37, 99, 235, 0.18);
  transform: translateY(-1px);
}

.constraint-trigger:active {
  transform: translateY(0);
}

.constraint-popover {
  display: grid;
  gap: 12px;
}

.constraint-popover header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.constraint-popover header strong {
  color: #e6edf3;
  font-size: 13px;
}

.constraint-popover header span {
  color: #7e8893;
  font-size: 12px;
}

.constraint-popover-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.constraint-popover-list span {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid rgba(96, 165, 250, 0.24);
  border-radius: 999px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.08);
  font-size: 12px;
}

.episode-list {
  display: grid;
  gap: 10px;
}

.episode-card {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.025);
}

.episode-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  border-radius: 999px;
  color: #dbeafe;
  background: rgba(37, 99, 235, 0.16);
  font-size: 12px;
  font-weight: 700;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.episode-card h3 {
  margin: 0 0 5px;
  color: #e6edf3;
  font-size: 15px;
}

.episode-card p {
  margin: 0 0 6px;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.7;
}

.episode-card strong {
  color: #fcd34d;
  font-size: 12px;
}

.asset-panel {
  padding-bottom: 14px;
}

.asset-section-title {
  align-items: flex-start;
}

.asset-title-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.asset-title-copy strong,
.asset-title-copy span {
  display: block;
}

.asset-title-copy span {
  color: #6e7681;
  font-size: 12px;
}

.asset-manage-btn {
  --el-button-bg-color: rgba(255, 255, 255, 0.04);
  --el-button-border-color: rgba(255, 255, 255, 0.08);
  --el-button-text-color: #c5cdd6;
  --el-button-hover-bg-color: rgba(37, 99, 235, 0.14);
  --el-button-hover-border-color: rgba(96, 165, 250, 0.42);
  --el-button-hover-text-color: #ffffff;
  --el-button-active-bg-color: rgba(37, 99, 235, 0.20);
  --el-button-active-border-color: rgba(96, 165, 250, 0.52);
  height: 30px;
  padding: 0 10px;
  border-radius: 8px;
  color: #c5cdd6;
  border-color: rgba(255, 255, 255, 0.08);
  background-color: rgba(255, 255, 255, 0.04);
  font-size: 12px;
  font-weight: 600;
}

.asset-manage-btn :deep(.el-icon) {
  margin-right: 0;
  font-size: 13px;
}

.asset-manage-btn:hover,
.asset-manage-btn:focus {
  color: #ffffff;
  border-color: rgba(96, 165, 250, 0.42);
  background-color: rgba(37, 99, 235, 0.14);
}

.asset-accordion {
  display: grid;
  gap: 8px;
  border: 0;
}

.asset-accordion :deep(.el-collapse-item) {
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.025);
  overflow: hidden;
}

.asset-accordion :deep(.el-collapse-item__header) {
  height: 42px;
  padding: 0 12px;
  border-bottom: 0;
  background: transparent;
  color: #d5dce4;
  line-height: 42px;
}

.asset-accordion :deep(.el-collapse-item__header.is-active) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(37, 99, 235, 0.06);
}

.asset-accordion :deep(.el-collapse-item__arrow) {
  margin-left: 8px;
  color: #6e7681;
}

.asset-accordion :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
  background: transparent;
}

.asset-accordion :deep(.el-collapse-item__content) {
  padding: 10px 12px 12px;
  color: inherit;
}

.asset-group__head {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.asset-group__head span {
  color: #d5dce4;
  font-size: 13px;
  font-weight: 700;
}

.asset-group__head em {
  min-width: 24px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.12);
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.asset-list {
  display: grid;
  gap: 8px;
}

.asset-empty {
  margin: 0;
  padding: 12px;
  border-radius: 10px;
  color: #6e7681;
  background: rgba(8, 12, 18, 0.42);
  font-size: 12px;
  text-align: center;
}

.asset-item {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 9px;
  align-items: start;
  padding: 9px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  background: rgba(8, 12, 18, 0.54);
}

.asset-item__mark {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: #dbeafe;
  background: rgba(96, 165, 250, 0.12);
  font-size: 12px;
  font-weight: 800;
}

.asset-item__body {
  min-width: 0;
}

.asset-item__body strong,
.asset-item__body p {
  display: block;
}

.asset-item__body strong {
  color: #f2f4f8;
  font-size: 13px;
  line-height: 1.35;
}

.asset-item__body p {
  margin: 4px 0 0;
  color: #8b949e;
  font-size: 12px;
  line-height: 1.55;
}

.asset-item--role .asset-item__mark {
  color: #93c5fd;
  background: rgba(96, 165, 250, 0.12);
}

.asset-item--scene .asset-item__mark {
  color: #5eead4;
  background: rgba(20, 184, 166, 0.10);
}

.asset-item--prop .asset-item__mark {
  color: #fcd34d;
  background: rgba(245, 158, 11, 0.10);
}

.generation-popover-panel {
  display: grid;
  gap: 12px;
}

.generation-task-card {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  background: rgba(15, 22, 32, 0.88);
}

.generation-task-card :deep(.el-icon) {
  margin-top: 2px;
  color: #93c5fd;
  font-size: 18px;
}

.generation-task-card strong,
.generation-task-card span {
  display: block;
}

.generation-task-card strong {
  color: #f2f4f8;
  font-size: 14px;
  line-height: 1.35;
  font-weight: 750;
}

.generation-task-card span {
  margin-top: 3px;
  color: #9ca3af;
  font-size: 13px;
  line-height: 1.45;
}

@media (max-width: 1180px) {
  .workspace {
    grid-template-columns: minmax(320px, 0.75fr) minmax(0, 1fr);
  }

  .hero-taxonomy {
    grid-template-columns: repeat(auto-fit, minmax(124px, max-content));
  }

  .result-panel {
    grid-template-columns: 1fr;
  }

  .resource-panel {
    grid-column: auto;
    grid-row: auto;
    max-height: none;
  }
}

@media (max-width: 920px) {
  .original-page {
    min-height: 920px;
  }

  .app-shell {
    grid-template-columns: 1fr;
    gap: 14px;
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

  .page-header,
  .page-header__right {
    flex-direction: column;
    align-items: stretch;
  }

  .concept-hero {
    flex-direction: column;
  }

  .hero-taxonomy {
    grid-template-columns: repeat(auto-fit, minmax(124px, 1fr));
    max-width: none;
  }

  .hero-meta {
    width: 100%;
    flex-direction: row;
    min-width: 0;
  }

  .hero-meta-card {
    flex: 1;
  }

  .workspace,
  .result-panel,
  .content-grid {
    grid-template-columns: 1fr;
  }

  .workspace {
    overflow-y: auto;
    align-content: start;
  }

  .ai-chat-panel,
  .workspace-main,
  .result-panel,
  .resource-panel {
    overflow: visible;
  }

  .ai-chat-panel {
    min-height: 640px;
  }

  .result-panel,
  .resource-panel {
    min-height: auto;
  }

  .assistant-shell {
    min-height: 640px;
  }

  .resource-panel {
    max-height: none;
  }
}
</style>

<style>
.template-popover.el-popper {
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
  color: #e6edf3;
}

.template-popover.el-popper .el-popper__arrow::before {
  background: #14181f;
  border-color: rgba(255, 255, 255, 0.08);
}

.template-popover.el-popper .el-button {
  border-radius: 8px;
}

.template-popover.el-popper .el-button:not(.el-button--primary) {
  color: #c5cdd6;
  border-color: rgba(255, 255, 255, 0.10);
  background-color: rgba(255, 255, 255, 0.04);
}

.template-popover.el-popper .el-button:not(.el-button--primary):hover {
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.20);
  background-color: rgba(255, 255, 255, 0.08);
}

.template-popover.el-popper .el-button--primary {
  border-color: #2563eb;
  background-color: #2563eb;
}

.generation-popover.el-popper {
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  background: linear-gradient(180deg, #111821 0%, #0b1016 100%);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.52);
  color: #e6edf3;
}

.generation-popover.el-popper .el-popper__arrow::before {
  background: #111821;
  border-color: rgba(255, 255, 255, 0.08);
}

.template-add-dialog {
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 18px;
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.55);
  color: #e6edf3;
  overflow: hidden;
}

.template-add-dialog .el-dialog__header {
  margin: 0;
  padding: 18px 22px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.template-add-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 18px;
  font-weight: 750;
}

.template-add-dialog .el-dialog__headerbtn {
  top: 12px;
  right: 14px;
  width: 34px;
  height: 34px;
  border-radius: 10px;
}

.template-add-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
}

.template-add-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #ffffff;
}

.template-add-dialog .el-dialog__body {
  padding: 18px 22px 8px;
}

.template-add-dialog .el-dialog__footer {
  padding: 14px 22px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.template-add-dialog .el-dialog__footer .el-button {
  border-radius: 9px;
}

.template-add-dialog .el-dialog__footer .el-button:not(.el-button--primary) {
  color: #c5cdd6;
  border-color: rgba(255, 255, 255, 0.10);
  background-color: rgba(255, 255, 255, 0.04);
}

.template-add-dialog .el-dialog__footer .el-button:not(.el-button--primary):hover {
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.20);
  background-color: rgba(255, 255, 255, 0.08);
}

.template-add-dialog .el-dialog__footer .el-button--primary {
  border-color: #2563eb;
  background-color: #2563eb;
}

.original-duration-select.el-popper {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background-color: #14181f;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}

.original-taxonomy-select.el-popper {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background-color: #14181f;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}

.original-taxonomy-select.el-popper .el-select-dropdown__item {
  height: 32px;
  margin: 2px 4px;
  padding: 0 12px;
  border-radius: 8px;
  color: #c5cdd6;
  line-height: 32px;
}

.original-taxonomy-select.el-popper .el-select-dropdown__item:hover,
.original-taxonomy-select.el-popper .el-select-dropdown__item.is-hovering {
  background-color: rgba(255, 255, 255, 0.06);
  color: #fff;
}

.original-taxonomy-select.el-popper .el-select-dropdown__item.is-selected {
  background-color: rgba(37, 99, 235, 0.16);
  color: #93c5fd;
  font-weight: 600;
}

.original-duration-select.el-popper .el-select-dropdown__item {
  height: 32px;
  margin: 2px 4px;
  padding: 0 12px;
  border-radius: 8px;
  color: #c5cdd6;
  line-height: 32px;
}

.original-duration-select.el-popper .el-select-dropdown__item:hover,
.original-duration-select.el-popper .el-select-dropdown__item.is-hovering {
  background-color: rgba(255, 255, 255, 0.06);
  color: #fff;
}

.original-duration-select.el-popper .el-select-dropdown__item.is-selected {
  background-color: rgba(37, 99, 235, 0.16);
  color: #93c5fd;
  font-weight: 600;
}

.original-duration-select.el-popper .duration-custom-option {
  height: auto;
  padding: 0;
  line-height: normal;
  cursor: default;
}

.original-duration-select.el-popper .duration-custom-option:hover,
.original-duration-select.el-popper .duration-custom-option.is-hovering,
.original-duration-select.el-popper .duration-custom-option.is-selected {
  background: transparent;
}

.duration-custom {
  display: grid;
  grid-template-columns: 1fr 92px 76px auto;
  gap: 8px;
  align-items: center;
  padding: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.duration-custom__label {
  color: #8b949e;
  font-size: 12px;
  white-space: nowrap;
}

.duration-custom__amount,
.duration-custom__unit {
  width: 100%;
}

.duration-custom__unit {
  height: 24px;
  padding: 0 8px;
  border: none;
  border-radius: 6px;
  color: #e6edf3;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.10) inset;
  outline: none;
}

.duration-custom__unit:focus {
  box-shadow:
    0 0 0 1px rgba(96, 165, 250, 0.48) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.duration-custom .el-input-number__decrease,
.duration-custom .el-input-number__increase,
.duration-custom .el-input__wrapper {
  background-color: #0c1015;
  border-color: rgba(255, 255, 255, 0.08) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.10) inset;
}

.duration-custom .el-input-number {
  color: #e6edf3;
  background: transparent;
  border-color: transparent;
}

.duration-custom .el-input-number__decrease,
.duration-custom .el-input-number__increase {
  color: #8b949e;
}

.duration-custom .el-input-number__increase {
  border-bottom-color: rgba(255, 255, 255, 0.08) !important;
}

.duration-custom .el-input-number__decrease {
  border-left-color: rgba(255, 255, 255, 0.08) !important;
  border-right-color: rgba(255, 255, 255, 0.08) !important;
}

.duration-custom .el-input-number__decrease:hover,
.duration-custom .el-input-number__increase:hover {
  color: #dbeafe;
  background-color: rgba(37, 99, 235, 0.16);
}

.duration-custom .el-input__inner {
  color: #e6edf3;
}

.duration-custom__apply {
  min-width: 54px;
}

.original-constraint-popover.el-popper {
  padding: 12px;
  border: 1px solid rgba(96, 165, 250, 0.24);
  border-radius: 12px;
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.48);
  color: #e6edf3;
}

.original-constraint-popover.el-popper .el-popper__arrow::before {
  background: #14181f;
  border-color: rgba(96, 165, 250, 0.24);
}
</style>