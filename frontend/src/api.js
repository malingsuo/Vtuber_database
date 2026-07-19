import axios from 'axios'
import { ElMessage } from 'element-plus'
import { clearSession } from './session.js'

const api = axios.create({ baseURL: '/api' })

// 每個請求自動帶上登入權杖
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 統一的錯誤提示：後端回的中文錯誤訊息直接彈出來；
// 401（未登入/過期）就清掉 session 導回登入頁
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data?.detail
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg).join('；')
      : detail || err.message
    const isLoginCall = err.config?.url?.includes('/auth/login')
    if (err.response?.status === 401 && !isLoginCall) {
      clearSession()
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
        return Promise.reject(err)
      }
    }
    ElMessage.error(msg)
    return Promise.reject(err)
  },
)

export default api
