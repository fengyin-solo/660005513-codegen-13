import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import axios from 'axios'
import type { Tick, OrderBook, GridConfig, GridResult, BatchResponse, SortOrder } from '@/types'

const STORAGE_KEY = 'grid-batch-compare-v1'
interface PersistedBatch {
  response: BatchResponse | null
  selectedKeys: string[]
  sortProp: string
  sortOrder: SortOrder
}

function loadPersisted(): PersistedBatch {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { response: null, selectedKeys: [], sortProp: 'index', sortOrder: null, ...JSON.parse(raw) }
  } catch {}
  return { response: null, selectedKeys: [], sortProp: 'index', sortOrder: null }
}

export const useTradingStore = defineStore('trading', () => {
  const loading = ref(false)
  const ticks = ref<Tick[]>([])
  const orderBook = ref<OrderBook | null>(null)
  const gridResult = ref<GridResult | null>(null)
  const wsConnected = ref(false)
  const config = ref<GridConfig>({ lowerPrice: 95, upperPrice: 115, gridCount: 20, capitalPerGrid: 1000, initialCapital: 100000 })

  // ---- 批量对比状态（刷新后恢复：结果清单、勾选项、排序） ----
  const persisted = loadPersisted()
  const batchLoading = ref(false)
  const batchResponse = ref<BatchResponse | null>(persisted.response)
  const selectedKeys = ref<string[]>(persisted.selectedKeys)
  const sortProp = ref<string>(persisted.sortProp)
  const sortOrder = ref<SortOrder>(persisted.sortOrder)

  function persist() {
    const data: PersistedBatch = {
      response: batchResponse.value,
      selectedKeys: selectedKeys.value,
      sortProp: sortProp.value,
      sortOrder: sortOrder.value,
    }
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)) } catch {}
  }
  watch([batchResponse, selectedKeys, sortProp, sortOrder], persist, { deep: true })

  let ws: WebSocket | null = null
  function connectWS() {
    ws = new WebSocket(`ws://${location.hostname}:8000/ws`)
    ws.onopen = () => { wsConnected.value = true }
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        if (d.ticks) ticks.value = d.ticks.slice(-60)
        if (d.orderBook) orderBook.value = d.orderBook
      } catch {}
    }
    ws.onclose = () => { wsConnected.value = false }
  }

  async function runBacktest() {
    loading.value = true
    try { const { data } = await axios.post('/api/backtest', config.value) ; gridResult.value = data }
    finally { loading.value = false }
  }

  async function runBatch(configs: GridConfig[]) {
    batchLoading.value = true
    try {
      const { data } = await axios.post<BatchResponse>('/api/backtest/batch', { configs })
      batchResponse.value = data
      // 保留上一次选择：只留下本次仍然存在的组合，新增的不自动勾选
      const valid = new Set(data.results.map(r => `${r.config.lowerPrice}|${r.config.upperPrice}|${r.config.gridCount}|${r.config.capitalPerGrid}`))
      selectedKeys.value = selectedKeys.value.filter(k => valid.has(k))
      return data
    } finally { batchLoading.value = false }
  }

  function toggleSelected(keys: string[]) { selectedKeys.value = keys }

  function disconnectWS() { ws?.close(); ws = null; wsConnected.value = false }

  return {
    loading, ticks, orderBook, gridResult, wsConnected, config,
    batchLoading, batchResponse, selectedKeys, sortProp, sortOrder,
    connectWS, runBacktest, runBatch, toggleSelected, disconnectWS,
  }
})
