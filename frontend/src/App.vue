<template>
  <a-layout class="app-layout">
    <TopNav />
    <a-layout-content class="app-content"><router-view /></a-layout-content>
    <a-layout-footer class="app-footer">觅旅 MiliTravel · 基于 MoMA 的智能旅行规划</a-layout-footer>
  </a-layout>
</template>
<script setup lang="ts">
import TopNav from './components/TopNav.vue'
</script>
<style>
#app,.app-layout{min-height:100vh}.app-layout{background:linear-gradient(135deg,#cbd5ff 0%,#e8dcfa 48%,#cbb9ef 100%);background-attachment:fixed}.app-header{height:auto;min-height:0;padding:0;background:transparent;line-height:normal}.app-content{padding:24px}.app-footer{text-align:center;background:transparent;color:#514d7d}
:root{--brand-start:#cbd5ff;--brand-end:#cbb9ef;--brand-ink:#46527a;--brand-soft:#eeeaff}
body{margin:0;background:#d9d8f4;color:#27324a}
:where(.ant-btn).ant-btn-primary{border-color:rgba(93,83,164,.18);color:#46527a;background:linear-gradient(110deg,var(--brand-start),var(--brand-end));box-shadow:0 6px 14px rgba(93,83,164,.16)}
:where(.ant-btn).ant-btn-primary:not(:disabled):hover{border-color:rgba(93,83,164,.28);color:#364264;background:linear-gradient(110deg,#d5ddff,#d2c1f2)}
:where(.ant-input,.ant-input-number,.ant-picker,.ant-select-selector):focus,:where(.ant-input-affix-wrapper-focused,.ant-input-number-focused,.ant-picker-focused,.ant-select-focused) .ant-input-number,.ant-select-selector{border-color:var(--brand-start)!important;box-shadow:0 0 0 2px rgba(102,126,234,.12)!important}
.ant-checkbox-checked .ant-checkbox-inner,.ant-radio-checked .ant-radio-inner{background-color:var(--brand-start);border-color:var(--brand-start)}
@media (max-width: 640px){.app-content{padding:12px}}
</style>
