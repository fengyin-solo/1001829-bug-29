<template>
  <section class="page" data-module="patrol">
    <header class="page-head">
      <div>
        <h2>巡查任务管理</h2>
        <p class="page-desc">维护巡查单，围绕巡查单号、巡查路线、巡查人员、巡查日期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记巡查单</button>
        <button class="btn" type="button" @click="exportRows">导出巡查任务清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>巡查状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="bulk-bar">
      <label class="select-all">
        <input type="checkbox" :checked="allSelected" :indeterminate.prop="someSelected" @change="toggleAll" />
        全选本页
      </label>
      <button class="btn primary" type="button" :disabled="!selectedIds.length || voiding" @click="batchVoid">
        {{ voiding ? '批量作废中…' : `批量作废（${selectedIds.length}）` }}
      </button>
      <span class="bulk-hint">已提交结果的巡查单不允许作废；同一批重复提交不会多留作废记录</span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th style="width: 36px">选择</th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>
            <input
              type="checkbox"
              :value="Number(row.id)"
              v-model="selectedIds"
              :disabled="!canVoid(row)"
              :title="canVoid(row) ? '' : '当前状态不可作废'"
            />
          </td>
          <td v-for="column in columns" :key="column">
            <button v-if="column === '巡查单号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(row).length" class="muted-text">无可用动作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无巡查任务数据，可先登记巡查单</td>
        </tr>
      </tbody>
    </table>

    <div v-if="batchResult" class="receipt-panel">
      <header class="receipt-head">
        <strong>批量作废回执（批次号 {{ batchResult.batch_no }}）</strong>
        <span>共 {{ batchResult.total }} 张 · 成功 {{ batchResult.success_count }} 张 · 失败 {{ batchResult.failed_count }} 张</span>
        <button class="link" type="button" @click="batchResult = null">关闭回执</button>
      </header>
      <table class="data-table receipt-table">
        <thead>
          <tr><th>巡查单号</th><th>结果</th><th>说明 / 失败原因</th></tr>
        </thead>
        <tbody>
          <tr v-for="(receipt, index) in batchResult.receipts" :key="`${receipt.id}-${index}`">
            <td>{{ receipt.巡查单号 || receipt.id }}</td>
            <td :class="receipt.ok ? 'ok-text' : 'error-text'">{{ receipt.voided ? '已作废' : receipt.ok ? '未重复处理' : '失败' }}</td>
            <td>{{ receipt.reason }}</td>
          </tr>
        </tbody>
      </table>
      <footer v-if="batchResult.failed_count > 0" class="receipt-foot">
        <button class="btn" type="button" :disabled="voiding" @click="resumeBatch">
          按原批次续走（仍有 {{ failedIds.length }} 张未成功）
        </button>
        <span class="muted-text">中断后重进页面，可凭批次号 {{ batchResult.batch_no }} 找回本回执；已作废的不会重复记录</span>
      </footer>
    </div>

    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal-card">
        <header class="modal-head">
          <strong>巡查单详情 · {{ detail.巡查单号 }}</strong>
          <button class="link" type="button" @click="detail = null">关闭</button>
        </header>
        <dl class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] ?? '—' }}</dd>
          </template>
          <dt>作废记录数</dt>
          <dd>{{ detail.void_logs?.length ?? 0 }}</dd>
        </dl>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条巡查任务记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null> & { void_logs?: unknown[] }
type Receipt = { id: number | string; 巡查单号: string; ok: boolean; voided: boolean; reason: string }
type BatchResult = {
  batch_no: string
  total: number
  success_count: number
  failed_count: number
  receipts: Receipt[]
}

const ENDPOINT = '/api/patrol'
const columns = ['巡查单号', '巡查路线', '巡查人员', '巡查日期', '巡查里程', '发现问题数', '巡查时长', '巡查状态']
const statuses = ['待派发', '巡查中', '已提交', '已作废']
const actionByStatus: Record<string, string[]> = {
  待派发: ['派发巡查', '作废巡查'],
  巡查中: ['提交结果', '作废巡查'],
  已提交: [],
  已作废: [],
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)
const selectedIds = ref<number[]>([])
const voiding = ref(false)
const batchResult = ref<BatchResult | null>(null)
const detail = ref<Row | null>(null)

const stats = computed(() => [
  { label: '巡查单总数', value: total.value },
  { label: '待派发巡查', value: rows.value.filter((row) => row.status === '待派发').length },
  { label: '巡查中任务', value: rows.value.filter((row) => row.status === '巡查中').length },
  { label: '已作废数', value: rows.value.filter((row) => row.status === '已作废').length },
])

const voidableRows = computed(() => rows.value.filter((row) => canVoid(row)))
const allSelected = computed(
  () => voidableRows.value.length > 0 && voidableRows.value.every((row) => selectedIds.value.includes(Number(row.id))),
)
const someSelected = computed(() => selectedIds.value.length > 0 && !allSelected.value)
const failedIds = computed(() =>
  (batchResult.value?.receipts ?? []).filter((receipt) => !receipt.ok).map((receipt) => Number(receipt.id)),
)

function canVoid(row: Row): boolean {
  return row.status === '待派发' || row.status === '巡查中'
}

function availableActions(row: Row): string[] {
  return actionByStatus[String(row.status ?? '')] ?? []
}

function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selectedIds.value = checked ? voidableRows.value.map((row) => Number(row.id)) : []
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '巡查单登记入口尚未接入审批流'
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('巡查单详情读取失败')
    }
    detail.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查单详情读取失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message || '巡查任务动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查任务操作失败'
  }
}

async function submitBatch(ids: number[], batchNo?: string) {
  voiding.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/batch-void`, {
      method: 'POST',
      body: JSON.stringify({ ids, batch_no: batchNo }),
    })
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(payload?.detail || '批量作废请求未被接受')
    }
    batchResult.value = (await response.json()) as BatchResult
    selectedIds.value = []
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量作废失败，可稍后凭批次号重试'
  } finally {
    voiding.value = false
  }
}

function batchVoid() {
  void submitBatch([...selectedIds.value])
}

function resumeBatch() {
  if (!batchResult.value) {
    return
  }
  // 续走原批次：整批 id 连同批次号重发，后端原样回放首次回执，
  // 中断没收到回执时凭批次号把结果取回来，同一批只算一次、不多留作废记录。
  const ids = batchResult.value.receipts
    .map((receipt) => Number(receipt.id))
    .filter((id) => Number.isFinite(id))
  void submitBatch(ids, batchResult.value.batch_no)
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams(filters.value as Record<string, string>)
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}&size=200`)
    if (!response.ok) {
      throw new Error('巡查单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    selectedIds.value = selectedIds.value.filter((id) =>
      rows.value.some((row) => Number(row.id) === id && canVoid(row)),
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查任务列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.bulk-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.select-all {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.bulk-hint,
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.receipt-panel {
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  padding: 10px 12px;
}
.receipt-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 13px;
}
.receipt-head span {
  color: var(--muted);
}
.receipt-head button {
  margin-left: auto;
}
.receipt-table {
  margin-top: 4px;
}
.receipt-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}
.ok-text {
  color: #067647;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 560px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 6px 12px;
  margin: 0;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
</style>
