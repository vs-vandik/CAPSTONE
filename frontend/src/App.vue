<script setup lang="ts">
import { useRoute } from 'vue-router'
import TopBar from '@/components/TopBar.vue'

const route = useRoute()
</script>

<template>
  <div class="min-h-screen flex flex-col bg-bg">
    <TopBar />
    <main class="flex-1 w-full flex flex-col">
      <!--
        Plain <router-view> on purpose. Previously this was wrapped in a
        <transition name="fade" mode="out-in"> with `v-slot="{ Component }"`,
        which produced an intermittent "blank page until refresh" bug:
        on a route change the leave hook would fire but the new
        component would mount with `opacity: 0` and occasionally never
        receive the `enter-to` class, leaving the page invisibly
        rendered until the user refreshed. A global fade is not worth a
        broken navigation flow; route-level transitions can be re-added
        per-component later if we want them.
      -->
      <router-view />
    </main>
    <!--
      The site-wide footer is hidden on routes that ship their own
      full-bleed footer (silhouetted heads). Those pages should sit
      flush with the bottom of the viewport — no extra whitespace or
      fine-print band beneath the heads.
    -->
    <footer
      v-if="route.name !== 'home' && route.name !== 'experts'"
      class="border-t border-border mt-24"
    >
      <div
        class="max-w-page mx-auto px-6 py-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs text-ink-faint"
      >
        <span>plato — structured dialogue for asset managers.</span>
        <span>Output is a record of debate. Not investment advice.</span>
      </div>
    </footer>
  </div>
</template>
