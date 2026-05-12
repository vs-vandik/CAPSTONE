<script setup lang="ts">
</script>

<template>
  <!--
    Hero band — navy, full bleed, sits directly under the top bar.
    The lockup (π mark + divider + plato wordmark) is shipped as a
    single pre-composed SVG from design (header_logo_final.svg) so the
    spacing and proportions exactly match the source file.
  -->
  <section class="bg-accent">
    <div class="max-w-page mx-auto px-6 min-h-[240px] flex items-center justify-center">
      <img
        src="/header_logo_final.svg"
        alt="plato"
        class="h-20 w-auto block select-none"
        draggable="false"
      />
    </div>
  </section>

  <!-- Existing landing content (will be replaced in later steps). -->
  <section class="max-w-page mx-auto px-6">
    <div class="pt-20 pb-12 flex flex-col items-center text-center">
      <img
        src="/header_text.svg"
        alt="Be literate. Inform yourself. Listen. Observe. Build your own opinions"
        class="w-full max-w-[660px] h-auto"
      />
      <img
        src="/quote.svg"
        alt="Create friction between ideas."
        class="mt-20 w-full max-w-[600px] h-auto"
      />

      <div class="mt-12 flex items-center gap-10">
        <RouterLink
          to="/experts"
          class="inline-flex items-center justify-center bg-accent hover:bg-accent-hover transition-colors duration-150 px-5 py-2.5 rounded-sm"
          aria-label="Start a discourse"
        >
          <img
            src="/start_a_discourse_text.svg"
            alt="Start a discourse"
            class="h-3 w-auto block"
          />
        </RouterLink>
        <RouterLink
          to="/about"
          class="inline-flex items-center justify-center px-2 py-2.5 opacity-80 hover:opacity-100 transition-opacity duration-150"
          aria-label="About"
        >
          <img
            src="/about_text.svg"
            alt="About"
            class="h-3 w-auto block"
          />
        </RouterLink>
      </div>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-px bg-border border border-border rounded-sm overflow-hidden mt-6 mb-20">
      <div class="bg-surface p-6">
        <p class="label mb-2.5">01 — Experts</p>
        <h3 class="text-base font-serif text-ink mb-1.5">Curated, sourced</h3>
        <p class="text-[13px] text-ink-muted leading-relaxed">
          Each expert speaks from a curated corpus of their public
          writing or, where appropriate, hand-selected source material.
          No generic models.
        </p>
      </div>
      <div class="bg-surface p-6">
        <p class="label mb-2.5">02 — Dialogue</p>
        <h3 class="text-base font-serif text-ink mb-1.5">Plato moderates</h3>
        <p class="text-[13px] text-ink-muted leading-relaxed">
          A non-partisan facilitator opens the question, prompts each
          turn, and closes the inquiry. You advance the dialogue one
          move at a time.
        </p>
      </div>
      <div class="bg-surface p-6">
        <p class="label mb-2.5">03 — Aporia</p>
        <h3 class="text-base font-serif text-ink mb-1.5">A reasoned critique</h3>
        <p class="text-[13px] text-ink-muted leading-relaxed">
          When the dialogue concludes, Aporia surfaces the unexamined
          assumptions, points of contradiction, and questions the
          dialogue left unanswered.
        </p>
      </div>
    </div>
  </section>

  <!--
    Footer band — silhouetted heads, full bleed.
    Fixed top margin keeps the page from stretching to fill the
    viewport: heads sit just below the feature grid with controlled
    breathing room, not pinned to the bottom of tall screens.

    Hidden below `sm` because at phone widths the silhouettes squish
    down to a ~60px-tall band of grey blur that reads as visual noise.
    Restored on tablets/desktops where the SVG has room to breathe.
  -->
  <section class="hidden sm:block mt-10">
    <img
      src="/footer_landing.svg"
      alt=""
      aria-hidden="true"
      class="w-full h-auto block select-none"
      draggable="false"
    />
  </section>
</template>
