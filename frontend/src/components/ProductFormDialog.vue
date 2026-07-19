<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api.js'

const props = defineProps({
  modelValue: Boolean,
  eventId: Number,
  artist: Object, // { id, name }
  itemTypes: Array,
  vendors: Array,
  // 該藝人此活動已有的規格（做套組內容物用）：[{ id, label }]
  artistVariants: Array,
})
const emit = defineEmits(['update:modelValue', 'saved'])

// 欄位以空值起始，讓格子內的提示文字（placeholder）看得到
const emptyVariant = () => ({
  variant_name: '',
  production_qty: null,
  cost_amount: null,
  cost_currency: 'TWD',
  exchange_rate: null,
})

const form = reactive({
  item_type_id: null,
  name: '',
  price_twd: 0,
  vendor_id: null,
  contact_person: '',
  notes: '',
  is_bundle: false,
  bundle_qty: null,
  variants: [emptyVariant()],
  bundle_selection: [],
})

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      Object.assign(form, {
        item_type_id: null,
        name: '',
        price_twd: 0,
        vendor_id: null,
        contact_person: '',
        notes: '',
        is_bundle: false,
        bundle_qty: null,
        variants: [emptyVariant()],
        bundle_selection: props.artistVariants.map((v) => ({
          variant_id: v.id,
          label: v.label,
          checked: false,
          quantity: 1,
        })),
      })
    }
  },
)

// 選品項類別時自動帶出商品名（可再改）
function onItemTypeChange(id) {
  const it = props.itemTypes.find((t) => t.id === id)
  if (it && !form.name) form.name = `${props.artist.name} ${it.name}`
}

function copyLastVariant() {
  const last = form.variants[form.variants.length - 1]
  form.variants.push({ ...last })
}

const rate = (v) => v.exchange_rate ?? (v.cost_currency === 'TWD' ? 1 : 0)
const twd = (v) => ((v.cost_amount ?? 0) * rate(v)).toFixed(2)

const canSubmit = computed(() => {
  if (!form.name) return false
  if (form.is_bundle) return form.bundle_selection.some((b) => b.checked)
  return form.item_type_id != null
})

const submitting = ref(false)

async function submit() {
  submitting.value = true
  try {
    await api.post('/products', {
      event_id: props.eventId,
      artist_id: props.artist.id,
      item_type_id: form.is_bundle ? null : form.item_type_id,
      name: form.name,
      price_twd: form.price_twd,
      vendor_id: form.vendor_id || null,
      contact_person: form.contact_person || null,
      notes: form.notes || null,
      is_bundle: form.is_bundle,
      variants: form.is_bundle
        ? [{
            variant_name: '單一規格',
            production_qty: form.bundle_qty ?? 0,
            cost_amount: 0,
            cost_currency: 'TWD',
            exchange_rate: 1,
          }]
        : form.variants.map((v) => ({
            variant_name: v.variant_name?.trim() || '單一規格',
            production_qty: v.production_qty ?? 0,
            cost_amount: v.cost_amount ?? 0,
            cost_currency: v.cost_currency,
            exchange_rate: rate(v) || 1,
          })),
      bundle_items: form.is_bundle
        ? form.bundle_selection
            .filter((b) => b.checked)
            .map((b) => ({ variant_id: b.variant_id, quantity: b.quantity }))
        : [],
    })
    ElMessage.success('商品已建立')
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
    :title="`新增商品 — ${artist?.name ?? ''}`"
    width="760px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form label-width="100px">
      <el-form-item :label="form.is_bundle ? '商品型態' : '品項類別'" required>
        <!-- 套組是多種品項的組合，不屬於單一品項類別，所以不選 -->
        <el-select
          v-if="!form.is_bundle"
          v-model="form.item_type_id"
          placeholder="選擇品項"
          style="width: 200px"
          @change="onItemTypeChange"
        >
          <el-option v-for="t in itemTypes" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
        <el-tag v-else type="success">套組（內容物可跨品項，不必選類別）</el-tag>
        <el-switch
          v-model="form.is_bundle"
          active-text="這是套組"
          style="margin-left: 24px"
        />
      </el-form-item>

      <el-form-item label="商品名稱" required>
        <el-input
          v-model="form.name"
          :placeholder="form.is_bundle ? '例：小貓全套組' : '選了品項會自動帶出，可修改'"
        />
      </el-form-item>

      <el-form-item label="售價 (NT$)" required>
        <el-input-number v-model="form.price_twd" :min="0" :step="10" />
        <span class="hint">贈品填 0</span>
      </el-form-item>

      <template v-if="!form.is_bundle">
        <el-form-item label="規格">
          <div style="width: 100%">
            <div v-for="(v, i) in form.variants" :key="i" class="variant-row">
              <el-input
                v-model="v.variant_name"
                placeholder="規格名（單一款可不填）"
                style="width: 170px"
              />
              <el-input-number
                v-model="v.production_qty" :min="0"
                placeholder="製作量" style="width: 120px"
              />
              <el-input-number
                v-model="v.cost_amount" :min="0" :precision="2"
                placeholder="單位成本(原幣)" style="width: 150px"
              />
              <el-select v-model="v.cost_currency" style="width: 90px">
                <el-option label="TWD" value="TWD" />
                <el-option label="CNY" value="CNY" />
                <el-option label="JPY" value="JPY" />
              </el-select>
              <el-input-number
                v-model="v.exchange_rate" :min="0.0001" :precision="4" :step="0.1"
                placeholder="匯率" style="width: 110px"
                :disabled="v.cost_currency === 'TWD'"
              />
              <span class="hint">= NT${{ twd(v) }}</span>
              <el-button
                v-if="form.variants.length > 1"
                type="danger" link @click="form.variants.splice(i, 1)"
              >移除</el-button>
            </div>
            <el-space>
              <el-button size="small" @click="form.variants.push(emptyVariant())">
                ＋ 加一個空白規格
              </el-button>
              <el-button size="small" @click="copyLastVariant">
                ⧉ 複製上一個規格
              </el-button>
            </el-space>
          </div>
        </el-form-item>
      </template>

      <template v-else>
        <el-form-item label="套組份數">
          <el-input-number
            v-model="form.bundle_qty" :min="0" placeholder="準備賣幾套"
          />
        </el-form-item>
        <el-form-item label="內容物">
          <div v-if="form.bundle_selection.length" style="width: 100%">
            <div v-for="b in form.bundle_selection" :key="b.variant_id" class="variant-row">
              <el-checkbox v-model="b.checked" :label="b.label" style="width: 320px" />
              <el-input-number v-model="b.quantity" :min="1" :disabled="!b.checked" size="small" />
              <span class="hint">件/套</span>
            </div>
            <div class="hint" style="margin-left: 0">
              同一件單品可以被多個套組收錄，不衝突
            </div>
          </div>
          <div v-else class="hint" style="margin-left: 0">
            這位藝人在此活動還沒有單品，先建立單品才能組成套組
          </div>
        </el-form-item>
      </template>

      <el-form-item label="廠商">
        <el-select v-model="form.vendor_id" clearable placeholder="選填" style="width: 200px">
          <el-option v-for="v in vendors" :key="v.id" :label="v.name" :value="v.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="製作聯絡人">
        <el-input v-model="form.contact_person" placeholder="選填，公司內部備忘" style="width: 200px" />
      </el-form-item>

      <el-form-item label="備註">
        <el-input v-model="form.notes" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!canSubmit" :loading="submitting" @click="submit">
        建立商品
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.variant-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.hint {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
}
</style>
