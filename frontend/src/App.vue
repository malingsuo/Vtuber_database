<script setup>
import { useRoute, useRouter } from 'vue-router'
import { clearSession, ROLE_LABEL, session } from './session.js'

const route = useRoute()
const router = useRouter()

function logout() {
  clearSession()
  router.push('/login')
}
</script>

<template>
  <!-- 登入頁自成一格，不套主版面 -->
  <router-view v-if="route.path === '/login'" />
  <el-container v-else>
    <el-header class="header">
      <span class="logo">VTuber 週邊管理系統</span>
      <el-menu mode="horizontal" :default-active="route.path" router :ellipsis="false">
        <el-menu-item index="/">查詢活動</el-menu-item>
        <el-menu-item index="/events/new">新建活動</el-menu-item>
        <el-menu-item index="/reports">報表</el-menu-item>
        <el-menu-item index="/forecast">預測</el-menu-item>
        <el-menu-item index="/data">資料維護</el-menu-item>
        <el-menu-item index="/settings">設定</el-menu-item>
      </el-menu>
      <span v-if="session.user" class="user-info">
        {{ session.user.display_name || session.user.username }}
        <el-tag size="small">{{ ROLE_LABEL[session.user.role] }}</el-tag>
        <el-button link type="primary" @click="logout">登出</el-button>
      </span>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  gap: 32px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.logo {
  font-size: 18px;
  font-weight: bold;
  white-space: nowrap;
}
.header :deep(.el-menu) {
  border-bottom: none;
  flex-grow: 1;
}
.user-info {
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #606266;
}
</style>
