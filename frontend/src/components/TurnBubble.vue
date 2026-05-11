<script setup lang="ts">
import { computed } from 'vue'
import type { Persona, Turn } from '@/types'
import { renderParagraphs } from '@/services/format'

const props = defineProps<{
  turn: Turn
  persona?: Persona
}>()

const isPlato = computed(() => props.turn.role === 'plato')
const html = computed(() => renderParagraphs(props.turn.content))

const typeLabel = computed(() => {
  switch (props.turn.type) {
    case 'opening':
      return 'Opening'
    case 'transition':
      return 'Transition'
    case 'closing':
      return 'Closing'
    default:
      return ''
  }
})

const accentColor = computed(() => props.persona?.color ?? '#1F3A5F')
</script>

<template>
  <article
    v-if="isPlato"
    class="my-8 mx-auto max-w-prose text-center"
  >
    <p
      v-if="typeLabel"
      class="label mb-2"
    >
      Plato — {{ typeLabel }}
    </p>
    <div
      class="prose-plato text-ink-muted font-serif italic leading-relaxed"
      v-html="html"
    />
  </article>

  <article
    v-else
    class="my-8"
  >
    <header class="flex items-center gap-3 mb-3">
      <span
        class="w-8 h-8 inline-flex items-center justify-center rounded-sm font-serif text-sm flex-shrink-0"
        :style="{
          backgroundColor: accentColor + '18',
          color: accentColor,
          border: `1px solid ${accentColor}40`,
        }"
        aria-hidden="true"
      >
        {{ persona?.icon ?? turn.speaker.charAt(0) }}
      </span>
      <div class="min-w-0">
        <p class="text-sm font-medium text-ink">{{ turn.speaker }}</p>
        <p
          v-if="persona?.title"
          class="text-xs text-ink-faint truncate"
        >
          {{ persona.title }}
        </p>
      </div>
    </header>
    <div
      class="prose-turn text-ink leading-relaxed pl-11 border-l-2"
      :style="{ borderLeftColor: accentColor + '60' }"
    >
      <div class="pl-0" v-html="html" />
    </div>
  </article>
</template>

<style scoped>
.prose-plato :deep(p) {
  margin-bottom: 0.75rem;
}
.prose-plato :deep(p:last-child) {
  margin-bottom: 0;
}
.prose-plato :deep(strong) {
  color: theme('colors.ink');
  font-weight: 500;
  font-style: normal;
}
.prose-plato :deep(blockquote) {
  border-left: 2px solid theme('colors.border-strong');
  padding-left: 1rem;
  margin: 1rem auto;
  max-width: 36rem;
  font-style: italic;
}

.prose-turn :deep(p) {
  margin-bottom: 0.85rem;
}
.prose-turn :deep(p:last-child) {
  margin-bottom: 0;
}
.prose-turn :deep(strong) {
  font-weight: 600;
}
.prose-turn :deep(em) {
  font-style: italic;
}
</style>
