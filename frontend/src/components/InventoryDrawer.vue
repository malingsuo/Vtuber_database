<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api.js'

const props = defineProps({
  modelValue: Boolean,
  variant: Object, // { id, label, price }
})
const emit = defineEmits(['update:modelValue', 'changed'])

const today = () => new Date().toISOString().slice(0, 10)

const stock = ref(null)
const movements = ref([])
const preorders = ref([])
const shippedPreorders = ref([])
const showShipped = ref(false)

const TYPE_LABEL = {
  inbound: '入庫',
  sale: '銷售',
  sale_return: '銷售退回',
  pr_gift: '轉公關',
  scrap: '報廢',
  adjustment: '盤點調整',
}
const CHANNEL_LABEL = { preorder: '預購', onsite: '現場', online: '通販' }

async function load() {
  if (!props.variant) return
  const id = props.variant.id
  const [s, m, p, sp] = await Promise.all([
    api.get(`/inventory/variants/${id}/stock`),
    api.get(`/inventory/variants/${id}/movements`),
    api.get('/preorders', { params: { variant_id: id, status: 'reserved' } }),
    api.get('/preorders', { params: { variant_id: id, status: 'shipped' } }),
  ])
  stock.value = s.data
  movements.value = m.data
  preorders.value = p.data
  shippedPreorders.value = sp.data
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      Object.assign(moveForm, {
        movement_type: 'inbound', quantity: null,
        movement_date: today(), recipient: '', purpose: '', notes: '',
        channel: null, sale_price_twd: null,
      })
      Object.assign(preForm, { quantity: null, created_date: today() })
      opDate.value = today()
      showShipped.value = false
      load()
    }
  },
)

// ── 新增異動 ──
const moveForm = reactive({
  movement_type: 'inbound',
  quantity: null,
  movement_date: today(),
  recipient: '',
  purpose: '',
  notes: '',
  channel: null, // 銷售退回專用：從哪個通路的營收扣回
  sale_price_twd: null, // 銷售退回專用：退款單價，不填用定價
})
const savingMove = ref(false)

async function submitMovement() {
  if (!moveForm.quantity) {
    ElMessage.warning('請填數量')
    return
  }
  const isReturn = moveForm.movement_type === 'sale_return'
  if (isReturn && !moveForm.channel) {
    ElMessage.warning('請選擇退回的通路')
    return
  }
  // 這筆異動會讓可售變負（吃到圈存的貨）時，先提醒再寫入
  const SIGNS = { inbound: 1, sale_return: 1, pr_gift: -1, scrap: -1 }
  const delta =
    moveForm.movement_type === 'adjustment'
      ? moveForm.quantity
      : SIGNS[moveForm.movement_type] * moveForm.quantity
  if (delta < 0 && stock.value.available + delta < 0) {
    try {
      await ElMessageBox.confirm(
        `目前還有 ${stock.value.reserved} 件圈存中的預購未出貨。` +
          `這個操作後可售庫存會變成 ${stock.value.available + delta}，` +
          `到時可能不夠出貨給預購客人。確定要繼續嗎？`,
        '注意：即將動用圈存的貨',
        { confirmButtonText: '仍要寫入', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }
  // 累計入庫超過製作量：要求填寫原因才放行（後端也會擋）
  const excess =
    moveForm.movement_type === 'inbound'
      ? stock.value.inbound_qty + moveForm.quantity - stock.value.production_qty
      : 0
  if (excess > 0 && !moveForm.notes.trim()) {
    try {
      const { value } = await ElMessageBox.prompt(
        `已入庫 ${stock.value.inbound_qty}／製作量 ${stock.value.production_qty}，` +
          `這次再入 ${moveForm.quantity} 件，累計將超量 ${excess} 件。請填寫超量原因：`,
        '入庫超過製作量',
        {
          confirmButtonText: '寫入',
          cancelButtonText: '取消',
          inputValidator: (v) => !!v?.trim() || '必須填寫原因',
        },
      )
      moveForm.notes = `超量 ${excess} 件｜原因：${value.trim()}`
    } catch {
      return
    }
  }
  savingMove.value = true
  try {
    await api.post('/inventory/movements', {
      variant_id: props.variant.id,
      movement_type: moveForm.movement_type,
      quantity: moveForm.quantity,
      movement_date: moveForm.movement_date,
      channel: isReturn ? moveForm.channel : null,
      sale_price_twd: isReturn ? moveForm.sale_price_twd : null,
      recipient: moveForm.recipient || null,
      purpose: moveForm.purpose || null,
      notes: moveForm.notes || null,
    })
    ElMessage.success('異動已寫入')
    moveForm.quantity = null
    moveForm.notes = ''
    moveForm.sale_price_twd = null
    await load()
    emit('changed')
  } finally {
    savingMove.value = false
  }
}

// ── 預購 ──
const preForm = reactive({ quantity: null, created_date: today() })
const opDate = ref(today()) // 出貨／取消用的日期

async function createPreorder() {
  if (!preForm.quantity) {
    ElMessage.warning('請填預購數量')
    return
  }
  await api.post('/preorders', {
    variant_id: props.variant.id,
    quantity: preForm.quantity,
    created_date: preForm.created_date,
  })
  ElMessage.success('預購已圈存')
  preForm.quantity = null
  await load()
  emit('changed')
}

async function ship(id) {
  await api.post(`/preorders/${id}/ship`, { ship_date: opDate.value })
  ElMessage.success('已出貨並扣庫存')
  await load()
  emit('changed')
}

async function cancelPre(id) {
  await api.post(`/preorders/${id}/cancel`, { cancel_date: opDate.value })
  ElMessage.success('已取消，圈存釋放')
  await load()
  emit('changed')
}

async function shipAll() {
  const { data } = await api.post('/preorders/ship-all', {
    variant_id: props.variant.id,
    ship_date: opDate.value,
  })
  ElMessage.success(`已出貨 ${data.shipped} 筆、共 ${data.total_qty} 件`)
  await load()
  emit('changed')
}

// 出貨退回：帳（出貨異動被沖銷）與約（預購改回圈存）在同一交易內還原
async function unship(p) {
  try {
    await ElMessageBox.confirm(
      `預購 #${p.id}（${p.quantity} 件，${p.status_changed_date} 出貨）要退回圈存嗎？` +
        '原出貨紀錄會保留並標為已沖銷，另新增一筆沖銷紀錄把庫存加回來。',
      '出貨退回',
      { confirmButtonText: '退回圈存', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await api.post(`/preorders/${p.id}/unship`)
  ElMessage.success('已退回圈存，庫存已加回')
  await load()
  emit('changed')
}

// 流水帳只追加：更正輸入錯誤用「沖銷」（新增反向紀錄、原紀錄保留），
// 僅限管理者且需重新輸入密碼確認
const reverseDlg = reactive({
  visible: false,
  movement: null,
  reason: '',
  password: '',
  saving: false,
})

function movementDesc(m) {
  return `#${m.id}｜${m.movement_date}｜${TYPE_LABEL[m.movement_type]}｜` +
    `${m.quantity_delta > 0 ? '+' : ''}${m.quantity_delta}`
}

function openReverse(m) {
  Object.assign(reverseDlg, { visible: true, movement: m, reason: '', password: '' })
}

async function submitReverse() {
  if (!reverseDlg.reason.trim()) {
    ElMessage.warning('請填寫沖銷原因')
    return
  }
  if (!reverseDlg.password) {
    ElMessage.warning('請輸入管理者密碼')
    return
  }
  reverseDlg.saving = true
  try {
    await api.post(
      `/inventory/movements/${reverseDlg.movement.id}/reverse`,
      { reason: reverseDlg.reason.trim() },
      { headers: { 'X-Confirm-Password': reverseDlg.password } },
    )
    ElMessage.success('已沖銷，原紀錄保留')
    reverseDlg.visible = false
    await load()
    emit('changed')
  } finally {
    reverseDlg.saving = false
  }
}

// created_at 是資料庫以 UTC 記錄的時間（不帶時區），轉成本地時間顯示
function fmtTime(t) {
  return new Date(`${t}Z`).toLocaleString('zh-TW', { hour12: false })
}

function movementText(m) {
  const parts = []
  if (m.channel) parts.push(CHANNEL_LABEL[m.channel])
  if (m.sale_price_twd != null) parts.push(`單價 NT$${Number(m.sale_price_twd)}`)
  if (m.sold_out_today) parts.push('當日完售')
  if (m.recipient) parts.push(`對象:${m.recipient}`)
  if (m.purpose) parts.push(m.purpose)
  if (m.notes) parts.push(m.notes)
  return parts.join('｜')
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="`庫存管理 — ${variant?.label ?? ''}`"
    size="560px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-if="stock">
      <el-row :gutter="12" class="stats">
        <el-col :span="8"><el-statistic title="實體庫存" :value="stock.physical" /></el-col>
        <el-col :span="8"><el-statistic title="圈存（預購未出貨）" :value="stock.reserved" /></el-col>
        <el-col :span="8"><el-statistic title="可售" :value="stock.available" /></el-col>
      </el-row>
      <div class="hint" style="text-align: center">
        製作量 {{ stock.production_qty }}｜累計入庫 {{ stock.inbound_qty }}
        <span
          v-if="stock.inbound_qty > stock.production_qty"
          style="color: #e6a23c; font-weight: bold"
        >
          ｜超額 {{ stock.inbound_qty - stock.production_qty }} 件
        </span>
      </div>

      <el-divider content-position="left">新增庫存異動</el-divider>
      <el-space wrap>
        <el-select v-model="moveForm.movement_type" style="width: 130px">
          <el-option label="入庫" value="inbound" />
          <el-option label="銷售退回" value="sale_return" />
          <el-option label="轉公關" value="pr_gift" />
          <el-option label="報廢" value="scrap" />
          <el-option label="盤點調整" value="adjustment" />
        </el-select>
        <el-input-number
          v-model="moveForm.quantity" :controls="false"
          :placeholder="moveForm.movement_type === 'adjustment' ? '±數量' : '數量'"
          style="width: 100px"
        />
        <el-date-picker
          v-model="moveForm.movement_date" type="date" value-format="YYYY-MM-DD"
          style="width: 140px"
        />
      </el-space>
      <template v-if="moveForm.movement_type === 'sale_return'">
        <el-space wrap style="margin-top: 8px">
          <el-select v-model="moveForm.channel" placeholder="退回的通路（必填）" style="width: 160px">
            <el-option label="預購" value="preorder" />
            <el-option label="現場" value="onsite" />
            <el-option label="通販" value="online" />
          </el-select>
          <el-input-number
            v-model="moveForm.sale_price_twd" :min="0" :controls="false"
            :placeholder="`退款單價（預設定價 ${variant?.price ?? ''}）`" style="width: 200px"
          />
        </el-space>
        <div class="hint">
          銷售退回＝客人真的退貨，會從所選通路的營收扣回「數量 × 退款單價」；
          折扣賣出的請填實際退款單價。只是輸入錯誤請改用異動歷史的「沖銷」
        </div>
      </template>
      <el-space v-if="moveForm.movement_type === 'pr_gift'" wrap style="margin-top: 8px">
        <el-input v-model="moveForm.recipient" placeholder="對象（必填）" style="width: 160px" />
        <el-input v-model="moveForm.purpose" placeholder="用途" style="width: 160px" />
      </el-space>
      <div style="margin-top: 8px">
        <el-input v-model="moveForm.notes" placeholder="備註（選填）" style="width: 300px" />
        <el-button
          type="primary" :loading="savingMove" style="margin-left: 8px"
          @click="submitMovement"
        >寫入</el-button>
      </div>
      <div v-if="moveForm.movement_type === 'adjustment'" class="hint">
        盤點調整：盤盈填正數、盤虧填負數（例：-3）
      </div>
      <div class="hint">
        銷售不在這裡輸入——現場/通販請用活動頁的「逐日銷售輸入」，預購出貨在下方預購區
      </div>

      <el-divider content-position="left">預購圈存</el-divider>
      <el-space wrap>
        <el-input-number
          v-model="preForm.quantity" :min="1" :controls="false"
          placeholder="預購數量" style="width: 110px"
        />
        <el-date-picker
          v-model="preForm.created_date" type="date" value-format="YYYY-MM-DD"
          style="width: 140px"
        />
        <el-button @click="createPreorder">新增預購</el-button>
      </el-space>
      <div v-if="preorders.length" style="margin-top: 8px">
        <el-space style="margin-bottom: 8px">
          <span class="hint">出貨/取消日期：</span>
          <el-date-picker
            v-model="opDate" type="date" value-format="YYYY-MM-DD" style="width: 140px"
          />
          <el-button size="small" type="primary" @click="shipAll">全部出貨</el-button>
        </el-space>
        <el-table :data="preorders" size="small">
          <el-table-column prop="created_date" label="成立日" width="110" />
          <el-table-column prop="quantity" label="數量" width="70" align="right" />
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="ship(row.id)">出貨</el-button>
              <el-button size="small" type="danger" link @click="cancelPre(row.id)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else class="hint" style="margin-top: 8px">目前沒有圈存中的預購</div>
      <div v-if="shippedPreorders.length" style="margin-top: 8px">
        <el-button link size="small" @click="showShipped = !showShipped">
          {{ showShipped ? '收合' : '展開' }}已出貨的預購（{{ shippedPreorders.length }} 筆）
        </el-button>
        <el-table v-if="showShipped" :data="shippedPreorders" size="small" max-height="200">
          <el-table-column prop="id" label="#" width="60" />
          <el-table-column prop="created_date" label="成立日" width="100" />
          <el-table-column prop="status_changed_date" label="出貨日" width="100" />
          <el-table-column prop="quantity" label="數量" width="60" align="right" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button size="small" type="warning" link @click="unship(row)">
                出貨退回
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-divider content-position="left">異動歷史（新到舊）</el-divider>
      <el-table :data="movements" size="small" max-height="320">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column prop="movement_date" label="日期" width="100" />
        <el-table-column label="類型" width="80">
          <template #default="{ row }">{{ TYPE_LABEL[row.movement_type] }}</template>
        </el-table-column>
        <el-table-column label="數量" width="60" align="right">
          <template #default="{ row }">
            <span
              :class="{ voided: row.reversed_by_id }"
              :style="{ color: row.quantity_delta < 0 ? '#f56c6c' : '#67c23a' }"
            >
              {{ row.quantity_delta > 0 ? '+' : '' }}{{ row.quantity_delta }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="明細" min-width="160">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.reverses_movement_id"
              :content="`沖銷於 ${fmtTime(row.created_at)}`"
              placement="top"
            >
              <el-tag size="small" type="warning" class="mark">
                沖銷 #{{ row.reverses_movement_id }}
              </el-tag>
            </el-tooltip>
            <el-tooltip
              v-else-if="row.reversed_by_id"
              :content="`由 #${row.reversed_by_id} 沖銷`"
              placement="top"
            >
              <el-tag size="small" type="info" class="mark">已沖銷</el-tag>
            </el-tooltip>
            <span :class="{ voided: row.reversed_by_id }">{{ movementText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.reverses_movement_id && !row.reversed_by_id"
              type="danger" link size="small" @click="openReverse(row)"
            >
              沖銷
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <el-dialog
      v-model="reverseDlg.visible" title="沖銷異動（僅限管理者）" width="440px"
      append-to-body
    >
      <template v-if="reverseDlg.movement">
        <div style="font-weight: bold">{{ movementDesc(reverseDlg.movement) }}</div>
        <div class="hint">
          會新增一筆數量相反的沖銷紀錄，日期沿用原紀錄（{{ reverseDlg.movement.movement_date }}），
          原紀錄保留並標為「已沖銷」。真的退貨請改記「銷售退回」。
        </div>
        <el-alert
          v-if="reverseDlg.movement.channel === 'preorder'"
          type="warning" :closable="false" show-icon style="margin-top: 8px"
          title="預購出貨產生的銷售不能在這裡沖銷，請改用上方預購區「已出貨的預購」的「出貨退回」"
        />
        <el-form label-position="top" style="margin-top: 12px">
          <el-form-item label="沖銷原因" required>
            <el-input
              v-model="reverseDlg.reason" type="textarea" :rows="2"
              placeholder="例：數量輸入錯誤，應為 30"
            />
          </el-form-item>
          <el-form-item label="管理者密碼" required>
            <el-input
              v-model="reverseDlg.password" type="password" show-password
              @keyup.enter="submitReverse"
            />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="reverseDlg.visible = false">取消</el-button>
        <el-button type="danger" :loading="reverseDlg.saving" @click="submitReverse">
          沖銷
        </el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<style scoped>
.stats {
  text-align: center;
}
.hint {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}
.voided {
  text-decoration: line-through;
  opacity: 0.55;
}
.mark {
  margin-right: 4px;
}
</style>
