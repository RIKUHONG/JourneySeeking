<template>
  <header class="top-nav">
    <div class="title">觅旅 MiliTravel</div>
    <nav class="switcher" aria-label="页面切换">
      <RouterLink to="/" :class="{ active: route.path === '/' }">规划页</RouterLink>
      <RouterLink to="/result" :class="{ active: route.path === '/result' }">结果页</RouterLink>
      <RouterLink to="/history" :class="{ active: route.path === '/history' }">历史列表</RouterLink>
    </nav>
  </header>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<style scoped>
.top-nav { width: min(1100px, calc(100% - 24px)); box-sizing: border-box; margin: 18px auto 0; padding: 22px 24px 18px; border-radius: 28px; color: #46527a; text-align: center; background: linear-gradient(135deg, #cbd5ff, #e8dcfa 48%, #cbb9ef); box-shadow: 0 16px 36px rgba(93, 83, 164, .16); }
.eyebrow { display: inline-block; padding: 5px 14px; border-radius: 999px; background: rgba(255,255,255,.72); color: #59658e; font-size: 12px; font-weight: 700; letter-spacing: .3px; }
.title { margin: 8px 0 14px; font-size: 32px; font-weight: 800; letter-spacing: 1px; }
.switcher { display: inline-flex; gap: 4px; padding: 4px; border-radius: 999px; background: rgba(255,255,255,.14); }
.switcher a { min-width: 76px; padding: 7px 13px; border-radius: 999px; color: #59658e; font-size: 14px; font-weight: 700; text-decoration: none; transition: .2s ease; }
.switcher a:hover, .switcher a.active { color: #46527a; background: rgba(255,255,255,.76); }
@media (max-width: 640px) { .top-nav { margin: 10px 12px 0; padding: 16px 12px 14px; border-radius: 20px; } .title { font-size: 25px; } .switcher a { min-width: 64px; padding: 6px 8px; font-size: 13px; } }
</style>
