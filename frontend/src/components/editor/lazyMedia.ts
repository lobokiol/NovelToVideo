import type { Directive } from 'vue'

/**
 * 素材媒体懒加载：基于 IntersectionObserver 的 v-lazy-src 指令。
 *
 * 元素挂载时不设置 src，进入所属滚动容器可视区上下一屏范围内才挂载真实地址：
 * 初始只加载第 1 屏（可视区）与第 2 屏（下方预载一屏）的素材，其余跟随滚动逐步加载；
 * 隐藏页签（display:none）内的素材不产生任何请求，切换页签后按需加载。
 */

/** 懒加载滚动容器选择器：指令按最近祖先匹配，一个容器共享一个观察器。 */
const LAZY_ROOT_SELECTOR = '.library-list'

/** 可视窗口外扩：上下各一屏（相对滚动容器高度），即"当前屏 + 预载一屏"。 */
const LAZY_ROOT_MARGIN = '100% 0px 100% 0px'

/** 进入可视窗口前暂存的真实媒体地址。 */
const pendingSrc = new WeakMap<Element, string>()

/** 滚动容器 → 观察器；rootMargin 相对 root 计算，不能跨容器共用。 */
const observers = new Map<Element, IntersectionObserver>()

type LazyMediaElement = HTMLImageElement | HTMLVideoElement

const observerFor = (root: Element) => {
  let observer = observers.get(root)
  if (observer) return observer
  observer = new IntersectionObserver(
    (entries, self) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const el = entry.target as LazyMediaElement
        const src = pendingSrc.get(el)
        pendingSrc.delete(el)
        self.unobserve(el)
        if (src) el.src = src
      }
    },
    { root, rootMargin: LAZY_ROOT_MARGIN },
  )
  observers.set(root, observer)
  return observer
}

/** 已加载元素换源判断：el.src 读出为绝对地址，与相对路径值尾部匹配即视为同源。 */
const sameSrc = (el: LazyMediaElement, src: string) => Boolean(el.src) && el.src.endsWith(src)

/** v-lazy-src="url"：替代 :src 使用；不在滚动容器内的元素退化为直接加载。 */
export const lazySrcDirective: Directive<LazyMediaElement, string> = {
  mounted(el, binding) {
    const root = el.closest(LAZY_ROOT_SELECTOR)
    if (!root) {
      el.src = binding.value
      return
    }
    pendingSrc.set(el, binding.value)
    observerFor(root).observe(el)
  },
  updated(el, binding) {
    // 列表刷新复用节点：未加载的仅更新待载地址，已加载且地址变化的直接换源。
    if (pendingSrc.has(el)) {
      pendingSrc.set(el, binding.value)
      return
    }
    if (!sameSrc(el, binding.value)) el.src = binding.value
  },
  unmounted(el) {
    pendingSrc.delete(el)
    for (const observer of observers.values()) observer.unobserve(el)
  },
}

/** 释放全部观察器；素材面板卸载时调用，避免跨页面残留。 */
export const disconnectLazyObservers = () => {
  for (const observer of observers.values()) observer.disconnect()
  observers.clear()
}
