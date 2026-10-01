<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th><th>已作废</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
          <td>{{ row.voided }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type ModuleRow = { name: string; created: number; pending: number; abnormal: number; voided: number }
type Overview = {
  cards: { label: string; value: number }[]
  modules: ModuleRow[]
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])

function fallbackModules(): ModuleRow[] {
  const names = ['管段档案', '检查井', '阀门井室', '泵站设施', '巡查任务', '缺陷登记', '内窥检测', '修复施工', '压力监测', '流量监测', '泄漏排查', '清淤疏浚', '养护材料', '养护机械', '占道许可', '公众诉求', '养护资金', '管网档案']
  return names.map((name) => ({ name, created: 0, pending: 0, abnormal: 0, voided: 0 }))
}

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
  } catch {
    cards.value = [
      { label: '业务模块', value: 0 },
      { label: '今日新增', value: 0 },
      { label: '待处理', value: 0 },
      { label: '异常量', value: 0 },
      { label: '已作废', value: 0 },
    ]
    moduleRows.value = fallbackModules()
  }
})
</script>
