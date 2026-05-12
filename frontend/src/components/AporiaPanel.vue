<script setup lang="ts">
import { computed } from 'vue'
import type { AporiaResult } from '@/types'
import { renderParagraphs } from '@/services/format'

const props = defineProps<{
  open: boolean
  result: AporiaResult | null
  loading: boolean
}>()

defineEmits<{
  (e: 'close'): void
}>()

const headerHtml = computed(() =>
  props.result ? renderParagraphs(props.result.content) : '',
)

const findings = computed(() => props.result?.findings ?? [])
const guidanceHtml = computed(() =>
  props.result ? renderParagraphs(props.result.guidance) : '',
)

function findingTitle(f: Record<string, unknown>): string {
  return (
    String(f.title ?? f.type ?? f.kind ?? 'Finding')
  ).toString()
}
function findingBody(f: Record<string, unknown>): string {
  const body = f.detail ?? f.description ?? f.content ?? ''
  return typeof body === 'string' ? body : JSON.stringify(body)
}
</script>

<template>
  <!--
    Two layouts behind a `sm:` breakpoint:

    Mobile (< sm): bottom sheet. Slides up from the bottom, takes the
    full width, max-height 85vh so the user can still see the bottom of
    the transcript above it. Rounded top corners and a small drag
    handle communicate "dismissable sheet."

    Desktop (sm+): right-side drawer, 480px wide, full height. The
    original layout.

    Transition direction differs per breakpoint (translateY on mobile,
    translateX on desktop). We use a CSS media query inside the scoped
    style block to switch which transform applies.
  -->
  <transition name="aporia">
    <aside
      v-if="open"
      class="fixed bg-surface shadow-xl z-40 overflow-y-auto
             inset-x-0 bottom-0 max-h-[85vh] rounded-t-lg border-t border-border
             sm:inset-y-0 sm:right-0 sm:left-auto sm:bottom-auto sm:max-h-none
             sm:w-[480px] sm:rounded-none sm:border-t-0 sm:border-l"
      role="dialog"
      aria-labelledby="aporia-title"
      style="padding-bottom: env(safe-area-inset-bottom);"
    >
      <!--
        Drag-handle bar at the top of the mobile sheet. Visual
        affordance only — not functionally draggable in v1. Hidden on
        desktop where the right-side drawer reads as a panel, not a
        sheet.
      -->
      <div
        class="sm:hidden mx-auto h-1 w-10 rounded-full bg-border my-2"
        aria-hidden="true"
      />

      <header
        class="sticky top-0 bg-surface border-b border-border px-6 py-4 flex items-center justify-between"
      >
        <div>
          <p class="label">Aporia</p>
          <h2 id="aporia-title" class="font-serif text-xl text-ink">
            Critical examination
          </h2>
        </div>
        <!--
          Close button: 44x44 hit area on mobile (iOS HIG floor); on
          desktop, the ghost-button shape with text label is preserved.
          The `min-h-[44px] min-w-[44px]` floor applies everywhere
          rather than only at <sm, because a cursor-tap on a 24px
          button is just as annoying as a thumb-tap.
        -->
        <button
          class="btn-ghost min-h-[44px] min-w-[44px] px-3"
          aria-label="Close"
          @click="$emit('close')"
        >
          Close
        </button>
      </header>

      <div class="px-6 py-6">
        <div v-if="loading" class="text-sm text-ink-muted">
          Examining the dialogue.
        </div>

        <div v-else-if="result">
          <div
            v-if="headerHtml"
            class="prose-aporia text-ink-muted leading-relaxed font-serif italic mb-8"
            v-html="headerHtml"
          />

          <div v-if="findings.length" class="space-y-5 mb-8">
            <p class="label">Findings</p>
            <article
              v-for="(f, i) in findings"
              :key="i"
              class="border-l-2 border-border-strong pl-4 py-1"
            >
              <h3 class="font-serif text-base text-ink mb-1">
                {{ findingTitle(f as Record<string, unknown>) }}
              </h3>
              <p class="text-sm text-ink-muted leading-relaxed">
                {{ findingBody(f as Record<string, unknown>) }}
              </p>
            </article>
          </div>
          <p
            v-else
            class="text-sm text-ink-faint italic mb-8"
          >
            No discrete findings surfaced.
          </p>

          <div v-if="guidanceHtml">
            <p class="label mb-2">Guidance</p>
            <div
              class="prose-aporia text-ink leading-relaxed"
              v-html="guidanceHtml"
            />
          </div>
        </div>

        <div v-else class="text-sm text-ink-muted">
          No analysis yet.
        </div>
      </div>
    </aside>
  </transition>
</template>

<style scoped>
.aporia-enter-active,
.aporia-leave-active {
  transition: transform 220ms ease, opacity 220ms ease;
}
/*
  Mobile (< 640px): slide up from the bottom.
  Desktop (>= 640px): slide in from the right.
  Two media queries keep the transform direction matching the layout.
*/
.aporia-enter-from,
.aporia-leave-to {
  transform: translateY(20px);
  opacity: 0;
}
@media (min-width: 640px) {
  .aporia-enter-from,
  .aporia-leave-to {
    transform: translateX(20px);
  }
}
.prose-aporia :deep(p) {
  margin-bottom: 0.75rem;
}
.prose-aporia :deep(p:last-child) {
  margin-bottom: 0;
}
.prose-aporia :deep(strong) {
  font-weight: 600;
}
</style>
