<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { computed, ref, watch } from 'vue'
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

// Mobile menu state. Below `sm` (640px) we collapse the three nav links
// into a hamburger; above, the horizontal list is unchanged. Close the
// menu whenever the route changes so it doesn't stay open after a click.
const menuOpen = ref(false)
watch(activeName, () => {
  menuOpen.value = false
})
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
      class="max-w-page mx-auto px-4 sm:px-12 h-16 flex items-center justify-between"
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

      <!--
        Desktop nav: horizontal list, visible at `sm` and above.
        The gap-20 spacing matches the Figma rhythm; on phones this
        overflows the viewport, so we hide the list and show a
        hamburger toggle instead.
      -->
      <nav aria-label="Primary" class="hidden sm:block">
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

      <!--
        Mobile nav: hamburger toggle. 44x44 hit area meets the iOS HIG
        touch-target minimum. The icon stroke colour mirrors the bar's
        type colour (white on the landing's navy band, dark elsewhere).
      -->
      <button
        type="button"
        class="sm:hidden inline-flex items-center justify-center min-h-[44px] min-w-[44px] -mr-2"
        :class="isLanding ? 'text-bg' : 'text-ink'"
        :aria-expanded="menuOpen"
        aria-controls="mobile-nav"
        aria-label="Menu"
        @click="menuOpen = !menuOpen"
      >
        <svg
          v-if="!menuOpen"
          xmlns="http://www.w3.org/2000/svg"
          width="22"
          height="22"
          viewBox="0 0 22 22"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          aria-hidden="true"
        >
          <line x1="3" y1="6" x2="19" y2="6" />
          <line x1="3" y1="11" x2="19" y2="11" />
          <line x1="3" y1="16" x2="19" y2="16" />
        </svg>
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          width="22"
          height="22"
          viewBox="0 0 22 22"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          aria-hidden="true"
        >
          <line x1="5" y1="5" x2="17" y2="17" />
          <line x1="17" y1="5" x2="5" y2="17" />
        </svg>
      </button>
    </div>

    <!--
      Mobile dropdown panel. Lives inside <header> so the border-b
      stays visually attached to the bar above it. Hidden by default;
      shown when `menuOpen` is true. Closes on route change (watch
      above). Stacked vertically with comfortable 56px row heights.
    -->
    <nav
      v-if="menuOpen"
      id="mobile-nav"
      aria-label="Primary"
      class="sm:hidden border-t"
      :class="isLanding ? 'border-[#D9D9D9] bg-accent' : 'border-border bg-bg'"
    >
      <ul class="max-w-page mx-auto px-4 py-2">
        <li v-for="item in navItems" :key="item.to">
          <RouterLink
            :to="item.to"
            class="flex items-center min-h-[56px] text-base font-light tracking-[0.2em] transition-opacity"
            :class="
              isLanding
                ? item.matches.includes(activeName)
                  ? 'text-bg'
                  : 'text-bg/70 hover:text-bg'
                : item.matches.includes(activeName)
                  ? 'text-ink'
                  : 'text-ink-muted hover:text-ink'
            "
            @click="menuOpen = false"
          >
            {{ item.name }}
          </RouterLink>
        </li>
      </ul>
    </nav>
  </header>
</template>
