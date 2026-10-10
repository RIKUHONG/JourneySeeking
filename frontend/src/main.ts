import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import Home from './views/Home.vue'
import Result from './views/Result.vue'

const router = createRouter({ history: createWebHistory(), routes: [{ path: '/', component: Home }, { path: '/result', component: Result }] })
createApp(App).use(router).use(Antd).mount('#app')
