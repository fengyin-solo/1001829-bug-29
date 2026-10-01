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
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="batch-bar">
      <label class="select-all">
        <input type="checkbox" :checked="allCurrentSelected" :indeterminate.prop="someCurrentSelected" @change="toggleSelectAll" />
        全选本页
      </label>
      <span class="batch-tip">已选 {{ selectedIds.length }} 张</span>
      <button class="btn danger" type="button" :disabled="!selectedIds.length || batchLoading" @click="submitBatch">
        {{ batchLoading ? '批量作废中…' : '批量作废' }}
      </button>
      <button
        v-if="pendingResume"
        class="btn warn"
        type="button"
        :disabled="batchLoading"
        @click="continueBatch"
      >
        继续处理中断批次
      </button>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col"></th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input type="checkbox" :checked="isSelected(Number(row.id))" @change="toggleSelect(Number(row.id))" />
          </td>
          <td v-for="column in columns" :key="column">
            <a v-if="column === '巡查单号'" class="link" @click="openDetail(row)">{{ row[column] ?? '—' }}</a>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无巡查任务数据，可先登记巡查单</td>
        </tr>
      </tbody>
    </table>

    <section v-if="batchResult" class="receipt-panel">
      <header class="receipt-head">
        <strong>批量作废回执</strong>
        <span :class="batchResult.ok ? 'ok-text' : 'error-text'">{{ batchResult.message }}</span>
        <span class="receipt-meta">批次 {{ batchResult.batch_key }}｜共 {{ batchResult.total }} 张，成功 {{ batchResult.success_count }}，失败 {{ batchResult.failed_count }}</span>
        <span class="receipt-spacer"></span>
        <button
          v-if="batchResult.failed_count > 0 || !batchResult.finished"
          class="btn"
          type="button"
          :disabled="batchLoading"
          @click="continueBatch"
        >
          {{ batchResult.finished ? '再次提交失败项' : '接着处理剩余单据' }}
        </button>
        <button class="btn ghost" type="button" @click="batchResult = null">关闭回执</button>
      </header>
      <table class="data-table receipt-table">
        <thead>
          <tr><th>巡查单号</th><th>结果</th><th>当前状态</th><th>说明 / 失败原因</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in batchResult.results" :key="String(item.id)">
            <td>{{ item.code }}</td>
            <td>
              <span :class="item.ok ? 'ok-text' : 'fail-text'">{{ item.ok ? '成功' : '失败' }}</span>
            </td>
            <td>{{ item.status || '—' }}</td>
            <td>{{ item.message }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal-card">
        <header class="modal-head">
          <strong>{{ detail['巡查单号'] }} 巡查单详情</strong>
          <button class="btn ghost" type="button" @click="detail = null">关闭</button>
        </header>
        <table class="data-table">
          <tbody>
            <tr v-for="column in columns" :key="column">
              <th>{{ column }}</th>
              <td>{{ detail[column] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <h4 class="log-title">流转 / 作废记录</h4>
        <ul v-if="detail.logs && detail.logs.length" class="log-list">
          <li v-for="(log, index) in detail.logs" :key="index">
            <span class="log-time">{{ log.time }}</span>
            <span class="log-action">{{ log.action }}</span>
            <span class="log-detail">{{ log.detail }}</span>
          </li>
        </ul>
        <p v-else class="empty-state">暂无流转记录</p>
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

type Row = Record<string, string | number | null>
type LogEntry = { action: string; time: string; detail: string }
type Receipt = { id: number | null; code: string; ok: boolean; status: string; message: string }
type BatchResponse = {
  ok: boolean
  message: string
  action: string
  batch_key: string
  total: number
  success_count: number
  failed_count: number
  finished: boolean
  results: Receipt[]
}
type Stats = { total: number; '待派发': number; '巡查中': number; '已提交': number; '已作废': number }

const ENDPOINT = '/api/patrol'
const VOID_ACTION = '作废巡查'
const RESUME_STORAGE_KEY = 'patrol:interrupted-batch'
const columns = ['巡查单号', '巡查路线', '巡查人员', '巡查日期', '巡查里程', '发现问题数', '巡查时长', '巡查状态']
const actions = ['派发巡查', '提交结果', '作废巡查']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const selectedIds = ref<number[]>([])
const batchLoading = ref(false)
const batchResult = ref<BatchResponse | null>(null)
const pendingResume = ref(false)
const detail = ref<(Row & { logs?: LogEntry[] }) | null>(null)

const stats = ref([
  { label: '待派发巡查', value: 0 },
  { label: '巡查中任务', value: 0 },
  { label: '已提交结果', value: 0 },
  { label: '已作废', value: 0 },
])

const currentPageIds = computed(() => rows.value.map((row) => Number(row.id)))
const allCurrentSelected = computed(
  () => currentPageIds.value.length > 0 && currentPageIds.value.every((id) => selectedIds.value.includes(id)),
)
const someCurrentSelected = computed(
  () => !allCurrentSelected.value && currentPageIds.value.some((id) => selectedIds.value.includes(id)),
)

function isSelected(id: number) {
  return selectedIds.value.includes(id)
}

function toggleSelect(id: number) {
  if (isSelected(id)) {
    selectedIds.value = selectedIds.value.filter((item) => item !== id)
  } else {
    selectedIds.value = [...selectedIds.value, id]
  }
}

function toggleSelectAll() {
  if (allCurrentSelected.value) {
    selectedIds.value = selectedIds.value.filter((id) => !currentPageIds.value.includes(id))
  } else {
    selectedIds.value = Array.from(new Set([...selectedIds.value, ...currentPageIds.value]))
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '巡查单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message || '巡查任务动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查任务操作失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('巡查单详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查单详情读取失败'
  }
}

// -- 批量作废：一次提交、逐条回执、中断续跑、同一批只算一次 -----------------------

async function postBatch(ids: number[]): Promise<BatchResponse> {
  const response = await request(`${ENDPOINT}/batch-actions`, {
    method: 'POST',
    body: JSON.stringify({ ids, action: VOID_ACTION }),
  })
  if (!response.ok) {
    throw new Error(`批量作废请求失败（${response.status}）`)
  }
  return (await response.json()) as BatchResponse
}

async function submitBatch() {
  const ids = [...selectedIds.value]
  if (!ids.length) {
    return
  }
  errorMessage.value = ''
  batchLoading.value = true
  try {
    const payload = await postBatch(ids)
    batchResult.value = payload
    if (!payload.finished) {
      localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify({ ids, batchKey: payload.batch_key }))
      pendingResume.value = true
    } else {
      localStorage.removeItem(RESUME_STORAGE_KEY)
      pendingResume.value = false
      selectedIds.value = []
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    // 请求未送达时同样保留批次，恢复网络后可接着走。
    localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify({ ids, batchKey: '' }))
    pendingResume.value = true
    errorMessage.value = error instanceof Error ? error.message : '批量作废未送达，可点击继续处理'
  } finally {
    batchLoading.value = false
  }
}

async function continueBatch() {
  const stored = readStoredBatch()
  if (stored) {
    return resumeWith(stored.ids)
  }
  // 没有中断批次时，就把回执里失败的几张重新提交一次（已作废的不会多留记录）。
  const failedIds = (batchResult.value?.results ?? [])
    .filter((item) => !item.ok && typeof item.id === 'number')
    .map((item) => item.id as number)
  if (!failedIds.length) {
    return
  }
  errorMessage.value = ''
  batchLoading.value = true
  try {
    const payload = await postBatch(failedIds)
    if (batchResult.value) {
      batchResult.value = mergeReceipts(batchResult.value, payload)
    } else {
      batchResult.value = payload
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    // 网络中断：把这批失败项记下来，重开页面也能接着走。
    localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify({ ids: failedIds, batchKey: '' }))
    pendingResume.value = true
    errorMessage.value = error instanceof Error ? error.message : '失败项重提未送达，可点击继续处理'
  } finally {
    batchLoading.value = false
  }
}

function mergeReceipts(previous: BatchResponse, latest: BatchResponse): BatchResponse {
  // 同一批再提交：保留首次成功的回执，失败项用最新回执覆盖。
  const byId = new Map<number, Receipt>()
  for (const item of previous.results) {
    if (typeof item.id === 'number') {
      byId.set(item.id, item)
    }
  }
  for (const item of latest.results) {
    if (typeof item.id === 'number') {
      byId.set(item.id, item)
    }
  }
  const results = [...byId.values()]
  const success_count = results.filter((item) => item.ok).length
  const failed_count = results.length - success_count
  const message = failed_count
    ? `批量作废完成：成功 ${success_count} 张，失败 ${failed_count} 张，详见逐条回执`
    : `批量作废完成：${success_count} 张巡查单全部作废成功`
  return {
    ...previous,
    ok: failed_count === 0,
    message,
    success_count,
    failed_count,
    finished: true,
    results,
  }
}

async function resumeWith(ids: number[]) {
  if (!ids.length) {
    return
  }
  errorMessage.value = ''
  batchLoading.value = true
  try {
    const payload = await postBatch(ids)
    batchResult.value = payload
    if (!payload.finished) {
      localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify({ ids, batchKey: payload.batch_key }))
      pendingResume.value = true
    } else {
      localStorage.removeItem(RESUME_STORAGE_KEY)
      pendingResume.value = false
      selectedIds.value = []
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify({ ids, batchKey: '' }))
    pendingResume.value = true
    errorMessage.value = error instanceof Error ? error.message : '批量作废未送达，可再次继续处理'
  } finally {
    batchLoading.value = false
  }
}

function readStoredBatch(): { ids: number[]; batchKey: string } | null {
  try {
    const raw = localStorage.getItem(RESUME_STORAGE_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as { ids?: unknown; batchKey?: unknown }
    if (!Array.isArray(parsed.ids) || !parsed.ids.every((id) => typeof id === 'number')) {
      return null
    }
    return { ids: parsed.ids, batchKey: String(parsed.batchKey ?? '') }
  } catch {
    return null
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('巡查单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查任务列表读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = (await response.json()) as Stats
    stats.value = [
      { label: '待派发巡查', value: payload['待派发'] ?? 0 },
      { label: '巡查中任务', value: payload['巡查中'] ?? 0 },
      { label: '已提交结果', value: payload['已提交'] ?? 0 },
      { label: '已作废', value: payload['已作废'] ?? 0 },
    ]
  } catch {
    // 统计读不出来时保留上一次数字，列表仍可正常使用。
  }
}

onMounted(async () => {
  await Promise.all([reload(), loadStats()])
  const stored = readStoredBatch()
  if (stored) {
    pendingResume.value = true
    // 页面重开后自动续跑中断批次，逐条回执补齐；已成功的不会重复作废。
    await resumeWith(stored.ids)
  }
})
</script>

<style scoped>
.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.batch-tip {
  color: var(--muted);
  font-size: 13px;
}
.select-all {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.check-col {
  width: 36px;
  text-align: center;
}
.btn.danger {
  color: #b42318;
  border-color: #f0a8a0;
}
.btn.warn {
  color: #b54708;
  border-color: #f5c28a;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.receipt-panel {
  margin-top: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.receipt-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}
.receipt-meta {
  color: var(--muted);
}
.receipt-spacer {
  flex: 1;
}
.receipt-table th,
.receipt-table td {
  font-size: 12px;
}
.ok-text {
  color: #067647;
}
.fail-text {
  color: #b42318;
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
  background: #fff;
  border-radius: 10px;
  width: 640px;
  max-width: 92vw;
  max-height: 86vh;
  overflow: auto;
  padding: 16px;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.log-title {
  margin: 14px 0 8px;
}
.log-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.log-list li {
  display: flex;
  gap: 10px;
  font-size: 12px;
  border-bottom: 1px dashed var(--border);
  padding-bottom: 6px;
}
.log-time {
  color: var(--muted);
  width: 140px;
}
.log-action {
  width: 72px;
  color: var(--brand);
}
.log-detail {
  flex: 1;
}
</style>
