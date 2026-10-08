import { createApp } from 'vue'
import { createPinia } from 'pinia'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import './styles/main.scss'

import App from './App.vue'

const app = createApp(App)

// 组件、样式、图标全部走 vite 按需解析（见 vite.config.js 的 unplugin），
// 不再 app.use(ElementPlus) 全量注册，也不再循环注册 300+ 图标——
// 模板里用到的组件由 unplugin-vue-components 自动按需引入并带样式。
// 中文化交给 <el-config-provider>（见 App.vue），语言包只引 zh-cn 一份。
app.use(createPinia())
app.mount('#app')
