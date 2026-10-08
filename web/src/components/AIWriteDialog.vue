<template>
  <el-dialog v-model="visible" title="AI 落笔" width="560px" :close-on-click-modal="false" class="ai-write-dialog">
    <el-alert v-if="!ready" type="warning" :closable="false" show-icon
              title="AI 未配置"
              description="在 config.json 或环境变量里填 AI_API_KEY / AI_BASE_URL / AI_MODEL 后重启后端即可。" />

    <el-form label-width="88px" style="margin-top:14px">
      <el-form-item label="主题" required>
        <el-input v-model="form.topic" placeholder="例如：用 Python 手写一个任务队列" />
      </el-form-item>
      <el-form-item label="文风">
        <el-select v-model="form.style" placeholder="默认：技术干货" style="width:100%">
          <el-option label="技术干货" value="技术干货，有代码示例" />
          <el-option label="通俗科普" value="通俗易懂，面向初学者" />
          <el-option label="观点评论" value="有观点、有论据的评论" />
          <el-option label="教程步骤" value="分步骤教程，可直接照做" />
        </el-select>
      </el-form-item>
      <el-form-item label="字数">
        <el-slider v-model="form.words" :min="600" :max="6000" :step="200" show-input />
      </el-form-item>
      <el-form-item label="标签提示">
        <el-input v-model="form.tags_hint" placeholder="可选，逗号分隔，例如：Python,后端" />
      </el-form-item>
      <el-form-item label="直接发布">
        <el-select v-model="form.publish_to" multiple placeholder="不选则只入库" style="width:100%">
          <el-option v-for="p in platforms" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" :disabled="!form.topic.trim()" @click="submit">
        开始落笔
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
:deep(.el-dialog__title) {
  font-family: var(--font-serif);
  font-weight: 600;
  letter-spacing: .02em;
}
</style>

<script setup>
import { ref, reactive, watch } from 'vue'
import { api } from '@/api'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: Boolean,
  platforms: { type: Array, default: () => [] },
  ready: Boolean
})
const emit = defineEmits(['update:modelValue', 'done'])

const visible = ref(false)
const loading = ref(false)
const form = reactive({ topic: '', style: '', words: 2000, tags_hint: '', publish_to: [] })

// v-model 双向：外面改 modelValue，里面改 visible
watch(() => props.modelValue, v => { visible.value = v })
watch(visible, v => emit('update:modelValue', v))

async function submit() {
  loading.value = true
  try {
    const r = await api.aiWrite({
      topic: form.topic.trim(),
      style: form.style,
      words: form.words,
      tags_hint: form.tags_hint,
      publish_to: form.publish_to.length ? form.publish_to : null
    })
    ElMessage.success(`已生成《${r.title}》${r.chars} 字`)
    emit('done', r.id)
    visible.value = false
  } finally { loading.value = false }
}
</script>
