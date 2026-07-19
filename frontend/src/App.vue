<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <el-container>
    <el-header class="header">
      <span class="logo">VTuber 週邊管理系統</span>
      <el-menu mode="horizontal" :default-active="route.path" router :ellipsis="false">
        <el-menu-item index="/">查詢活動</el-menu-item>
        <el-menu-item index="/events/new">新建活動</el-menu-item>
        <el-menu-item index="/reports">報表</el-menu-item>
        <el-menu-item index="/settings">設定</el-menu-item>
      </el-menu>
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
</style>
