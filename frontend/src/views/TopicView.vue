<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDiscourseStore } from '@/stores/discourse'
import { useSpeechRecognition } from '@/services/voice'

const store = useDiscourseStore()
const router = useRouter()

// Local draft. Only commit to the store when the user clicks Continue,
// so navigating back/forward doesn't churn the store.
const nameDraft = ref(store.userName)
const draft = ref(store.topic)
const submitting = ref(false)

const canContinue = computed(
  () => nameDraft.value.trim().length > 0 && draft.value.trim().length > 0,
)

// Speech-to-text for the proposition field. We track whatever was in
// the textarea before recording started so each utterance appends to
// (rather than replaces) the user's typed text. The composable's
// transcript replaces the appended portion in real time, including
// while it is still interim — gives the user immediate visual feedback
// that the recognizer heard them.
const draftBeforeListen = ref('')
const speech = useSpeechRecognition({
  onUpdate(text) {
    const prefix = draftBeforeListen.value
    if (!prefix) {
      draft.value = text
    } else {
      // Preserve a single space between the existing text and the new
      // utterance unless the user's text already ends with whitespace.
      const sep = /\s$/.test(prefix) ? '' : ' '
      draft.value = prefix + sep + text
    }
  },
})

function toggleMic() {
  if (speech.listening.value) {
    speech.stop()
    return
  }
  draftBeforeListen.value = draft.value
  speech.start()
}

// Suggested propositions for asset managers / enterprise risk.
// Framed as debatable claims, not yes/no questions, so personas have
// something to push against.
const suggestions: { label: string; text: string }[] = [
  {
    label: 'Generational transition',
    text: "Does NTP's business model remain economically viable across generational transition? Examine what if the next generation values digital experience and cost efficiency more than a stable and long-term relationship.",
  },
  {
    label: 'AI governance',
    text: 'What happens when AI becomes embedded in investment decisions faster than governance frameworks mature? Examine how can NTP maintain fiduciary defensibility in an environment where decision support becomes probabilistic and opaque.',
  },
  {
    label: 'Geopolitical fragmentation',
    text: "What is NTP's operating model if the next five years are characterized by persistent geopolitical fragmentation rather than globalization? Discuss what would happen if the architecture of international finance becomes structurally less integrated.",
  },
]

function applySuggestion(text: string) {
  draft.value = text
}

async function submit() {
  if (!canContinue.value || submitting.value) return
  submitting.value = true
  store.setUserName(nameDraft.value)
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
        class="h-auto max-w-full w-auto sm:h-[44px] mb-8"
      />
      <img
        src="/thesis_paragraph.svg"
        alt="Phrase it as a proposition the experts can agree with, contest, or refine — not as an open-ended prompt. The sharper the framing, the sharper the dialogue."
        class="h-auto w-full max-w-[496px]"
      />
    </div>

    <div class="max-w-3xl">
      <div class="mb-8">
        <label
          for="user-name"
          class="label mb-2 block"
        >
          Plato asks
        </label>
        <input
          id="user-name"
          v-model="nameDraft"
          class="input text-base"
          type="text"
          maxlength="60"
          autocomplete="name"
          placeholder="What shall we call you?"
          @keydown.enter.exact.prevent="submit"
        />
      </div>

      <label
        for="topic"
        class="label mb-2 block"
      >
        Proposition
      </label>
      <!--
        Textarea + microphone button. The mic floats in the top-right
        corner of the textarea so it doesn't disturb the page rhythm.
        Hidden entirely when SpeechRecognition is unavailable
        (Firefox, older Safari) — the typed flow keeps working
        unchanged. Clicking the mic appends speech to whatever is
        already in the textarea rather than replacing it, so users can
        mix typing and dictation freely.
      -->
      <div class="relative">
        <textarea
          id="topic"
          v-model="draft"
          rows="3"
          class="input font-serif text-lg leading-snug"
          :class="{ 'pr-12': speech.supported.value }"
          placeholder=""
          @keydown.enter.exact.prevent="submit"
          @keydown.meta.enter.prevent="submit"
          @keydown.ctrl.enter.prevent="submit"
        />
        <button
          v-if="speech.supported.value"
          type="button"
          class="mic-btn"
          :class="{ 'mic-btn--listening': speech.listening.value }"
          :aria-label="speech.listening.value ? 'Stop dictation' : 'Dictate proposition'"
          :aria-pressed="speech.listening.value"
          @click="toggleMic"
        >
          <!-- Inline SVG keeps us free of any icon-font dependency. -->
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            class="w-4 h-4"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <rect x="9" y="3" width="6" height="12" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0" />
            <line x1="12" y1="18" x2="12" y2="21" />
            <line x1="9" y1="21" x2="15" y2="21" />
          </svg>
        </button>
      </div>
      <p class="text-xs text-ink-faint mt-2">
        Press Enter to begin. Use Shift+Enter for a new line.
        <span v-if="speech.supported.value">
          Click the microphone to dictate.
        </span>
      </p>
      <p
        v-if="speech.error.value"
        class="text-xs text-red-700 mt-1"
        role="alert"
      >
        Microphone error: {{ speech.error.value }}
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

<style scoped>
/* Mic button: small circular control floated inside the textarea's
   top-right corner. Sized to feel like part of the field, not a
   separate widget. Color matches the ink palette in idle state and
   shifts to a soft red while recording so the user always knows the
   mic is live. */
.mic-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  width: 2rem;
  height: 2rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid theme('colors.border');
  border-radius: 9999px;
  background: theme('colors.surface');
  color: theme('colors.ink-muted');
  transition: color 120ms ease, border-color 120ms ease, background 120ms ease;
}
.mic-btn:hover {
  color: theme('colors.ink');
  border-color: theme('colors.border-strong');
}
.mic-btn:focus-visible {
  outline: 2px solid theme('colors.ink-muted');
  outline-offset: 2px;
}
.mic-btn--listening {
  color: #b91c1c;            /* red-700 */
  border-color: #b91c1c66;
  background: #fef2f2;        /* red-50 */
  animation: mic-pulse 1.4s ease-in-out infinite;
}
@keyframes mic-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(185, 28, 28, 0.0);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(185, 28, 28, 0.18);
  }
}
@media (prefers-reduced-motion: reduce) {
  .mic-btn--listening {
    animation: none;
  }
}
</style>
