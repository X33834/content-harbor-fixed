<template>
  <div class="empty-brand" :style="{ '--esz': px + 'px' }">
    <svg viewBox="0 0 48 48" class="illu" aria-hidden="true">
      <!-- 文学插画：竖排书卷 + 落笔一横 + 墨点，单色铜金 -->
      <rect x="10" y="6" width="20" height="30" rx="4"
            fill="none" stroke="var(--line-strong)" stroke-width="1.6" />
      <line x1="15" y1="14" x2="25" y2="14" stroke="var(--tx-4)" stroke-width="1.6" stroke-linecap="round" />
      <line x1="15" y1="19" x2="23" y2="19" stroke="var(--tx-4)" stroke-width="1.6" stroke-linecap="round" />
      <!-- 落笔"一"字：古铜金横笔 -->
      <line x1="15" y1="25" x2="24" y2="25" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" />
      <circle cx="30" cy="30" r="1.6" fill="var(--accent-hi)" opacity=".8" />
      <circle cx="34" cy="33" r="1.1" fill="var(--accent)" opacity=".5" />
      <circle cx="37.5" cy="35.5" r=".8" fill="var(--accent)" opacity=".3" />
    </svg>
    <p class="tt">{{ title }}</p>
    <p v-if="desc" class="dd">{{ desc }}</p>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '空空如也' },
  desc: { type: String, default: '' },
  px: { type: Number, default: 44 }
})
</script>

<style scoped>
.empty-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px 16px;
  text-align: center;
  animation: fadeUp .3s var(--ease-out) both;
}
.illu {
  width: var(--esz, 44px);
  height: auto;
  margin-bottom: 12px;
  opacity: .9;
}
.tt {
  margin: 0;
  font-family: var(--font-serif);
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--tx-1);
  letter-spacing: .02em;
}
.dd {
  margin: 7px 0 0;
  font-size: var(--fs-sm);
  color: var(--tx-3);
  max-width: 240px;
  line-height: 1.7;
}
:deep(.el-button) { margin-top: 16px; }
</style>
