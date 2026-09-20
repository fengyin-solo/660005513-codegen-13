<template>
  <div class="panel batch-panel">
    <h4>🧪 批量回测对比</h4>

    <!-- 1. 参数组合编排 -->
    <div class="draft-head">
      <span class="section-title">待提交组合（{{ drafts.length }} 组）</span>
      <div class="draft-actions">
        <el-button size="small" @click="addDraft">+ 添加一组</el-button>
        <el-button size="small" @click="resetDrafts">重置示例</el-button>
      </div>
    </div>
    <el-table :data="drafts" size="small" class="draft-table" empty-text="点击「添加一组」编排参数组合">
      <el-table-column label="#" type="index" width="34" />
      <el-table-column label="下限" width="92">
        <template #default="{ row }"><el-input-number v-model="row.lowerPrice" :min="BATCH_LIMITS.lower" :max="BATCH_LIMITS.upper" :step="5" size="small" controls-position="right" style="width:100%" /></template>
      </el-table-column>
      <el-table-column label="上限" width="92">
        <template #default="{ row }"><el-input-number v-model="row.upperPrice" :min="BATCH_LIMITS.lower" :max="BATCH_LIMITS.upper" :step="5" size="small" controls-position="right" style="width:100%" /></template>
      </el-table-column>
      <el-table-column label="网格数" width="86">
        <template #default="{ row }"><el-input-number v-model="row.gridCount" :min="BATCH_LIMITS.gridMin" :max="BATCH_LIMITS.gridMax" :step="5" size="small" controls-position="right" style="width:100%" /></template>
      </el-table-column>
      <el-table-column label="每格资金" width="118">
        <template #default="{ row }"><el-input-number v-model="row.capitalPerGrid" :min="BATCH_LIMITS.capitalMin" :max="BATCH_LIMITS.capitalMax" :step="500" size="small" controls-position="right" style="width:100%" /></template>
      </el-table-column>
      <el-table-column label="操作" width="56">
        <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeDraft($index)">删除</el-button></template>
      </el-table-column>
    </el-table>
    <div class="submit-row">
      <div class="initial-capital">
        <span>初始资金</span>
        <el-input-number v-model="initialCapital" :min="BATCH_LIMITS.initialMin" :max="BATCH_LIMITS.initialMax" :step="10000" size="small" controls-position="right" />
      </div>
      <el-button type="primary" size="small" :loading="batch.loading" :disabled="!drafts.length" @click="runBatch">
        🚀 一次性提交 {{ drafts.length }} 组回测
      </el-button>
    </div>

    <!-- 2. 跳过提示：指出是哪几条、为什么跳过，不影响其余组 -->
    <el-alert v-if="batch.skipped.length" type="warning" :closable="true" show-icon class="skip-alert"
      :title="`${batch.skipped.length} 条被跳过，其余组合已正常执行`" @close="batch.skipped = []">
      <div v-for="(s, i) in batch.skipped" :key="i" class="skip-line">
        <b>第 {{ s.index }} 条</b>：{{ s.reason }}
        <span class="skip-params" v-if="s.params">（{{ formatParams(s.params) }}）</span>
      </div>
    </el-alert>

    <!-- 3. 对比清单：可多选、可按统计指标排序；刷新后仍停留在同一组对比 -->
    <template v-if="batch.results.length">
      <div class="draft-head result-head">
        <span class="section-title">对比清单（{{ batch.results.length }} 组，已选 {{ batch.selectedIds.length }} 组）</span>
        <div class="draft-actions">
          <el-button size="small" @click="selectAll">全选</el-button>
          <el-button size="small" :disabled="!batch.selectedIds.length" @click="batch.clearSelection()">清除选择</el-button>
          <el-button size="small" type="danger" plain @click="batch.clearResults()">清空清单</el-button>
        </div>
      </div>
      <el-table :data="sortedResults" size="small" class="result-table" @sort-change="onSortChange" row-key="id"
        :default-sort="{ prop: batch.sort.prop, order: batch.sort.order }">
        <el-table-column label="对比" width="50" align="center">
          <template #default="{ row }">
            <el-checkbox :model-value="batch.isSelected(row.id)" @change="batch.toggleSelect(row.id)" />
          </template>
        </el-table-column>
        <el-table-column label="下限" prop="params.lowerPrice" width="64" align="right">
          <template #default="{ row }">{{ row.params.lowerPrice }}</template>
        </el-table-column>
        <el-table-column label="上限" prop="params.upperPrice" width="64" align="right">
          <template #default="{ row }">{{ row.params.upperPrice }}</template>
        </el-table-column>
        <el-table-column label="网格数" prop="params.gridCount" width="64" align="center">
          <template #default="{ row }">{{ row.params.gridCount }}</template>
        </el-table-column>
        <el-table-column label="每格资金" prop="params.capitalPerGrid" width="84" align="right">
          <template #default="{ row }">¥{{ row.params.capitalPerGrid.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="收益率" prop="returnRate" sortable="custom" width="88" align="right">
          <template #default="{ row }"><span :class="row.returnRate >= 0 ? 'profit' : 'loss'">{{ row.returnRate.toFixed(2) }}%</span></template>
        </el-table-column>
        <el-table-column label="最大回撤" prop="maxDrawdown" sortable="custom" width="88" align="right">
          <template #default="{ row }">{{ row.maxDrawdown.toFixed(2) }}%</template>
        </el-table-column>
        <el-table-column label="夏普比率" prop="sharpeRatio" sortable="custom" width="84" align="right">
          <template #default="{ row }">{{ row.sharpeRatio.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="成交笔数" prop="tradeCount" sortable="custom" width="78" align="right">
          <template #default="{ row }">{{ row.tradeCount }}</template>
        </el-table-column>
        <el-table-column label="" width="50">
          <template #default="{ row }"><el-button link type="danger" size="small" @click="batch.removeResult(row.id)">移除</el-button></template>
        </el-table-column>
      </el-table>

      <!-- 4. 两两对照：勾选的多组并排逐条对照 -->
      <div class="compare-box" v-if="selectedResults.length">
        <div class="section-title">已选组合两两对照（{{ selectedResults.length }} 组）<span class="hint">绿/红高亮为该指标最优</span></div>
        <div class="compare-grid" :style="{ gridTemplateColumns: `86px repeat(${selectedResults.length}, minmax(110px, 1fr))` }">
          <div class="compare-cell head">#</div>
          <div class="compare-cell head" v-for="r in selectedResults" :key="r.id">
            组{{ batch.results.indexOf(r) + 1 }}
            <div class="sub">{{ r.params.lowerPrice }}-{{ r.params.upperPrice }} / {{ r.params.gridCount }}格 / ¥{{ r.params.capitalPerGrid }}</div>
          </div>

          <template v-for="m in metrics" :key="m.key">
            <div class="compare-cell label">{{ m.label }}</div>
            <div class="compare-cell" v-for="r in selectedResults" :key="r.id + m.key">
              <span :class="metricClass(r, m.key)">{{ m.fmt(r) }}</span>
            </div>
          </template>
        </div>
      </div>
      <div v-else class="hint select-hint">勾选上方清单中的若干组即可两两对照（刷新后选择仍保留）</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useBatchStore, validateDraft, BATCH_LIMITS, type SortProp } from '../store/batch'
import type { BatchDraftRow, BatchResultItem } from '../types'
import { ElMessage } from 'element-plus'

const batch = useBatchStore()
// storeToRefs 保持响应式（store setup 语法下解构会丢失响应性）
const { results, selectedIds, sort } = storeToRefs(batch)

const initialCapital = ref(100000)
let draftKey = 1
function makeDraft(lower: number, upper: number, count: number, cap: number): BatchDraftRow {
  return { key: draftKey++, lowerPrice: lower, upperPrice: upper, gridCount: count, capitalPerGrid: cap }
}
function sampleDrafts(): BatchDraftRow[] {
  draftKey = 1
  return [
    makeDraft(95, 115, 20, 1000),
    makeDraft(90, 110, 10, 2000),
    makeDraft(92, 118, 30, 800),
  ]
}
const drafts = ref<BatchDraftRow[]>(sampleDrafts())
function addDraft() {
  const last = drafts.value[drafts.value.length - 1]
  drafts.value.push(last ? makeDraft(last.lowerPrice, last.upperPrice, last.gridCount, last.capitalPerGrid) : makeDraft(95, 115, 20, 1000))
}
function removeDraft(i: number) { drafts.value.splice(i, 1) }
function resetDrafts() { drafts.value = sampleDrafts() }

async function runBatch() {
  // 提前给出越界/重复的条数提示；真正的逐条原因在提交后由 skip 清单列出
  const invalid = drafts.value.filter(d => validateDraft(d, initialCapital.value) !== null).length
  await batch.submitBatch(drafts.value, initialCapital.value)
  if (batch.skipped.length) {
    ElMessage.warning(`${batch.skipped.length} 条被跳过（越界或重复），其余已完成`)
  } else if (!invalid) {
    ElMessage.success(`${drafts.value.length} 组回测全部完成`)
  }
}

function formatParams(p: unknown): string {
  const q = p as Partial<BatchDraftRow>
  return [q.lowerPrice, q.upperPrice, q.gridCount, q.capitalPerGrid].filter(v => v !== undefined).join(' / ')
}

// ---- 排序（状态持久化，刷新后仍是同一排序）----
function onSortChange({ prop, order }: { prop: string; order: 'ascending' | 'descending' | null }) {
  if (prop && order) sort.value = { prop: prop as SortProp, order }
}
const sortedResults = computed<BatchResultItem[]>(() => {
  const { prop, order } = sort.value
  const get = (r: BatchResultItem): number => {
    if (prop === 'returnRate' || prop === 'maxDrawdown' || prop === 'sharpeRatio' || prop === 'tradeCount') return r[prop]
    return (r.params as unknown as Record<string, number>)[prop] ?? 0
  }
  return [...results.value].sort((a, b) => order === 'ascending' ? get(a) - get(b) : get(b) - get(a))
})

function selectAll() {
  selectedIds.value = sortedResults.value.map(r => r.id)
}

const selectedResults = computed(() => results.value.filter(r => selectedIds.value.includes(r.id)))

// ---- 对照指标 ----
const metrics = [
  { key: 'returnRate', label: '收益率', fmt: (r: BatchResultItem) => `${r.returnRate.toFixed(2)}%`, higherBetter: true },
  { key: 'maxDrawdown', label: '最大回撤', fmt: (r: BatchResultItem) => `${r.maxDrawdown.toFixed(2)}%`, higherBetter: false },
  { key: 'sharpeRatio', label: '夏普比率', fmt: (r: BatchResultItem) => r.sharpeRatio.toFixed(2), higherBetter: true },
  { key: 'tradeCount', label: '成交笔数', fmt: (r: BatchResultItem) => String(r.tradeCount), higherBetter: true },
  { key: 'totalProfit', label: '总盈亏', fmt: (r: BatchResultItem) => `¥${r.totalProfit.toFixed(0)}`, higherBetter: true },
  { key: 'winRate', label: '胜率', fmt: (r: BatchResultItem) => `${r.winRate.toFixed(1)}%`, higherBetter: true },
] as const

function metricClass(r: BatchResultItem, key: string): string {
  const m = metrics.find(x => x.key === key)
  if (!m || selectedResults.value.length < 2) return ''
  const vals = selectedResults.value.map(x => (x as unknown as Record<string, number>)[key])
  const target = (r as unknown as Record<string, number>)[key]
  const best = m.higherBetter ? Math.max(...vals) : Math.min(...vals)
  if (target === best) return 'best-good'  // 无论指标方向，最优值一律绿色高亮
  const worst = m.higherBetter ? Math.min(...vals) : Math.max(...vals)
  if (target === worst) return 'best-bad'
  return ''
}
</script>

<style scoped>
.batch-panel{margin-top:12px}
.draft-head{display:flex;justify-content:space-between;align-items:center;margin:8px 0 4px}
.draft-actions{display:flex;gap:6px}
.submit-row{display:flex;justify-content:space-between;align-items:center;margin-top:8px;flex-wrap:wrap;gap:8px}
.initial-capital{display:flex;align-items:center;gap:6px;font-size:12px;color:#94a3b8}
.skip-alert{margin-top:8px}
.skip-line{font-size:11px;line-height:1.6;color:#fbbf24}
.skip-params{color:#94a3b8}
.result-head{margin-top:14px}
.result-table,.draft-table{background:transparent}
:deep(.el-table),:deep(.el-table tr),:deep(.el-table th.el-table__cell){background:transparent;color:#cbd5e1}
:deep(.el-table td.el-table__cell),:deep(.el-table th.el-table__cell.is-leaf){border-bottom:1px solid #1e2a5a55}
:deep(.el-table th.el-table__cell){background:#0a0e27;color:#94a3b8;font-size:11px}
:deep(.el-table .caret-wrapper){color:#94a3b8}
:deep(.el-table .ascending .sort-caret.ascending){border-bottom-color:#4fc3f7}
:deep(.el-table .descending .sort-caret.descending){border-top-color:#4fc3f7}
.profit{color:#22c55e}.loss{color:#ef4444}
.compare-box{margin-top:10px;border:1px solid #1e2a5a;border-radius:6px;padding:8px;background:#0a0e27;overflow-x:auto}
.compare-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;margin-top:6px}
.compare-cell{padding:5px 8px;font-size:12px;text-align:right;background:#0f1535;border-radius:3px}
.compare-cell.head{text-align:center;font-weight:700;color:#4fc3f7;font-size:11px}
.compare-cell.label{text-align:left;color:#94a3b8;font-size:11px}
.compare-cell .sub{font-weight:400;color:#64748b;font-size:10px;margin-top:2px}
.best-good{color:#22c55e;font-weight:700}
.best-bad{color:#ef4444}
.hint{font-size:10px;color:#64748b;font-weight:400;margin-left:6px}
.select-hint{display:block;margin-top:8px;font-size:11px}
.section-title{font-size:11px;color:#64748b}
</style>
