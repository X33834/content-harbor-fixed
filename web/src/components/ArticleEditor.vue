<template>
  <div class="pane" style="height:100%">
    <div class="pane-head editor-head">
      <span class="title">{{ article.id ? '#' + article.id : '新文章' }}</span>
      <el-tag v-if="dirty" size="small" type="warning" effect="dark" class="dirty-tag">未保存</el-tag>
      <span class="spacer" />

      <!-- 视图切换（编辑/分屏/预览）+ AI 动作，全部收进一个「视图与 AI」下拉，避免平铺堆叠 -->
      <el-dropdown trigger="click" @command="onMore">
        <el-button size="small" :icon="Menu" class="more-btn">
          <span class="btxt">视图与 AI</span>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item divided command="edit" :icon="Edit"
                               :class="{ 'is-active-cmd': view === 'edit' }">编辑</el-dropdown-item>
            <el-dropdown-item command="split" :icon="Operation"
                               :class="{ 'is-active-cmd': view === 'split' }">分屏</el-dropdown-item>
            <el-dropdown-item command="preview" :icon="View"
                               :class="{ 'is-active-cmd': view === 'preview' }">预览</el-dropdown-item>
            <el-dropdown-item divided command="rewrite" :icon="Aim">AI 改写</el-dropdown-item>
            <el-dropdown-item command="polish" :icon="Brush">AI 润色</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 发布会先自动保存（不需要"先保存再发布"），loading 由 store 驱动 -->
      <el-button size="small" :icon="Promotion" :loading="hub.publishing" @click="$emit('publish')">
        <span class="btxt">发布</span>
      </el-button>

      <el-button v-if="hub.updatable.length" size="small" :icon="Refresh"
                 :loading="hub.publishing" @click="$emit('sync-update')">
        <span class="btxt">同步更新</span>
      </el-button>

      <el-button size="small" type="primary" :icon="Check" :loading="saving" @click="$emit('save')">
        <span class="btxt">保存</span>
      </el-button>
    </div>

    <div class="pane-body editor-body">
      <el-input
        v-model="article.title"
        size="large"
        placeholder="文章标题"
        class="title-input"
        @input="touch"
      />

      <el-input
        v-model="article.summary"
        type="textarea"
        :rows="2"
        placeholder="摘要（可选，部分平台用它当描述）"
        @input="touch"
      />

      <div class="meta-row">
        <el-input v-model="article.tags" placeholder="标签，逗号分隔" class="tags-input" :prefix-icon="PriceTag" @input="touch" />
        <el-select v-model="article.status" class="status-sel" @change="touch">
          <el-option label="草稿" value="draft" />
          <el-option label="已发布" value="published" />
          <el-option label="待审" value="review" />
          <el-option label="归档" value="archived" />
        </el-select>
        <span class="spacer" />
        <span class="meta-chip">
          {{ chars }} 字 · 约 {{ Math.ceil(chars / 350) }} 分钟读完
        </span>
      </div>

      <!-- Markdown 编辑器（md-editor-v3）：编辑/分屏/预览三态对应 preview=false/true/'preview' -->
      <div class="md-wrap">
        <MdEditor
          v-model="article.content_md"
          :preview="editorPreview"
          :theme="'dark'"
          language="zh-CN"
          :toolbars="toolbars"
          class="md-editor"
          @on-change="touch"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { MdEditor } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'
import { Check, PriceTag, Aim, Brush, Menu, Edit, Operation, View, Promotion, Refresh } from '@element-plus/icons-vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useHubStore } from '@/stores/hub'

const props = defineProps({
  article: { type: Object, default: null },
  isNew: Boolean,
  dirty: Boolean,
  saving: Boolean
})
const hub = useHubStore()
const emit = defineEmits(['save', 'touch', 'ai-rewrite', 'ai-polish', 'publish', 'sync-update'])

const { isMobile } = useBreakpoint()
// 手机默认只看编辑，分屏两栏根本没法用；桌面默认分屏
const view = ref(isMobile.value ? 'edit' : 'split')
// 用响应式断点监听：从桌面拖窄到手机时，若还停在分屏就切回编辑
watch(isMobile, m => { if (m && view.value === 'split') view.value = 'edit' })

// 编辑=纯编辑 / 分屏=左编右览 / 预览=纯预览（对应 md-editor-v3 的 preview prop）
const editorPreview = computed(() =>
  view.value === 'edit' ? false : view.value === 'preview' ? 'preview' : true)

// 常用工具栏（砍掉导入导出/目录等低频项，保持轻量）
const toolbars = ref(['bold', 'italic', 'strikethrough', 'heading',
  'quote', 'ul', 'ol', 'code', 'link', 'image', 'table',
  'revoke', 'next', 'preview', 'expand'])

const chars = computed(() => (props.article?.content_md || '').length)
const touch = () => emit('touch')

// 「视图与 AI」下拉：命令分发
function onMore(cmd) {
  switch (cmd) {
    case 'edit': view.value = 'edit'; break
    case 'split': view.value = 'split'; break
    case 'preview': view.value = 'preview'; break
    case 'rewrite': emit('ai-rewrite'); break
    case 'polish': emit('ai-polish'); break
  }
}
</script>

<style scoped lang="scss">
.is-active-cmd {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.dirty-tag {
  animation: popIn .2s var(--ease-out);
}
.title-input :deep(.el-input__inner) {
  font-size: var(--fs-xl);
  font-weight: 600;
  letter-spacing: -.01em;
}

.editor-body {
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.meta-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.tags-input { max-width: 300px; }
.status-sel { width: 116px; }
.meta-row .spacer { flex: 1; }

// Markdown 编辑器容器撑满剩余高度
.md-wrap { flex: 1; min-height: 0; }

// 让 md-editor-v3 融入"夜墨金箔"暗色体系
.md-editor {
  height: 100%;

  :deep() {
    // 编辑器本体
    --md-bk-color: var(--surface);
    --md-bk-color-light: var(--surface-2);
    --md-bk-color-dark: var(--surface-3);
    --md-border-color: var(--line);
    --md-color: var(--tx-2);
    --md-hover-bg-color: var(--surface-3);
    --md-active-bg-color: var(--surface-3);
    --md-accent-color: var(--accent);
    --md-accent-color-light: var(--accent-soft);
    --md-accent-color-dark: var(--accent-hi);
    --md-code-bk-color: var(--surface-3);
    --md-content-bk-color: var(--surface);
    --md-meta-color: var(--tx-4);
    --md-scrollbar-bg-color: transparent;
    --md-scrollbar-thumb-bg-color: var(--line-strong);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
  }
}
</style>
