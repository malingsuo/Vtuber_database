import { reactive } from 'vue'

// 極簡 session 存放：token 進 localStorage（重開瀏覽器仍有效），
// user 物件做成 reactive 讓導覽列即時反應登入/登出
export const session = reactive({
  user: JSON.parse(localStorage.getItem('user') || 'null'),
})

export function setSession(token, user) {
  localStorage.setItem('token', token)
  localStorage.setItem('user', JSON.stringify(user))
  session.user = user
}

export function clearSession() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  session.user = null
}

export const ROLE_LABEL = { admin: '管理者', editor: '輸入者', viewer: '唯讀' }
