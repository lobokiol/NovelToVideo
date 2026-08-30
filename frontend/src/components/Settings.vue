<template>
  <el-dialog
    v-model="visible"
    title="设置"
    width="860px"
    top="8vh"
    destroy-on-close
    class="settings-dark-dialog"
  >
    <div class="settings-shell">
      <aside class="settings-nav">
        <button
          v-for="item in categories"
          :key="item.key"
          class="settings-nav__btn"
          :class="{ 'is-active': activeKey === item.key }"
          @click="activeKey = item.key"
        >
          <el-icon class="settings-nav__icon"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </button>
      </aside>

      <section class="settings-panel">
        <!-- 用户信息更新 -->
        <div v-if="activeKey === 'profile'" class="settings-section">
          <header class="section-head">
            <h2>个人资料</h2>
            <p>修改账号显示名称、邮箱和昵称</p>
          </header>

          <el-form
            ref="profileFormRef"
            v-loading="profileLoading"
            :model="profileForm"
            :rules="profileRules"
            label-position="top"
            class="settings-form"
            element-loading-background="rgba(13, 17, 23, 0.55)"
          >
            <div class="account-grid">
              <div class="account-avatar">
                <div class="avatar-circle">
                  <img v-if="profileForm.avatar_url" :src="profileForm.avatar_url" class="avatar-image" :alt="avatarLetter" />
                  <template v-else>{{ avatarLetter }}</template>
                </div>
                <el-button class="ghost-btn" size="small" :loading="avatarUploading" @click="pickAvatarFile">更换头像</el-button>
                <input
                  ref="avatarInputRef"
                  type="file"
                  accept="image/png,image/jpeg,image/jpg"
                  hidden
                  @change="onAvatarFileSelected"
                />
              </div>

              <div class="account-fields">
                <el-form-item label="账号" prop="username">
                  <el-input v-model="profileForm.username" placeholder="登录账号" maxlength="32" />
                </el-form-item>
                <el-form-item label="昵称" prop="nickname">
                  <el-input v-model="profileForm.nickname" placeholder="显示名称" maxlength="32" />
                </el-form-item>
                <el-form-item label="邮箱" prop="email">
                  <el-input v-model="profileForm.email" placeholder="example@mail.com" />
                </el-form-item>
              </div>
            </div>

            <div class="settings-form__actions">
              <el-button class="ghost-btn" @click="resetProfile">重置</el-button>
              <el-button type="primary" :loading="profileSaving" @click="saveProfile">保存修改</el-button>
            </div>
          </el-form>
        </div>

        <!-- 密码修改 -->
        <div v-else-if="activeKey === 'password'" class="settings-section">
          <header class="section-head">
            <h2>修改密码</h2>
            <p>定期更换密码，保障账号安全</p>
          </header>

          <el-form
            ref="passwordFormRef"
            :model="passwordForm"
            :rules="passwordRules"
            label-position="top"
            class="settings-form password-form"
          >
            <el-form-item label="当前密码" prop="oldPassword">
              <el-input
                v-model="passwordForm.oldPassword"
                type="password"
                show-password
                placeholder="输入当前登录密码"
              />
            </el-form-item>

            <el-form-item label="新密码" prop="newPassword">
              <el-input
                v-model="passwordForm.newPassword"
                type="password"
                show-password
                placeholder="8 位以上，建议含大小写字母与数字"
              />
              <div class="password-strength">
                <div
                  v-for="i in 4"
                  :key="i"
                  class="password-strength__bar"
                  :class="{ 'is-on': passwordStrength >= i }"
                  :data-level="passwordStrength"
                ></div>
                <span class="password-strength__label">{{ passwordStrengthLabel }}</span>
              </div>
            </el-form-item>

            <el-form-item label="确认新密码" prop="confirmPassword">
              <el-input
                v-model="passwordForm.confirmPassword"
                type="password"
                show-password
                placeholder="再次输入新密码"
              />
            </el-form-item>

            <div class="settings-form__actions">
              <el-button class="ghost-btn" @click="resetPassword">清空</el-button>
              <el-button type="primary" :loading="passwordSaving" @click="savePassword">提交修改</el-button>
            </div>
          </el-form>
        </div>

        <!-- 模型服务供应商 -->
        <div v-else-if="activeKey === 'providers'" class="settings-section">
          <header class="section-head">
            <div class="section-head__row">
              <div>
                <h2>模型服务</h2>
                <p>管理大模型供应商，配置 API Key、Base URL 与可用模型</p>
              </div>
              <div class="section-head__actions">
                <el-button class="ghost-btn" size="small" :loading="providersLoading" @click="loadProviders">刷新</el-button>
                <el-button type="primary" size="small" @click="openProviderCreate">新增供应商</el-button>
              </div>
            </div>
          </header>

          <div
            v-loading="providersLoading"
            class="provider-list"
            element-loading-background="rgba(13, 17, 23, 0.55)"
          >
            <el-empty v-if="!providersLoading && providers.length === 0" description="暂无供应商" />
            <article
              v-for="provider in providers"
              :key="provider.key"
              class="provider-card"
              :class="{ 'is-disabled': !provider.enabled }"
            >
              <div class="provider-card__head">
                <div class="provider-card__avatar">
                  <img v-if="provider.icon" :src="provider.icon" :alt="provider.name" style="background: white;" />
                  <span v-else>{{ (provider.name || provider.key).slice(0, 1).toUpperCase() }}</span>
                </div>
                <div class="provider-card__meta">
                  <div class="provider-card__title-row">
                    <h3 class="provider-card__title">{{ provider.name }}</h3>
                    <a
                      v-if="provider.url"
                      class="provider-card__link"
                      :href="provider.url"
                      target="_blank"
                      rel="noopener noreferrer"
                      :title="provider.url"
                    >
                      <el-icon><Link /></el-icon>
                      <span>官网</span>
                    </a>
                    <a
                      v-if="provider.decs_url"
                      class="provider-card__link"
                      :href="provider.decs_url"
                      target="_blank"
                      rel="noopener noreferrer"
                      :title="provider.decs_url"
                    >
                      <el-icon><Link /></el-icon>
                      <span>文档</span>
                    </a>
                    <el-tag v-if="providerHasSecret(provider)" size="small" type="success" effect="plain" round>已配置密钥</el-tag>
                    <el-tag v-else size="small" type="warning" effect="plain" round>未配置密钥</el-tag>
                  </div>
                  <div class="provider-card__chips">
                    <span class="provider-chip">{{ provider.protocol }}</span>
                    <span class="provider-chip">v{{ provider.version }}</span>
                    <span class="provider-chip provider-chip--info">{{ provider.models.length }} 个模型</span>
                  </div>
                  <div v-if="providerCapabilityCounts(provider).length" class="provider-card__capabilities">
                    <span
                      v-for="cap in providerCapabilityCounts(provider)"
                      :key="cap.type"
                      class="capability-chip"
                      :class="MODEL_TYPE_COLOR_CLASS[cap.type]"
                    >
                      <em>{{ cap.label }}</em>
                      <strong>{{ cap.count }}</strong>
                    </span>
                  </div>
                  <p v-if="provider.description" class="provider-card__desc">{{ provider.description }}</p>
                </div>
                <div class="provider-card__actions">
                  <el-switch
                    :model-value="provider.enabled"
                    @change="onToggleProviderEnabled(provider, $event)"
                  />
                  <el-button size="small" class="ghost-btn" @click="openProviderEdit(provider)">编辑</el-button>
                  <el-button size="small" type="danger" @click="onDeleteProvider(provider)">删除</el-button>
                </div>
              </div>
            </article>
          </div>
        </div>

        <!-- 注销登录 -->
        <div v-else-if="activeKey === 'logout'" class="settings-section">
          <header class="section-head">
            <h2>注销登录</h2>
            <p>退出当前账号，需要重新登录后才能继续使用</p>
          </header>

          <div class="logout-card">
            <div class="logout-card__main">
              <div class="logout-card__avatar">
                <img
                  v-if="profileForm.avatar_url"
                  :src="profileForm.avatar_url"
                  class="logout-card__avatar-image"
                  :alt="avatarLetter"
                />
                <template v-else>{{ avatarLetter }}</template>
              </div>
              <div class="logout-card__info">
                <div class="logout-card__name">{{ profileForm.nickname || profileForm.username }}</div>
                <div class="logout-card__sub">{{ profileForm.username }} · {{ profileForm.email || '未填写邮箱' }}</div>
                <div class="logout-card__meta">
                  <span class="logout-tag">最近登录：{{ lastLoginAt }}</span>
                  <span class="logout-tag">设备：{{ currentDevice }}</span>
                </div>
              </div>
            </div>

            <div class="logout-card__tip">
              <el-icon><WarningFilled /></el-icon>
              <span>注销后将清除本地登录凭证，需要重新输入账号密码登录。</span>
            </div>

            <div class="logout-actions">
              <el-button class="ghost-btn" @click="visible = false">取消</el-button>
              <el-button type="danger" :loading="loggingOut" @click="logout">
                <el-icon><SwitchButton /></el-icon>
                确认注销登录
              </el-button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <el-dialog
      v-model="cropDialogVisible"
      title="裁剪头像"
      width="520px"
      append-to-body
      destroy-on-close
      class="settings-dark-dialog"
      @closed="onCropDialogClosed"
    >
      <div class="avatar-cropper">
        <div
          class="avatar-cropper__stage"
          :style="stageStyle"
        >
          <img
            v-if="cropSourceUrl"
            :src="cropSourceUrl"
            class="avatar-cropper__image"
            :style="imageStyle"
            draggable="false"
            alt="裁剪原图"
          />
          <div
            v-if="cropBox.size > 0"
            class="avatar-cropper__box"
            :style="boxStyle"
            @pointerdown.stop="onBoxPointerDown"
          >
            <span class="avatar-cropper__grid"></span>
            <span
              class="avatar-cropper__handle"
              @pointerdown.stop="onHandlePointerDown"
            ></span>
          </div>
        </div>
        <p class="avatar-cropper__hint">拖动选区移动位置；右下角可缩放。选区将作为 1:1 头像。</p>
      </div>

      <template #footer>
        <el-button class="ghost-btn" @click="cropDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="avatarUploading" @click="confirmCrop">确认裁剪并上传</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="providerDialogVisible"
      :title="providerDialogTitle"
      width="780px"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
      class="settings-dark-dialog provider-dialog"
    >
      <el-form
        ref="providerFormRef"
        :key="providerDialogMode === 'edit' ? `edit-${providerEditingKey}` : 'create'"
        :model="providerForm"
        :rules="providerRules"
        label-position="top"
        class="provider-form"
      >
        <section class="provider-form__section">
          <header class="provider-form__head">
            <div class="provider-form__head-text">
              <h4 class="provider-form__title">基础信息</h4>
              <span class="provider-form__hint">供应商身份与对外展示信息</span>
            </div>
          </header>
          <div class="provider-form__grid">
            <el-form-item v-if="providerDialogMode === 'create'" label="供应商标识 key" prop="key">
              <el-input v-model="providerForm.key" placeholder="如 openai、deepseek" />
            </el-form-item>
            <el-form-item label="协议标识" prop="protocol">
              <el-input v-model="providerForm.protocol" placeholder="如 openai、volcengine" />
            </el-form-item>
            <el-form-item label="名称" prop="name">
              <el-input v-model="providerForm.name" placeholder="对外显示名称" />
            </el-form-item>
            <el-form-item label="版本">
              <el-input v-model="providerForm.version" placeholder="1.0" />
            </el-form-item>
            <el-form-item label="排序">
              <el-input-number v-model="providerForm.sort_order" :min="0" :step="1" controls-position="right" class="provider-form__number" />
            </el-form-item>
            <el-form-item label="图标" class="provider-form__icon-item">
              <div class="provider-form__icon">
                <div class="provider-form__icon-preview">
                  <img v-if="providerForm.icon" :src="providerForm.icon" alt="icon preview" />
                  <span v-else>无</span>
                </div>
                <div class="provider-form__icon-controls">
                  <el-input
                    v-model="providerForm.icon"
                    type="textarea"
                    :rows="2"
                    placeholder="支持 https://... 或 data:image/png;base64,..."
                    resize="none"
                  />
                  <div class="provider-form__icon-actions">
                    <el-button class="ghost-btn" size="small" :loading="iconUploading" @click="pickIconFile">上传图片转 Base64</el-button>
                    <el-button v-if="providerForm.icon" size="small" type="danger" @click="providerForm.icon = ''">清除</el-button>
                    <input
                      ref="iconInputRef"
                      type="file"
                      accept="image/png,image/jpeg,image/jpg,image/webp,image/gif,image/svg+xml"
                      hidden
                      @change="onIconFileSelected"
                    />
                  </div>
                </div>
              </div>
            </el-form-item>
          </div>
          <el-form-item label="描述">
            <el-input v-model="providerForm.description" type="textarea" :rows="2" placeholder="供应商或服务说明" />
          </el-form-item>
          <el-form-item label="官方网址">
            <el-input v-model="providerForm.url" placeholder="https://example.com" />
          </el-form-item>
          <el-form-item label="接口文档">
            <el-input v-model="providerForm.decs_url" placeholder="https://example.com/docs" />
          </el-form-item>
        </section>

        <section class="provider-form__section provider-form__section--key">
          <header class="provider-form__head">
            <div class="provider-form__head-text">
              <h4 class="provider-form__title">默认请求地址</h4>
              <span class="provider-form__hint">供应商默认 Base URL；具体凭据在下方 input_values 中维护</span>
            </div>
          </header>
          <div class="provider-form__grid">
            <el-form-item label="Base URL">
              <el-input v-model="providerForm.base_url" placeholder="https://api.example.com/v1" />
            </el-form-item>
          </div>
        </section>

        <section class="provider-form__section">
          <header class="provider-form__head">
            <div class="provider-form__head-text">
              <h4 class="provider-form__title">额外配置项</h4>
              <span class="provider-form__hint">声明额外字段（如 region、project_id）并填写对应值</span>
            </div>
            <el-button class="ghost-btn" size="small" @click="addProviderInput">+ 新增配置项</el-button>
          </header>
          <p v-if="providerForm.inputs.length === 0" class="provider-form__empty">
            尚未定义额外配置项；如供应商需要更多字段，可在此添加。
          </p>
          <article
            v-for="(item, idx) in providerForm.inputs"
            :key="`input-${idx}`"
            class="provider-form__row"
          >
            <div class="provider-form__row-head">
              <span class="provider-form__row-title">
                <em class="provider-form__row-index">#{{ idx + 1 }}</em>
                <strong>{{ item.label || item.key || '未命名配置' }}</strong>
              </span>
              <el-button size="small" type="danger" @click="removeProviderInput(idx)">移除</el-button>
            </div>
            <div class="provider-form__grid provider-form__grid--input">
              <el-form-item label="key">
                <el-input v-model="item.key" placeholder="如 region" />
              </el-form-item>
              <el-form-item label="label">
                <el-input v-model="item.label" placeholder="显示名称" />
              </el-form-item>
              <el-form-item label="类型">
                <el-select v-model="item.type" popper-class="settings-dark-select">
                  <el-option v-for="opt in INPUT_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="必填">
                <el-switch v-model="item.required" />
              </el-form-item>
            </div>
            <el-form-item :label="`填写值（${item.key || 'value'}）`">
              <el-input
                v-model="providerForm.input_values[item.key]"
                :type="item.type === 'password' ? 'password' : 'text'"
                :show-password="item.type === 'password'"
                :placeholder="
                  item.type === 'password' && hasSavedSecretValue(item.key)
                    ? '已保存，留空保持不变'
                    : `请输入${item.label || item.key || '配置值'}`
                "
                :disabled="!item.key"
              />
            </el-form-item>
          </article>
        </section>

        <section class="provider-form__section">
          <header class="provider-form__head">
            <div class="provider-form__head-text">
              <h4 class="provider-form__title">模型列表</h4>
              <span class="provider-form__hint">{{ providerForm.models.length }} 个模型 · 配置 model_id 与模型能力类型</span>
            </div>
            <div class="provider-form__head-actions">
              <el-button
                class="provider-form__inline-btn"
                size="small"
                text
                :loading="providerModelsFetching"
                @click="fetchProviderModels"
              >
                <el-icon><Refresh /></el-icon>
                <span>自动获取</span>
              </el-button>
              <el-button class="ghost-btn" size="small" @click="addProviderModel">+ 添加模型</el-button>
            </div>
          </header>
          <p v-if="providerForm.models.length === 0" class="provider-form__empty">
            尚未添加模型，点击「添加模型」配置 model_id、类型等信息。
          </p>

          <div v-if="providerForm.models.length" class="provider-form__filterbar">
            <el-icon class="provider-form__filterbar-icon"><Filter /></el-icon>
            <button
              v-for="opt in MODEL_FILTER_OPTIONS"
              :key="opt.value"
              type="button"
              class="provider-form__filter-chip"
              :class="[
                opt.value !== 'all' ? MODEL_TYPE_COLOR_CLASS[opt.value] : '',
                { 'is-active': modelTypeFilter === opt.value },
              ]"
              @click="modelTypeFilter = opt.value"
            >
              <span>{{ opt.label }}</span>
              <em>{{ modelTypeCounts[opt.value] }}</em>
            </button>
          </div>

          <article
            v-for="(model, idx) in providerForm.models"
            v-show="modelTypeFilter === 'all' || model.model_type === modelTypeFilter"
            :key="`model-${idx}`"
            class="provider-form__row"
            :class="{ 'is-collapsed': !isModelExpanded(idx) }"
          >
            <div class="provider-form__row-head">
              <button
                type="button"
                class="provider-form__row-toggle"
                :aria-expanded="isModelExpanded(idx)"
                @click="toggleModelExpand(idx)"
              >
                <span class="provider-form__row-caret" aria-hidden="true">▶</span>
                <em class="provider-form__row-index">#{{ idx + 1 }}</em>
                <strong>{{ model.name || model.model_id || '未命名模型' }}</strong>
                <span
                  v-if="model.model_type"
                  class="provider-form__row-tag provider-form__row-tag--type"
                  :class="MODEL_TYPE_COLOR_CLASS[model.model_type]"
                >{{ MODEL_TYPE_LABELS[model.model_type] }}</span>
                <span v-if="model.think" class="provider-form__row-tag provider-form__row-tag--think">深度思考</span>
                <span v-if="audioBadgeLabel(model)" class="provider-form__row-tag provider-form__row-tag--audio">{{ audioBadgeLabel(model) }}</span>
                <span v-if="durationCountLabel(model)" class="provider-form__row-tag">{{ durationCountLabel(model) }}</span>
                <span v-if="model.aspect_ratios?.length" class="provider-form__row-tag">{{ model.aspect_ratios.length }} 个比例</span>
                <span v-if="model.model_type === 'image' && model.sizes?.length" class="provider-form__row-tag">{{ model.sizes.length }} 档尺寸</span>
                <span v-if="model.model_type === 'video' && model.fps?.length" class="provider-form__row-tag">{{ model.fps.length }} 档帧率</span>
                <span v-if="model.model_type === 'tts' && (model.voices ?? []).length" class="provider-form__row-tag">{{ (model.voices ?? []).length }} 个音色</span>
              </button>
              <div class="provider-form__row-actions">
                <el-button size="small" type="danger" @click="removeProviderModel(idx)">删除</el-button>
              </div>
            </div>
            <div v-show="isModelExpanded(idx)" class="provider-form__row-body">
            <div class="provider-form__grid provider-form__grid--model">
              <el-form-item label="显示名">
                <el-input v-model="model.name" placeholder="如 Doubao-Seedream" />
              </el-form-item>
              <el-form-item label="model_id">
                <el-input v-model="model.model_id" placeholder="后端模型标识" />
              </el-form-item>
              <el-form-item label="类型">
                <el-select v-model="model.model_type" popper-class="settings-dark-select">
                  <el-option v-for="opt in MODEL_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="深度思考">
                <el-switch v-model="model.think" />
              </el-form-item>
              <el-form-item label="描述" class="provider-form__model-desc">
                <el-input v-model="model.description" placeholder="可选说明" />
              </el-form-item>
            </div>

            <!-- 图像 / 视频 / 语音 模型的高级配置 -->
            <div
              v-if="['image', 'video', 'tts'].includes(model.model_type)"
              class="provider-form__model-advanced"
            >
              <header class="provider-form__model-advanced-head">
                <span>高级配置</span>
                <em>按模型类型展示对应字段</em>
              </header>

              <!-- 图像 / 视频：输入模式 -->
              <el-form-item
                v-if="model.model_type === 'image' || model.model_type === 'video'"
                label="支持的输入模式"
              >
                <el-select
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  :model-value="modesAsStrings(model)"
                  popper-class="settings-dark-select"
                  placeholder="选择 1 个或多个模式"
                  @update:model-value="onModesSelectChange(model, $event)"
                >
                  <el-option
                    v-for="opt in (model.model_type === 'image' ? IMAGE_MODE_OPTIONS : VIDEO_MODE_OPTIONS)"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </el-form-item>

              <!-- 视频：音频策略 -->
              <el-form-item v-if="model.model_type === 'video'" label="音频">
                <el-radio-group v-model="model.audio">
                  <el-radio-button
                    v-for="opt in AUDIO_OPTIONS"
                    :key="String(opt.value)"
                    :value="opt.value"
                  >
                    {{ opt.label }}
                  </el-radio-button>
                </el-radio-group>
              </el-form-item>

              <!-- 视频：时长 / 分辨率组合 -->
              <el-form-item v-if="model.model_type === 'video'" label="时长 / 分辨率方案">
                <div class="provider-form__matrix">
                  <p v-if="!(model.duration_resolution_map ?? []).length" class="provider-form__matrix-empty">
                    尚未添加方案。每个方案约定一组「时长（秒）」对应可用的「分辨率」。
                  </p>
                  <div
                    v-for="(row, rowIdx) in (model.duration_resolution_map ?? [])"
                    :key="`dr-${rowIdx}`"
                    class="provider-form__matrix-row"
                  >
                    <div class="provider-form__matrix-cell">
                      <span class="provider-form__matrix-label">时长（秒）</span>
                      <el-select
                        v-model="row.duration"
                        multiple
                        filterable
                        allow-create
                        default-first-option
                        popper-class="settings-dark-select"
                        placeholder="例如 5, 8, 10"
                      >
                        <el-option v-for="n in [3, 4, 5, 6, 7, 8, 9, 10, 12, 15]" :key="n" :label="String(n)" :value="n" />
                      </el-select>
                    </div>
                    <div class="provider-form__matrix-cell">
                      <span class="provider-form__matrix-label">分辨率</span>
                      <el-select
                        v-model="row.resolution"
                        multiple
                        filterable
                        allow-create
                        default-first-option
                        popper-class="settings-dark-select"
                        placeholder="例如 480p, 720p"
                      >
                        <el-option v-for="r in ['480p', '720p', '1080p', '2K', '4K']" :key="r" :label="r" :value="r" />
                      </el-select>
                    </div>
                    <el-button
                      class="provider-form__matrix-remove"
                      size="small"
                      type="danger"
                      plain
                      @click="removeDurationResolutionRow(model, rowIdx)"
                    >
                      移除
                    </el-button>
                  </div>
                  <el-button class="ghost-btn" size="small" @click="addDurationResolutionRow(model)">
                    + 添加方案
                  </el-button>
                </div>
              </el-form-item>

              <!-- 图像 / 视频：画面比例 -->
              <el-form-item
                v-if="model.model_type === 'image' || model.model_type === 'video'"
                label="画面比例"
              >
                <el-select
                  v-model="model.aspect_ratios"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  collapse-tags
                  collapse-tags-tooltip
                  popper-class="settings-dark-select"
                  placeholder="例如 16:9、1:1"
                >
                  <el-option v-for="r in ASPECT_RATIO_PRESETS" :key="r" :label="r" :value="r" />
                </el-select>
              </el-form-item>

              <!-- 图像：输出尺寸 -->
              <el-form-item v-if="model.model_type === 'image'" label="输出尺寸">
                <el-select
                  v-model="model.sizes"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  collapse-tags
                  collapse-tags-tooltip
                  popper-class="settings-dark-select"
                  placeholder="例如 1K、2K、4K"
                >
                  <el-option v-for="s in SIZE_PRESETS" :key="s" :label="s" :value="s" />
                </el-select>
              </el-form-item>

              <!-- 视频：帧率 -->
              <el-form-item v-if="model.model_type === 'video'" label="帧率（fps）">
                <el-select
                  v-model="model.fps"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  collapse-tags
                  collapse-tags-tooltip
                  popper-class="settings-dark-select"
                  placeholder="例如 24、30、60"
                >
                  <el-option v-for="f in FPS_PRESETS" :key="f" :label="String(f)" :value="f" />
                </el-select>
              </el-form-item>

              <!-- 语音：音色列表 -->
              <el-form-item v-if="model.model_type === 'tts'" label="可选音色">
                <div class="provider-form__matrix">
                  <p v-if="!(model.voices ?? []).length" class="provider-form__matrix-empty">
                    尚未配置音色。点击下方按钮添加显示名与音色 ID。
                  </p>
                  <div
                    v-for="(voice, vIdx) in (model.voices ?? [])"
                    :key="`voice-${vIdx}`"
                    class="provider-form__matrix-row provider-form__matrix-row--voice"
                  >
                    <div class="provider-form__matrix-cell">
                      <span class="provider-form__matrix-label">显示名</span>
                      <el-input v-model="voice.title" placeholder="如 温柔女声" />
                    </div>
                    <div class="provider-form__matrix-cell">
                      <span class="provider-form__matrix-label">音色 ID</span>
                      <el-input v-model="voice.voice" placeholder="后端 voice 标识" />
                    </div>
                    <el-button
                      class="provider-form__matrix-remove"
                      size="small"
                      type="danger"
                      plain
                      @click="removeVoiceRow(model, vIdx)"
                    >
                      移除
                    </el-button>
                  </div>
                  <el-button class="ghost-btn" size="small" @click="addVoiceRow(model)">
                    + 添加音色
                  </el-button>
                </div>
              </el-form-item>
            </div>
            </div>
          </article>
        </section>

        <section class="provider-form__section provider-form__section--code">
          <header class="provider-form__head">
            <div class="provider-form__head-text">
              <h4 class="provider-form__title">服务文件源码</h4>
              <span class="provider-form__hint">创建时可基于模板生成；编辑时可单独保存源码并由服务端校验</span>
            </div>
            <div class="provider-form__head-actions">
              <el-button
                class="ghost-btn"
                size="small"
                :disabled="providerTemplateLoading || providerCodeLoading"
                @click="openProviderCodeEditor"
              >
                Web编辑器
              </el-button>
              <el-button
                v-if="providerDialogMode === 'create'"
                class="ghost-btn"
                size="small"
                :loading="providerTemplateLoading"
                @click="generateProviderTemplateCode"
              >
                生成模板
              </el-button>
              <el-button
                v-else
                class="ghost-btn"
                size="small"
                :loading="providerCodeLoading"
                @click="reloadProviderCode"
              >
                刷新源码
              </el-button>
              <el-button
                v-if="providerDialogMode === 'edit'"
                type="primary"
                size="small"
                :loading="providerCodeSaving"
                @click="saveProviderCode"
              >
                保存源码
              </el-button>
            </div>
          </header>
          <el-input
            v-model="providerForm.code"
            type="textarea"
            :rows="14"
            resize="vertical"
            spellcheck="false"
            class="provider-code-editor"
            placeholder="服务文件源码。源码中必须包含 PROVIDER_CONFIG，并至少声明一个继承 BaseProvider 的工具类。"
          />
        </section>
      </el-form>

      <template #footer>
        <el-button class="ghost-btn" @click="providerDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="providerSaving" @click="saveProvider">
          {{ providerDialogMode === 'create' ? '创建服务' : '保存配置' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="providerCodeEditorVisible"
      title="服务文件源码 Web编辑器"
      width="min(1180px, 96vw)"
      top="4vh"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
      class="settings-dark-dialog provider-code-web-dialog"
    >
      <ProviderCodeWebEditor v-model="providerCodeEditorDraft" />

      <template #footer>
        <el-button class="ghost-btn" @click="providerCodeEditorVisible = false">取消</el-button>
        <el-button class="ghost-btn" @click="syncProviderCodeEditorDraft">同步到源码框</el-button>
        <el-button type="primary" :loading="providerCodeSaving" @click="saveProviderCodeEditor">
          {{ providerCodeEditorSaveLabel }}
        </el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { AxiosError } from 'axios'
import type { FormInstance, FormRules, FormItemRule } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Cpu, Filter, Link, Lock, Refresh, SwitchButton, User, WarningFilled } from '@element-plus/icons-vue'
import {
  getCurrentUserApi,
  updateCurrentUserPasswordApi,
  updateCurrentUserProfileApi,
  uploadCurrentUserAvatarApi,
  type UserRecord,
} from '../api/user'
import {
  createProviderApi,
  deleteProviderApi,
  fetchProviderModelsApi,
  generateProviderTemplateApi,
  getProviderApi,
  getProviderTemplateApi,
  listProvidersApi,
  updateProviderCodeApi,
  updateProviderConfigApi,
  type ProviderConfig,
  type ProviderInput,
  type ProviderInputType,
  type ProviderModel,
  type ProviderModelType,
} from '../api/modelProvider'
import ProviderCodeWebEditor from './ProviderCodeWebEditor.vue'

const visible = defineModel<boolean>({ default: false })
const router = useRouter()

type CategoryKey = 'profile' | 'password' | 'providers' | 'logout'

const categories: { key: CategoryKey; label: string; icon: any }[] = [
  { key: 'profile', label: '个人资料', icon: User },
  { key: 'password', label: '修改密码', icon: Lock },
  { key: 'providers', label: '模型服务', icon: Cpu },
  { key: 'logout', label: '注销登录', icon: SwitchButton },
]

const activeKey = ref<CategoryKey>('profile')

interface ProfileFormState {
  username: string
  nickname: string
  email: string
  avatar_url: string
  last_login_at: string | null
}

const emptyProfile = (): ProfileFormState => ({
  username: '',
  nickname: '',
  email: '',
  avatar_url: '',
  last_login_at: null,
})

const currentUserSnapshot = ref<ProfileFormState>(emptyProfile())

// ---------- 个人资料 ----------
const profileFormRef = ref<FormInstance>()
const profileLoading = ref(false)
const profileSaving = ref(false)
const profileForm = reactive<ProfileFormState>(emptyProfile())

const profileRules: FormRules<ProfileFormState> = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { min: 3, max: 32, message: '账号长度需在 3-32 之间', trigger: 'blur' },
  ],
  nickname: [{ max: 32, message: '昵称不能超过 32 字', trigger: 'blur' }],
  email: [
    {
      pattern: /^[\w.+-]+@[\w-]+\.[\w.-]+$/,
      message: '请输入有效的邮箱地址',
      trigger: 'blur',
    },
  ],
}

const avatarLetter = computed(() => (profileForm.nickname || profileForm.username || 'A').slice(0, 1).toUpperCase())

const getErrorMessage = (error: unknown) => {
  const axiosError = error as AxiosError<{ detail?: string }>
  return axiosError.response?.data?.detail || axiosError.message || '请求失败'
}

const applyUser = (user: UserRecord) => {
  const next: ProfileFormState = {
    username: user.username ?? '',
    nickname: user.nickname ?? '',
    email: user.email ?? '',
    avatar_url: user.avatar_url ?? '',
    last_login_at: user.last_login_at,
  }
  Object.assign(profileForm, next)
  currentUserSnapshot.value = { ...next }
}

const loadCurrentUser = async () => {
  profileLoading.value = true
  try {
    const { data } = await getCurrentUserApi()
    applyUser(data)
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    profileLoading.value = false
  }
}

const resetProfile = () => {
  Object.assign(profileForm, currentUserSnapshot.value)
  profileFormRef.value?.clearValidate()
  ElMessage.info('已恢复修改前的资料')
}

const saveProfile = async () => {
  if (!profileFormRef.value) return
  const valid = await profileFormRef.value.validate().catch(() => false)
  if (!valid) return

  profileSaving.value = true
  try {
    const { data } = await updateCurrentUserProfileApi({
      username: profileForm.username,
      nickname: profileForm.nickname || null,
      email: profileForm.email || null,
    })
    applyUser(data)
    ElMessage.success('个人资料已保存')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    profileSaving.value = false
  }
}

const avatarInputRef = ref<HTMLInputElement | null>(null)
const avatarUploading = ref(false)
const ALLOWED_AVATAR_TYPES = ['image/png', 'image/jpeg', 'image/jpg']
const MAX_AVATAR_BYTES = 5 * 1024 * 1024

const pickAvatarFile = () => {
  if (avatarUploading.value) return
  avatarInputRef.value?.click()
}

const onAvatarFileSelected = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file) return

  if (!ALLOWED_AVATAR_TYPES.includes(file.type)) {
    ElMessage.error('仅支持 PNG/JPEG/JPG 格式的图片')
    return
  }
  if (file.size > MAX_AVATAR_BYTES) {
    ElMessage.error('图片过大，最多支持 5MB')
    return
  }
  openCropper(file)
}

// ---------- 头像裁剪 ----------
const CROP_STAGE_MAX = 420
const CROP_MIN_SIZE = 48

const cropDialogVisible = ref(false)
const cropSourceFile = ref<File | null>(null)
const cropSourceUrl = ref('')
const cropImageNatural = reactive({ width: 0, height: 0 })
const cropImageDisplay = reactive({ width: 0, height: 0 })
const cropBox = reactive({ x: 0, y: 0, size: 0 })

let cropDragMode: 'move' | 'resize' | null = null
let cropDragStart = { pointerX: 0, pointerY: 0, boxX: 0, boxY: 0, boxSize: 0 }

const stageStyle = computed(() => ({
  width: cropImageDisplay.width ? `${cropImageDisplay.width}px` : '320px',
  height: cropImageDisplay.height ? `${cropImageDisplay.height}px` : '320px',
}))

const imageStyle = computed(() => ({
  width: `${cropImageDisplay.width}px`,
  height: `${cropImageDisplay.height}px`,
}))

const boxStyle = computed(() => ({
  left: `${cropBox.x}px`,
  top: `${cropBox.y}px`,
  width: `${cropBox.size}px`,
  height: `${cropBox.size}px`,
}))

const openCropper = (file: File) => {
  cropSourceFile.value = file
  if (cropSourceUrl.value) URL.revokeObjectURL(cropSourceUrl.value)
  cropSourceUrl.value = URL.createObjectURL(file)
  cropBox.size = 0
  cropDialogVisible.value = true

  const img = new Image()
  img.onload = () => {
    cropImageNatural.width = img.naturalWidth
    cropImageNatural.height = img.naturalHeight
    const fit = Math.min(
      CROP_STAGE_MAX / img.naturalWidth,
      CROP_STAGE_MAX / img.naturalHeight,
      1,
    )
    cropImageDisplay.width = Math.max(1, Math.round(img.naturalWidth * fit))
    cropImageDisplay.height = Math.max(1, Math.round(img.naturalHeight * fit))
    const side = Math.min(cropImageDisplay.width, cropImageDisplay.height)
    cropBox.size = side
    cropBox.x = Math.round((cropImageDisplay.width - side) / 2)
    cropBox.y = Math.round((cropImageDisplay.height - side) / 2)
  }
  img.onerror = () => {
    ElMessage.error('图片加载失败')
    cropDialogVisible.value = false
  }
  img.src = cropSourceUrl.value
}

const onCropDialogClosed = () => {
  if (cropSourceUrl.value) URL.revokeObjectURL(cropSourceUrl.value)
  cropSourceUrl.value = ''
  cropSourceFile.value = null
  cropImageNatural.width = 0
  cropImageNatural.height = 0
  cropImageDisplay.width = 0
  cropImageDisplay.height = 0
  cropBox.size = 0
  detachCropPointerListeners()
}

const onBoxPointerDown = (event: PointerEvent) => {
  cropDragMode = 'move'
  cropDragStart = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    boxX: cropBox.x,
    boxY: cropBox.y,
    boxSize: cropBox.size,
  }
  attachCropPointerListeners()
}

const onHandlePointerDown = (event: PointerEvent) => {
  cropDragMode = 'resize'
  cropDragStart = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    boxX: cropBox.x,
    boxY: cropBox.y,
    boxSize: cropBox.size,
  }
  attachCropPointerListeners()
}

const onCropPointerMove = (event: PointerEvent) => {
  if (!cropDragMode) return
  const dx = event.clientX - cropDragStart.pointerX
  const dy = event.clientY - cropDragStart.pointerY

  if (cropDragMode === 'move') {
    const maxX = cropImageDisplay.width - cropBox.size
    const maxY = cropImageDisplay.height - cropBox.size
    cropBox.x = Math.max(0, Math.min(cropDragStart.boxX + dx, maxX))
    cropBox.y = Math.max(0, Math.min(cropDragStart.boxY + dy, maxY))
    return
  }

  const delta = Math.max(dx, dy)
  const maxBySpace = Math.min(
    cropImageDisplay.width - cropDragStart.boxX,
    cropImageDisplay.height - cropDragStart.boxY,
  )
  cropBox.size = Math.max(
    CROP_MIN_SIZE,
    Math.min(cropDragStart.boxSize + delta, maxBySpace),
  )
}

const onCropPointerUp = () => {
  cropDragMode = null
  detachCropPointerListeners()
}

const attachCropPointerListeners = () => {
  document.addEventListener('pointermove', onCropPointerMove)
  document.addEventListener('pointerup', onCropPointerUp)
  document.addEventListener('pointercancel', onCropPointerUp)
}

const detachCropPointerListeners = () => {
  document.removeEventListener('pointermove', onCropPointerMove)
  document.removeEventListener('pointerup', onCropPointerUp)
  document.removeEventListener('pointercancel', onCropPointerUp)
}

const renderCropBlob = (sx: number, sy: number, ss: number): Promise<Blob | null> => {
  return new Promise((resolve) => {
    if (!cropSourceUrl.value) return resolve(null)
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = ss
      canvas.height = ss
      const ctx = canvas.getContext('2d')
      if (!ctx) return resolve(null)
      ctx.drawImage(img, sx, sy, ss, ss, 0, 0, ss, ss)
      canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.92)
    }
    img.onerror = () => resolve(null)
    img.src = cropSourceUrl.value
  })
}

const confirmCrop = async () => {
  if (!cropSourceFile.value || cropBox.size === 0 || !cropImageDisplay.width) return
  const ratio = cropImageNatural.width / cropImageDisplay.width
  const sx = Math.round(cropBox.x * ratio)
  const sy = Math.round(cropBox.y * ratio)
  const ss = Math.max(1, Math.round(cropBox.size * ratio))

  avatarUploading.value = true
  try {
    const blob = await renderCropBlob(sx, sy, ss)
    if (!blob) {
      ElMessage.error('裁剪失败，请重试')
      return
    }
    const file = new File([blob], 'avatar.jpg', { type: 'image/jpeg' })
    const { data } = await uploadCurrentUserAvatarApi(file)
    applyUser(data)
    ElMessage.success('头像已更新')
    cropDialogVisible.value = false
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    avatarUploading.value = false
  }
}

// ---------- 修改密码 ----------
const passwordFormRef = ref<FormInstance>()
const passwordSaving = ref(false)
const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const validateNewPassword: FormItemRule['validator'] = (_rule, value, cb) => {
  if (!value) return cb(new Error('请输入新密码'))
  if (value.length < 8) return cb(new Error('新密码长度不少于 8 位'))
  if (value === passwordForm.oldPassword) return cb(new Error('新密码不能与当前密码相同'))
  cb()
}

const validateConfirmPassword: FormItemRule['validator'] = (_rule, value, cb) => {
  if (!value) return cb(new Error('请再次输入新密码'))
  if (value !== passwordForm.newPassword) return cb(new Error('两次输入的密码不一致'))
  cb()
}

const passwordRules: FormRules<typeof passwordForm> = {
  oldPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [{ required: true, validator: validateNewPassword, trigger: 'blur' }],
  confirmPassword: [{ required: true, validator: validateConfirmPassword, trigger: 'blur' }],
}

const passwordStrength = computed(() => {
  const value = passwordForm.newPassword
  if (!value) return 0
  let score = 0
  if (value.length >= 8) score += 1
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1
  if (/\d/.test(value)) score += 1
  if (/[^A-Za-z0-9]/.test(value)) score += 1
  return score
})

const passwordStrengthLabel = computed(() => {
  if (!passwordForm.newPassword) return '请输入密码'
  return ['极弱', '较弱', '一般', '强', '极强'][passwordStrength.value] || '极弱'
})

watch(
  () => passwordForm.newPassword,
  () => {
    if (passwordForm.confirmPassword) {
      passwordFormRef.value?.validateField('confirmPassword').catch(() => {})
    }
  },
)

const resetPassword = () => {
  passwordForm.oldPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
  passwordFormRef.value?.clearValidate()
}

const savePassword = async () => {
  if (!passwordFormRef.value) return
  const valid = await passwordFormRef.value.validate().catch(() => false)
  if (!valid) return

  passwordSaving.value = true
  try {
    await updateCurrentUserPasswordApi({
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword,
      confirm_password: passwordForm.confirmPassword,
    })
    resetPassword()
    ElMessage.success('密码修改成功，下次登录请使用新密码')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    passwordSaving.value = false
  }
}

// ---------- 模型服务供应商 ----------
const providers = ref<ProviderConfig[]>([])
const providersLoading = ref(false)
const providerSaving = ref(false)
const providerCodeLoading = ref(false)
const providerCodeSaving = ref(false)
const providerTemplateLoading = ref(false)
const providerModelsFetching = ref(false)
const providerDialogVisible = ref(false)
const providerDialogMode = ref<'create' | 'edit'>('create')
const providerEditingKey = ref('')
const providerFormRef = ref<FormInstance>()
const providerCodeEditorVisible = ref(false)
const providerCodeEditorDraft = ref('')
const providerCodeEditorSaveLabel = computed(() =>
  providerDialogMode.value === 'edit' ? '保存源码' : '保存并同步',
)

const MODEL_TYPE_OPTIONS: { label: string; value: ProviderModelType }[] = [
  { label: '文本', value: 'text' },
  { label: '图像', value: 'image' },
  { label: '视频', value: 'video' },
  { label: '语音', value: 'tts' },
]

const MODEL_TYPE_LABELS: Record<ProviderModelType, string> = {
  text: '文本',
  image: '图像',
  video: '视频',
  tts: '语音',
}

const INPUT_TYPE_OPTIONS: { label: string; value: ProviderInputType }[] = [
  { label: '文本', value: 'text' },
  { label: '密码', value: 'password' },
  { label: 'URL', value: 'url' },
]

const IMAGE_MODE_OPTIONS = [
  { label: '文生图', value: 'text' },
  { label: '单图参考', value: 'singleImage' },
  { label: '多图参考', value: 'multiReference' },
]

const VIDEO_MODE_OPTIONS = [
  { label: '文生视频', value: 'text' },
  { label: '单图首帧', value: 'singleImage' },
  { label: '首尾帧双图', value: 'startEndRequired' },
  { label: '可选首帧', value: 'startFrameOptional' },
  { label: '可选尾帧', value: 'endFrameOptional' },
]

const AUDIO_OPTIONS: { label: string; value: false | true | 'optional' }[] = [
  { label: '关闭', value: false },
  { label: '可选', value: 'optional' },
  { label: '开启', value: true },
]

const ASPECT_RATIO_PRESETS = ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9', '3:2', '2:3']
const SIZE_PRESETS = ['512', '1024', '1K', '2K', '4K']
const FPS_PRESETS = [24, 25, 30, 60]

const MODEL_TYPE_COLOR_CLASS: Record<ProviderModelType, string> = {
  text: 'is-text',
  image: 'is-image',
  video: 'is-video',
  tts: 'is-tts',
}

const MODEL_FILTER_OPTIONS: { value: 'all' | ProviderModelType; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'text', label: '文本' },
  { value: 'image', label: '图像' },
  { value: 'video', label: '视频' },
  { value: 'tts', label: '语音' },
]

const modelTypeFilter = ref<'all' | ProviderModelType>('all')
const expandedModelKeys = ref<Set<number>>(new Set())

const resetModelEditorState = () => {
  modelTypeFilter.value = 'all'
  expandedModelKeys.value = new Set()
}

const isModelExpanded = (idx: number) => expandedModelKeys.value.has(idx)
const toggleModelExpand = (idx: number) => {
  const next = new Set(expandedModelKeys.value)
  if (next.has(idx)) next.delete(idx)
  else next.add(idx)
  expandedModelKeys.value = next
}

const modelTypeCounts = computed<Record<'all' | ProviderModelType, number>>(() => {
  const counts = { all: 0, text: 0, image: 0, video: 0, tts: 0 }
  for (const m of providerForm.models) {
    counts.all += 1
    counts[m.model_type] += 1
  }
  return counts
})

const providerCapabilityCounts = (provider: ProviderConfig): { type: ProviderModelType; label: string; count: number }[] => {
  const counts: Record<ProviderModelType, number> = { text: 0, image: 0, video: 0, tts: 0 }
  for (const m of provider.models) counts[m.model_type] += 1
  return MODEL_TYPE_OPTIONS
    .map((opt) => ({ type: opt.value, label: opt.label, count: counts[opt.value] }))
    .filter((item) => item.count > 0)
}

const secretInputKeys = (inputs: ProviderInput[]) =>
  inputs.filter((item) => item.type === 'password').map((item) => item.key).filter(Boolean)

const providerHasSecret = (provider: ProviderConfig) =>
  secretInputKeys(provider.inputs).some((key) => Boolean(provider.input_values?.[key]))

const hasSavedSecretValue = (key: string) => Boolean(key && providerForm.saved_secret_values[key])

const modesAsStrings = (model: ProviderModel): string[] =>
  (model.modes ?? [])
    .filter((m): m is string => typeof m === 'string')

const setModesFromSelect = (model: ProviderModel, next: string[]) => {
  const preservedComplex = (model.modes ?? []).filter((m) => Array.isArray(m))
  model.modes = [...next, ...preservedComplex]
}

const onModesSelectChange = (model: ProviderModel, next: unknown) => {
  if (Array.isArray(next)) {
    setModesFromSelect(model, next.filter((v): v is string => typeof v === 'string'))
  }
}

const addDurationResolutionRow = (model: ProviderModel) => {
  model.duration_resolution_map = [
    ...(model.duration_resolution_map ?? []),
    { duration: [], resolution: [] },
  ]
}

const removeDurationResolutionRow = (model: ProviderModel, index: number) => {
  const list = [...(model.duration_resolution_map ?? [])]
  list.splice(index, 1)
  model.duration_resolution_map = list
}

const addVoiceRow = (model: ProviderModel) => {
  model.voices = [...(model.voices ?? []), { title: '', voice: '' }]
}

const removeVoiceRow = (model: ProviderModel, index: number) => {
  const list = [...(model.voices ?? [])]
  list.splice(index, 1)
  model.voices = list
}

const audioBadgeLabel = (model: ProviderModel): string | null => {
  if (model.audio === true) return '音频开启'
  if (model.audio === 'optional') return '音频可选'
  return null
}

const durationCountLabel = (model: ProviderModel): string | null => {
  const groups = model.duration_resolution_map ?? []
  if (!groups.length) return null
  return `${groups.length} 组时长方案`
}

interface ProviderFormState {
  key: string
  protocol: string
  version: string
  name: string
  description: string
  decs_url: string
  icon: string
  url: string
  base_url: string
  enabled: boolean
  sort_order: number
  inputs: ProviderInput[]
  input_values: Record<string, string>
  saved_secret_values: Record<string, string>
  models: ProviderModel[]
  code: string
}

const emptyProviderForm = (): ProviderFormState => ({
  key: '',
  protocol: '',
  version: '1.0',
  name: '',
  description: '',
  decs_url: '',
  icon: '',
  url: '',
  base_url: '',
  enabled: false,
  sort_order: 0,
  inputs: [],
  input_values: {},
  models: [],
  saved_secret_values: {},
  code: '',
})

const providerForm = reactive<ProviderFormState>(emptyProviderForm())

const providerRules: FormRules<ProviderFormState> = {
  key: [
    { required: true, message: '请输入供应商标识', trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9_]{1,63}$/, message: '仅支持小写字母、数字和下划线，并以字母开头', trigger: 'blur' },
  ],
  protocol: [{ required: true, message: '请输入协议标识', trigger: 'blur' }],
  name: [{ required: true, message: '请输入供应商名称', trigger: 'blur' }],
}

const providerDialogTitle = computed(() =>
  providerDialogMode.value === 'create' ? '新增模型服务供应商' : `编辑：${providerForm.name || providerForm.key}`,
)

const emptyProviderModel = (): ProviderModel => ({
  name: '',
  model_id: '',
  model_type: 'text',
  description: '',
  modes: [],
  think: false,
  audio: null,
  duration_resolution_map: [],
  aspect_ratios: [],
  sizes: [],
  fps: [],
  voices: [],
  raw_config: {},
})

const cloneProviderModel = (model: ProviderModel): ProviderModel => ({
  ...model,
  think: !!model.think,
  modes: [...(model.modes ?? [])],
  duration_resolution_map: (model.duration_resolution_map ?? []).map((row) => ({ ...row })),
  aspect_ratios: [...(model.aspect_ratios ?? [])],
  sizes: [...(model.sizes ?? [])],
  fps: [...(model.fps ?? [])],
  voices: (model.voices ?? []).map((v) => ({ ...v })),
  raw_config: { ...(model.raw_config ?? {}) },
})

const visibleInputValues = (record: ProviderConfig) => {
  const values = { ...record.input_values }
  for (const key of secretInputKeys(record.inputs)) {
    if (values[key]) values[key] = ''
  }
  return values
}

const savedSecretValues = (record: ProviderConfig) => {
  const values: Record<string, string> = {}
  for (const key of secretInputKeys(record.inputs)) {
    const value = record.input_values?.[key]
    if (value) values[key] = value
  }
  return values
}

const fillProviderFormFromRecord = (record: ProviderConfig | null, code = '') => {
  if (!record) {
    Object.assign(providerForm, emptyProviderForm())
    return
  }
  Object.assign(providerForm, {
    key: record.key,
    protocol: record.protocol,
    version: record.version,
    name: record.name,
    description: record.description,
    decs_url: record.decs_url,
    icon: record.icon,
    url: record.url,
    base_url: record.base_url,
    enabled: record.enabled,
    sort_order: record.sort_order,
    inputs: record.inputs.map((item) => ({ ...item })),
    input_values: visibleInputValues(record),
    saved_secret_values: savedSecretValues(record),
    models: record.models.map(cloneProviderModel),
    code,
  })
}

const loadProviders = async () => {
  providersLoading.value = true
  try {
    const { data } = await listProvidersApi()
    providers.value = data
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    providersLoading.value = false
  }
}

const onToggleProviderEnabled = async (provider: ProviderConfig, value: boolean | string | number) => {
  const next = Boolean(value)
  try {
    const { data } = await updateProviderConfigApi(provider.key, { ...provider, enabled: next })
    const index = providers.value.findIndex((item) => item.key === provider.key)
    if (index >= 0) providers.value[index] = data
    ElMessage.success(next ? '供应商已启用' : '供应商已禁用')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

const loadProviderTemplateCode = async () => {
  providerTemplateLoading.value = true
  try {
    const { data } = await getProviderTemplateApi()
    providerForm.code = data.code
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    providerTemplateLoading.value = false
  }
}

const generateProviderTemplateCode = async () => {
  if (!providerFormRef.value) return
  const valid = await providerFormRef.value.validate().catch(() => false)
  if (!valid || warnIncompleteProviderModels()) return

  providerTemplateLoading.value = true
  try {
    const { data } = await generateProviderTemplateApi({ config: buildProviderConfig() })
    providerForm.code = data.code
    ElMessage.success('模板已生成')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    providerTemplateLoading.value = false
  }
}

const openProviderCreate = async () => {
  providerDialogMode.value = 'create'
  providerEditingKey.value = ''
  fillProviderFormFromRecord(null)
  resetModelEditorState()
  providerDialogVisible.value = true
  await loadProviderTemplateCode()
}

const openProviderEdit = async (provider: ProviderConfig) => {
  providerDialogMode.value = 'edit'
  providerEditingKey.value = provider.key
  resetModelEditorState()
  providerCodeLoading.value = true
  try {
    const { data } = await getProviderApi(provider.key)
    fillProviderFormFromRecord(data.config, data.code)
    providerDialogVisible.value = true
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    providerCodeLoading.value = false
  }
}

const reloadProviderCode = async () => {
  if (!providerEditingKey.value) return
  providerCodeLoading.value = true
  try {
    const { data } = await getProviderApi(providerEditingKey.value)
    fillProviderFormFromRecord(data.config, data.code)
    ElMessage.success('源码已刷新')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    providerCodeLoading.value = false
  }
}

const openProviderCodeEditor = () => {
  providerCodeEditorDraft.value = providerForm.code
  providerCodeEditorVisible.value = true
}

const syncProviderCodeEditorDraft = () => {
  providerForm.code = providerCodeEditorDraft.value
  providerCodeEditorVisible.value = false
  ElMessage.success('源码已同步到源码框')
}

const ALLOWED_ICON_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif', 'image/svg+xml']
const MAX_ICON_BYTES = 1 * 1024 * 1024
const iconInputRef = ref<HTMLInputElement | null>(null)
const iconUploading = ref(false)

const pickIconFile = () => {
  if (iconUploading.value) return
  iconInputRef.value?.click()
}

const onIconFileSelected = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file) return
  if (!ALLOWED_ICON_TYPES.includes(file.type)) {
    ElMessage.error('仅支持 PNG/JPEG/WEBP/GIF/SVG 格式的图片')
    return
  }
  if (file.size > MAX_ICON_BYTES) {
    ElMessage.error('图标文件过大，最多支持 1MB')
    return
  }
  iconUploading.value = true
  const reader = new FileReader()
  reader.onload = () => {
    const result = typeof reader.result === 'string' ? reader.result : ''
    if (!result.startsWith('data:')) {
      ElMessage.error('图片转换失败，请重试')
    } else {
      providerForm.icon = result
      ElMessage.success('图标已转换为 Base64')
    }
    iconUploading.value = false
  }
  reader.onerror = () => {
    ElMessage.error('图片读取失败')
    iconUploading.value = false
  }
  reader.readAsDataURL(file)
}

const addProviderInput = () => {
  providerForm.inputs.push({ key: '', label: '', type: 'text', required: false })
}

const removeProviderInput = (index: number) => {
  const removed = providerForm.inputs.splice(index, 1)[0]
  if (removed && removed.key in providerForm.input_values) {
    delete providerForm.input_values[removed.key]
  }
}

const addProviderModel = () => {
  const newIndex = providerForm.models.length
  providerForm.models.push(emptyProviderModel())
  expandedModelKeys.value = new Set(expandedModelKeys.value).add(newIndex)
}

const fetchProviderModels = async () => {
  if (providerModelsFetching.value) return
  if (!providerForm.key.trim() || !providerForm.protocol.trim() || !providerForm.name.trim()) {
    ElMessage.warning('请先填写供应商 key、协议标识和名称')
    return
  }

  if (providerForm.models.length > 0) {
    try {
      await ElMessageBox.confirm('自动获取会覆盖当前弹窗中的模型列表，是否继续？', '自动获取模型', {
        confirmButtonText: '继续获取',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'settings-dark-messagebox',
      })
    } catch (error) {
      if (error === 'cancel' || error === 'close') return
      return
    }
  }

  providerModelsFetching.value = true
  try {
    const { data } = await fetchProviderModelsApi({ config: buildProviderConfig() })
    const nextModels = data.map(cloneProviderModel)
    providerForm.models.splice(0, providerForm.models.length, ...nextModels)
    expandedModelKeys.value = new Set(nextModels.map((_, idx) => idx))
    modelTypeFilter.value = 'all'
    if (nextModels.length) {
      ElMessage.success(`已获取 ${nextModels.length} 个模型`)
    } else {
      ElMessage.warning('远端未返回可用模型')
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    providerModelsFetching.value = false
  }
}

const removeProviderModel = (index: number) => {
  providerForm.models.splice(index, 1)
  const next = new Set<number>()
  expandedModelKeys.value.forEach((value) => {
    if (value === index) return
    next.add(value > index ? value - 1 : value)
  })
  expandedModelKeys.value = next
}

const warnIncompleteProviderModels = () => {
  const incompleteModelIndices: number[] = []
  providerForm.models.forEach((model, idx) => {
    if (!model.name.trim() || !model.model_id.trim()) incompleteModelIndices.push(idx)
  })
  if (!incompleteModelIndices.length) return false

  const next = new Set(expandedModelKeys.value)
  incompleteModelIndices.forEach((idx) => next.add(idx))
  expandedModelKeys.value = next
  ElMessage.error(`存在 ${incompleteModelIndices.length} 个模型未填写显示名或 model_id，请补全后再继续`)
  return true
}

const buildProviderInputValues = () => {
  const values: Record<string, string> = {}
  for (const input of providerForm.inputs) {
    const key = input.key.trim()
    if (!key) continue
    const value = providerForm.input_values[key] ?? ''
    values[key] = input.type === 'password' && !value && providerForm.saved_secret_values[key]
      ? providerForm.saved_secret_values[key]
      : String(value)
  }
  return values
}

const normalizeDurationValues = (values: unknown[] | undefined) =>
  (values ?? [])
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))

const buildProviderConfig = (): ProviderConfig => ({
  key: providerForm.key.trim(),
  protocol: providerForm.protocol.trim(),
  version: providerForm.version || '1.0',
  name: providerForm.name.trim(),
  description: providerForm.description.trim(),
  decs_url: providerForm.decs_url.trim(),
  icon: providerForm.icon.trim(),
  url: providerForm.url.trim(),
  base_url: providerForm.base_url.trim(),
  inputs: providerForm.inputs
    .filter((item) => item.key.trim() && item.label.trim())
    .map((item) => ({
      key: item.key.trim(),
      label: item.label.trim(),
      type: item.type,
      required: !!item.required,
    })),
  input_values: buildProviderInputValues(),
  enabled: providerForm.enabled,
  sort_order: providerForm.sort_order,
  models: providerForm.models.map((model) => ({
    ...model,
    name: model.name.trim(),
    model_id: model.model_id.trim(),
    description: model.description?.trim() ?? '',
    modes: [...(model.modes ?? [])],
    think: model.think ?? null,
    audio: model.audio ?? null,
    duration_resolution_map: (model.duration_resolution_map ?? [])
      .map((row) => ({
        duration: normalizeDurationValues(row.duration as unknown[]),
        resolution: (row.resolution ?? []).map(String).filter(Boolean),
      }))
      .filter((row) => row.duration.length || row.resolution.length),
    voices: (model.voices ?? [])
      .map((voice) => ({ title: voice.title.trim(), voice: voice.voice.trim() }))
      .filter((voice) => voice.title && voice.voice),
  })),
})

const buildProviderPayload = () => {
  const config = buildProviderConfig()
  return {
    config,
    code: providerForm.code.trim() || null,
  }
}

const saveProviderCode = async (): Promise<boolean> => {
  if (!providerEditingKey.value) return false
  const code = providerForm.code.trim()
  if (!code) {
    ElMessage.warning('源码不能为空')
    return false
  }
  providerCodeSaving.value = true
  try {
    const { data } = await updateProviderCodeApi(providerEditingKey.value, { code })
    fillProviderFormFromRecord(data.config, data.code)
    await loadProviders()
    ElMessage.success('源码已保存')
    return true
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
    return false
  } finally {
    providerCodeSaving.value = false
  }
}

const saveProviderCodeEditor = async () => {
  providerForm.code = providerCodeEditorDraft.value
  if (providerDialogMode.value === 'create') {
    syncProviderCodeEditorDraft()
    return
  }

  const saved = await saveProviderCode()
  if (saved) providerCodeEditorVisible.value = false
}

const saveProvider = async () => {
  if (!providerFormRef.value) return
  const valid = await providerFormRef.value.validate().catch(() => false)
  if (!valid) return

  const incompleteModelIndices: number[] = []
  providerForm.models.forEach((model, idx) => {
    if (!model.name.trim() || !model.model_id.trim()) incompleteModelIndices.push(idx)
  })
  if (incompleteModelIndices.length) {
    const next = new Set(expandedModelKeys.value)
    incompleteModelIndices.forEach((idx) => next.add(idx))
    expandedModelKeys.value = next
    ElMessage.error(`存在 ${incompleteModelIndices.length} 个模型未填写显示名或 model_id，请补全后再保存`)
    return
  }

  providerSaving.value = true
  try {
    if (providerDialogMode.value === 'create') {
      await createProviderApi(buildProviderPayload())
      ElMessage.success('供应商已创建')
    } else {
      await updateProviderConfigApi(providerEditingKey.value, buildProviderConfig())
      const { data } = await getProviderApi(providerEditingKey.value)
      fillProviderFormFromRecord(data.config, data.code)
      ElMessage.success('供应商已更新')
    }
    providerDialogVisible.value = false
    await loadProviders()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    providerSaving.value = false
  }
}

const onDeleteProvider = async (provider: ProviderConfig) => {
  try {
    await ElMessageBox.confirm(`确定删除「${provider.name}」吗？该操作不可恢复。`, '删除供应商', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'settings-dark-messagebox',
    })
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    return
  }
  try {
    await deleteProviderApi(provider.key)
    ElMessage.success('供应商已删除')
    await loadProviders()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}


const loggingOut = ref(false)

const formatDateTime = (value: string | null) => {
  if (!value) return '暂无记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const lastLoginAt = computed(() => formatDateTime(profileForm.last_login_at))

const currentDevice = computed(() => {
  if (typeof navigator === 'undefined') return '未知设备'
  return navigator.userAgent || '未知设备'
})

const logout = async () => {
  try {
    await ElMessageBox.confirm('确认要退出当前账号吗？', '注销登录', {
      confirmButtonText: '确认注销',
      cancelButtonText: '再想想',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'settings-dark-messagebox',
    })
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    return
  }

  loggingOut.value = true
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('token_type')
  localStorage.removeItem('expires_in')
  localStorage.removeItem('user')
  loggingOut.value = false
  visible.value = false
  ElMessage.success('已注销，正在返回登录页')
  router.push('/login')
}

// 弹窗每次打开复位到第一项 + 清空密码字段 + 加载当前用户
watch(visible, (val) => {
  if (val) {
    activeKey.value = 'profile'
    resetPassword()
    void loadCurrentUser()
  }
})

watch(activeKey, (val) => {
  if (val === 'providers' && providers.value.length === 0) {
    void loadProviders()
  }
})

watch(providerDialogVisible, (val) => {
  if (!val) providerCodeEditorVisible.value = false
})
</script>

<style scoped>
.settings-shell {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 18px;
  min-height: 460px;
}

.settings-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  align-self: flex-start;
}

.settings-nav__btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: #c5cdd6;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: background-color 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.settings-nav__btn:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #ffffff;
}

.settings-nav__btn.is-active {
  color: #dbeafe;
  border-color: rgba(37, 99, 235, 0.32);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.22), rgba(37, 99, 235, 0.1));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.settings-nav__icon {
  font-size: 18px;
}

.settings-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.section-head h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: #f2f4f8;
}

.section-head p {
  margin: 4px 0 0;
  color: #8b949e;
  font-size: 13px;
}

.settings-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.ghost-btn {
  background-color: rgba(255, 255, 255, 0.04) !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  color: #e6edf3 !important;
  border-radius: 10px !important;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.ghost-btn:hover {
  background-color: rgba(255, 255, 255, 0.08) !important;
  border-color: rgba(255, 255, 255, 0.22) !important;
  color: #ffffff !important;
}

/* 个人资料 */
.account-grid {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 24px;
  align-items: flex-start;
}

.account-avatar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.avatar-circle {
  width: 96px;
  height: 96px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 36px;
  font-weight: 800;
  color: #0a0a0a;
  background: linear-gradient(135deg, #f3d96b, #c4b5fd);
  box-shadow: 0 12px 24px rgba(243, 217, 107, 0.18);
  user-select: none;
  overflow: hidden;
}

.avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* 头像裁剪 */
.avatar-cropper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.avatar-cropper__stage {
  position: relative;
  display: inline-block;
  max-width: 100%;
  background: #0c1015;
  border-radius: 12px;
  overflow: hidden;
  touch-action: none;
  user-select: none;
}

.avatar-cropper__image {
  display: block;
  pointer-events: none;
  user-select: none;
  -webkit-user-drag: none;
}

.avatar-cropper__box {
  position: absolute;
  box-sizing: border-box;
  border: 2px solid #ffffff;
  border-radius: 4px;
  box-shadow: 0 0 0 9999px rgba(7, 10, 16, 0.55);
  cursor: move;
  touch-action: none;
}

.avatar-cropper__grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(to right, rgba(255, 255, 255, 0.35) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(255, 255, 255, 0.35) 1px, transparent 1px);
  background-size: 33.333% 33.333%;
  background-position: 0 0;
}

.avatar-cropper__handle {
  position: absolute;
  right: -7px;
  bottom: -7px;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  background: #ffffff;
  border: 1.5px solid rgba(37, 99, 235, 0.6);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
  cursor: nwse-resize;
  touch-action: none;
}

.avatar-cropper__hint {
  margin: 0;
  color: #8b949e;
  font-size: 12px;
}

.account-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}

/* 密码 */
.password-form {
  max-width: 480px;
}

.password-strength {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.password-strength__bar {
  width: 48px;
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  transition: background 0.2s ease;
}

.password-strength__bar.is-on[data-level='1'] {
  background: #f87171;
}

.password-strength__bar.is-on[data-level='2'] {
  background: #fb923c;
}

.password-strength__bar.is-on[data-level='3'] {
  background: #facc15;
}

.password-strength__bar.is-on[data-level='4'] {
  background: #22c55e;
}

.password-strength__label {
  margin-left: 8px;
  font-size: 12px;
  color: #8b949e;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

/* 注销 */
.logout-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 20px 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.022), rgba(255, 255, 255, 0.012));
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.logout-card__main {
  display: flex;
  align-items: center;
  gap: 18px;
}

.logout-card__avatar {
  width: 64px;
  height: 64px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 26px;
  font-weight: 800;
  color: #0a0a0a;
  background: linear-gradient(135deg, #f3d96b, #c4b5fd);
  box-shadow: 0 8px 18px rgba(243, 217, 107, 0.18);
  flex-shrink: 0;
  overflow: hidden;
}

.logout-card__avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.logout-card__info {
  min-width: 0;
}

.logout-card__name {
  font-size: 18px;
  font-weight: 700;
  color: #f2f4f8;
}

.logout-card__sub {
  margin-top: 4px;
  color: #8b949e;
  font-size: 13px;
}

.logout-card__meta {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.logout-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.logout-card__tip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(248, 113, 113, 0.06);
  border: 1px solid rgba(248, 113, 113, 0.22);
  color: #fca5a5;
  font-size: 13px;
}

.logout-card__tip .el-icon {
  font-size: 18px;
}

.logout-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.section-head__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.section-head__actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* ---------- 模型服务列表 ---------- */
.provider-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 540px;
  overflow-y: auto;
  padding: 4px 10px 4px 2px;
  margin-right: -6px;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.35) transparent;
}

.provider-list::-webkit-scrollbar {
  width: 8px;
}

.provider-list::-webkit-scrollbar-track {
  background: transparent;
  margin: 4px 0;
}

.provider-list::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.28);
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: padding-box;
  transition: background-color 0.18s ease;
}

.provider-list::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}

.provider-card {
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 16px 18px 16px 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.012)),
    radial-gradient(160% 100% at 0% 0%, rgba(96, 165, 250, 0.05) 0%, transparent 55%);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
  overflow: hidden;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.provider-card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, #4ade80, #16a34a);
  opacity: 0.85;
  pointer-events: none;
  transition: opacity 0.18s ease, background 0.18s ease;
}

.provider-card.is-disabled::before {
  background: linear-gradient(180deg, #475569, #1f2937);
  opacity: 0.55;
}

.provider-card.is-disabled {
  opacity: 0.82;
}

.provider-card:hover {
  transform: translateY(-1px);
  border-color: rgba(255, 255, 255, 0.18);
  box-shadow: 0 18px 36px rgba(0, 0, 0, 0.32);
}

.provider-card__head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.provider-card__avatar {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #1f2937, #0f172a);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: #d5dce4;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.5px;
  overflow: hidden;
  flex-shrink: 0;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 6px 14px rgba(0, 0, 0, 0.32);
}

.provider-card__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.provider-card__meta {
  flex: 1;
  min-width: 0;
}

.provider-card__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.provider-card__title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #f2f4f8;
  letter-spacing: -0.2px;
}

.provider-card__link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 500;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.14);
  border: 1px solid rgba(37, 99, 235, 0.32);
  text-decoration: none;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.provider-card__link:hover {
  color: #dbeafe;
  background: rgba(37, 99, 235, 0.24);
  border-color: rgba(96, 165, 250, 0.55);
}

.provider-card__link .el-icon {
  font-size: 12px;
}

.provider-card__chips {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.provider-chip {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  letter-spacing: 0.2px;
  transition: background-color 0.18s ease, border-color 0.18s ease;
}

.provider-card:hover .provider-chip {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.14);
}

.provider-chip--info {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.14);
  border-color: rgba(37, 99, 235, 0.32);
}

.provider-card__desc {
  margin: 10px 0 0;
  color: #8b949e;
  font-size: 12.5px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.provider-card__actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
}

.provider-card__actions :deep(.el-switch) {
  --el-switch-on-color: #16a34a;
  --el-switch-off-color: rgba(255, 255, 255, 0.12);
}

.provider-card__actions :deep(.el-button) {
  height: 30px;
  padding: 0 12px;
  font-size: 12px;
  border-radius: 9px;
}

/* ---------- 供应商编辑表单 ---------- */
.provider-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.provider-form__section {
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 14px;
  padding: 14px 18px 4px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.006));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.04),
    0 8px 22px rgba(0, 0, 0, 0.18);
  overflow: hidden;
}

.provider-form__section::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(120% 60% at 0% 0%, rgba(96, 165, 250, 0.045) 0%, transparent 55%);
  pointer-events: none;
}

.provider-form__section--key::before {
  background: radial-gradient(120% 60% at 100% 0%, rgba(244, 114, 182, 0.05) 0%, transparent 55%);
}

.provider-form__section--code::before {
  background: radial-gradient(120% 60% at 50% 0%, rgba(34, 211, 238, 0.045) 0%, transparent 55%);
}

.provider-form__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin: -2px -4px 12px;
  padding: 6px 4px 10px;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.06);
  position: relative;
}

.provider-form__head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.provider-form__inline-btn {
  height: 30px;
  padding: 0 8px;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  color: #93c5fd;
  font-size: 12px;
  font-weight: 600;
}

.provider-form__inline-btn:hover,
.provider-form__inline-btn:focus {
  color: #dbeafe;
  background: rgba(96, 165, 250, 0.08) !important;
}

.provider-form__inline-btn .el-icon {
  margin-right: 4px;
}

.provider-form__head-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.provider-form__title {
  position: relative;
  margin: 0;
  padding-left: 12px;
  font-size: 14px;
  font-weight: 700;
  color: #f2f4f8;
  letter-spacing: -0.1px;
}

.provider-form__title::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 14px;
  border-radius: 999px;
  background: linear-gradient(180deg, #60a5fa, #2563eb);
}

.provider-form__section--key .provider-form__title::before {
  background: linear-gradient(180deg, #f472b6, #db2777);
}

.provider-form__hint {
  margin-left: 12px;
  color: #6e7681;
  font-size: 11.5px;
  letter-spacing: 0.1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-form__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
}

.provider-form__icon-item {
  grid-column: 1 / -1;
}

.provider-form__icon {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.provider-form__icon-preview {
  flex-shrink: 0;
  width: 72px;
  height: 72px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: rgba(7, 10, 16, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #6e7681;
  font-size: 12px;
  overflow: hidden;
}

.provider-form__icon-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.provider-form__icon-controls {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.provider-form__icon-actions {
  display: flex;
  gap: 8px;
}

.provider-form__grid--input,
.provider-form__grid--model {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0 12px;
}

.provider-form__grid--model .provider-form__model-desc {
  grid-column: 1 / -1;
}

.provider-form__model-advanced {
  margin-top: 6px;
  padding: 12px 14px 4px;
  border: 1px dashed rgba(96, 165, 250, 0.22);
  border-radius: 12px;
  background: rgba(96, 165, 250, 0.04);
}

.provider-form__model-advanced-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
  color: #c5cdd6;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.provider-form__model-advanced-head em {
  font-style: normal;
  color: #6e7681;
  font-size: 11px;
  font-weight: 400;
}

.provider-form__matrix {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.provider-form__matrix-empty {
  margin: 2px 0 2px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px dashed rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.014);
  color: #6e7681;
  font-size: 12px;
  line-height: 1.5;
}

.provider-form__matrix-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  align-items: end;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(7, 10, 16, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.provider-form__matrix-row--voice {
  background: rgba(7, 10, 16, 0.35);
}

.provider-form__matrix-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.provider-form__matrix-label {
  color: #8b949e;
  font-size: 11.5px;
  letter-spacing: 0.1px;
}

.provider-form__matrix-remove {
  align-self: end;
}

.provider-form__row-tag--audio {
  color: #fcd34d;
  background: rgba(251, 191, 36, 0.14);
  border-color: rgba(251, 191, 36, 0.4);
}

/* ===== 模型类型上色 · 雅黑风格 ===== */
.provider-form__row-tag--type {
  font-weight: 600;
  letter-spacing: 0.4px;
}
.provider-form__row-tag--type.is-text,
.capability-chip.is-text,
.provider-form__filter-chip.is-text.is-active {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.16);
  border-color: rgba(96, 165, 250, 0.45);
}
.provider-form__row-tag--type.is-image,
.capability-chip.is-image,
.provider-form__filter-chip.is-image.is-active {
  color: #67e8f9;
  background: rgba(8, 145, 178, 0.18);
  border-color: rgba(34, 211, 238, 0.45);
}
.provider-form__row-tag--type.is-video,
.capability-chip.is-video,
.provider-form__filter-chip.is-video.is-active {
  color: #fdba74;
  background: rgba(234, 88, 12, 0.18);
  border-color: rgba(251, 146, 60, 0.45);
}
.provider-form__row-tag--type.is-tts,
.capability-chip.is-tts,
.provider-form__filter-chip.is-tts.is-active {
  color: #c4b5fd;
  background: rgba(124, 58, 237, 0.18);
  border-color: rgba(167, 139, 250, 0.45);
}

/* 供应商卡片 · 能力分布徽章 */
.provider-card__capabilities {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.capability-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  font-size: 11.5px;
  color: #c5cdd6;
  font-family: "Microsoft YaHei", "PingFang SC", Inter, -apple-system, sans-serif;
  letter-spacing: 0.2px;
  line-height: 1.4;
}

.capability-chip em {
  font-style: normal;
  opacity: 0.85;
}

.capability-chip strong {
  font-weight: 700;
  font-size: 12.5px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

/* ===== 模型列表 · 筛选条 ===== */
.provider-form__filterbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: -2px 0 12px;
  padding: 6px 10px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.012));
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.provider-form__filterbar-icon {
  color: #6e7681;
  font-size: 13px;
  margin-right: 2px;
}

.provider-form__filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  font-family: "Microsoft YaHei", "PingFang SC", Inter, sans-serif;
  font-size: 12.5px;
  font-weight: 500;
  color: #b8c2cc;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  cursor: pointer;
  letter-spacing: 0.3px;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.provider-form__filter-chip:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
}

.provider-form__filter-chip.is-active {
  color: #ffffff;
  background: linear-gradient(180deg, rgba(96, 165, 250, 0.28), rgba(37, 99, 235, 0.18));
  border-color: rgba(96, 165, 250, 0.6);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.provider-form__filter-chip em {
  font-style: normal;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 11.5px;
  font-weight: 700;
  padding: 0 6px;
  min-width: 18px;
  text-align: center;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.32);
  color: inherit;
  opacity: 0.85;
}

/* ===== 模型行 · 可折叠 ===== */
.provider-form__row-toggle {
  flex: 1;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 0;
  background: transparent;
  border: 0;
  color: inherit;
  font-family: "Microsoft YaHei", "PingFang SC", Inter, sans-serif;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  outline: none;
}

.provider-form__row-toggle:focus-visible {
  outline: 1px solid rgba(96, 165, 250, 0.55);
  outline-offset: 2px;
  border-radius: 6px;
}

.provider-form__row-toggle strong {
  color: #f2f4f8;
  font-weight: 600;
  letter-spacing: 0.2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}

.provider-form__row-caret {
  flex-shrink: 0;
  display: inline-grid;
  place-items: center;
  width: 16px;
  height: 16px;
  font-size: 9px;
  color: #6e7681;
  transition: transform 0.2s ease, color 0.2s ease;
}

.provider-form__row:not(.is-collapsed) .provider-form__row-caret {
  transform: rotate(90deg);
  color: #93c5fd;
}

.provider-form__row.is-collapsed {
  padding-bottom: 12px;
}

.provider-form__row.is-collapsed .provider-form__row-head {
  border-bottom: 0;
  margin-bottom: 0;
  padding-bottom: 0;
}

.provider-form__row-body {
  padding-top: 6px;
}

.provider-form__number {
  width: 100%;
}

.provider-form__row {
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 14px;
  padding: 14px 16px 4px;
  margin-bottom: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.024), rgba(255, 255, 255, 0.006)),
    rgba(15, 20, 28, 0.62);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.22);
  transition: border-color 0.2s ease, background-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

.provider-form__row:hover {
  border-color: rgba(96, 165, 250, 0.32);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.012)),
    rgba(15, 20, 28, 0.75);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.3);
}

.provider-form__row.is-collapsed:hover {
  transform: none;
}

.provider-form__row:last-child {
  margin-bottom: 0;
}

.provider-form__row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.08);
}

.provider-form__row-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #e6edf3;
  font-size: 13px;
}

.provider-form__row-index {
  flex-shrink: 0;
  display: inline-grid;
  place-items: center;
  min-width: 24px;
  height: 20px;
  padding: 0 6px;
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.18), rgba(37, 99, 235, 0.12));
  border: 1px solid rgba(96, 165, 250, 0.28);
  color: #c7d2fe;
  font-style: normal;
  font-size: 10.5px;
  font-weight: 700;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  letter-spacing: 0.2px;
}

.provider-form__row-title strong {
  color: #e6edf3;
  font-weight: 600;
  letter-spacing: -0.1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-form__row-tag {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #c5cdd6;
  font-size: 10.5px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.provider-form__row-tag--think {
  color: #c4b5fd;
  background: rgba(139, 92, 246, 0.18);
  border-color: rgba(139, 92, 246, 0.4);
}

.provider-form__row-actions {
  display: flex;
  gap: 6px;
}

.provider-form__empty {
  margin: 4px 2px 14px;
  padding: 16px 18px;
  border-radius: 10px;
  border: 1px dashed rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.014);
  color: #6e7681;
  font-size: 12.5px;
  line-height: 1.55;
  text-align: center;
}

.provider-form :deep(.el-form-item__label) {
  font-size: 12px;
  font-weight: 500;
  color: #b8c2cc;
  padding-bottom: 4px;
}

.provider-form :deep(.el-input__wrapper),
.provider-form :deep(.el-select__wrapper),
.provider-form :deep(.el-textarea__inner),
.provider-form :deep(.el-input-number) {
  background-color: rgba(7, 10, 16, 0.55) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset !important;
}

.provider-form :deep(.el-input__wrapper:hover),
.provider-form :deep(.el-select__wrapper:hover),
.provider-form :deep(.el-textarea__inner:hover) {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset !important;
}

.provider-form :deep(.el-input__wrapper.is-focus),
.provider-form :deep(.el-select__wrapper.is-focused),
.provider-form :deep(.el-textarea__inner:focus) {
  box-shadow:
    0 0 0 1px rgba(96, 165, 250, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12) !important;
}

.provider-form :deep(.el-select__placeholder) {
  pointer-events: none;
}

.provider-form :deep(.el-input-number .el-input-number__increase),
.provider-form :deep(.el-input-number .el-input-number__decrease) {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
}

.provider-form :deep(.el-switch) {
  --el-switch-on-color: #2563eb;
  --el-switch-off-color: rgba(255, 255, 255, 0.12);
}

.provider-code-editor :deep(.el-textarea__inner) {
  min-height: 260px !important;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  tab-size: 4;
}

/* ---------- 编辑弹窗整体 ---------- */
.provider-dialog .el-dialog__header {
  background: linear-gradient(180deg, rgba(96, 165, 250, 0.06), transparent 80%);
}

@media (max-width: 760px) {
  .provider-form__grid,
  .provider-form__grid--input,
  .provider-form__grid--model {
    grid-template-columns: 1fr;
  }

  .provider-card__head {
    flex-direction: column;
  }

  .provider-card__actions {
    flex-direction: row;
    align-self: stretch;
    justify-content: flex-end;
  }
}

@media (max-width: 760px) {
  .settings-shell {
    grid-template-columns: 1fr;
  }

  .settings-nav {
    flex-direction: row;
    overflow-x: auto;
  }

  .account-grid {
    grid-template-columns: 1fr;
  }

  .account-fields {
    grid-template-columns: 1fr;
  }
}
</style>

<style>
/* settings 弹窗 / messagebox 暗色样式（teleport 到 body） */
.settings-dark-dialog {
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 22px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  color: #e6edf3;
  font-family: "Microsoft YaHei", "PingFang SC", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
  font-feature-settings: "ss01", "ss02", "cv11";
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.settings-dark-dialog .el-dialog__header {
  margin: 0;
  padding: 20px 26px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.settings-dark-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.settings-dark-dialog .el-dialog__headerbtn {
  top: 14px;
  right: 18px;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
}

.settings-dark-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
  font-size: 18px;
}

.settings-dark-dialog .el-dialog__headerbtn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.18);
}

.settings-dark-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #ffffff;
}

.settings-dark-dialog .el-dialog__body {
  padding: 18px 26px 22px;
  color: #b8c2cc;
  max-height: calc(100vh - 180px);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.35) transparent;
}

.settings-dark-dialog .el-dialog__body::-webkit-scrollbar {
  width: 8px;
}

.settings-dark-dialog .el-dialog__body::-webkit-scrollbar-track {
  background: transparent;
  margin: 8px 0;
}

.settings-dark-dialog .el-dialog__body::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.3);
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: padding-box;
  transition: background-color 0.18s ease;
}

.settings-dark-dialog .el-dialog__body::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}

.settings-dark-dialog .el-textarea__inner {
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.32) transparent;
}

.settings-dark-dialog .el-textarea__inner::-webkit-scrollbar {
  width: 6px;
}

.settings-dark-dialog .el-textarea__inner::-webkit-scrollbar-track {
  background: transparent;
}

.settings-dark-dialog .el-textarea__inner::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.28);
  border-radius: 999px;
}

.settings-dark-dialog .el-textarea__inner::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}

.settings-dark-dialog .el-form-item__label {
  color: #d5dce4;
  font-size: 13px;
  font-weight: 600;
  padding: 0 0 6px;
}

.settings-dark-dialog .el-form-item.is-error .el-form-item__error {
  color: #fca5a5;
  padding-top: 4px;
}

.settings-dark-dialog .el-input__wrapper {
  min-height: 40px;
  padding: 0 12px;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border-radius: 10px;
  color: #e6edf3;
  font-size: 13px;
}

.settings-dark-dialog .el-input__wrapper:hover {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.settings-dark-dialog .el-input__wrapper.is-focus {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.settings-dark-dialog .el-input__inner {
  color: #e6edf3;
}

.settings-dark-dialog .el-input__inner::placeholder {
  color: #7e8893;
}

.settings-dark-dialog .el-input__suffix .el-icon {
  color: #8b949e;
}

.settings-dark-dialog .el-button {
  height: 38px;
  padding: 0 18px;
  border-radius: 10px;
  font-weight: 700;
}

.settings-dark-dialog .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.22);
}

.settings-dark-dialog .el-button--primary:hover {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
}

.settings-dark-dialog .el-button--danger {
  background-color: #dc2626;
  border-color: #dc2626;
  box-shadow: 0 8px 18px rgba(220, 38, 38, 0.22);
}

.settings-dark-dialog .el-button--danger:hover {
  background-color: #b91c1c;
  border-color: #b91c1c;
}

.provider-code-web-dialog .el-dialog__body {
  overflow: hidden;
}

/* messagebox */
.settings-dark-messagebox {
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.settings-dark-messagebox .el-message-box__header {
  padding: 18px 24px 8px;
}

.settings-dark-messagebox .el-message-box__title {
  color: #e6edf3;
  font-weight: 700;
}

.settings-dark-messagebox .el-message-box__content {
  padding: 8px 24px 18px;
  color: #b8c2cc;
}

.settings-dark-messagebox .el-message-box__btns {
  padding: 12px 24px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.settings-dark-messagebox .el-message-box__btns .el-button {
  border-radius: 8px;
}

.settings-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
}

.settings-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger):hover {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}

/* select 下拉浮层（模型类型 / 输入类型） */
.settings-dark-select.el-popper {
  background-color: #14181f;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}

.settings-dark-select.el-popper .el-select-dropdown__list {
  padding: 6px 4px;
}

.settings-dark-select.el-popper .el-select-dropdown__item {
  color: #c5cdd6;
  border-radius: 8px;
  margin: 2px 4px;
  padding: 0 12px;
  height: 32px;
  line-height: 32px;
}

.settings-dark-select.el-popper .el-select-dropdown__item:hover,
.settings-dark-select.el-popper .el-select-dropdown__item.is-hovering {
  background-color: rgba(255, 255, 255, 0.06);
  color: #ffffff;
}

.settings-dark-select.el-popper .el-select-dropdown__item.is-selected {
  color: #93c5fd;
  background-color: rgba(37, 99, 235, 0.16);
  font-weight: 600;
}

.settings-dark-select.el-popper .el-popper__arrow::before {
  background-color: #14181f;
  border-color: rgba(255, 255, 255, 0.08);
}
</style>
