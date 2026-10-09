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

  // ---------------- AI Provider / 模型选择 ----------------
  aiProviders: () => http.get('/ai/providers'),

  // ---------------- AI 写稿 ----------------
  aiWrite: (data) => http.post('/ai/write', data),
  aiRewrite: (id, instruction, publishTo, model, provider) =>
    http.post(`/articles/${id}/ai-rewrite`, {
      instruction, publish_to: publishTo,
      model: model || '', preferred_provider: provider || ''
    }),
  aiPolish: (id, model, provider) =>
    http.post(`/articles/${id}/ai-polish`, {
      model: model || '', preferred_provider: provider || ''
    }),
  aiStatus: () => http.get('/ai/status'),

  // ---------------- AI 增强工具 ----------------
  aiTranslate: (id, lang = 'en', model, provider) => http.post(`/articles/${id}/ai-translate`, {
    model: model || '', preferred_provider: provider || ''
  }, { params: { target_lang: lang } }),
  aiImagePrompts: (id, n = 3, model, provider) => http.get(`/articles/${id}/ai-image-prompts`, {
    params: { n, model: model || undefined, preferred_provider: provider || undefined }
  }),
  aiOutline: (id) => http.get(`/articles/${id}/ai-outline`),
  aiSeo: (id) => http.get(`/articles/${id}/ai-seo`),
  cloneArticle: (id) => http.post(`/articles/${id}/clone`),
  aiTemplates: () => http.get('/ai/templates'),
  aiWriteTemplate: (data) => http.post('/ai/write-template', null, { params: data }),

  // ---------------- 版本历史 ----------------
  versions: (id, limit = 50) => http.get(`/articles/${id}/versions`, { params: { limit } }),
  version: (id, vid) => http.get(`/articles/${id}/versions/${vid}`),
  versionDiff: (id, v1, v2) => http.get(`/articles/${id}/versions/diff`, { params: { v1, v2 } }),
  rollback: (id, vid) => http.post(`/articles/${id}/versions/${vid}/rollback`),

  // ---------------- 定时发布调度器 ----------------
  schedules: (includeDisabled = false) => http.get('/schedules', { params: { include_disabled: includeDisabled } }),
  createSchedule: (data) => http.post('/schedules', data),
  updateSchedule: (sid, data) => http.put(`/schedules/${sid}`, data),
  pauseSchedule: (sid) => http.post(`/schedules/${sid}/pause`),
  resumeSchedule: (sid) => http.post(`/schedules/${sid}/resume`),
  triggerSchedule: (sid) => http.post(`/schedules/${sid}/trigger`),
  deleteSchedule: (sid) => http.delete(`/schedules/${sid}`),

  // ---------------- 标签治理 ----------------
  tags: (limit = 50, category) => http.get('/tags', { params: { limit, category } }),
  tagsTrending: (limit = 10) => http.get('/tags/trending', { params: { limit } }),
  syncTags: () => http.post('/tags/sync'),
  renameTag: (oldName, newName) => http.post('/tags/rename', null, { params: { old: oldName, new: newName } }),
  mergeTag: (from, to) => http.post('/tags/merge', null, { params: { _from: from, to } }),
  addTagAlias: (alias, canonical) => http.post('/tags/alias', null, { params: { alias, canonical } }),
  suggestTags: (title, contentMd) => http.post('/tags/suggest', null, { params: { title, content_md: contentMd } }),

  jobs: () => http.get('/jobs'),

  // ---------------- 内容质检 ----------------
  qaArticle: (aid) => http.post(`/articles/${aid}/qa`),
  qaAnalyze: (contentMd, title, summary, tags) =>
    http.post('/qa/analyze', { content_md: contentMd, title, summary, tags }),

  // ---------------- Webhook / 事件通知 ----------------
  webhooks: () => http.get('/webhooks'),
  createWebhook: (data) => http.post('/webhooks', data),
  updateWebhook: (wid, data) => http.put(`/webhooks/${wid}`, data),
  deleteWebhook: (wid) => http.delete(`/webhooks/${wid}`),
  testWebhook: (wid) => http.post(`/webhooks/${wid}/test`),
  notifications: (since, limit = 50) =>
    http.get('/notifications', { params: { since, limit } })
}
