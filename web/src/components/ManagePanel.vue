<template>
  <div class="pane manage">
    <div class="pane-head">
      <span class="title">发布管理</span>
      <span class="spacer" />
      <el-button size="small" text :icon="Refresh" :loading="reloading" @click="reloadAll">刷新全部</el-button>
    </div>

    <div class="pane-body">
      <el-tabs v-model="tab">
        <!-- 需要人工 -->
        <el-tab-pane name="human">
          <template #label>
            需要人工
            <el-badge v-if="hub.pendingHuman.length + hub.waitingTasks.length"
                      :value="hub.pendingHuman.length + hub.waitingTasks.length"
                      type="warning" class="tab-badge" />
          </template>

          <!-- 任务挂起等人工（统一任务引擎 waiting_human） -->
          <div v-if="hub.waitingTasks.length" class="human-grid">
            <div v-for="t in hub.waitingTasks" :key="t.task_id" class="human-card run-card">
              <div class="hc-head">
                <el-tag size="small" type="danger" effect="dark">{{ t.kind }}</el-tag>
                <el-tag size="small" effect="plain">{{ (t.platforms || []).join('、') || '?' }}</el-tag>
                <span class="hc-title">{{ t.article_id ? `文章 #${t.article_id}` : '平台任务' }}</span>
              </div>
              <div class="hc-sub">
                {{ t.message || '任务挂起，等待人工处理' }}
                <div v-if="t.error" class="hc-err">{{ t.error }}</div>
              </div>
              <div class="hc-ops">
                <el-button size="small" type="primary"
                           :loading="resuming === t.task_id"
                           @click="doResume(t, true)">已处理，继续</el-button>
                <el-button size="small" text @click="doResume(t, false)">放弃</el-button>
                <el-button size="small" text @click="showTask(t)">详情</el-button>
              </div>
            </div>
          </div>

          <!-- 发布实例 pending_human（平台草稿等人点发布） -->
          <div v-if="hub.pendingHuman.length" class="human-grid" style="margin-top:12px">
            <div v-for="it in hub.pendingHuman" :key="it.platform + it.article_id" class="human-card">
              <div class="hc-head">
                <el-tag size="small" type="warning" effect="dark">{{ it.platform }}</el-tag>
                <span class="hc-title">{{ it.title || '未命名文章' }}</span>
              </div>
              <div class="hc-sub">自动化已完成到草稿，差最后一步人工发布（登录后点「确定并发布」）</div>
              <div class="hc-ops">
                <el-button size="small" type="warning" @click="goHandle(it)">打开草稿去发布</el-button>
                <el-button size="small" text @click="hub.loadPendingHuman()">我处理完了，刷新</el-button>
              </div>
            </div>
          </div>
          <EmptyState v-if="!hub.pendingHuman.length && !hub.waitingTasks.length"
                      title="没有等待人工的任务"
                      desc="全自动发布顺利时这里一直是空的；掘金等平台需要人工收尾或任务挂起时会出现在这里"
                      :px="72" />
        </el-tab-pane>

        <!-- 任务记录（统一任务引擎全史） -->
        <el-tab-pane label="任务记录" name="tasks">
          <el-table v-if="hub.tasks.length" :data="hub.tasks" size="default" max-height="620"
                    @row-click="showTask" row-style="cursor:pointer">
            <el-table-column label="任务" width="150">
              <template #default="{ row }"><span class="dim">{{ row.task_id }}</span></template>
            </el-table-column>
            <el-table-column label="类型" width="90">
              <template #default="{ row }">{{ kindText(row.kind) }}</template>
            </el-table-column>
            <el-table-column label="对象" min-width="160">
              <template #default="{ row }">
                {{ row.article_id ? ('文章 #' + row.article_id) : '' }}
                {{ (row.platforms || []).join('、') }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="taskTagType(row.status)" effect="dark">
                  {{ taskTagText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="180">
              <template #default="{ row }">
                <span v-if="row.message" class="dim">{{ row.message }}</span>
                <span v-else-if="row.error" class="run-err">{{ row.error.slice(0, 40) }}</span>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
            </el-table-column>
          </el-table>
          <EmptyState v-else title="还没有任务" desc="发布、更新、登录、同步都会产生任务记录" :px="96" />
        </el-tab-pane>

        <!-- 发布记录 -->
        <el-tab-pane label="发布记录" name="pubs">
          <el-table v-if="hub.allPubs.length" :data="hub.allPubs" size="default" max-height="620">
            <el-table-column label="文章" min-width="220">
              <template #default="{ row }">
                <span class="p-title">{{ row.title || ('#' + row.article_id) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="平台" width="90">
              <template #default="{ row }">{{ row.platform }}</template>
            </el-table-column>
            <el-table-column label="状态" width="96">
              <template #default="{ row }">
                <el-tag size="small" :type="tagType(row.status)" effect="dark">{{ tagText(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="链接" min-width="160">
              <template #default="{ row }">
                <a v-if="row.post_url" class="p-link" :href="row.post_url" target="_blank" rel="noopener">打开文章</a>
                <a v-else-if="row.edit_url" class="p-link" :href="row.edit_url" target="_blank" rel="noopener">打开编辑页</a>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
            </el-table-column>
          </el-table>
          <EmptyState v-else title="还没有发布记录" :px="96" />
        </el-tab-pane>

        <!-- 平台与账号 -->
        <el-tab-pane label="平台与账号" name="accounts">
          <div class="acct-grid">
            <div v-for="p in hub.platforms" :key="p.id" class="acct-card">
              <div class="ac-top">
                <b class="ac-name">{{ p.name }}</b>
                <el-tag size="small" :type="acctState(p.id) ? 'success' : 'info'" effect="dark">
                  {{ acctState(p.id) ? '在线' : '离线' }}
                </el-tag>
              </div>
              <div class="ac-sub">{{ p.needs_browser ? '需要浏览器登录（扫码一次长期有效）' : '免登 API，凭据在 config.json' }}</div>
              <el-button
                v-if="p.needs_browser" size="small" text type="primary"
                :loading="hub.loginTasks[p.id]?.status === 'running'"
                @click="hub.startLogin(p.id)"
              >{{ hub.loginTasks[p.id]?.status === 'running' ? '等待扫码…' : (acctState(p.id) ? '重新登录' : '去登录') }}</el-button>
              <el-button size="small" text :loading="refreshingId === p.id"
                         @click="doRefresh(p)">抓取文章入库</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 任务详情：平台结果 + 失败原因 -->
    <el-dialog v-model="taskDialog" :title="`任务 ${taskDetail?.task_id || ''}`" width="640px">
      <template v-if="taskDetail">
        <div class="rd-meta">
          <el-tag size="small" :type="taskTagType(taskDetail.status)" effect="dark">
            {{ taskTagText(taskDetail.status) }}
          </el-tag>
          <span class="dim">{{ kindText(taskDetail.kind) }} ·
            {{ taskDetail.article_id ? ('文章 #' + taskDetail.article_id) : '' }}
            {{ (taskDetail.platforms || []).join('、') }}</span>
          <span v-if="taskDetail.attempts" class="dim">尝试 {{ taskDetail.attempts }} 次</span>
        </div>

        <div v-if="taskDetail.result?.human_task" class="rd-sec rd-human">
          <b>⏸ 人工任务</b>
          <div>{{ taskDetail.result.human_task.message }}</div>
          <div v-if="taskDetail.result.human_task.edit_url" class="dim">
            <a :href="taskDetail.result.human_task.edit_url" target="_blank" class="p-link">
              {{ taskDetail.result.human_task.edit_url }}
            </a>
          </div>
        </div>

        <div v-if="Array.isArray(taskDetail.result) && taskDetail.result.length" class="rd-sec">
          <b>平台结果</b>
          <div v-for="(r, i) in taskDetail.result" :key="i" class="rd-line">
            <el-tag size="small" :type="r.ok ? 'success' : 'danger'" effect="plain">{{ r.platform }}</el-tag>
            <span v-if="r.warning" class="dim">需人工收尾</span>
            <span v-if="r.skipped" class="dim">已跳过（内容未变）</span>
            <span v-if="r.error" class="run-err">{{ r.error }}</span>
            <a v-if="r.post_url" class="p-link" :href="r.post_url" target="_blank">文章链接</a>
          </div>
        </div>

        <div v-if="taskDetail.error" class="rd-sec"><b>错误</b><div class="run-err">{{ taskDetail.error }}</div></div>
        <div v-if="taskDetail.message" class="rd-sec"><b>说明</b><div class="dim">{{ taskDetail.message }}</div></div>
      </template>
      <template #footer>
        <el-button @click="taskDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useHubStore } from '@/stores/hub'
import { api } from '@/api'
import EmptyState from './EmptyState.vue'

const hub = useHubStore()
const tab = ref('human')
const reloading = ref(false)
const resuming = ref('')          // 正在恢复的任务
const refreshingId = ref('')      // 正在抓取入库的平台
const taskDialog = ref(false)
const taskDetail = ref(null)      // 当前详情任务

onMounted(reloadAll)

async function reloadAll() {
  reloading.value = true
  try {
    await Promise.all([hub.loadPendingHuman(), hub.loadTasks(), hub.loadAllPubs(),
                       hub.loadStatus(), hub.loadPlatforms()])
  } finally { reloading.value = false }
}

async function doRefresh(p) {
  refreshingId.value = p.id
  try { await hub.refreshPlatform(p.id) } finally { refreshingId.value = '' }
}

function acctState(platform) {
  const a = hub.accounts.find(x => x.platform === platform)
  return a && a.status === 'logined'
}

const goHandle = (it) => it.edit_url && window.open(it.edit_url, '_blank', 'noopener')

async function doResume(task, approved) {
  if (!approved) {
    try {
      await ElMessageBox.confirm(
        `放弃「${task.kind} #${task.task_id}」这个任务？该平台会记为失败。`,
        '确认放弃', { type: 'warning', confirmButtonText: '放弃', cancelButtonText: '再想想' })
    } catch { return }
  }
  resuming.value = task.task_id
  try { await hub.resumeTask(task.task_id, approved) }
  finally { resuming.value = '' }
}

async function showTask(row) {
  try {
    taskDetail.value = await api.task(row.task_id)
  } catch { taskDetail.value = null }
  if (!taskDetail.value) return
  taskDialog.value = true
}

const kindText = (k) => ({
  publish: '发布', update: '更新', sync: '同步', refresh: '抓取',
  login: '登录', assist: '人工接管'
}[k] || k || '—')

const tagType = (s) =>
  s === 'ok' ? 'success' : s === 'failed' ? 'danger' : s === 'pending_human' ? 'warning' : 'info'
const tagText = (s) =>
  s === 'ok' ? '已发布' : s === 'failed' ? '失败' : s === 'pending_human' ? '待人工' : '待更新'

const taskTagType = (s) =>
  s === 'ok' ? 'success' : s === 'failed' ? 'danger'
  : s === 'waiting_human' ? 'warning' : 'info'
const taskTagText = (s) =>
  s === 'ok' ? '完成' : s === 'failed' ? '失败'
  : s === 'waiting_human' ? '等人工' : (s === 'running' ? '执行中' : '排队中')

const fmtTime = (ts) => {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<style scoped lang="scss">
.manage { height: 100%; }
.tab-badge { margin-left: 4px; }

.human-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.human-card {
  border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
  background: var(--line-soft);
  .hc-head { display: flex; align-items: center; gap: 10px; }
  .hc-title { font-size: var(--fs-md, 14px); color: var(--tx-1); overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; }
  .hc-sub { font-size: var(--fs-xs); color: var(--tx-3); margin: 8px 0 10px; }
  .hc-ops { display: flex; gap: 8px; }
}
.run-card { border-color: var(--warn, #e6a23c); }
.hc-err { color: var(--bad, #f56c6c); margin-top: 4px; word-break: break-all; }
.run-err { color: var(--bad, #f56c6c); font-size: var(--fs-xs); }

.rd-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.rd-sec { border-top: 1px solid var(--line); padding: 10px 0; font-size: var(--fs-xs);
  color: var(--tx-2); b { color: var(--tx-1); display: block; margin-bottom: 6px; } }
.rd-human { border-left: 3px solid var(--warn, #e6a23c); padding-left: 10px; }
.rd-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 4px 0; }

.p-title { color: var(--tx-1); }
.p-link { color: var(--accent-hi); text-decoration: none; &:hover { text-decoration: underline; } }
.dim { color: var(--tx-4); }

.acct-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.acct-card {
  border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
  .ac-top { display: flex; align-items: center; justify-content: space-between; }
  .ac-name { color: var(--tx-1); font-size: var(--fs-md, 14px); }
  .ac-sub { font-size: var(--fs-xs); color: var(--tx-3); margin: 8px 0; }
}
</style>
