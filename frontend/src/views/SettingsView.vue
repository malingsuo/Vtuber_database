<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api.js'

// ── 刪除商品確認方式（存瀏覽器 localStorage，預設開啟）──
const confirmByName = ref(localStorage.getItem('delete_confirm_by_name') !== 'false')
watch(confirmByName, (v) => localStorage.setItem('delete_confirm_by_name', String(v)))

// ── 品項類別管理 ──
const itemTypes = ref([])

async function loadItemTypes() {
  const { data } = await api.get('/item-types')
  itemTypes.value = data
}
onMounted(loadItemTypes)

async function createItemType() {
  let name
  try {
    const { value } = await ElMessageBox.prompt('輸入新品項名稱', '新增品項類別', {
      confirmButtonText: '建立',
      cancelButtonText: '取消',
      inputValidator: (v) => !!v?.trim() || '名稱不能空白',
    })
    name = value.trim()
  } catch {
    return
  }
  await api.post('/item-types', { name })
  ElMessage.success(`品項「${name}」已建立`)
  loadItemTypes()
}

async function renameItemType(t) {
  let name
  try {
    const { value } = await ElMessageBox.prompt(
      `將「${t.name}」改名。注意：所有使用此品項的歷史商品會一起顯示新名稱`,
      '品項改名',
      {
        inputValue: t.name,
        confirmButtonText: '改名',
        cancelButtonText: '取消',
        inputValidator: (v) => !!v?.trim() || '名稱不能空白',
      },
    )
    name = value.trim()
  } catch {
    return
  }
  if (name === t.name) return
  await api.put(`/item-types/${t.id}`, { name, notes: t.notes ?? null })
  ElMessage.success(`已改名為「${name}」`)
  loadItemTypes()
}

async function deleteItemType(t) {
  try {
    await ElMessageBox.confirm(
      `確定刪除品項「${t.name}」嗎？已有商品使用的品項會被系統擋下。`,
      '刪除品項',
      { confirmButtonText: '刪除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await api.delete(`/item-types/${t.id}`) // 使用中的品項後端回 409
  ElMessage.success('已刪除')
  loadItemTypes()
}
</script>

<template>
  <div class="page" style="max-width: 640px">
    <h2>設定</h2>

    <el-card>
      <template #header>刪除商品的確認方式</template>
      <el-space>
        <el-switch v-model="confirmByName" />
        <span>刪除商品前需輸入完整商品名稱確認（關閉則只跳一般確認框）</span>
      </el-space>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <span>品項類別管理</span>
          <el-button type="primary" size="small" @click="createItemType">
            ＋新增品項
          </el-button>
        </div>
      </template>
      <el-table :data="itemTypes" size="small">
        <el-table-column prop="name" label="品項名稱" min-width="200" />
        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="renameItemType(row)">改名</el-button>
            <el-button size="small" type="danger" @click="deleteItemType(row)">
              刪除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="hint">
        改名會讓使用此品項的歷史商品一起顯示新名稱；已有商品使用的品項無法刪除
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.hint {
  font-size: 12px;
  color: #909399;
  margin-top: 10px;
}
</style>
