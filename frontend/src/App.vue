<template>
  <a-layout class="app-layout">
    <a-layout-header class="app-header"><div class="brand">🌍 觅旅 · 智能旅行助手</div></a-layout-header>
    <a-layout-content class="app-content"><router-view /></a-layout-content>
    <a-layout-footer class="app-footer">觅旅 MiliTravel · 基于 MoMA 的智能旅行规划</a-layout-footer>
  </a-layout>
</template>
<style>
#app,.app-layout{min-height:100vh}.app-header{padding:0 50px;background:#001529}.brand{color:#fff;font-size:24px;font-weight:700}.app-content{padding:24px}.app-footer{text-align:center}
@media (max-width: 640px){.app-header{padding:0 20px}.brand{font-size:18px}.app-content{padding:12px}}
</style>
