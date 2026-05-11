<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { computed } from 'vue'
import Logo from '@/components/Logo.vue'

const route = useRoute()

interface NavItem {
  /** Lowercase label, matches the Figma. */
  name: string
  to: string
  /** A nav link is "active" if the current route name matches any of these. */
  matches: string[]
}

const navItems: NavItem[] = [
  { name: 'home', to: '/', matches: ['home'] },
  { name: 'discourse', to: '/experts', matches: ['experts', 'topic', 'discourse'] },
  { name: 'about', to: '/about', matches: ['about'] },
]

const activeName = computed(() => String(route.name ?? ''))

// The landing page anchors the brand with a navy band under the top bar;
// the bar itself sits flush on that band, so it stays navy with white
// type. Every other route is on the off-white page surface — there the
// bar should disappear into the page (transparent, dark type, hairline
// separator) so the editorial header below it carries the visual weight.
const isLanding = computed(() => activeName.value === 'home')
</script>

<template>
  <header
    class="border-b"
    :class="
      isLanding
        ? 'bg-accent border-[#D9D9D9]'
        : 'bg-bg border-border'
    "
  >
    <div
      class="max-w-page mx-auto px-12 h-16 flex items-center justify-between"
    >
      <RouterLink
        to="/"
        class="flex items-center"
        aria-label="plato — home"
      >
        <!--
          Landing renders the standalone π-in-a-circle mark; the navy
          band immediately below the top bar carries the full lockup,
          so repeating "plato" here would be redundant. Other routes
          keep the full lockup (mark + wordmark) since they don't have
          the hero band beneath.
        -->
        <Logo
          :mode="isLanding ? 'mark' : 'lockup'"
          :variant="isLanding ? 'white' : 'black'"
          :height="isLanding ? 32 : 22"
        />
      </RouterLink>

      <nav aria-label="Primary">
        <ul class="flex items-center gap-20">
          <li v-for="item in navItems" :key="item.to">
            <RouterLink
              :to="item.to"
              class="text-sm font-light tracking-[0.2em] transition-opacity"
              :class="
                isLanding
                  ? item.matches.includes(activeName)
                    ? 'text-bg'
                    : 'text-bg/70 hover:text-bg'
                  : item.matches.includes(activeName)
                    ? 'text-ink'
                    : 'text-ink-muted hover:text-ink'
              "
            >
              {{ item.name }}
            </RouterLink>
          </li>
        </ul>
      </nav>
    </div>
  </header>
</template>
