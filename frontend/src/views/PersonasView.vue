<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDiscourseStore } from '@/stores/discourse'

const store = useDiscourseStore()
const router = useRouter()

onMounted(() => {
  // Fire-and-forget: the store coalesces concurrent calls, retries
  // transient failures, and exposes `personasLoading` / `error` so the
  // template can react. The persona catalog is also prefetched at app
  // boot in main.ts, so by the time the user lands here it's typically
  // already populated.
  store.loadPersonas()
})

const selectedCount = computed(() => store.selectedPersonaIds.length)
const canContinue = computed(() => selectedCount.value === 2)
const hasPersonas = computed(() => store.personas.length > 0)
// We're "loading" whenever a fetch is in flight OR we simply have no
// data yet and no error has surfaced. This keeps the spinner visible
// during retries instead of flashing a blank panel.
const showLoading = computed(
  () => !hasPersonas.value && !store.error,
)
const showError = computed(() => !hasPersonas.value && !!store.error)

function isSelected(id: string) {
  return store.selectedPersonaIds.includes(id)
}

function onCardClick(id: string) {
  store.togglePersona(id)
}

function next() {
  if (canContinue.value) router.push('/topic')
}

function retry() {
  store.loadPersonas({ force: true })
}
</script>

<template>
  <section class="max-w-page mx-auto px-6 py-16">
    <!--
      Header lockup matches the Figma export for /experts. The three
      pieces are individual SVGs so the type renders pixel-identical to
      the design without relying on font loading. Heights are picked to
      preserve each SVG's intrinsic aspect ratio:
        - expertise_label.svg     78x11   -> h-[11px]
        - select_two_experts.svg  343x38  -> rendered at h-[52px] so the
          heading reads more dominant against the surrounding type, per
          the latest design direction.
        - experts_intro.svg       566x72  -> h-auto, capped at full
          container width on narrow viewports.
      Spacing between the three elements is intentionally generous
      (mb-10 / mb-12) to give the page the airy editorial feel the
      Figma calls for.
    -->
    <div class="max-w-3xl mb-20">
      <img
        src="/expertise_label.svg"
        alt="Expertise"
        class="h-[11px] w-auto mb-10"
      />
      <img
        src="/select_two_experts.svg"
        alt="Select two experts"
        class="h-auto max-w-full w-auto sm:h-[52px] mb-12"
      />
      <img
        src="/experts_intro.svg"
        alt="Create a Socratic dialog. Pair voices that share the question but disagree on the answer. This is not artificial intelligence — we help you train your own intelligence."
        class="h-auto w-full max-w-[566px]"
      />
    </div>

    <!-- Hard failure: retries exhausted. Show actionable retry, not a
         dead end that forces a full-page refresh. -->
    <div
      v-if="showError"
      class="card p-6 mb-8 border-l-2 border-l-red-700"
    >
      <p class="text-sm text-ink">
        Could not load experts.
        <span class="text-ink-muted">{{ store.error }}</span>
      </p>
      <button class="btn-secondary mt-4" @click="retry">
        Try again
      </button>
    </div>

    <div
      v-if="showLoading"
      class="text-sm text-ink-faint"
      aria-live="polite"
    >
      <span class="inline-block animate-pulse">Loading experts…</span>
    </div>

    <ul
      v-if="hasPersonas"
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <li v-for="p in store.personas" :key="p.id">
        <button
          type="button"
          class="card w-full text-left p-6 transition-all duration-150 hover:border-border-strong"
          :class="isSelected(p.id) ? 'ring-1 ring-accent border-accent' : ''"
          :aria-pressed="isSelected(p.id)"
          @click="onCardClick(p.id)"
        >
          <div class="flex items-start gap-4">
            <span
              class="flex-shrink-0 w-10 h-10 rounded-sm flex items-center justify-center font-serif text-base"
              :style="{
                backgroundColor: p.color + '18',
                color: p.color,
                border: `1px solid ${p.color}40`,
              }"
              aria-hidden="true"
            >
              {{ p.icon }}
            </span>
            <div class="flex-1 min-w-0">
              <h3 class="font-serif text-lg text-ink leading-snug">
                {{ p.name }}
              </h3>
              <p class="text-xs text-ink-faint mt-0.5">{{ p.title }}</p>
              <p class="text-sm text-ink-muted mt-3 leading-relaxed">
                {{ p.bio }}
              </p>
            </div>
          </div>
        </button>
      </li>
    </ul>

    <div
      v-if="hasPersonas"
      class="mt-12 flex items-center justify-between gap-4 sticky bottom-0 bg-bg/90 backdrop-blur py-4 border-t border-border"
      style="padding-bottom: max(1rem, env(safe-area-inset-bottom));"
    >
      <p class="text-sm text-ink-muted">
        <span class="text-ink font-medium">{{ selectedCount }}</span>
        of 2 selected
      </p>
      <button
        class="btn-primary"
        :disabled="!canContinue"
        @click="next"
      >
        Continue
      </button>
    </div>
  </section>

  <!--
    Footer band — silhouetted heads, full bleed. Same treatment as the
    landing page: mt-auto pins it to the bottom of <main> on tall
    screens, pt-32 keeps a comfortable gap above the heads on shorter
    content. The site-wide App.vue footer is suppressed on this route.

    Hidden below `sm` (same reason as on the landing): at phone widths
    the silhouettes squish into an unreadable grey blur. Restored at
    tablet+ where there's room for the band to breathe.
  -->
  <section class="hidden sm:block mt-auto pt-32">
    <img
      src="/footer_landing.svg"
      alt=""
      aria-hidden="true"
      class="w-full h-auto block select-none"
      draggable="false"
    />
  </section>
</template>
