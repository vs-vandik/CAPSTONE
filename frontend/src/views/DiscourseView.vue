<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDiscourseStore } from '@/stores/discourse'
import TurnBubble from '@/components/TurnBubble.vue'
import AporiaPanel from '@/components/AporiaPanel.vue'

const store = useDiscourseStore()
const router = useRouter()

const transcriptEnd = ref<HTMLElement | null>(null)
const aporiaLoading = ref(false)
const userInputDraft = ref('')

// Build a quick lookup so TurnBubble can resolve persona by id.
const personaById = computed(() => {
  const m = new Map(store.personas.map((p) => [p.id, p]))
  return m
})

onMounted(async () => {
  // Make sure persona catalog is loaded so we can render avatars/colors.
  await store.loadPersonas()
  // If we landed here directly with no session (shouldn't happen because
  // the router guard catches it, but defensive), kick back to setup.
  if (!store.sessionId) {
    router.replace('/experts')
    return
  }
  window.addEventListener('keydown', onKey)
  // Kick the discourse off immediately: don't make the user click a
  // separate "Open the dialogue" button after they just clicked "Start
  // a Discourse" on the topic page. That intermediate step makes the
  // app look broken. The very first /next call returns Plato's opening.
  if (store.turns.length === 0 && store.status !== 'loading') {
    advance()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})

function onKey(e: KeyboardEvent) {
  // Spacebar advances the dialogue. Ignore when typing in the participant
  // input bar or when a modifier is held.
  if (e.target instanceof HTMLElement) {
    const tag = e.target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
  }
  if (e.code === 'Space' && !e.metaKey && !e.ctrlKey && !e.altKey) {
    e.preventDefault()
    advance()
  }
}

watch(
  () => store.turns.length,
  async () => {
    await nextTick()
    transcriptEnd.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  },
)

const isLoading = computed(() => store.status === 'loading')
const isDone = computed(() => store.status === 'done')
const isEmpty = computed(() => store.turns.length === 0)
const canContinue = computed(() => !isLoading.value && !isDone.value && !isEmpty.value)
const lastTurn = computed(() => store.turns[store.turns.length - 1] ?? null)
const expertTurnsSoFar = computed(
  () => store.turns.filter((t) => t.role === 'expert').length,
)
const canOfferUserInput = computed(
  () =>
    canContinue.value &&
    lastTurn.value?.role === 'expert' &&
    expertTurnsSoFar.value < store.maxTurns,
)
const canSubmitUserInput = computed(
  () => canOfferUserInput.value && userInputDraft.value.trim().length > 0,
)
// While the backend is generating the next turn, surface *who* is
// thinking when we can. Plato's turns are template-based and effectively
// instant, so the only loading states the user actually sees are expert
// turns — which means most of the time we have a concrete name to show.
// Falls back to "— thinking —" when we can't determine the speaker
// (e.g. opening turn, or somehow no personas loaded).
const thinkingLabel = computed(() => {
  const p = store.nextExpertSpeaker
  return p ? `${p.name} is thinking…` : '— thinking —'
})
const advanceLabel = computed(() => {
  if (isLoading.value) return 'Thinking…'
  if (isDone.value) return 'Dialogue concluded'
  if (isEmpty.value) return 'Opening…'
  if (canOfferUserInput.value) return 'Continue listening ▸'
  return 'Continue ▸'
})

async function advance() {
  if (isLoading.value || isDone.value) return
  await store.nextTurn()
}

async function submitUserInput() {
  if (!canSubmitUserInput.value) return
  const content = userInputDraft.value.trim()
  await store.addUserInput(content)
  if (!store.error) {
    userInputDraft.value = ''
  }
}

async function aporia() {
  if (store.turns.length === 0) return
  aporiaLoading.value = true
  await store.runAporia()
  aporiaLoading.value = false
}

async function endSession() {
  await store.end()
  store.resetAll()
  router.push('/')
}
</script>

<template>
  <section class="max-w-page mx-auto px-6 py-12">
    <!-- Header: topic + participants -->
    <header class="mb-12 max-w-3xl">
      <p class="label mb-3">Discourse</p>
      <h1
        class="font-serif text-2xl sm:text-3xl leading-snug tracking-tightish text-ink"
      >
        {{ store.topic }}
      </h1>
      <div class="mt-5 flex flex-wrap gap-2">
        <span
          v-for="p in store.selectedPersonas"
          :key="p.id"
          class="inline-flex items-center gap-2 px-3 py-1 rounded-sm border text-sm"
          :style="{
            borderColor: p.color + '40',
            backgroundColor: p.color + '10',
            color: p.color,
          }"
        >
          <span class="font-serif" aria-hidden="true">{{ p.icon }}</span>
          <span class="text-ink">{{ p.name }}</span>
        </span>
      </div>
    </header>

    <!-- Error banner -->
    <div
      v-if="store.error"
      class="card p-4 mb-6 border-l-2 border-l-red-700"
      role="alert"
    >
      <p class="text-sm text-ink">{{ store.error }}</p>
    </div>

    <!-- Transcript -->
    <div class="max-w-prose mx-auto">
      <div
        v-if="isEmpty && isLoading"
        class="text-center py-16 text-ink-faint"
        aria-live="polite"
      >
        <p class="text-sm">
          <span class="inline-block animate-pulse">Plato is opening the dialogue…</span>
        </p>
      </div>

      <TurnBubble
        v-for="(turn, i) in store.turns"
        :key="i"
        :turn="turn"
        :persona="turn.persona_id ? personaById.get(turn.persona_id) : undefined"
      />

      <div
        v-if="isLoading && !isEmpty"
        class="my-6 text-center text-sm text-ink-faint"
        aria-live="polite"
      >
        <span class="inline-block animate-pulse">{{ thinkingLabel }}</span>
      </div>

      <!-- Per-turn nudge: tell the user how to advance, sitting just
           under the most recent turn so the affordance is unmissable.
           Hidden below `sm` because the on-screen button is the only
           affordance on touch devices; the keyboard hint is desktop-only
           and confuses phone users. -->
      <p
        v-if="canContinue"
        class="hidden sm:block mt-2 mb-10 text-center text-xs text-ink-faint"
      >
        Press
        <kbd
          class="mx-1 px-1.5 py-0.5 font-mono text-[11px] text-ink-muted
                 border border-border rounded-sm bg-surface"
        >Space</kbd>
        to continue.
        <span v-if="canOfferUserInput">
          Add your thought below, or keep listening.
        </span>
        <span v-else>
          Or click <span class="text-ink-muted">Continue</span> below.
        </span>
      </p>

      <div ref="transcriptEnd" />
    </div>

    <!--
      Sticky controls.

      Desktop (sm+): single row with End/Aporia on the left and a large
      Continue on the right. This is the original layout, untouched.

      Mobile (< sm): stacked. Continue gets its own full-width row at
      the top (the primary affordance, easy thumb-target), then a thin
      row underneath holds End discourse + Aporia. `env(safe-area-inset-bottom)`
      adds padding below the bar so the iPhone home indicator doesn't
      sit on top of the controls. The spacer below the transcript is
      bumped from h-24 (96px, the old desktop value) to h-44 sm:h-24
      (~176px) because the stacked mobile bar is taller than the desktop
      row and would otherwise cover the final turn.
    -->
    <div
      class="fixed bottom-0 left-0 right-0 border-t border-border bg-bg/95 backdrop-blur z-20"
      style="padding-bottom: env(safe-area-inset-bottom);"
    >
      <form
        v-if="canOfferUserInput"
        class="max-w-page mx-auto px-4 sm:px-6 pt-3 pb-2"
        @submit.prevent="submitUserInput"
      >
        <label
          for="participant-input"
          class="label mb-2 block"
        >
          Plato offers the floor
        </label>
        <div class="flex flex-col sm:flex-row gap-2">
          <textarea
            id="participant-input"
            v-model="userInputDraft"
            class="input discourse-input text-sm leading-snug"
            rows="2"
            maxlength="1200"
            placeholder="Add a question, objection, or detail for the experts to use."
            @keydown.enter.exact.prevent="submitUserInput"
          />
          <button
            class="btn-secondary sm:self-stretch"
            type="submit"
            :disabled="!canSubmitUserInput"
          >
            Add your thought
          </button>
        </div>
      </form>

      <!-- Mobile: stacked layout -->
      <div class="sm:hidden max-w-page mx-auto px-4 py-3 flex flex-col gap-2">
        <button
          class="btn-primary btn-continue w-full"
          :class="{ 'btn-continue--ready': canContinue }"
          :disabled="isLoading || isDone || isEmpty"
          @click="advance"
        >
          {{ advanceLabel }}
        </button>
        <div class="flex items-center justify-between gap-2">
          <button class="btn-ghost" @click="endSession">End discourse</button>
          <button
            class="btn-secondary"
            :disabled="isEmpty || aporiaLoading"
            @click="aporia"
          >
            {{ aporiaLoading ? 'Examining…' : 'Aporia' }}
          </button>
        </div>
      </div>

      <!-- Desktop: original single-row layout -->
      <div
        class="hidden sm:flex max-w-page mx-auto px-6 py-4 flex-wrap items-center justify-between gap-3"
      >
        <div class="flex items-center gap-2">
          <button class="btn-ghost" @click="endSession">End discourse</button>
          <button
            class="btn-secondary"
            :disabled="isEmpty || aporiaLoading"
            @click="aporia"
          >
            {{ aporiaLoading ? 'Examining…' : 'Aporia' }}
          </button>
        </div>
        <button
          class="btn-primary btn-continue"
          :class="{ 'btn-continue--ready': canContinue }"
          :disabled="isLoading || isDone || isEmpty"
          @click="advance"
        >
          {{ advanceLabel }}
        </button>
      </div>
    </div>

    <!-- Bottom spacer so content isn't hidden by the sticky bar.
         Mobile stacked bar is ~140px tall; desktop is ~76px. -->
    <div :class="canOfferUserInput ? 'h-72 sm:h-48' : 'h-44 sm:h-24'" />

    <AporiaPanel
      :open="!!store.aporia || aporiaLoading"
      :result="store.aporia"
      :loading="aporiaLoading"
      @close="store.closeAporia()"
    />
  </section>
</template>

<style scoped>
/* The Continue button is the primary affordance during a discourse — make
   it noticeably bigger and weightier than the surrounding ghost/secondary
   controls so new users can't miss it. */
.btn-continue {
  padding: 0.75rem 1.5rem;
  font-size: 0.95rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.discourse-input {
  min-height: 3.25rem;
  max-height: 8rem;
  resize: vertical;
}
@media (min-width: 640px) {
  .discourse-input {
    resize: none;
  }
}
/* When the user can actually advance (turn rendered, not loading, not
   done), gently pulse the button so the eye is drawn to it after the
   speaker finishes. */
.btn-continue--ready {
  animation: continue-pulse 2.2s ease-in-out infinite;
}
@keyframes continue-pulse {
  0%, 100% {
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05),
                0 0 0 0 rgba(31, 58, 95, 0.0);
  }
  50% {
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05),
                0 0 0 6px rgba(31, 58, 95, 0.15);
  }
}
@media (prefers-reduced-motion: reduce) {
  .btn-continue--ready {
    animation: none;
  }
}
</style>
