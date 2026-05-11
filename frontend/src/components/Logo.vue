<script setup lang="ts">
/**
 * Logo — plato wordmark + π mark.
 *
 * Files in /public:
 *   /plato_logo_{variant}.svg     : full lockup (mark adjacent to wordmark)
 *   /plato_mark_{variant}.svg     : square π mark only
 *   /plato_wordmark_{variant}.svg : "plato" wordmark only (no π)
 *
 * Loaded as <img> rather than inlined because the SVGs ship with their
 * own brand colors (black / off-white) baked in. Use `variant` to pick
 * the right one for the surrounding context, and `mode` to pick which
 * piece of the brand mark you want.
 */
withDefaults(
  defineProps<{
    /** Which slice of the brand to render. */
    mode?: 'lockup' | 'mark' | 'wordmark'
    /** Visual height in px. Width auto-sized by SVG aspect. */
    height?: number
    /** Color variant. Pick to contrast with the parent surface. */
    variant?: 'black' | 'white'
    /** Optional aria-label override. */
    label?: string
  }>(),
  {
    mode: 'lockup',
    height: 28,
    variant: 'black',
    label: 'plato',
  },
)
</script>

<template>
  <img
    v-if="mode === 'lockup'"
    :src="`/plato_logo_${variant}.svg`"
    :alt="label"
    :height="height"
    class="block select-none"
    draggable="false"
  />
  <img
    v-else-if="mode === 'mark'"
    :src="`/plato_mark_${variant}.svg`"
    :alt="label"
    :height="height"
    :width="height"
    class="block select-none"
    draggable="false"
  />
  <img
    v-else
    :src="`/plato_wordmark_${variant}.svg`"
    :alt="label"
    :height="height"
    class="block select-none"
    draggable="false"
  />
</template>
