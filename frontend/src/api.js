import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({ baseURL: '/api' })

// 統一的錯誤提示：後端回的中文錯誤訊息直接彈出來
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data?.detail
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg).join('；')
      : detail || err.message
    ElMessage.error(msg)
    return Promise.reject(err)
  },
)

export default api
