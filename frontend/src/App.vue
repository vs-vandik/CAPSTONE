<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import TopBar from '@/components/TopBar.vue'

const route = useRoute()

const routeTransitionName = computed(() =>
  route.meta.transitionName === 'route-back' ? 'route-back' : 'route-forward',
)
</script>

<template>
  <!--
    100dvh, not 100vh: on iOS Safari the browser's address bar shrinks
    on scroll, and the static `vh` unit doesn't account for that, so
    100vh ends up 60-80px taller than the actually-visible viewport and
    sticky bars get pushed below the fold. Dynamic viewport units fix
    this; supported since iOS 15.4 / Chrome 108.
  -->
  <div class="min-h-[100dvh] flex flex-col bg-bg">
    <TopBar />
    <main class="flex-1 w-full flex flex-col route-stage">
      <!--
        Route components are eagerly imported in router/index.ts, so this
        transition does not introduce an async component boundary. Only
        the routed page content moves; the top bar and footer remain outside
        the animation.
      -->
      <router-view v-slot="{ Component, route: currentRoute }">
        <transition :name="routeTransitionName">
          <div
            :key="currentRoute.fullPath"
            class="route-page"
          >
            <component :is="Component" />
          </div>
        </transition>
      </router-view>
    </main>
    <!--
      The site-wide footer is hidden on routes that ship their own
      full-bleed footer (silhouetted heads). Those pages should sit
      flush with the bottom of the viewport — no extra whitespace or
      fine-print band beneath the heads.
    -->
    <footer
      v-if="route.name === 'topic'"
      class="border-t border-border mt-24"
    >
      <div
        class="max-w-page mx-auto px-6 py-8 flex items-center justify-center"
      >
        <img
          src="/footer_logo_black.svg"
          alt="plato"
          class="h-6 w-auto block"
          draggable="false"
        />
      </div>
    </footer>
  </div>
</template>

<style scoped>
.route-stage {
  position: relative;
  overflow: hidden;
}
.route-page {
  flex: 1 1 auto;
  width: 100%;
}
.route-forward-enter-active,
.route-forward-leave-active,
.route-back-enter-active,
.route-back-leave-active {
  transition: transform 720ms cubic-bezier(0.32, 0.72, 0, 1);
  will-change: transform;
}
.route-forward-leave-active,
.route-back-leave-active {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.route-forward-enter-from {
  transform: translateX(100%);
}
.route-forward-leave-to {
  transform: translateX(-100%);
}
.route-back-enter-from {
  transform: translateX(-100%);
}
.route-back-leave-to {
  transform: translateX(100%);
}
@media (prefers-reduced-motion: reduce) {
  .route-forward-enter-active,
  .route-forward-leave-active,
  .route-back-enter-active,
  .route-back-leave-active {
    transition: none;
  }
}
</style>
