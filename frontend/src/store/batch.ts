import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import axios from 'axios'
import type { BatchResultItem, BatchDraftRow, BatchBacktestResponse, BatchParams } from '@/types'

const STORAGE_KEY = 'grid-batch-compare-v1'
export const BATCH_LIMITS = {
  lower: 50, upper: 200, gridMin: 5, gridMax: 50,
  capitalMin: 100, capitalMax: 50000, initialMin: 10000, initialMax: 1000000, batchMax: 50,
} as const

export type SortProp = 'returnRate' | 'maxDrawdown' | 'sharpeRatio' | 'tradeCount'
export interface SortState { prop: SortProp; order: 'ascending' | 'descending' }

interface Persisted {
  results: BatchResultItem[]
  selectedIds: number[]
  sort: SortState
  nextId: number
}

export function paramsSignature(p: { lowerPrice: number; upperPrice: number; gridCount: number; capitalPerGrid: number }): string {
  return [p.lowerPrice, p.upperPrice, p.gridCount, p.capitalPerGrid]
    .map(v => typeof v === 'number' ? Number(v.toFixed(4)) : v).join('/')
}

/** 客户端越界校验，返回错误原因；合法返回 null。与后端规则保持一致。 */
export function validateDraft(row: BatchDraftRow, initialCapital: number): string | null {
  const n = (v: unknown) => typeof v === 'number' && !Number.isNaN(v)
  if (!n(row.lowerPrice) || !n(row.upperPrice) || !n(row.gridCount) || !n(row.capitalPerGrid) || !n(initialCapital)) {
    return '参数必须为有效数值'
  }
  if (row.lowerPrice < BATCH_LIMITS.lower || row.lowerPrice > BATCH_LIMITS.upper) return `下限价格超出允许范围 [${BATCH_LIMITS.lower}, ${BATCH_LIMITS.upper}]`
  if (row.upperPrice < BATCH_LIMITS.lower || row.upperPrice > BATCH_LIMITS.upper) return `上限价格超出允许范围 [${BATCH_LIMITS.lower}, ${BATCH_LIMITS.upper}]`
  if (row.lowerPrice >= row.upperPrice) return '下限价格必须小于上限价格'
  if (row.gridCount < BATCH_LIMITS.gridMin || row.gridCount > BATCH_LIMITS.gridMax) return `网格数量超出允许范围 [${BATCH_LIMITS.gridMin}, ${BATCH_LIMITS.gridMax}]`
  if (row.capitalPerGrid < BATCH_LIMITS.capitalMin || row.capitalPerGrid > BATCH_LIMITS.capitalMax) return `每格资金超出允许范围 [${BATCH_LIMITS.capitalMin}, ${BATCH_LIMITS.capitalMax}]`
  if (initialCapital < BATCH_LIMITS.initialMin || initialCapital > BATCH_LIMITS.initialMax) return `初始资金超出允许范围 [${BATCH_LIMITS.initialMin}, ${BATCH_LIMITS.initialMax}]`
  if (row.gridCount * row.capitalPerGrid > initialCapital) return '总网格资金(网格数量×每格资金)不能超过初始资金'
  return null
}

function loadPersisted(): Persisted {
  const fallback: Persisted = { results: [], selectedIds: [], sort: { prop: 'returnRate', order: 'descending' }, nextId: 1 }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const data = JSON.parse(raw) as Partial<Persisted>
    return {
      results: Array.isArray(data.results) ? data.results : [],
      // 仅保留仍然存在的组合，避免脏数据
      selectedIds: Array.isArray(data.selectedIds) ? data.selectedIds : [],
      sort: data.sort && data.sort.prop ? data.sort : fallback.sort,
      nextId: typeof data.nextId === 'number' && data.nextId > 0 ? data.nextId : 1,
    }
  } catch {
    return fallback
  }
}

export interface BatchSkipEntry { index: number; reason: string; params?: unknown }

export const useBatchStore = defineStore('batchCompare', () => {
  const initial = loadPersisted()
  const results = ref<BatchResultItem[]>(initial.results)
  const selectedIds = ref<number[]>(initial.selectedIds.filter(id => initial.results.some(r => r.id === id)))
  const sort = ref<SortState>(initial.sort)
  const nextId = ref(initial.nextId)
  const loading = ref(false)
  const skipped = ref<BatchSkipEntry[]>([])

  function persist() {
    const data: Persisted = { results: results.value, selectedIds: selectedIds.value, sort: sort.value, nextId: nextId.value }
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)) } catch { /* 存储不可用时静默降级 */ }
  }
  watch([results, selectedIds, sort, nextId], persist, { deep: true })

  function isSelected(id: number) { return selectedIds.value.includes(id) }
  function toggleSelect(id: number) {
    if (isSelected(id)) selectedIds.value = selectedIds.value.filter(x => x !== id)
    else selectedIds.value = [...selectedIds.value, id]
  }
  function clearSelection() { selectedIds.value = [] }

  /**
   * 提交批量回测。
   * 提交前先在客户端逐条校验/去重（草稿内重复、与已有清单重复都跳过），
   * 合法组合一次性发给后端；后端再次兜底校验，任何一条失败都不会影响其余条目。
   */
  async function submitBatch(drafts: BatchDraftRow[], initialCapital: number) {
    loading.value = true
    skipped.value = []
    const toSend: Array<BatchParams & { cid: number }> = []
    const draftSig = new Set<string>()
    try {
      drafts.forEach((row, i) => {
        const index = i + 1
        const err = validateDraft(row, initialCapital)
        if (err) { skipped.value.push({ index, reason: err, params: row }); return }
        const sig = paramsSignature(row)
        if (draftSig.has(sig)) {
          skipped.value.push({ index, reason: '与本批中更靠前的组合重复', params: row }); return
        }
        draftSig.add(sig)
        if (results.value.some(r => paramsSignature(r.params) === sig)) {
          skipped.value.push({ index, reason: '与对比清单中已有组合重复', params: row }); return
        }
        toSend.push({
          cid: i + 1,
          lowerPrice: row.lowerPrice, upperPrice: row.upperPrice,
          gridCount: row.gridCount, capitalPerGrid: row.capitalPerGrid,
          initialCapital,
        })
      })

      if (toSend.length) {
        const { data } = await axios.post<BatchBacktestResponse>('/api/backtest/batch', { configs: toSend })
        // 保留此前选择：只追加新组合，默认不自动勾选；已选 id 不变
        const now = Date.now()
        const added: BatchResultItem[] = data.results.map(r => ({
          id: nextId.value++,
          params: r.params,
          returnRate: r.returnRate,
          maxDrawdown: r.maxDrawdown,
          sharpeRatio: r.sharpeRatio,
          tradeCount: r.tradeCount,
          totalProfit: r.totalProfit,
          winRate: r.winRate,
          createdAt: now,
        }))
        results.value = [...results.value, ...added]
        data.skipped.forEach(s => {
          skipped.value.push({ index: s.cid, reason: s.reason, params: s.config })
        })
      }
      skipped.value.sort((a, b) => a.index - b.index)
    } finally {
      loading.value = false
    }
  }

  function removeResult(id: number) {
    results.value = results.value.filter(r => r.id !== id)
    selectedIds.value = selectedIds.value.filter(x => x !== id)
  }
  function clearResults() {
    results.value = []
    selectedIds.value = []
  }

  return {
    results, selectedIds, sort, loading, skipped,
    isSelected, toggleSelect, clearSelection, submitBatch, removeResult, clearResults,
  }
})
