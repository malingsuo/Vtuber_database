<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api.js'

const router = useRouter()

const years = ref([])
const events = ref([])
const selectedYear = ref(null)
const selectedEvent = ref(null)
const loading = ref(false)

const TYPE_LABEL = { onsite: '場販', online: '通販', mixed: '混合' }

onMounted(async () => {
  const { data } = await api.get('/events/years')
  years.value = data
})

async function onYearChange(year) {
  selectedEvent.value = null
  events.value = []
  if (year == null) return
  loading.value = true
  try {
    const { data } = await api.get('/events', { params: { year } })
    events.value = data
  } finally {
    loading.value = false
  }
}

function goDetail() {
  if (selectedEvent.value) router.push(`/events/${selectedEvent.value}`)
}

// 刪除商品時是否要求輸入商品名稱確認（存在瀏覽器 localStorage，預設開啟）
const confirmByName = ref(localStorage.getItem('delete_confirm_by_name') !== 'false')
watch(confirmByName, (v) => localStorage.setItem('delete_confirm_by_name', String(v)))
</script>

<template>
  <div class="page">
    <h2>查詢活動</h2>
    <el-space wrap>
      <el-select
        v-model="selectedYear"
        placeholder="選擇年份"
        clearable
        style="width: 140px"
        @change="onYearChange"
      >
        <el-option v-for="y in years" :key="y" :label="`${y} 年`" :value="y" />
      </el-select>

      <el-select
        v-model="selectedEvent"
        placeholder="選擇活動"
        :disabled="!selectedYear"
        :loading="loading"
        style="width: 280px"
      >
        <el-option
          v-for="e in events"
          :key="e.id"
          :label="`${e.name}（${TYPE_LABEL[e.event_type]}）`"
          :value="e.id"
        />
      </el-select>

      <el-button type="primary" :disabled="!selectedEvent" @click="goDetail">
        查看活動
      </el-button>
    </el-space>

    <el-empty
      v-if="!selectedYear"
      description="從年份開始，逐層選到你要查的活動"
    />

    <el-divider />
    <h3>設定</h3>
    <el-space>
      <el-switch v-model="confirmByName" />
      <span>刪除商品前需輸入完整商品名稱確認（關閉則只跳一般確認框）</span>
    </el-space>
  </div>
</template>
