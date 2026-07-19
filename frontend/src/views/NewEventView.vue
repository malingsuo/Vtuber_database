<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api.js'

const router = useRouter()
const formRef = ref(null)

const form = reactive({
  name: '',
  dates: null, // [start, end]
  event_type: 'onsite',
  preorder_dates: null,
  notes: '',
})

const rules = {
  name: [{ required: true, message: '請輸入活動名稱', trigger: 'blur' }],
  dates: [{ required: true, message: '請選擇活動起訖日', trigger: 'change' }],
}

const submitting = ref(false)

async function submit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    const { data } = await api.post('/events', {
      name: form.name,
      start_date: form.dates[0],
      end_date: form.dates[1],
      event_type: form.event_type,
      preorder_start: form.preorder_dates?.[0] ?? null,
      preorder_end: form.preorder_dates?.[1] ?? null,
      notes: form.notes || null,
    })
    ElMessage.success('活動建立成功，開始輸入商品吧')
    router.push(`/events/${data.id}`)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page" style="max-width: 640px">
    <h2>新建活動</h2>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
      <el-form-item label="活動名稱" prop="name">
        <el-input v-model="form.name" placeholder="例：2026 夏日祭場販" />
      </el-form-item>

      <el-form-item label="活動起訖日" prop="dates">
        <el-date-picker
          v-model="form.dates"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="開始日"
          end-placeholder="結束日"
        />
      </el-form-item>

      <el-form-item label="活動類型">
        <el-radio-group v-model="form.event_type">
          <el-radio-button value="onsite">場販</el-radio-button>
          <el-radio-button value="online">通販</el-radio-button>
          <el-radio-button value="mixed">混合</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="預購期間">
        <el-date-picker
          v-model="form.preorder_dates"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="預購開始"
          end-placeholder="預購截止"
        />
        <div class="hint">選填。有開預購才填，之後預測會用到預購曲線</div>
      </el-form-item>

      <el-form-item label="備註">
        <el-input v-model="form.notes" type="textarea" :rows="2" />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">
          建立活動
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
.hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}
</style>
