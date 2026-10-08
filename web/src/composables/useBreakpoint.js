import { ref, onMounted, onBeforeUnmount, computed } from 'vue'

/**
 * 响应式断点。窗口尺寸变化时自动更新，组件按这个决定"固定栏"还是"抽屉"。
 *   xs  手机竖屏      < 768
 *   sm  手机横屏/平板  < 1024
 *   md  小笔记本      < 1440
 *   lg  常规桌面      >= 1440
 */
export function useBreakpoint() {
  const w = ref(window.innerWidth)
  const onResize = () => { w.value = window.innerWidth }
  onMounted(() => window.addEventListener('resize', onResize))
  onBeforeUnmount(() => window.removeEventListener('resize', onResize))

  const bp = computed(() => {
    if (w.value < 768) return 'xs'
    if (w.value < 1024) return 'sm'
    if (w.value < 1440) return 'md'
    return 'lg'
  })

  return {
    width: w,
    bp,
    // 宽到能常驻时就别塞抽屉了，抽屉在桌面端反而碍事
    // 列表在平板横屏(>=1024)就常驻；侧栏在 13 寸笔记本(>=1280)就常驻，
    // 否则 1280~1439 会被迫用 FAB 抽屉发稿，体验割裂。
    listDocked: computed(() => w.value >= 1024),
    sideDocked: computed(() => w.value >= 1280),
    isMobile: computed(() => w.value < 768)
  }
}
