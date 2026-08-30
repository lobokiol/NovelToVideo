import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

const request = axios.create({
  baseURL: '/api',  // /api/user/login
  timeout: 10000,
})

interface TokenRefreshResult {
  access_token: string
  token_type: string
  expires_in: number
}

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

let refreshTokenRequest: Promise<string> | null = null

const clearAuthStorage = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('token_type')
  localStorage.removeItem('expires_in')
  localStorage.removeItem('user')
}

const isAuthRoute = (url = '') => {
  return url.includes('/users/login') || url.includes('/users/refresh-token')
}

const refreshAccessToken = (refreshToken: string) => {
  if (!refreshTokenRequest) {
    refreshTokenRequest = axios
      .post<TokenRefreshResult>(
        '/api/users/refresh-token',
        { refresh_token: refreshToken },
        { timeout: 10000 },
      )
      .then(({ data }) => {
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('token_type', data.token_type)
        localStorage.setItem('expires_in', String(data.expires_in))
        return data.access_token
      })
      .finally(() => {
        refreshTokenRequest = null
      })
  }

  return refreshTokenRequest
}


const withAuthHeader = (init: RequestInit, accessToken = localStorage.getItem('access_token')) => {
  const headers = new Headers(init.headers)
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }
  return {
    ...init,
    headers,
  }
}

export const fetchWithAuthRetry = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const firstResponse = await fetch(input, withAuthHeader(init))
  if (firstResponse.status !== 401 || isAuthRoute(String(input))) {
    return firstResponse
  }

  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) {
    clearAuthStorage()
    return firstResponse
  }

  try {
    const accessToken = await refreshAccessToken(refreshToken)
    return await fetch(input, withAuthHeader(init, accessToken))
  } catch (refreshError) {
    clearAuthStorage()
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    throw refreshError
  }
}


// 网络请求守卫
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')

  if (token) {
    config.headers.Authorization = 'Bearer ' + token
  }

  return config
})

// 网络响应守卫
request.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ detail?: string }>) => {
    const response = error.response
    const originalConfig = error.config as RetriableRequestConfig | undefined

    if (
      response?.status !== 401 ||
      !originalConfig ||
      originalConfig._retry ||
      isAuthRoute(originalConfig.url)
    ) {
      return Promise.reject(error)
    }

    const detail = response.data?.detail || ''
    if (!detail.includes('access token')) {
      return Promise.reject(error)
    }

    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      clearAuthStorage()
      return Promise.reject(error)
    }

    originalConfig._retry = true

    try {
      const accessToken = await refreshAccessToken(refreshToken)
      originalConfig.headers.Authorization = `Bearer ${accessToken}`
      return request(originalConfig)
    } catch (refreshError) {
      clearAuthStorage()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
      return Promise.reject(refreshError)
    }
  },
)

export default request
