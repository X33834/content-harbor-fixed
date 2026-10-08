import axios from 'axios'
import { ElMessage } from 'element-plus'

// dev 走 vite proxy(/api -> :8800)，生产构建后与 FastAPI 同源
const http = axios.create({
  baseURL: import.meta.env.DEV ? '/api' : '',
  timeout: 120000   // 发布/更新要开浏览器，慢是正常的
})

http.interceptors.response.use(
  r => r.data,
  err => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    return Promise.reject(err)
  }
)

export default http

// 所有长任务统一走任务引擎：提交返回 {task_id}，轮询 task() 看进度。
// 登录、发布、更新、同步、抓取都这么用，前端不再有第二套轮询逻辑。
export const api = {
  // ---------------- 总览 ----------------
  status: () => http.get('/status'),
  platforms: () => http.get('/platforms'),
  accounts: () => http.get('/accounts'),
  checkAccount: (platform, account = 'default') =>
    http.get(`/accounts/${platform}/check`, { params: { account } }),

  // ---------------- 账号 / 登录（统一任务语义） ----------------
  startLogin: (platform, account = 'default') =>
    http.post(`/accounts/${platform}/login`, { account, timeout: 300 }),
  assistOpen: (platform, url) =>
    http.post(`/accounts/${platform}/assist`, { url }),
  refresh: (platform) => http.post(`/refresh/${platform}`),

  // ---------------- 统一任务查询 ----------------
  tasks: (limit = 50, kind, status) =>
    http.get('/tasks', { params: { limit, kind, status } }),
  task: (taskId) => http.get(`/tasks/${taskId}`),
  resumeTask: (taskId, approved = true) =>
    http.post(`/tasks/${taskId}/resume`, { approved }),

  // ---------------- 文章 ----------------
  listArticles: (status) => http.get('/articles', { params: { status } }),
  getArticle: (id) => http.get(`/articles/${id}`),
  createArticle: (data) => http.post('/articles', data),
  updateArticle: (id, data) => http.put(`/articles/${id}`, data),
  search: (kw) => http.get(`/articles/search/${kw}`),

  // ---------------- 发布 / 更新 / 同步（统一任务语义） ----------------
  publish: (id, platforms, draftOnly = false, account = 'default', settings = {}) =>
    http.post(`/articles/${id}/publish`,
              { platforms, draft_only: draftOnly, account, settings }),
  update: (id, platforms, account = 'default') =>
    http.post(`/articles/${id}/update`, { platforms, account }),
  syncPending: (account = 'default') =>
    http.post('/sync/pending', { account }),

  publications: (articleId) => http.get('/publications', { params: { article_id: articleId } }),
  // 需要人工处理的发布实例（掘金草稿等人点"确定并发布"）
  pendingHuman: () => http.get('/pending-human'),

  // ---------------- AI 写稿 ----------------
  aiWrite: (data) => http.post('/ai/write', data),
  aiRewrite: (id, instruction, publishTo) =>
    http.post(`/articles/${id}/ai-rewrite`, { instruction, publish_to: publishTo }),
  aiPolish: (id) => http.post(`/articles/${id}/ai-polish`),
  aiStatus: () => http.get('/ai/status'),

  jobs: () => http.get('/jobs')
}
