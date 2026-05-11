<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDiscourseStore } from '@/stores/discourse'

const store = useDiscourseStore()
const router = useRouter()

// Local draft. Only commit to the store when the user clicks Continue,
// so navigating back/forward doesn't churn the store.
const draft = ref(store.topic)
const submitting = ref(false)

const canContinue = computed(() => draft.value.trim().length > 0)

// Suggested propositions for asset managers / enterprise risk.
// Framed as debatable claims, not yes/no questions, so personas have
// something to push against.
const suggestions: { label: string; text: string }[] = [
  {
    label: 'Climate risk in IG credit',
    text: 'Climate transition risk is mispriced across investment-grade credit, and current portfolios systematically underweight it.',
  },
  {
    label: 'Private credit & systemic risk',
    text: 'Private credit growth since 2020 has shifted systemic risk off bank balance sheets without reducing it.',
  },
  {
    label: 'AI gains and labor',
    text: 'AI-driven productivity gains will accrue to capital holders, not labor, deepening the retirement-savings gap.',
  },
  {
    label: 'Geopolitical fragmentation & cost of capital',
    text: 'Geopolitical fragmentation has permanently raised the cost of capital for multinational operations, and DCF models built on pre-2020 assumptions overstate fair value.',
  },
]

function applySuggestion(text: string) {
  draft.value = text
}

async function submit() {
  if (!canContinue.value || submitting.value) return
  submitting.value = true
  store.setTopic(draft.value)
  const sessionId = await store.start()
  submitting.value = false
  if (sessionId) {
    router.push('/discourse')
  }
}
</script>

<template>
  <section class="max-w-page mx-auto px-6 py-16">
    <!--
      Header lockup — the "State the question." heading and the
      explanatory paragraph below it are shipped as SVGs from design so
      the type renders pixel-identical to the Figma without depending
      on web-font loading.
        - state_the_question.svg  336x38  -> rendered at h-[44px] so the
          heading carries comparable weight to the rest of the page.
        - thesis_paragraph.svg    496x71  -> h-auto, capped at the
          SVG's native width on wider viewports.
      The small uppercase "Thesis" label is kept as live text since it's
      a re-usable UI label (also appears elsewhere as `.label`).
    -->
    <div class="max-w-3xl mb-12">
      <p class="label mb-6">Thesis</p>
      <img
        src="/state_the_question.svg"
        alt="State the question."
        class="h-[44px] w-auto mb-8"
      />
      <img
        src="/thesis_paragraph.svg"
        alt="Phrase it as a proposition the experts can agree with, contest, or refine — not as an open-ended prompt. The sharper the framing, the sharper the dialogue."
        class="h-auto w-full max-w-[496px]"
      />
    </div>

    <div class="max-w-3xl">
      <label
        for="topic"
        class="label mb-2 block"
      >
        Proposition
      </label>
      <textarea
        id="topic"
        v-model="draft"
        rows="3"
        class="input font-serif text-lg leading-snug"
        placeholder="e.g. Climate transition risk is mispriced across investment-grade credit."
        @keydown.enter.exact.prevent="submit"
        @keydown.meta.enter.prevent="submit"
        @keydown.ctrl.enter.prevent="submit"
      />
      <p class="text-xs text-ink-faint mt-2">
        Press Enter to begin. Use Shift+Enter for a new line.
      </p>

      <div class="mt-10">
        <p class="label mb-4">Suggested propositions</p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            v-for="(s, i) in suggestions"
            :key="i"
            type="button"
            class="card text-left p-4 hover:border-border-strong transition-colors"
            @click="applySuggestion(s.text)"
          >
            <p class="text-xs text-ink-faint mb-1">{{ s.label }}</p>
            <p class="text-sm text-ink leading-relaxed">{{ s.text }}</p>
          </button>
        </div>
      </div>

      <div
        v-if="store.error"
        class="mt-8 card p-4 border-l-2 border-l-red-700"
      >
        <p class="text-sm text-ink">{{ store.error }}</p>
      </div>

      <div class="mt-10 flex items-center justify-between gap-4">
        <RouterLink to="/experts" class="btn-ghost">Back</RouterLink>
        <button
          class="btn-primary"
          :disabled="!canContinue || submitting"
          @click="submit"
        >
          {{ submitting ? 'Convening the dialogue…' : 'Start a Discourse' }}
        </button>
      </div>
    </div>
  </section>
</template>
