<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api.js'

const props = defineProps({
  modelValue: Boolean,
  // [{ id, label, price, available }]
  variants: Array,
  defaultChannel: String, // 'onsite' | 'online'
})
const emit = defineEmits(['update:modelValue', 'saved'])

const today = () => new Date().toISOString().slice(0, 10)

const form = reactive({ date: today(), channel: 'onsite', rows: [] })

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      form.date = today()
      form.channel = props.defaultChannel === 'online' ? 'online' : 'onsite'
      form.rows = props.variants.map((v) => ({
        ...v,
        quantity: null,
        sold_out: false,
      }))
    }
  },
)

const submitting = ref(false)

async function submit() {
  const items = form.rows
    .filter((r) => r.quantity > 0)
    .map((r) => ({
      variant_id: r.id,
      quantity: r.quantity,
      sold_out_today: r.sold_out,
    }))
  if (!items.length) {
    ElMessage.warning('沒有填任何銷量')
    return
  }
  submitting.value = true
  try {
    const { data } = await api.post('/inventory/daily-sales', {
      movement_date: form.date,
      channel: form.channel,
      items,
    })
    ElMessage.success(`已寫入 ${data.created} 筆銷售`)
    emit('update:modelValue', false)
    emit('saved')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="逐日銷售輸入"
    width="680px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-space style="margin-bottom: 12px">
      <el-date-picker
        v-model="form.date" type="date" value-format="YYYY-MM-DD"
        placeholder="銷售日期" style="width: 150px"
      />
      <el-radio-group v-model="form.channel">
        <el-radio-button value="onsite">現場</el-radio-button>
        <el-radio-button value="online">通販</el-radio-button>
      </el-radio-group>
      <span class="hint">收攤／關帳後，把當天每樣商品的銷量填進來；沒賣的留空即可</span>
    </el-space>

    <el-table :data="form.rows" size="small" max-height="420">
      <el-table-column prop="label" label="商品（規格）" min-width="240" />
      <el-table-column label="可售" width="70" align="right">
        <template #default="{ row }">{{ row.available }}</template>
      </el-table-column>
      <el-table-column label="當日銷量" width="130">
        <template #default="{ row }">
          <el-input-number
            v-model="row.quantity" :min="0" :max="row.available" :controls="false"
            placeholder="0" style="width: 100px"
          />
        </template>
      </el-table-column>
      <el-table-column label="當天完售" width="90" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.sold_out" />
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        寫入當日銷售
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.hint {
  font-size: 12px;
  color: #909399;
}
</style>
