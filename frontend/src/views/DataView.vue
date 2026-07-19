<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api.js'

const activeTab = ref('quotes')
const itemTypes = ref([])
const vendors = ref([])
const artists = ref([])

const today = () => new Date().toISOString().slice(0, 10)
const nt = (n) => `NT$ ${Number(n).toLocaleString()}`

onMounted(async () => {
  const [t, v, a] = await Promise.all([
    api.get('/item-types'), api.get('/vendors'), api.get('/artists'),
  ])
  itemTypes.value = t.data
  vendors.value = v.data
  artists.value = a.data
})

const itemTypeName = (id) => itemTypes.value.find((t) => t.id === id)?.name ?? ''
const vendorName = (id) => vendors.value.find((v) => v.id === id)?.name ?? ''

// ── 報價紀錄 ──
const quoteFilter = reactive({ item_type_id: null, vendor_id: null })
const quoteRows = ref([])

const quoteForm = reactive({
  item_type_id: null, vendor_id: null, quantity: null,
  unit_price: null, currency: 'CNY', exchange_rate: null,
  quote_date: today(), notes: '',
})

const quoteTwd = computed(() => {
  const rate = quoteForm.currency === 'TWD' ? 1 : quoteForm.exchange_rate ?? 0
  return ((quoteForm.unit_price ?? 0) * rate).toFixed(2)
})

async function loadQuotes() {
  const params = {}
  if (quoteFilter.item_type_id) params.item_type_id = quoteFilter.item_type_id
  if (quoteFilter.vendor_id) params.vendor_id = quoteFilter.vendor_id
  const { data } = await api.get('/quotes', { params })
  quoteRows.value = data
}
onMounted(loadQuotes)

async function addQuote() {
  if (!quoteForm.item_type_id || !quoteForm.quantity || !quoteForm.unit_price) {
    ElMessage.warning('品項、詢價數量、單價為必填')
    return
  }
  const rate = quoteForm.currency === 'TWD' ? 1 : quoteForm.exchange_rate
  if (!rate) {
    ElMessage.warning('外幣報價請填匯率')
    return
  }
  await api.post('/quotes', {
    item_type_id: quoteForm.item_type_id,
    vendor_id: quoteForm.vendor_id || null,
    quantity: quoteForm.quantity,
    unit_price: quoteForm.unit_price,
    currency: quoteForm.currency,
    exchange_rate: rate,
    quote_date: quoteForm.quote_date,
    notes: quoteForm.notes || null,
  })
  ElMessage.success('報價已記錄——預測模組會用上它')
  quoteForm.quantity = null
  quoteForm.unit_price = null
  quoteForm.notes = ''
  loadQuotes()
}

async function deleteQuote(q) {
  try {
    await ElMessageBox.confirm(
      `刪除這筆報價？${itemTypeName(q.item_type_id)}｜${q.quantity} 個 @ ${q.unit_price} ${q.currency}`,
      '刪除報價',
      { confirmButtonText: '刪除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await api.delete(`/quotes/${q.id}`)
  ElMessage.success('已刪除')
  loadQuotes()
}

// 廠商就地新增（跟品項的做法一致）
async function addVendor() {
  let name
  try {
    const { value } = await ElMessageBox.prompt('輸入廠商名稱', '新增廠商', {
      confirmButtonText: '建立',
      cancelButtonText: '取消',
      inputValidator: (v) => !!v?.trim() || '名稱不能空白',
    })
    name = value.trim()
  } catch {
    return
  }
  const { data } = await api.post('/vendors', { name })
  ElMessage.success(`廠商「${data.name}」已建立`)
  vendors.value.push(data)
  quoteForm.vendor_id = data.id
}

// ── 藝人熱度 ──
const METRIC_LABEL = { subscribers: '訂閱數', followers: '追隨者', members: '會員數' }
const metricArtistId = ref(null)
const metricRows = ref([])

const metricForm = reactive({
  record_date: today(), platform: 'YouTube',
  metric_type: 'subscribers', value: null,
})

async function loadMetrics() {
  if (!metricArtistId.value) return
  const { data } = await api.get('/artist-metrics', {
    params: { artist_id: metricArtistId.value },
  })
  metricRows.value = data
}

async function addMetric() {
  if (!metricArtistId.value) {
    ElMessage.warning('先選藝人')
    return
  }
  if (metricForm.value == null) {
    ElMessage.warning('請填數值')
    return
  }
  await api.post('/artist-metrics', {
    artist_id: metricArtistId.value,
    ...metricForm,
  })
  ElMessage.success('熱度紀錄已新增')
  metricForm.value = null
  loadMetrics()
}

// ── Excel 匯入/匯出 ──
const importFile = ref(null)
const importReport = ref(null)
const importing = ref(false)

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadTemplate() {
  const res = await api.get('/excel/template', { responseType: 'blob' })
  saveBlob(res.data, '匯入範本.xlsx')
}

async function exportAll() {
  const res = await api.get('/excel/export', { responseType: 'blob' })
  saveBlob(res.data, `週邊資料匯出_${today()}.xlsx`)
}

function onFileChange(file) {
  importFile.value = file.raw
  importReport.value = null
}

async function runImport(dryRun) {
  if (!importFile.value) {
    ElMessage.warning('先選擇 .xlsx 檔案')
    return
  }
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value)
    const { data } = await api.post(`/excel/import?dry_run=${dryRun}`, fd)
    importReport.value = data
    if (data.imported) {
      ElMessage.success(`匯入完成：${data.valid} 列資料已寫入`)
      importFile.value = null
    } else if (data.errors.length === 0) {
      ElMessage.success('檢查通過，可以按「確認匯入」')
    } else {
      ElMessage.warning(`發現 ${data.errors.length} 個錯誤，請修正後重新上傳`)
    }
  } finally {
    importing.value = false
  }
}

async function deleteMetric(m) {
  try {
    await ElMessageBox.confirm(
      `刪除 ${m.record_date} ${m.platform} 的紀錄（${m.value.toLocaleString()}）？`,
      '刪除紀錄',
      { confirmButtonText: '刪除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await api.delete(`/artist-metrics/${m.id}`)
  ElMessage.success('已刪除')
  loadMetrics()
}
</script>

<template>
  <div class="page">
    <h2>資料維護</h2>
    <el-tabs v-model="activeTab">
      <!-- ── 報價紀錄 ── -->
      <el-tab-pane label="報價紀錄" name="quotes">
        <p class="hint">
          每次向廠商詢價就記一筆（不管最後有沒有下單）。報價點累積越多，
          預測頁的「訂多少最賺」比較就越準。
        </p>

        <el-card style="margin-bottom: 16px">
          <template #header>新增報價</template>
          <el-space wrap>
            <el-select v-model="quoteForm.item_type_id" placeholder="品項" style="width: 130px">
              <el-option v-for="t in itemTypes" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
            <el-select
              v-model="quoteForm.vendor_id" clearable placeholder="廠商（選填）"
              style="width: 150px"
            >
              <el-option v-for="v in vendors" :key="v.id" :label="v.name" :value="v.id" />
            </el-select>
            <el-button link type="primary" @click="addVendor">＋新增廠商</el-button>
            <el-input-number
              v-model="quoteForm.quantity" :min="1" :controls="false"
              placeholder="詢價數量" style="width: 100px"
            />
            <el-input-number
              v-model="quoteForm.unit_price" :min="0.01" :precision="2" :controls="false"
              placeholder="單價(原幣)" style="width: 110px"
            />
            <el-select v-model="quoteForm.currency" style="width: 90px">
              <el-option label="TWD" value="TWD" />
              <el-option label="CNY" value="CNY" />
              <el-option label="JPY" value="JPY" />
            </el-select>
            <el-input-number
              v-model="quoteForm.exchange_rate" :min="0.0001" :precision="4" :controls="false"
              placeholder="匯率" style="width: 90px"
              :disabled="quoteForm.currency === 'TWD'"
            />
            <span class="hint">= NT${{ quoteTwd }}</span>
            <el-date-picker
              v-model="quoteForm.quote_date" type="date" value-format="YYYY-MM-DD"
              style="width: 140px"
            />
            <el-input v-model="quoteForm.notes" placeholder="備註（選填）" style="width: 140px" />
            <el-button type="primary" @click="addQuote">記錄報價</el-button>
          </el-space>
        </el-card>

        <el-space style="margin-bottom: 12px">
          <el-select
            v-model="quoteFilter.item_type_id" clearable placeholder="全部品項"
            style="width: 140px" @change="loadQuotes"
          >
            <el-option v-for="t in itemTypes" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-select
            v-model="quoteFilter.vendor_id" clearable placeholder="全部廠商"
            style="width: 150px" @change="loadQuotes"
          >
            <el-option v-for="v in vendors" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
        </el-space>

        <el-table :data="quoteRows" size="small">
          <el-table-column prop="quote_date" label="日期" width="110" />
          <el-table-column label="品項" width="120">
            <template #default="{ row }">{{ itemTypeName(row.item_type_id) }}</template>
          </el-table-column>
          <el-table-column label="廠商" width="140">
            <template #default="{ row }">{{ vendorName(row.vendor_id) }}</template>
          </el-table-column>
          <el-table-column prop="quantity" label="數量" width="80" align="right" />
          <el-table-column label="單價(原幣)" width="120" align="right">
            <template #default="{ row }">{{ row.unit_price }} {{ row.currency }}</template>
          </el-table-column>
          <el-table-column label="單價(台幣)" width="110" align="right">
            <template #default="{ row }">{{ nt(row.unit_price_twd) }}</template>
          </el-table-column>
          <el-table-column prop="notes" label="備註" min-width="120" />
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ row }">
              <el-button type="danger" link size="small" @click="deleteQuote(row)">
                刪除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── 藝人熱度 ── -->
      <el-tab-pane label="藝人熱度" name="metrics">
        <p class="hint">
          記錄藝人的訂閱/追隨者數（建議活動前後各記一筆、平時每月一筆）。
          未來可用於熱度成長分析與預測係數校準。
        </p>

        <el-space wrap style="margin-bottom: 12px">
          <el-select
            v-model="metricArtistId" placeholder="選擇藝人" style="width: 160px"
            @change="loadMetrics"
          >
            <el-option v-for="a in artists" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
          <el-date-picker
            v-model="metricForm.record_date" type="date" value-format="YYYY-MM-DD"
            style="width: 140px"
          />
          <el-select v-model="metricForm.platform" style="width: 120px">
            <el-option label="YouTube" value="YouTube" />
            <el-option label="Twitch" value="Twitch" />
            <el-option label="X" value="X" />
            <el-option label="其他" value="其他" />
          </el-select>
          <el-select v-model="metricForm.metric_type" style="width: 110px">
            <el-option
              v-for="(label, key) in METRIC_LABEL" :key="key" :label="label" :value="key"
            />
          </el-select>
          <el-input-number
            v-model="metricForm.value" :min="0" :controls="false"
            placeholder="數值" style="width: 120px"
          />
          <el-button type="primary" :disabled="!metricArtistId" @click="addMetric">
            新增紀錄
          </el-button>
        </el-space>

        <el-table v-if="metricArtistId" :data="metricRows" size="small">
          <el-table-column prop="record_date" label="日期" width="110" />
          <el-table-column prop="platform" label="平台" width="100" />
          <el-table-column label="指標" width="100">
            <template #default="{ row }">
              {{ METRIC_LABEL[row.metric_type] ?? row.metric_type }}
            </template>
          </el-table-column>
          <el-table-column label="數值" width="120" align="right">
            <template #default="{ row }">{{ row.value.toLocaleString() }}</template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ row }">
              <el-button type="danger" link size="small" @click="deleteMetric(row)">
                刪除
              </el-button>
            </template>
          </el-table-column>
          <el-table-column />
        </el-table>
        <el-empty v-else description="選擇藝人來查看與輸入熱度紀錄" />
      </el-tab-pane>

      <!-- ── Excel 匯入/匯出 ── -->
      <el-tab-pane label="Excel 匯入/匯出" name="excel">
        <el-card style="margin-bottom: 16px">
          <template #header>匯入歷史資料</template>
          <p class="hint">
            流程：下載範本 → 照格式填歷史資料（範例列要刪掉）→ 上傳 → 檢查 → 確認匯入。
            任何一列有錯就整批不寫入，錯誤會逐列列出。藝人/品項/活動不存在會自動建立。
          </p>
          <el-space wrap>
            <el-button @click="downloadTemplate">下載匯入範本</el-button>
            <el-upload
              :auto-upload="false" :limit="1" accept=".xlsx"
              :show-file-list="true" :on-change="onFileChange"
              :on-remove="() => { importFile = null; importReport = null }"
            >
              <el-button type="primary" plain>選擇檔案</el-button>
            </el-upload>
            <el-button
              :disabled="!importFile" :loading="importing"
              @click="runImport(true)"
            >檢查檔案</el-button>
            <el-button
              type="primary"
              :disabled="!importReport || importReport.errors.length > 0 || importReport.imported"
              :loading="importing"
              @click="runImport(false)"
            >確認匯入</el-button>
          </el-space>

          <template v-if="importReport">
            <el-alert
              :type="importReport.errors.length ? 'error'
                : importReport.imported ? 'success' : 'info'"
              :closable="false" style="margin-top: 12px"
              :title="`共 ${importReport.total} 列，通過 ${importReport.valid} 列`
                + `；將建立：活動 ${importReport.new_events}、藝人 ${importReport.new_artists}`
                + `、品項 ${importReport.new_item_types}、商品 ${importReport.new_products}`
                + (importReport.imported ? '——已寫入' : '')"
            />
            <el-table
              v-if="importReport.errors.length"
              :data="importReport.errors" size="small" style="margin-top: 8px"
            >
              <el-table-column prop="row" label="列" width="70" />
              <el-table-column prop="message" label="錯誤" min-width="300" />
            </el-table>
          </template>
        </el-card>

        <el-card>
          <template #header>匯出全部資料</template>
          <p class="hint">
            四張工作表：商品銷售明細、報價紀錄、檔期開支、藝人熱度。備份或離線分析用。
          </p>
          <el-button type="primary" @click="exportAll">匯出 Excel</el-button>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.7;
}
</style>
