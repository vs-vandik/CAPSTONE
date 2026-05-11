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
  <transition name="aporia">
    <aside
      v-if="open"
      class="fixed inset-y-0 right-0 w-full sm:w-[480px] bg-surface border-l border-border shadow-xl z-40 overflow-y-auto"
      role="dialog"
      aria-labelledby="aporia-title"
    >
      <header
        class="sticky top-0 bg-surface border-b border-border px-6 py-4 flex items-center justify-between"
      >
        <div>
          <p class="label">Aporia</p>
          <h2 id="aporia-title" class="font-serif text-xl text-ink">
            Critical examination
          </h2>
        </div>
        <button
          class="btn-ghost px-2 py-1"
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
.aporia-enter-from,
.aporia-leave-to {
  transform: translateX(20px);
  opacity: 0;
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
