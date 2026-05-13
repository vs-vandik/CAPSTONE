<script setup lang="ts">
</script>

<template>
  <!--
    /about is image-driven, matching the editorial treatment used on
    the landing and /experts pages. Each section pairs a small eyebrow
    label SVG with a larger heading/body SVG so that the type renders
    pixel-identical to the design without depending on font loading.
    Intrinsic SVG dimensions, used here to preserve aspect ratios:

      about_label.svg            54x11
      outsource_thinking.svg     577x94    (hero headline)
      why_plato_label.svg        211x24
      why_plato_text.svg         783x341   (large prose block)
      our_pillars_label.svg      211x24
      our_pillars_graphic.svg    900x143   (the three pillars graphic)
      the_team_label.svg         175x19
      the_team_text.svg          720x39

    The full-bleed footer (silhouetted heads) is the same asset the
    landing page uses; the site-wide footer in App.vue is suppressed
    on this route so the heads sit flush at the bottom.
  -->
  <section class="max-w-page mx-auto px-6 pt-16 pb-20">
    <!-- Hero: ABOUT eyebrow + "Outsource thinking?" headline -->
    <div class="max-w-3xl">
      <img
        src="/about_label.svg"
        alt="About"
        class="h-[11px] w-auto mb-10"
      />
      <img
        src="/outsource_thinking.svg"
        alt="Outsource thinking?"
        class="h-auto w-full max-w-[577px]"
      />
    </div>

    <!-- Why plato -->
    <div class="mt-24 max-w-4xl">
      <img
        src="/why_plato_label.svg"
        alt="Why plato"
        class="h-[20px] w-auto mb-10"
      />
      <img
        src="/why_plato_text.svg"
        alt="Why plato"
        class="h-auto w-full max-w-[783px]"
      />
    </div>

    <!-- Our pillars -->
    <div class="mt-24">
      <img
        src="/our_pillars_label.svg"
        alt="Our pillars"
        class="h-[20px] w-auto mb-10"
      />
      <img
        src="/our_pillars_graphic.svg"
        alt="Our pillars"
        class="h-auto w-full max-w-[900px]"
      />
    </div>

    <!-- The team -->
    <div class="mt-24 max-w-4xl">
      <img
        src="/the_team_label.svg"
        alt="The team"
        class="h-[16px] w-auto mb-10"
      />
      <img
        src="/the_team_text.svg"
        alt="The team"
        class="h-auto w-full max-w-[720px]"
      />
    </div>
  </section>

  <!--
    Footer band — silhouetted heads, full bleed. Same treatment as the
    landing and /experts pages: mt-auto pins it to the bottom of
    <main> on tall screens, pt-24 keeps a comfortable gap above the
    heads on shorter content. The site-wide App.vue footer is
    suppressed on this route.

    Hidden below `sm` (same reason as on the landing): at phone widths
    the silhouettes squish into an unreadable grey blur. Restored at
    tablet+ where there's room for the band to breathe.
  -->
  <section class="hidden sm:block mt-auto pt-24">
    <img
      src="/footer_landing.svg"
      alt=""
      aria-hidden="true"
      class="w-full h-auto block select-none"
      draggable="false"
    />
  </section>
</template>
