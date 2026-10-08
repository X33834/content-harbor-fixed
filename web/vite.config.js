import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ command }) => ({
  plugins: [
    vue(),
    // 按需引入 Element Plus：模板里的 <el-xxx> 自动导入对应组件 + 样式，
    // 不再全量打包。ElMessage / ElMessageBox 在业务代码里显式具名 import
    // （树摇友好，不会拉全量），这里只管模板组件与样式。
    Components({
      resolvers: [ElementPlusResolver({ importStyle: 'css' })]
    })
  ],

  // build 产物落在 FastAPI 的 /static 下，所以静态资源必须带 /static/ 前缀，
  // 否则 index.html 会去请求 /assets/xxx.js —— 那个路径后端没挂，直接 404。
  base: command === 'build' ? '/static/' : '/',

  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },

  build: {
    outDir: '../server/static',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // 第三方依赖单独切出来，业务代码改动时浏览器缓存不失效
        manualChunks: {
          vue: ['vue', 'pinia', 'axios'],
          element: ['element-plus', '@element-plus/icons-vue'],
          md: ['markdown-it']
        }
      }
    }
  },

  server: {
    // dev 模式代理后端，避免 CORS
    proxy: {
      '/api': { target: 'http://127.0.0.1:8800', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') }
    }
  }
}))
