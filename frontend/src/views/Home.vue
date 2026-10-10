<template>
  <div class="home-container">
    <div class="page-header"><div class="hero-icon">✈️</div><h1>智能旅行助手</h1><p>基于 AI 的个性化旅行规划，让每一次出行都更从容</p></div>
    <a-card :bordered="false" class="form-card">
      <a-form :model="form" layout="vertical" @finish="submit">
        <div class="form-section"><div class="section-title">📍 目的地与日期</div><a-row :gutter="16">
          <a-col :xs="24" :md="8"><a-form-item label="目的地城市" name="destination" :rules="[{required:true,message:'请输入目的地城市'}]"><a-input v-model:value="form.destination" size="large" placeholder="例如：杭州" /></a-form-item></a-col>
          <a-col :xs="24" :md="6"><a-form-item label="开始日期" name="start_date" :rules="[{required:true,message:'请选择开始日期'}]"><a-date-picker v-model:value="form.start_date" size="large" style="width:100%" /></a-form-item></a-col>
          <a-col :xs="24" :md="6"><a-form-item label="结束日期" name="end_date" :rules="[{required:true,message:'请选择结束日期'}]"><a-date-picker v-model:value="form.end_date" size="large" style="width:100%" /></a-form-item></a-col>
          <a-col :xs="24" :md="4"><a-form-item label="旅行天数"><div class="days-display">{{ days }} 天</div></a-form-item></a-col>
        </a-row></div>
        <div class="form-section"><div class="section-title">⚙️ 规划偏好</div><a-row :gutter="16">
          <a-col :xs="24" :md="6"><a-form-item label="出行人数"><a-input-number v-model:value="form.travelers" :min="1" :max="20" size="large" style="width:100%" /></a-form-item></a-col>
          <a-col :xs="24" :md="6"><a-form-item label="预算（元）"><a-input-number v-model:value="form.budget" :min="0" size="large" style="width:100%" placeholder="不指定" /></a-form-item></a-col>
          <a-col :xs="24" :md="6"><a-form-item label="旅行节奏"><a-select v-model:value="form.pace" size="large" style="width:100%"><a-select-option value="relaxed">轻松</a-select-option><a-select-option value="normal">适中</a-select-option><a-select-option value="intensive">紧凑</a-select-option></a-select></a-form-item></a-col>
          <a-col :xs="24" :md="6"><a-form-item label="酒店等级"><a-select v-model:value="form.hotel_level" size="large" style="width:100%"><a-select-option value="不指定">不指定</a-select-option><a-select-option value="budget">经济型</a-select-option><a-select-option value="three_star">三星</a-select-option><a-select-option value="four_star">四星</a-select-option><a-select-option value="five_star">五星</a-select-option></a-select></a-form-item></a-col>
        </a-row><a-form-item label="旅行偏好"><a-checkbox-group v-model:value="form.preferences"><a-checkbox v-for="item in preferences" :key="item" :value="item">{{ item }}</a-checkbox></a-checkbox-group></a-form-item><a-form-item label="饮食偏好"><a-input v-model:value="dietaryText" placeholder="例如：不吃辣、海鲜过敏" /></a-form-item></div>
        <div class="form-section"><div class="section-title">💬 额外要求</div><a-textarea v-model:value="form.special_notes" :rows="3" placeholder="例如：希望安排亲子友好的景点，节奏不要太紧" /></div>
        <a-button type="primary" html-type="submit" block size="large" :loading="loading">{{ loading ? loadingStatus : '🚀 开始规划我的旅行' }}</a-button>
        <a-progress v-if="loading" :percent="progress" status="active" class="progress" />
      </a-form>
    </a-card>
  </div>
</template>
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import dayjs, { type Dayjs } from 'dayjs'
import { generateTrip } from '@/services/api'
import { normalizeItinerary, type HotelLevel, type Pace, type TripRequest } from '@/types'
const router = useRouter(); const loading = ref(false); const progress = ref(0); const loadingStatus = ref('正在生成行程…'); const dietaryText = ref('')
const preferences = ['历史文化','自然风光','美食','购物','艺术','亲子','休闲'];
const form = reactive({ destination:'', start_date:null as Dayjs|null, end_date:null as Dayjs|null, travelers:1, budget:null as number|null, pace:'normal' as Pace, hotel_level:'不指定' as HotelLevel, preferences:[] as string[], special_notes:'' })
const days = computed(() => form.start_date && form.end_date ? form.end_date.diff(form.start_date,'day') + 1 : 0)
watch([() => form.start_date, () => form.end_date], () => { if (days.value > 7) { message.warning('行程必须为 3 至 7 天'); form.end_date = null } else if (days.value > 0 && days.value < 3) { message.warning('行程至少需要 3 天'); form.end_date = null } })
async function submit() { if (!form.start_date || !form.end_date || days.value < 3 || days.value > 7) return message.error('请选择有效的 3 至 7 天日期范围'); loading.value=true; progress.value=10; const timer=window.setInterval(()=>{ progress.value=Math.min(progress.value+10,90); loadingStatus.value=progress.value<50?'正在准备旅行约束…':progress.value<80?'MoMA 正在生成每日安排…':'正在等待地图和天气补全，首次生成可能需要 1 至 3 分钟…' },600); try { const request: TripRequest={ destination:form.destination,start_date:form.start_date.format('YYYY-MM-DD'),end_date:form.end_date.format('YYYY-MM-DD'),travelers:form.travelers,budget:form.budget,preferences:form.preferences,pace:form.pace,dietary_preferences:dietaryText.value?dietaryText.value.split(/[，,、]/).map(v=>v.trim()).filter(Boolean):[],hotel_level:form.hotel_level,special_notes:form.special_notes||null }; const itinerary=normalizeItinerary(await generateTrip(request)); sessionStorage.setItem('itinerary',JSON.stringify(itinerary)); progress.value=100; message.success('旅行计划生成成功'); await router.push('/result') } catch(e) { message.error(e instanceof Error?e.message:'生成失败，请稍后重试') } finally { clearInterval(timer); loading.value=false; progress.value=0 } }
</script>
<style scoped>
.home-container{min-height:calc(100vh - 160px);padding:36px 12px;background:linear-gradient(135deg,#667eea,#764ba2);margin:-24px}.page-header{text-align:center;color:#fff;margin:10px auto 28px}.page-header h1{font-size:32px;margin:8px 0}.page-header p{margin:0}.hero-icon{font-size:40px}.form-card{max-width:1100px;margin:auto;border-radius:12px}.form-section{padding:8px 0 18px;border-bottom:1px solid #f0f0f0;margin-bottom:18px}.section-title{font-size:17px;font-weight:700;margin-bottom:18px}.days-display{height:40px;line-height:40px;color:#1677ff;font-weight:700}.progress{margin-top:16px}@media(max-width:640px){.home-container{margin:-12px;padding:24px 8px}.page-header h1{font-size:26px}}
</style>
