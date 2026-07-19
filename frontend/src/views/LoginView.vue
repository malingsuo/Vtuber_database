<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api.js'
import { setSession } from '../session.js'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function submit() {
  if (!form.username || !form.password) return
  loading.value = true
  try {
    const { data } = await api.post('/auth/login', form)
    setSession(data.token, data.user)
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 style="text-align: center; margin-top: 0">VTuber 週邊管理系統</h2>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="帳號">
          <el-input v-model="form.username" autofocus @keyup.enter="submit" />
        </el-form-item>
        <el-form-item label="密碼">
          <el-input
            v-model="form.password" type="password" show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary" style="width: 100%" :loading="loading" @click="submit"
        >登入</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
}
.login-card {
  width: 360px;
}
</style>
