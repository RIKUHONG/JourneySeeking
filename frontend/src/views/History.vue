<template>
  <div class="history-page">
    <a-card :bordered="false" class="intro">
      <div>
        <h1>历史行程</h1>
        <p>这里会展示已经保存到后端数据库的 itinerary 摘要。</p>
      </div>
      <div class="intro-actions"><a-button @click="router.push('/')">返回规划页</a-button><a-button type="primary" :loading="loading" @click="loadHistory">刷新列表</a-button></div>
    </a-card>

    <a-spin :spinning="loading">
      <a-empty v-if="!loading && !items.length" description="还没有保存的行程" />
      <div v-else class="trip-grid">
        <a-card v-for="item in items" :key="item.trip_id" :bordered="false" class="trip-card">
          <div class="card-heading"><h2>{{ item.destination }}</h2><a-tag color="geekblue">v{{ item.version }}</a-tag></div>
          <div class="trip-id">{{ item.trip_id }}</div>
          <p class="dates">{{ item.start_date }} 至 {{ item.end_date }}</p>
          <p class="summary">{{ item.summary || '暂无行程摘要' }}</p>
          <div class="card-actions">
            <a-button type="primary" block @click="openTrip(item.trip_id)">查看详情</a-button>
            <a-popconfirm title="确定删除这条行程吗？" ok-text="删除" cancel-text="取消" @confirm="removeTrip(item.trip_id)">
              <a-button danger block :loading="deleting === item.trip_id">删除行程</a-button>
            </a-popconfirm>
          </div>
        </a-card>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { deleteTrip, getTrip, listTrips } from '@/services/api'
import type { TripSummary } from '@/types'

const router = useRouter()
const items = ref<TripSummary[]>([])
const loading = ref(false)
const deleting = ref('')

async function loadHistory() {
  loading.value = true
  try { items.value = (await listTrips()).items } catch (e) { message.error(e instanceof Error ? e.message : '历史行程加载失败') } finally { loading.value = false }
}
async function openTrip(id: string) {
  try { sessionStorage.setItem('itinerary', JSON.stringify(await getTrip(id))); await router.push('/result') } catch (e) { message.error(e instanceof Error ? e.message : '行程打开失败') }
}
async function removeTrip(id: string) {
  deleting.value = id
  try { await deleteTrip(id); items.value = items.value.filter(item => item.trip_id !== id); message.success('行程已删除') } catch (e) { message.error(e instanceof Error ? e.message : '删除失败') } finally { deleting.value = '' }
}
onMounted(loadHistory)
</script>

<style scoped>
.history-page { max-width: 1120px; margin: 0 auto; }
.intro { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; border-radius: 18px; }
.intro h1 { margin: 0 0 6px; color: #27345f; font-size: 28px; }
.intro p { margin: 0; color: #7b8496; }
.intro-actions { display: flex; gap: 10px; }
.trip-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.trip-card { border-radius: 18px; box-shadow: 0 8px 24px rgba(80, 91, 160, .08); }
.card-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card-heading h2 { margin: 0; color: #263c78; font-size: 23px; }
.trip-id, .dates { color: #8992a5; font-size: 13px; }
.trip-id { margin-top: 5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.summary { min-height: 48px; margin: 14px 0; color: #566176; line-height: 1.7; }
.card-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 680px) { .intro { align-items: flex-start; flex-direction: column; gap: 14px; } .intro-actions { width: 100%; } .intro-actions .ant-btn { flex: 1; } .trip-grid { grid-template-columns: 1fr; } }
</style>
