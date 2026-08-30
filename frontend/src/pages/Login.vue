<template>
  <main class="login-page">
    <section class="login-window">
      <header class="topbar">
        <span class="dot red" />
        <span class="dot yellow" />
        <span class="dot green" />
      </header>

      <div class="content">
        <div class="logo">
          <div class="logo-mark">A</div>
          <h1 class="cursor">AnonForge</h1>
          <p class="subtitle">佚名AI智能体创作平台</p>
          <p class="terminal-hint">$ connect --agent forge</p>
        </div>

        <el-form
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          class="login-form"
          label-position="top"
          @submit.prevent
        >
          <el-form-item prop="username">
            <el-input
              v-model="loginForm.username"
              placeholder="username"
              size="large"
              autocomplete="username"
              clearable
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="loginForm.password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="password"
              size="large"
              autocomplete="current-password"
              @keyup.enter="handleLogin"
            >
              <template #suffix>
                <el-icon class="password-toggle" @click="showPassword = !showPassword">
                  <View v-if="!showPassword" />
                  <Hide v-else />
                </el-icon>
              </template>
            </el-input>
          </el-form-item>

          <el-button
            class="login-button"
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form>

        <div class="footer">
          default: <span>admin / admin123</span>
        </div>

        <nav class="router-actions">
          <el-link type="primary" :underline="false" @click="goForgotPassword">
            忘记密码?
          </el-link>
        </nav>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Hide, View } from '@element-plus/icons-vue'
import { loginApi } from '@/api/user'

interface LoginForm {
  username: string
  password: string
}

const router = useRouter()
const loginFormRef = ref<FormInstance>()
const loading = ref(false)
const showPassword = ref(false)

const loginForm = reactive<LoginForm>({
  username: '',
  password: '',
})

const loginRules: FormRules<LoginForm> = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
  ],
}

  const handleLogin = async () => {
    if (!loginFormRef.value) return

    const valid = await loginFormRef.value.validate().catch(() => false)
    if (!valid) return

    loading.value = true

    try {
      const { data } = await loginApi({
        username: loginForm.username.trim(),
        password: loginForm.password,
      })

      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      localStorage.setItem('token_type', data.token_type)
      localStorage.setItem('expires_in', String(data.expires_in))
      localStorage.setItem('user', JSON.stringify(data.user))

      ElMessage.success('登录成功')
      await router.replace('/project')
    } finally {
      loading.value = false
    }
  }

  const goForgotPassword = () => {
    ElMessage.info('请联系管理员重置密码')
  }
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: "JetBrains Mono", Consolas, monospace;
  color: #e6edf3;
  background: radial-gradient(circle at top, #161b22, #0b0d10);
}

.login-window {
  width: 420px;
  overflow: hidden;
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  background: #12161b;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
}

.topbar {
  height: 38px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: #171c22;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.dot.red {
  background: #ff5f57;
}

.dot.yellow {
  background: #febc2e;
}

.dot.green {
  background: #28c840;
}

.content {
  padding: 34px 30px 26px;
}

.logo {
  text-align: center;
  margin-bottom: 22px;
}

.logo-mark {
  width: 50px;
  height: 50px;
  display: grid;
  place-items: center;
  margin: 0 auto 10px;
  border-radius: 12px;
  color: #111;
  font-size: 18px;
  font-weight: 800;
  background: linear-gradient(135deg, #f3d96b, #a78bfa);
}

.logo h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 1px;
}

.subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8b949e;
}

.terminal-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #f3d96b;
}

.login-form {
  margin-top: 18px;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 44px;
  border-radius: 8px;
  background: #0f141a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
  transition: 0.2s;
}

.login-form :deep(.el-input__wrapper:hover),
.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px rgba(243, 217, 107, 0.75) inset,
    0 0 0 3px rgba(243, 217, 107, 0.12);
}

.login-form :deep(.el-input__inner) {
  color: #e6edf3;
  font-family: "JetBrains Mono", Consolas, monospace;
  font-size: 13px;
}

.login-form :deep(.el-input__inner::placeholder) {
  color: #8b949e;
}

.password-toggle {
  color: #8b949e;
  cursor: pointer;
}

.password-toggle:hover {
  color: #f3d96b;
}

.login-button {
  width: 100%;
  height: 44px;
  margin-top: 4px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  background: #2563eb;
}

.login-button:hover,
.login-button:focus {
  background: #1d4ed8;
}

.footer {
  margin-top: 14px;
  font-size: 11px;
  color: #8b949e;
  text-align: center;
}

.footer span {
  color: #f3d96b;
}

.router-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
  font-size: 12px;
}

.router-actions a {
  color: #409eff;
  text-decoration: none;
}

.router-actions a:hover {
  color: #79bbff;
}

.divider {
  color: #8b949e;
}

.cursor::after {
  content: "_";
  margin-left: 2px;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%,
  50%,
  100% {
    opacity: 1;
  }

  25%,
  75% {
    opacity: 0;
  }
}

@media (max-width: 480px) {
  .login-window {
    width: 100%;
  }

  .content {
    padding: 30px 22px 24px;
  }
}
</style>