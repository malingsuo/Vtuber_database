import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // 開發時把 /api 轉發給後端，前端程式碼裡不用寫死後端網址
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
