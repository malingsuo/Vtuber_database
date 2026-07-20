<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import VChart from 'vue-echarts'
import api from '../api.js'
import { CHANNEL_META, PALETTE } from '../charts.js'

const years = ref([])
const activeTab = ref('event')

const nt = (n) => `NT$ ${Math.round(Number(n)).toLocaleString()}`
const pct = (x) => `${Math.round(x * 100)}%`

const CATEGORY_LABEL = { booth: '攤位費', shipping: '運費', labor: '人力', other: '其他' }

onMounted(async () => {
  const { data } = await api.get('/events/years')
  years.value = data
})

// ── 活動報表 ──
const evYear = ref(null)
const evList = ref([])
const evId = ref(null)
const report = ref(null)
const artists = ref([])
const allocateBundles = ref(false) // 套組營收攤分口徑（Phase 1）

async function onEvYearChange(year) {
  evId.value = null
  report.value = null
  evList.value = []
  if (year == null) return
  const { data } = await api.get('/events', { params: { year } })
  evList.value = data
}

const daily = ref([])

async function loadReport() {
  if (!evId.value) return
  const [r, a, d] = await Promise.all([
    api.get(`/reports/events/${evId.value}`, {
      params: { allocate_bundles: allocateBundles.value },
    }),
    api.get('/artists'),
    api.get(`/reports/events/${evId.value}/daily`),
  ])
  report.value = r.data
  artists.value = a.data
  daily.value = d.data
}

// ── 圖表 option ──

// 逐日銷售：日期 × 通路 堆疊長條
const dailyOption = computed(() => {
  const dates = [...new Set(daily.value.map((p) => p.date))].sort()
  // 查表給 tooltip 用：date → channel → {qty, revenue}
  const lookup = {}
  for (const p of daily.value) {
    ;(lookup[p.date] ??= {})[p.channel] = p
  }
  const series = Object.entries(CHANNEL_META).map(([key, meta]) => ({
    name: meta.label,
    type: 'bar',
    stack: 'sales',
    barMaxWidth: 28,
    itemStyle: { color: meta.color, borderColor: '#fff', borderWidth: 2 },
    data: dates.map((dt) => lookup[dt]?.[key]?.qty ?? 0),
  }))
  return {
    grid: { left: 48, right: 16, top: 40, bottom: 28 },
    legend: { top: 0, textStyle: { color: '#606266' } },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const dt = params[0].axisValue
        const lines = params
          .filter((p) => p.value > 0)
          .map((p) => {
            const key = Object.keys(CHANNEL_META).find(
              (k) => CHANNEL_META[k].label === p.seriesName,
            )
            const rev = Number(lookup[dt]?.[key]?.revenue ?? 0)
            return `${p.marker} ${p.seriesName}：${p.value} 件｜NT$ ${Math.round(rev).toLocaleString()}`
          })
        return `<b>${dt}</b><br/>${lines.join('<br/>') || '無銷售'}`
      },
    },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: '#dcdfe6' } } },
    yAxis: {
      type: 'value', name: '件',
      splitLine: { lineStyle: { color: '#f2f3f5' } },
    },
    series,
  }
})

// 藝人營收占比圓餅（超過 8 位摺疊為「其他」，不生成第 9 個顏色）
const artistPieOption = computed(() => {
  const rows = (report.value?.by_artist ?? []).filter((r) => Number(r.revenue) > 0)
  let slices = rows.map((r) => ({ name: r.name, value: Math.round(Number(r.revenue)) }))
  if (slices.length > 8) {
    const rest = slices.slice(7).reduce((s, x) => s + x.value, 0)
    slices = [...slices.slice(0, 7), { name: '其他', value: rest }]
  }
  return {
    color: PALETTE,
    tooltip: {
      trigger: 'item',
      formatter: (p) =>
        `${p.marker} ${p.name}<br/>營收 NT$ ${p.value.toLocaleString()}（${p.percent}%）`,
    },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { color: '#606266', formatter: '{b}\n{d}%' },
      data: slices,
    }],
  }
})

const allocatedRowClass = ({ row }) => (row.allocated ? 'allocated-row' : '')

const artistName = (id) =>
  artists.value.find((a) => a.id === id)?.name ?? ''

// 開支輸入
const expForm = reactive({ category: 'booth', amount_twd: null, artist_id: null, notes: '' })

async function addExpense() {
  if (!expForm.amount_twd) {
    ElMessage.warning('請填金額')
    return
  }
  await api.post('/expenses', {
    event_id: evId.value,
    category: expForm.category,
    amount_twd: expForm.amount_twd,
    artist_id: expForm.artist_id || null,
    notes: expForm.notes || null,
  })
  ElMessage.success('開支已新增')
  expForm.amount_twd = null
  expForm.notes = ''
  await loadReport()
}

async function deleteExpense(e) {
  try {
    await ElMessageBox.confirm(
      `刪除這筆開支？${CATEGORY_LABEL[e.category]} ${nt(e.amount_twd)}`,
      '刪除開支',
      { confirmButtonText: '刪除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await api.delete(`/expenses/${e.id}`)
  ElMessage.success('已刪除')
  await loadReport()
}

// ── 彙總（藝人/品項）──
const sumYear = ref(null)
const artistRows = ref([])
const itemTypeRows = ref([])

async function loadSummaries() {
  const params = sumYear.value != null ? { year: sumYear.value } : {}
  const [a, t] = await Promise.all([
    api.get('/reports/artists', { params }),
    api.get('/reports/item-types', { params }),
  ])
  artistRows.value = a.data
  itemTypeRows.value = t.data
}
</script>

<template>
  <div class="page">
    <h2>報表</h2>
    <el-tabs v-model="activeTab" @tab-change="(t) => t !== 'event' && loadSummaries()">
      <!-- ── 活動報表 ── -->
      <el-tab-pane label="活動報表" name="event">
        <el-space wrap style="margin-bottom: 16px">
          <el-select
            v-model="evYear" placeholder="年份" clearable style="width: 120px"
            @change="onEvYearChange"
          >
            <el-option v-for="y in years" :key="y" :label="`${y} 年`" :value="y" />
          </el-select>
          <el-select
            v-model="evId" placeholder="選擇活動" :disabled="!evYear"
            style="width: 260px" @change="loadReport"
          >
            <el-option v-for="e in evList" :key="e.id" :label="e.name" :value="e.id" />
          </el-select>
          <el-switch
            v-model="allocateBundles"
            active-text="啟用套組營收攤分"
            :disabled="!evId"
            @change="loadReport"
          />
        </el-space>
        <el-alert
          v-if="allocateBundles && report"
          type="info" :closable="false" style="margin-bottom: 12px"
          title="攤分口徑：套組的營收與售出已按「內容物定價×件數」加權攤回各內容物（跟著內容物的藝人與品項走），套組自身歸零。活動總營收不變；內容物的銷售率可能超過 100%（售出含套組帶出的量）。"
        />

        <template v-if="report">
          <el-row :gutter="12" class="stats">
            <el-col :span="6"><el-statistic title="營收" :value="Number(report.revenue)" prefix="NT$" /></el-col>
            <el-col :span="6"><el-statistic title="銷貨成本" :value="Number(report.cogs)" prefix="NT$" /></el-col>
            <el-col :span="6"><el-statistic title="毛利" :value="Number(report.gross)" prefix="NT$" /></el-col>
            <el-col :span="6">
              <el-statistic title="銷售率" :value="Math.round(report.sell_through * 100)" suffix="%" />
            </el-col>
          </el-row>
          <el-row :gutter="12" class="stats" style="margin-top: 8px">
            <el-col :span="6">
              <el-statistic title="檔期開支" :value="Number(report.expenses_total)" prefix="NT$" />
            </el-col>
            <el-col :span="6">
              <el-statistic
                :title="`公關成本（${report.pr_qty} 件）`"
                :value="Number(report.pr_cost)" prefix="NT$"
              />
            </el-col>
            <el-col :span="12">
              <el-statistic title="淨利（毛利 − 開支 − 公關）" :value="Number(report.net)" prefix="NT$" />
            </el-col>
          </el-row>

          <el-row :gutter="16">
            <el-col :span="14">
              <el-card class="block">
                <template #header>逐日銷售（依通路）</template>
                <VChart
                  v-if="daily.length" :option="dailyOption"
                  autoresize style="height: 300px"
                />
                <el-empty v-else description="此活動尚無銷售紀錄" :image-size="60" />
              </el-card>
            </el-col>
            <el-col :span="10">
              <el-card class="block">
                <template #header>
                  藝人營收占比{{ report.allocate_bundles ? '（攤分口徑）' : '' }}
                </template>
                <VChart
                  v-if="artistPieOption.series[0].data.length"
                  :option="artistPieOption" autoresize style="height: 300px"
                />
                <el-empty v-else description="尚無營收" :image-size="60" />
              </el-card>
            </el-col>
          </el-row>

          <el-card class="block">
            <template #header>依藝人</template>
            <el-table :data="report.by_artist" size="small">
              <el-table-column prop="name" label="藝人" min-width="120" />
              <el-table-column prop="production" label="製作量" width="90" align="right" />
              <el-table-column prop="sold" label="售出" width="80" align="right" />
              <el-table-column label="營收" width="120" align="right">
                <template #default="{ row }">{{ nt(row.revenue) }}</template>
              </el-table-column>
              <el-table-column label="毛利" width="120" align="right">
                <template #default="{ row }">{{ nt(row.gross) }}</template>
              </el-table-column>
              <el-table-column label="銷售率" width="90" align="right">
                <template #default="{ row }">{{ pct(row.sell_through) }}</template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card class="block">
            <template #header>依品項</template>
            <el-table
              :data="report.by_item_type" size="small"
              :row-class-name="allocatedRowClass"
            >
              <el-table-column label="品項" min-width="120">
                <template #default="{ row }">
                  {{ row.name }}
                  <el-tag v-if="row.allocated" size="small" type="info">已攤分</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="production" label="製作量" width="90" align="right" />
              <el-table-column prop="sold" label="售出" width="80" align="right" />
              <el-table-column label="營收" width="120" align="right">
                <template #default="{ row }">{{ nt(row.revenue) }}</template>
              </el-table-column>
              <el-table-column label="毛利" width="120" align="right">
                <template #default="{ row }">{{ nt(row.gross) }}</template>
              </el-table-column>
              <el-table-column label="銷售率" width="90" align="right">
                <template #default="{ row }">{{ pct(row.sell_through) }}</template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card class="block">
            <template #header>檔期開支（算淨利用）</template>
            <el-space wrap style="margin-bottom: 12px">
              <el-select v-model="expForm.category" style="width: 110px">
                <el-option
                  v-for="(label, key) in CATEGORY_LABEL" :key="key"
                  :label="label" :value="key"
                />
              </el-select>
              <el-input-number
                v-model="expForm.amount_twd" :min="1" :controls="false"
                placeholder="金額 (NT$)" style="width: 120px"
              />
              <el-select
                v-model="expForm.artist_id" clearable placeholder="歸屬藝人（選填）"
                style="width: 160px"
              >
                <el-option v-for="a in artists" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
              <el-input v-model="expForm.notes" placeholder="備註（選填）" style="width: 180px" />
              <el-button type="primary" @click="addExpense">新增開支</el-button>
            </el-space>
            <el-table :data="report.expenses" size="small">
              <el-table-column label="類別" width="100">
                <template #default="{ row }">{{ CATEGORY_LABEL[row.category] }}</template>
              </el-table-column>
              <el-table-column label="金額" width="120" align="right">
                <template #default="{ row }">{{ nt(row.amount_twd) }}</template>
              </el-table-column>
              <el-table-column label="歸屬藝人" width="120">
                <template #default="{ row }">{{ artistName(row.artist_id) }}</template>
              </el-table-column>
              <el-table-column prop="notes" label="備註" min-width="140" />
              <el-table-column label="操作" width="70" align="center">
                <template #default="{ row }">
                  <el-button type="danger" link size="small" @click="deleteExpense(row)">
                    刪除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </template>
        <el-empty v-else description="選擇年份與活動來看報表" />
      </el-tab-pane>

      <!-- ── 藝人彙總 ── -->
      <el-tab-pane label="藝人彙總" name="artists">
        <el-space style="margin-bottom: 12px">
          <el-select
            v-model="sumYear" placeholder="全部年份" clearable style="width: 140px"
            @change="loadSummaries"
          >
            <el-option v-for="y in years" :key="y" :label="`${y} 年`" :value="y" />
          </el-select>
        </el-space>
        <el-table :data="artistRows" size="small">
          <el-table-column prop="name" label="藝人" min-width="120" />
          <el-table-column prop="event_count" label="場次" width="70" align="right" />
          <el-table-column prop="production" label="製作量" width="90" align="right" />
          <el-table-column prop="sold" label="售出" width="80" align="right" />
          <el-table-column label="營收" width="130" align="right">
            <template #default="{ row }">{{ nt(row.revenue) }}</template>
          </el-table-column>
          <el-table-column label="毛利" width="130" align="right">
            <template #default="{ row }">{{ nt(row.gross) }}</template>
          </el-table-column>
          <el-table-column label="銷售率" width="90" align="right">
            <template #default="{ row }">{{ pct(row.sell_through) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── 品項彙總 ── -->
      <el-tab-pane label="品項彙總" name="itemTypes">
        <el-space style="margin-bottom: 12px">
          <el-select
            v-model="sumYear" placeholder="全部年份" clearable style="width: 140px"
            @change="loadSummaries"
          >
            <el-option v-for="y in years" :key="y" :label="`${y} 年`" :value="y" />
          </el-select>
        </el-space>
        <el-table :data="itemTypeRows" size="small">
          <el-table-column prop="name" label="品項" min-width="120" />
          <el-table-column prop="event_count" label="場次" width="70" align="right" />
          <el-table-column prop="production" label="製作量" width="90" align="right" />
          <el-table-column prop="sold" label="售出" width="80" align="right" />
          <el-table-column label="營收" width="130" align="right">
            <template #default="{ row }">{{ nt(row.revenue) }}</template>
          </el-table-column>
          <el-table-column label="毛利" width="130" align="right">
            <template #default="{ row }">{{ nt(row.gross) }}</template>
          </el-table-column>
          <el-table-column label="銷售率" width="90" align="right">
            <template #default="{ row }">{{ pct(row.sell_through) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.stats {
  text-align: center;
}
.block {
  margin-top: 16px;
}
:deep(.allocated-row) {
  color: #c0c4cc; /* 已攤分歸零的套組列反灰 */
}
</style>
