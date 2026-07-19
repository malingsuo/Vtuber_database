<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api.js'
import { ROLE_LABEL, session } from '../session.js'

const isAdmin = computed(() => session.user?.role === 'admin')

// ── 刪除商品確認方式（存瀏覽器 localStorage，預設開啟）──
const confirmByName = ref(localStorage.getItem('delete_confirm_by_name') !== 'false')
watch(confirmByName, (v) => localStorage.setItem('delete_confirm_by_name', String(v)))

// ── 品項類別管理 ──
const itemTypes = ref([])

async function loadItemTypes() {
  const { data } = await api.get('/item-types')
  itemTypes.value = data
}
onMounted(() => {
  loadItemTypes()
  if (isAdmin.value) loadUsers()
})

// ── 修改自己的密碼 ──
const pwForm = reactive({ old_password: '', new_password: '' })

async function changePassword() {
  if (!pwForm.old_password || pwForm.new_password.length < 6) {
    ElMessage.warning('請填原密碼，新密碼至少 6 碼')
    return
  }
  await api.post('/auth/change-password', pwForm)
  ElMessage.success('密碼已更新')
  pwForm.old_password = ''
  pwForm.new_password = ''
}

// ── 使用者管理（僅管理者）──
const users = ref([])
const newUser = reactive({ username: '', password: '', display_name: '', role: 'editor' })

async function loadUsers() {
  const { data } = await api.get('/auth/users')
  users.value = data
}

async function createUser() {
  if (newUser.username.length < 3 || newUser.password.length < 6) {
    ElMessage.warning('帳號至少 3 碼、密碼至少 6 碼')
    return
  }
  await api.post('/auth/users', {
    username: newUser.username,
    password: newUser.password,
    display_name: newUser.display_name || null,
    role: newUser.role,
  })
  ElMessage.success('使用者已建立')
  Object.assign(newUser, { username: '', password: '', display_name: '', role: 'editor' })
  loadUsers()
}

async function updateUser(u, patch) {
  await api.put(`/auth/users/${u.id}`, patch)
  ElMessage.success('已更新')
  loadUsers()
}

async function resetPassword(u) {
  let value
  try {
    ;({ value } = await ElMessageBox.prompt(
      `為「${u.username}」設定新密碼（至少 6 碼）`,
      '重設密碼',
      {
        inputType: 'password',
        confirmButtonText: '重設',
        cancelButtonText: '取消',
        inputValidator: (v) => (v && v.length >= 6) || '至少 6 碼',
      },
    ))
  } catch {
    return
  }
  await api.put(`/auth/users/${u.id}`, { password: value })
  ElMessage.success('密碼已重設')
}

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

    <el-card style="margin-top: 16px">
      <template #header>修改我的密碼</template>
      <el-space wrap>
        <el-input
          v-model="pwForm.old_password" type="password" show-password
          placeholder="原密碼" style="width: 160px"
        />
        <el-input
          v-model="pwForm.new_password" type="password" show-password
          placeholder="新密碼（至少 6 碼）" style="width: 180px"
        />
        <el-button type="primary" @click="changePassword">更新密碼</el-button>
      </el-space>
    </el-card>

    <el-card v-if="isAdmin" style="margin-top: 16px">
      <template #header>使用者管理（僅管理者可見）</template>
      <el-space wrap style="margin-bottom: 12px">
        <el-input v-model="newUser.username" placeholder="帳號" style="width: 120px" />
        <el-input
          v-model="newUser.password" type="password" show-password
          placeholder="密碼" style="width: 130px"
        />
        <el-input v-model="newUser.display_name" placeholder="顯示名稱" style="width: 120px" />
        <el-select v-model="newUser.role" style="width: 100px">
          <el-option
            v-for="(label, key) in ROLE_LABEL" :key="key" :label="label" :value="key"
          />
        </el-select>
        <el-button type="primary" @click="createUser">建立</el-button>
      </el-space>
      <el-table :data="users" size="small">
        <el-table-column prop="username" label="帳號" width="110" />
        <el-table-column prop="display_name" label="顯示名稱" width="110" />
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-select
              :model-value="row.role" size="small"
              :disabled="row.id === session.user.id"
              @update:model-value="(v) => updateUser(row, { role: v })"
            >
              <el-option
                v-for="(label, key) in ROLE_LABEL" :key="key" :label="label" :value="key"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="啟用" width="80" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              :disabled="row.id === session.user.id"
              @update:model-value="(v) => updateUser(row, { is_active: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" @click="resetPassword(row)">重設密碼</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="hint">角色權限：管理者＝全功能；輸入者＝可輸入資料；唯讀＝只能看</div>
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
