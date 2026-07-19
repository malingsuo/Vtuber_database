<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api.js'
import ProductFormDialog from '../components/ProductFormDialog.vue'

const route = useRoute()
const eventId = Number(route.params.id)

const overview = ref(null)
const allArtists = ref([])
const itemTypes = ref([])
const vendors = ref([])
const loading = ref(true)

const TYPE_LABEL = { onsite: '場販', online: '通販', mixed: '混合' }

async function load() {
  loading.value = true
  try {
    const [ov, ar, it, ve] = await Promise.all([
      api.get(`/events/${eventId}/overview`),
      api.get('/artists'),
      api.get('/item-types'),
      api.get('/vendors'),
    ])
    overview.value = ov.data
    allArtists.value = ar.data
    itemTypes.value = it.data
    vendors.value = ve.data
  } finally {
    loading.value = false
  }
}
onMounted(load)

// 把「商品 × 規格」攤平成表格列
function rows(block) {
  return block.products.flatMap((p) =>
    p.variants.map((v) => ({
      product: p.name,
      is_bundle: p.is_bundle,
      variant: v.variant_name,
      price: Number(p.price_twd),
      cost: Number(v.cost_twd),
      production: v.production_qty,
      sold: v.sold_qty,
      stock: v.stock_qty,
      revenue: Number(v.revenue_twd),
    })),
  )
}

function blockSummary(block) {
  const r = rows(block)
  const production = r.reduce((s, x) => s + x.production, 0)
  const sold = r.reduce((s, x) => s + x.sold, 0)
  const revenue = r.reduce((s, x) => s + x.revenue, 0)
  return {
    revenue,
    sellThrough: production ? Math.round((sold / production) * 100) : 0,
  }
}

// 新增商品對話框
const dialogOpen = ref(false)
const dialogArtist = ref(null)
const newArtistId = ref(null)

const artistsNotInEvent = computed(() => {
  const inEvent = new Set((overview.value?.artists ?? []).map((b) => b.artist.id))
  return allArtists.value.filter((a) => !inEvent.has(a.id))
})

const dialogArtistVariants = computed(() => {
  const block = (overview.value?.artists ?? []).find(
    (b) => b.artist.id === dialogArtist.value?.id,
  )
  if (!block) return []
  return block.products
    .filter((p) => !p.is_bundle)
    .flatMap((p) =>
      p.variants.map((v) => ({ id: v.id, label: `${p.name}（${v.variant_name}）` })),
    )
})

function openDialog(artist) {
  dialogArtist.value = artist
  dialogOpen.value = true
}

function addForNewArtist() {
  const artist = allArtists.value.find((a) => a.id === newArtistId.value)
  if (artist) openDialog(artist)
  newArtistId.value = null
}

const nt = (n) => `NT$ ${Math.round(n).toLocaleString()}`
</script>

<template>
  <div class="page" v-loading="loading">
    <template v-if="overview">
      <el-page-header content="" @back="$router.push('/')">
        <template #title>回查詢</template>
      </el-page-header>

      <h2 style="margin-bottom: 4px">{{ overview.event.name }}</h2>
      <p class="meta">
        {{ overview.event.start_date }} ～ {{ overview.event.end_date }}
        <el-tag size="small">{{ TYPE_LABEL[overview.event.event_type] }}</el-tag>
        <template v-if="overview.event.preorder_start">
          <el-tag size="small" type="warning">
            預購 {{ overview.event.preorder_start }} ～ {{ overview.event.preorder_end }}
          </el-tag>
        </template>
      </p>

      <el-card v-for="block in overview.artists" :key="block.artist.id" class="artist-card">
        <template #header>
          <div class="card-header">
            <span class="artist-name">
              {{ block.artist.name }}
              <el-tag v-if="block.artist.status === 'graduated'" size="small" type="info">
                畢業
              </el-tag>
            </span>
            <span class="summary">
              營收 {{ nt(blockSummary(block).revenue) }}｜
              銷售率 {{ blockSummary(block).sellThrough }}%
              <el-button
                type="primary" size="small" style="margin-left: 12px"
                @click="openDialog(block.artist)"
              >新增商品</el-button>
            </span>
          </div>
        </template>

        <el-table :data="rows(block)" size="small">
          <el-table-column label="商品" min-width="180">
            <template #default="{ row }">
              {{ row.product }}
              <el-tag v-if="row.is_bundle" size="small" type="success">套組</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="variant" label="規格" width="90" />
          <el-table-column label="售價" width="90" align="right">
            <template #default="{ row }">{{ row.price.toLocaleString() }}</template>
          </el-table-column>
          <el-table-column label="成本" width="90" align="right">
            <template #default="{ row }">{{ row.cost.toLocaleString() }}</template>
          </el-table-column>
          <el-table-column prop="production" label="製作量" width="90" align="right" />
          <el-table-column prop="sold" label="售出" width="80" align="right" />
          <el-table-column label="庫存" width="80" align="right">
            <template #default="{ row }">
              <span :class="{ soldout: row.stock === 0 }">{{ row.stock }}</span>
            </template>
          </el-table-column>
          <el-table-column label="營收" width="110" align="right">
            <template #default="{ row }">{{ row.revenue.toLocaleString() }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card class="artist-card add-block">
        <el-space>
          <span>為其他藝人新增商品：</span>
          <el-select
            v-model="newArtistId" placeholder="選擇藝人" style="width: 180px"
            :disabled="!artistsNotInEvent.length"
          >
            <el-option
              v-for="a in artistsNotInEvent" :key="a.id" :label="a.name" :value="a.id"
            />
          </el-select>
          <el-button :disabled="!newArtistId" @click="addForNewArtist">新增</el-button>
        </el-space>
      </el-card>

      <ProductFormDialog
        v-model="dialogOpen"
        :event-id="eventId"
        :artist="dialogArtist"
        :item-types="itemTypes"
        :vendors="vendors"
        :artist-variants="dialogArtistVariants"
        @saved="load"
      />
    </template>
  </div>
</template>

<style scoped>
.meta {
  color: #909399;
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 0;
}
.artist-card {
  margin-top: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.artist-name {
  font-weight: bold;
  font-size: 16px;
}
.summary {
  color: #606266;
  font-size: 13px;
}
.soldout {
  color: #f56c6c;
  font-weight: bold;
}
.add-block {
  border-style: dashed;
}
</style>
