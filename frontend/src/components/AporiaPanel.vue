<script setup lang="ts">
import { computed } from 'vue'
import type { AporiaExpert, AporiaPoint, AporiaResult } from '@/types'
import { renderParagraphs } from '@/services/format'

const props = defineProps<{
  open: boolean
  result: AporiaResult | null
  loading: boolean
}>()

defineEmits<{
  (e: 'close'): void
}>()

// `content` is empty in the steady state. It's only populated for
// degraded responses (no LLM, no expert turns, parse error) to
// explain why no structured findings are below. Treat its presence
// as the signal to render a banner — never render it alongside a
// populated experts list.
const degradedMessageHtml = computed(() => {
  if (!props.result) return ''
  if (props.result.experts.length > 0) return ''
  return props.result.content ? renderParagraphs(props.result.content) : ''
})

const experts = computed<AporiaExpert[]>(() => props.result?.experts ?? [])

// A point is worth showing as long as it has either a `point` or a
// `why` — defensive against a model that fills only one field.
function hasContent(p: AporiaPoint): boolean {
  return Boolean((p.point && p.point.trim()) || (p.why && p.why.trim()))
}

function pointsOf(list: AporiaPoint[] | undefined): AporiaPoint[] {
  return (list ?? []).filter(hasContent)
}
</script>

<template>
  <!--
    Two layouts behind a `sm:` breakpoint:

    Mobile (< sm): bottom sheet. Slides up, takes full width,
    max-height 85vh.

    Desktop (sm+): right-side drawer, 480px wide, full height.

    Transition direction differs per breakpoint (translateY mobile,
    translateX desktop), driven by a CSS media query in the scoped
    style block.
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
      <!-- Drag-handle bar on the mobile sheet. Visual affordance only. -->
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
            Dialectical examination
          </h2>
        </div>
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
          <!--
            Degraded responses (no expert turns yet, no LLM configured,
            parse error) carry a one-line `content` and an empty
            `experts[]`. Render that line and nothing else.
          -->
          <div
            v-if="degradedMessageHtml"
            class="prose-aporia text-ink-muted leading-relaxed font-serif italic"
            v-html="degradedMessageHtml"
          />

          <!--
            Steady state: one section per expert, each with three
            fixed subheadings. Empty categories are simply omitted —
            an expert who reasoned cleanly may have zero fallacies,
            and rendering "(none)" three times would be noise.
          -->
          <section
            v-for="ex in experts"
            :key="ex.expert"
            class="mb-10 last:mb-0"
          >
            <h3 class="font-serif text-lg text-ink mb-4 pb-2 border-b border-border-strong">
              {{ ex.expert }}
            </h3>

            <!-- Assumptions -->
            <div v-if="pointsOf(ex.assumptions).length" class="mb-6 last:mb-0">
              <p class="label mb-3">Assumptions</p>
              <ol class="space-y-3">
                <li
                  v-for="(p, i) in pointsOf(ex.assumptions)"
                  :key="`a-${i}`"
                  class="border-l-2 border-border-strong pl-4 py-1"
                >
                  <p
                    v-if="p.point"
                    class="font-serif text-base text-ink mb-1"
                  >
                    {{ p.point }}
                  </p>
                  <p
                    v-if="p.why"
                    class="text-sm text-ink-muted leading-relaxed"
                  >
                    {{ p.why }}
                  </p>
                </li>
              </ol>
            </div>

            <!-- Fallacies (named) -->
            <div v-if="pointsOf(ex.fallacies).length" class="mb-6 last:mb-0">
              <p class="label mb-3">Fallacies</p>
              <ol class="space-y-3">
                <li
                  v-for="(p, i) in pointsOf(ex.fallacies)"
                  :key="`f-${i}`"
                  class="border-l-2 border-border-strong pl-4 py-1"
                >
                  <!--
                    The named fallacy is the centerpiece of this
                    entry — render it as a small uppercase chip above
                    the dialectical point itself.
                  -->
                  <p
                    v-if="p.name"
                    class="inline-block text-[10px] tracking-[0.12em] uppercase text-ink-faint mb-1"
                  >
                    {{ p.name }}
                  </p>
                  <p
                    v-if="p.point"
                    class="font-serif text-base text-ink mb-1"
                  >
                    {{ p.point }}
                  </p>
                  <p
                    v-if="p.why"
                    class="text-sm text-ink-muted leading-relaxed"
                  >
                    {{ p.why }}
                  </p>
                </li>
              </ol>
            </div>

            <!-- Contradictions -->
            <div v-if="pointsOf(ex.contradictions).length" class="mb-6 last:mb-0">
              <p class="label mb-3">Contradictions</p>
              <ol class="space-y-3">
                <li
                  v-for="(p, i) in pointsOf(ex.contradictions)"
                  :key="`c-${i}`"
                  class="border-l-2 border-border-strong pl-4 py-1"
                >
                  <p
                    v-if="p.point"
                    class="font-serif text-base text-ink mb-1"
                  >
                    {{ p.point }}
                  </p>
                  <p
                    v-if="p.why"
                    class="text-sm text-ink-muted leading-relaxed"
                  >
                    {{ p.why }}
                  </p>
                </li>
              </ol>
            </div>

            <!--
              All three categories empty for this speaker. Surface that
              cleanly rather than leaving the expert's heading hanging.
            -->
            <p
              v-if="!pointsOf(ex.assumptions).length
                && !pointsOf(ex.fallacies).length
                && !pointsOf(ex.contradictions).length"
              class="text-sm text-ink-faint italic"
            >
              No assumptions, fallacies, or contradictions surfaced.
            </p>
          </section>
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
