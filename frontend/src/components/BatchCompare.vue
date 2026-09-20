<template>
  <div class="panel batch-panel">
    <h4>📊 批量回测对比</h4>

    <!-- 组合构造器：填入候选值，自动排列成参数组合 -->
    <div class="builder">
      <div class="builder-hint">为每个参数输入候选值（逗号分隔），将按下限 × 上限 × 网格数量 × 每格资金排列组合</div>
      <div class="builder-grid">
        <div v-for="f in fields" :key="f.key" class="builder-field">
          <label>{{ f.label }}</label>
          <el-input v-model="rawInputs[f.key]" size="small" :placeholder="f.placeholder" />
        </div>
      </div>
      <div class="builder-actions">
        <el-button size="small" type="primary" plain @click="buildCombos">生成组合</el-button>
        <el-button size="small" @click="addCurrentConfig">加入当前单次配置</el-button>
        <el-button size="small" @click="clearDrafts">清空草稿</el-button>
        <span class="draft-count">草稿 {{ drafts.length }} 组，最多 100 组</span>
      </div>
      <div class="builder-msg" v-if="buildMsg" :class="buildMsg.type">{{ buildMsg.text }}</div>
    </div>

    <!-- 草稿清单 -->
    <div class="draft-table" v-if="drafts.length">
      <div class="draft-row draft-head">
        <span>#</span><span>下限</span><span>上限</span><span>网格数</span><span>每格资金</span><span></span>
      </div>
      <div v-for="(d, i) in drafts" :key="i" class="draft-row">
        <span>{{ i + 1 }}</span>
        <span>{{ d.lowerPrice }}</span><span>{{ d.upperPrice }}</span>
        <span>{{ d.gridCount }}</span><span>¥{{ d.capitalPerGrid }}</span>
        <span class="del" @click="drafts.splice(i, 1)">✕</span>
      </div>
    </div>

    <el-button type="primary" size="small" class="submit-btn" :loading="store.batchLoading"
               :disabled="!drafts.length" @click="submitBatch">
      🚀 批量回测（{{ drafts.length }} 组）
    </el-button>

    <!-- 越界 / 重复提示 -->
    <div class="skipped" v-if="store.batchResponse?.skipped.length">
      <div class="section-title">⚠️ 已跳过 {{ store.batchResponse.skipped.length }} 组</div>
      <div v-for="(s, i) in store.batchResponse.skipped" :key="i" class="skip-item">
        <span class="skip-idx" v-if="s.index">第 {{ s.index }} 组：</span>
        <span class="skip-reason">{{ s.reason }}</span>
      </div>
    </div>

    <!-- 结果清单 -->
    <template v-if="sortedResults.length">
      <div class="section-title">回测结果（点击表头排序，勾选多组进行对比）</div>
      <el-table :data="sortedResults" size="small" height="320" border
                :row-key="rowKey" @selection-change="onSelectionChange"
                @sort-change="onSortChange"
                :default-sort="{ prop: store.sortProp, order: store.sortOrder }"
                :row-class-name="rowClass" ref="tableRef">
        <el-table-column type="selection" width="38" reserve-selection />
        <el-table-column prop="index" label="#" width="44" sortable="custom"
                         :sort-orders="['descending','ascending',null]" />
        <el-table-column prop="config.lowerPrice" label="下限" width="64" sortable="custom"
                         :sort-orders="['descending','ascending',null]">
          <template #default="{ row }">{{ row.config.lowerPrice }}</template>
        </el-table-column>
        <el-table-column prop="config.upperPrice" label="上限" width="64" sortable="custom"
                         :sort-orders="['descending','ascending',null]">
          <template #default="{ row }">{{ row.config.upperPrice }}</template>
        </el-table-column>
        <el-table-column prop="config.gridCount" label="网格数" width="64" sortable="custom"
                         :sort-orders="['descending','ascending',null]">
          <template #default="{ row }">{{ row.config.gridCount }}</template>
        </el-table-column>
        <el-table-column prop="config.capitalPerGrid" label="每格资金" width="82" sortable="custom"
                         :sort-orders="['descending','ascending',null]">
          <template #default="{ row }">¥{{ row.config.capitalPerGrid }}</template>
        </el-table-column>
        <el-table-column prop="metrics.returnRate" label="收益率%" width="88" sortable="custom"
                         :sort-orders="['descending','ascending',null]" />
        <el-table-column prop="metrics.maxDrawdown" label="最大回撤%" width="92" sortable="custom"
                         :sort-orders="['ascending','descending',null]" />
        <el-table-column prop="metrics.sharpeRatio" label="夏普比率" width="82" sortable="custom"
                         :sort-orders="['descending','ascending',null]" />
        <el-table-column prop="metrics.tradeCount" label="成交笔数" width="78" sortable="custom"
                         :sort-orders="['descending','ascending',null]" />
      </el-table>
      <div class="table-foot">
        已选 <b>{{ selectedRows.length }}</b> 组
        <el-button link size="small" @click="clearSelection">清除选择</el-button>
        <el-button link size="small" @click="resetSort">恢复默认排序</el-button>
      </div>
    </template>

    <!-- 两两对照 -->
    <div class="compare" v-if="selectedRows.length >= 2">
      <div class="section-title">📌 {{ selectedRows.length }} 组参数对照（高亮为该指标最优）</div>
      <div class="compare-table-wrap">
        <table class="compare-table">
          <thead>
            <tr>
              <th class="idx-col">指标</th>
              <th v-for="r in selectedRows" :key="rowKey(r)">
                <div>第{{ r.index }}组</div>
                <div class="col-sub">{{ r.config.lowerPrice }}–{{ r.config.upperPrice }} / {{ r.config.gridCount }}格 / ¥{{ r.config.capitalPerGrid }}</div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in metricRows" :key="m.prop">
              <td class="idx-col">{{ m.label }}</td>
              <td v-for="r in selectedRows" :key="rowKey(r)" :class="{ best: isBest(m, r) }">
                {{ formatMetric(m, metricValue(r, m.prop)) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="compare-hint" v-else-if="(store.batchResponse?.results.length ?? 0) > 0">
      勾选 2 组及以上即可查看两两对照
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { useTradingStore } from '../store/trading'
import type { GridConfig, BatchResult } from '@/types'
import { comboKey } from '@/types'

type SortOrderValue = 'ascending' | 'descending' | null

/* eslint-disable @typescript-eslint/no-explicit-any */
const store = useTradingStore()

interface FieldDef { key: keyof GridConfig; label: string; placeholder: string }
const fields: FieldDef[] = [
  { key: 'lowerPrice', label: '下限价格', placeholder: '90,95' },
  { key: 'upperPrice', label: '上限价格', placeholder: '115,120' },
  { key: 'gridCount', label: '网格数量', placeholder: '15,20,25' },
  { key: 'capitalPerGrid', label: '每格资金', placeholder: '1000,2000' },
]
const rawInputs = reactive<Record<string, string>>({
  lowerPrice: '90,95', upperPrice: '115,120', gridCount: '15,20', capitalPerGrid: '1000,2000',
})
const drafts = ref<GridConfig[]>([])
const buildMsg = ref<{ type: 'warn' | 'ok'; text: string } | null>(null)
const tableRef = ref<any>(null)

function parseCandidates(input: string, isInt = false): number[] {
  return [...new Set(input.split(/[,，\s]+/).filter(Boolean).map(v => isInt ? parseInt(v, 10) : parseFloat(v)))]
    .filter(v => !Number.isNaN(v))
}

function buildCombos() {
  const lowers = parseCandidates(rawInputs.lowerPrice)
  const uppers = parseCandidates(rawInputs.upperPrice)
  const counts = parseCandidates(rawInputs.gridCount, true)
  const caps = parseCandidates(rawInputs.capitalPerGrid)
  if (!lowers.length || !uppers.length || !counts.length || !caps.length) {
    buildMsg.value = { type: 'warn', text: '四个参数都至少需要一个有效数字（逗号分隔）' }
    return
  }
  const combos: GridConfig[] = []
  for (const lowerPrice of lowers)
    for (const upperPrice of uppers)
      for (const gridCount of counts)
        for (const capitalPerGrid of caps)
          combos.push({ lowerPrice, upperPrice, gridCount, capitalPerGrid, initialCapital: store.config.initialCapital })

  if (combos.length > 100) {
    buildMsg.value = { type: 'warn', text: `共排列出 ${combos.length} 组，超过 100 组上限，请减少候选值` }
    return
  }
  // 合并已有草稿，按四元组去重
  const merged = new Map<string, GridConfig>()
  for (const c of drafts.value) merged.set(comboKey(c), c)
  for (const c of combos) merged.set(comboKey(c), c)
  drafts.value = [...merged.values()].slice(0, 100)
  buildMsg.value = { type: 'ok', text: `已生成并合并为 ${drafts.value.length} 组（重复/越界的组合将在提交后逐条提示并跳过）` }
}

function addCurrentConfig() {
  const c = { ...store.config }
  if (drafts.value.some(d => comboKey(d) === comboKey(c))) {
    buildMsg.value = { type: 'warn', text: '当前单次配置已在草稿中，未重复添加' }
    return
  }
  drafts.value.push(c)
  buildMsg.value = { type: 'ok', text: '已加入当前单次配置' }
}
function clearDrafts() { drafts.value = []; buildMsg.value = null }

async function submitBatch() {
  await store.runBatch(drafts.value)
  buildMsg.value = null
  await nextTick()
  restoreSelection()
}

// ---- 结果表：排序、多选、刷新恢复 ----
const results = computed<BatchResult[]>(() => store.batchResponse?.results ?? [])

function readProp(r: BatchResult, prop: string): number | string {
  if (prop === 'index') return r.index
  if (prop.startsWith('metrics.')) return (r.metrics as unknown as Record<string, number>)[prop.slice(8)]
  if (prop.startsWith('config.')) return (r.config as unknown as Record<string, number>)[prop.slice(7)]
  return (r as unknown as Record<string, number | string>)[prop]
}

const sortedResults = computed(() => {
  const list = [...results.value]
  if (!store.sortOrder || !store.sortProp) {
    list.sort((a, b) => a.index - b.index)
    return list
  }
  const dir = store.sortOrder === 'ascending' ? 1 : -1
  list.sort((a, b) => {
    const va = readProp(a, store.sortProp), vb = readProp(b, store.sortProp)
    if (va < vb) return -1 * dir
    if (va > vb) return 1 * dir
    return a.index - b.index
  })
  return list
})

function onSortChange({ prop, order }: { prop: string | null; order: SortOrderValue }) {
  store.sortProp = prop || 'index'
  store.sortOrder = order
}
function resetSort() {
  store.sortProp = 'index'
  store.sortOrder = null
}

const rowKey = (r: BatchResult) => comboKey(r.config)
function rowClass({ row }: { row: BatchResult }) {
  return store.selectedKeys.includes(rowKey(row)) ? 'row-selected' : ''
}
function onSelectionChange(rows: BatchResult[]) {
  store.toggleSelected(rows.map(rowKey))
}
const selectedRows = computed(() => {
  const map = new Map(results.value.map(r => [rowKey(r), r]))
  return store.selectedKeys.map(k => map.get(k)).filter((r): r is BatchResult => !!r)
})
function clearSelection() {
  tableRef.value?.clearSelection()
  store.toggleSelected([])
}
function restoreSelection() {
  if (!tableRef.value) return
  for (const r of results.value) {
    tableRef.value.toggleRowSelection(r, store.selectedKeys.includes(rowKey(r)))
  }
}
// 数据渲染（包括刷新后从 localStorage 恢复）之后，勾回上一次选择
watch(sortedResults, () => nextTick(restoreSelection), { flush: 'post' })

// ---- 指标对照 ----
interface MetricRow { prop: string; label: string; format: 'pct' | 'num2' | 'int'; better: 'high' | 'low' }
const metricRows: MetricRow[] = [
  { prop: 'returnRate', label: '收益率', format: 'pct', better: 'high' },
  { prop: 'maxDrawdown', label: '最大回撤', format: 'pct', better: 'low' },
  { prop: 'sharpeRatio', label: '夏普比率', format: 'num2', better: 'high' },
  { prop: 'tradeCount', label: '成交笔数', format: 'int', better: 'high' },
  { prop: 'totalProfit', label: '总盈亏(¥)', format: 'num2', better: 'high' },
  { prop: 'winRate', label: '胜率', format: 'pct', better: 'high' },
]
function formatMetric(m: MetricRow, v: number) {
  if (m.format === 'pct') return `${v.toFixed(2)}%`
  if (m.format === 'num2') return v.toFixed(2)
  return v
}
function metricValue(r: BatchResult, prop: string): number {
  return (r.metrics as unknown as Record<string, number>)[prop]
}
function isBest(m: MetricRow, r: BatchResult) {
  const vals = selectedRows.value.map(x => metricValue(x, m.prop))
  const best = m.better === 'high' ? Math.max(...vals) : Math.min(...vals)
  return metricValue(r, m.prop) === best
}
</script>

<style scoped>
.batch-panel{margin-top:12px}
.panel h4{color:#4fc3f7;font-size:13px;margin-bottom:8px}
.builder{background:#0a0e27;border-radius:6px;padding:8px;margin-bottom:8px}
.builder-hint{font-size:11px;color:#64748b;margin-bottom:6px;line-height:1.5}
.builder-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.builder-field label{display:block;font-size:10px;color:#94a3b8;margin-bottom:2px}
.builder-actions{display:flex;align-items:center;gap:6px;margin-top:8px;flex-wrap:wrap}
.draft-count{font-size:11px;color:#64748b}
.builder-msg{font-size:11px;margin-top:6px}.builder-msg.warn{color:#f59e0b}.builder-msg.ok{color:#22c55e}
.draft-table{max-height:150px;overflow-y:auto;margin-bottom:8px;border:1px solid #1e2a5a33;border-radius:4px}
.draft-row{display:grid;grid-template-columns:32px 1fr 1fr 1fr 1fr 30px;gap:4px;font-size:11px;padding:3px 8px;color:#cbd5e1}
.draft-row:nth-child(even){background:#0a0e2766}
.draft-head{color:#64748b;position:sticky;top:0;background:#0f1535}
.del{color:#ef4444;cursor:pointer;text-align:center}
.submit-btn{width:100%;margin-bottom:8px}
.section-title{font-size:11px;color:#64748b;margin:8px 0 4px}
.skipped{background:#f59e0b11;border:1px solid #f59e0b44;border-radius:6px;padding:6px 8px;margin-bottom:8px}
.skip-item{font-size:11px;color:#fbbf24;line-height:1.6}
.skip-idx{font-weight:700}
:deep(.el-table){background:transparent;font-size:11px}
:deep(.el-table th.el-table__cell){background:#0a0e27!important;color:#94a3b8}
:deep(.el-table tr),:deep(.el-table td.el-table__cell){background:transparent;color:#cbd5e1}
:deep(.el-table--border .el-table__cell){border-color:#1e2a5a88}
:deep(.el-table .row-selected){background:#4fc3f718!important}
:deep(.el-table .row-selected td.el-table__cell){background:#4fc3f718!important}
.table-foot{font-size:11px;color:#94a3b8;margin-top:4px}
.compare{margin-top:10px}
.compare-table-wrap{overflow-x:auto}
.compare-table{width:100%;border-collapse:collapse;font-size:11px;min-width:480px}
.compare-table th,.compare-table td{border:1px solid #1e2a5a;padding:6px 8px;text-align:center;color:#cbd5e1}
.compare-table th{background:#0a0e27;color:#94a3b8;font-weight:600}
.compare-table .idx-col{text-align:left;color:#64748b;white-space:nowrap}
.compare-table .col-sub{font-weight:400;font-size:10px;color:#64748b;margin-top:2px}
.compare-table td.best{color:#22c55e;font-weight:700;background:#22c55e10}
.compare-hint{font-size:11px;color:#64748b;margin-top:6px}
</style>
