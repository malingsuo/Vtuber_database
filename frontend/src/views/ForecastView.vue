<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api.js'

const artists = ref([])
const itemTypes = ref([])

onMounted(async () => {
  const [a, t] = await Promise.all([api.get('/artists'), api.get('/item-types')])
  artists.value = a.data
  itemTypes.value = t.data
})

const form = reactive({
  artist_id: null,
  item_type_id: null,
  price: null,
  cost: null,
  salvage: 0,
})

const result = ref(null)
const loading = ref(false)

async function run() {
  if (!form.artist_id || !form.item_type_id || !form.price) {
    ElMessage.warning('藝人、品項、預計售價為必填')
    return
  }
  loading.value = true
  try {
    const { data } = await api.get('/forecast', {
      params: {
        artist_id: form.artist_id,
        item_type_id: form.item_type_id,
        price: form.price,
        cost: form.cost ?? undefined,
        salvage: form.salvage || 0,
      },
    })
    result.value = data
  } catch {
    result.value = null
  } finally {
    loading.value = false
  }
}

const nt = (n) => `NT$ ${Math.round(Number(n)).toLocaleString()}`
</script>

<template>
  <div class="page">
    <h2>訂量與售價預測</h2>
    <p class="hint">
      選定「藝人 × 品項」後，系統以歷史銷售估計需求分布，再用報童模型算出期望利潤最高的訂量。
      資料越多越準；樣本不足時會自動退階到品項平均並註明依據。
    </p>

    <el-card>
      <el-space wrap>
        <el-select v-model="form.artist_id" placeholder="藝人" style="width: 150px">
          <el-option v-for="a in artists" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
        <el-select v-model="form.item_type_id" placeholder="品項" style="width: 150px">
          <el-option v-for="t in itemTypes" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
        <el-input-number
          v-model="form.price" :min="1" :controls="false"
          placeholder="預計售價 (NT$)" style="width: 140px"
        />
        <el-input-number
          v-model="form.cost" :min="0" :controls="false"
          placeholder="單位成本 (NT$，選填)" style="width: 170px"
        />
        <el-input-number
          v-model="form.salvage" :min="0" :controls="false"
          placeholder="殘值" style="width: 100px"
        />
        <el-button type="primary" :loading="loading" @click="run">計算</el-button>
      </el-space>
      <div class="hint" style="margin-top: 6px">
        殘值＝賣不掉時一件還值多少（預設 0；若會轉公關或次回販售可填估值）。
        成本可不填——不填就只看下方的報價點比較。
      </div>
    </el-card>

    <template v-if="result">
      <el-alert
        v-if="result.warning" :title="result.warning"
        type="error" :closable="false" style="margin-top: 16px"
      />

      <el-row :gutter="12" style="margin-top: 16px">
        <el-col :span="8">
          <el-card>
            <template #header>需求估計</template>
            <div class="big">{{ result.demand.mu }} ± {{ result.demand.sigma }}</div>
            <div class="hint">
              {{ result.demand.basis }}<br />
              （藝人樣本 {{ result.demand.n_artist }} 筆、品項樣本 {{ result.demand.n_type }} 筆）
            </div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card>
            <template #header>建議訂量（報童模型）</template>
            <template v-if="result.recommended_qty != null">
              <div class="big">{{ result.recommended_qty }} 件</div>
              <div class="hint">
                關鍵比率 {{ (result.critical_ratio * 100).toFixed(0) }}%｜
                此訂量的期望利潤 {{ nt(result.expected_profit) }}
              </div>
            </template>
            <div v-else class="hint">填入單位成本才能計算</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card>
            <template #header>建議售價</template>
            <template v-if="result.price">
              <div class="big">{{ nt(result.price.suggested) }}</div>
              <div class="hint">
                {{ result.price.basis }}<br />
                <template v-if="result.price.hist_median != null">
                  歷史價格帶 {{ nt(result.price.hist_low) }} ~
                  <b>{{ nt(result.price.hist_median) }}</b> ~
                  {{ nt(result.price.hist_high) }}
                </template>
              </div>
            </template>
            <div v-else class="hint">無歷史價格且未填成本</div>
          </el-card>
        </el-col>
      </el-row>

      <el-card v-if="result.quote_evals.length" style="margin-top: 16px">
        <template #header>
          報價點比較——在每個實際報價下，訂那個量的期望利潤（★ 為最佳）
        </template>
        <el-table :data="result.quote_evals" size="small">
          <el-table-column label="訂購量" width="100" align="right">
            <template #default="{ row }">
              <b v-if="row.is_best">★ {{ row.quantity }}</b>
              <span v-else>{{ row.quantity }}</span>
            </template>
          </el-table-column>
          <el-table-column label="單價" width="100" align="right">
            <template #default="{ row }">{{ nt(row.unit_price_twd) }}</template>
          </el-table-column>
          <el-table-column prop="vendor_name" label="廠商" width="140" />
          <el-table-column label="期望售出" width="100" align="right">
            <template #default="{ row }">{{ Math.round(row.expected_sold) }}</template>
          </el-table-column>
          <el-table-column label="期望利潤" width="130" align="right">
            <template #default="{ row }">
              <b v-if="row.is_best" style="color: #67c23a">{{ nt(row.expected_profit) }}</b>
              <span v-else>{{ nt(row.expected_profit) }}</span>
            </template>
          </el-table-column>
          <el-table-column />
        </el-table>
        <div class="hint" style="margin-top: 8px">
          單價低不代表利潤高——訂太多的滯銷損失會吃掉單價優勢，這正是這張表要回答的問題
        </div>
      </el-card>

      <el-card style="margin-top: 16px">
        <template #header>這位藝人 × 這個品項的歷史觀測</template>
        <el-table :data="result.demand.observations" size="small">
          <el-table-column prop="event_date" label="日期" width="110" />
          <el-table-column prop="event_name" label="活動" min-width="180" />
          <el-table-column prop="production" label="製作量" width="90" align="right" />
          <el-table-column prop="sold" label="售出" width="80" align="right" />
          <el-table-column label="完售" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.sold_out" size="small" type="danger">完售</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="需求估計" width="100" align="right">
            <template #default="{ row }">{{ row.demand_est }}</template>
          </el-table-column>
          <el-table-column />
        </el-table>
        <div class="hint" style="margin-top: 8px">
          完售代表「需求 ≥ 售出量」，估計時已按 1.2 倍上修——這是當初把「當天是否完售」記進資料的原因
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.7;
}
.big {
  font-size: 26px;
  font-weight: bold;
  margin-bottom: 6px;
}
</style>
