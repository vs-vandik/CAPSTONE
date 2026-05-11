<script setup lang="ts">
</script>

<template>
  <section class="max-w-page mx-auto px-6 py-20">
    <div class="max-w-prose">
      <p class="label mb-6">About</p>
      <h1 class="font-serif text-4xl sm:text-5xl leading-tight tracking-tightish text-ink mb-8">
        The reasoning layer beneath the decision.
      </h1>

      <div class="space-y-6 text-ink-muted leading-relaxed">
        <p>
          Discourse is a reasoning instrument for asset managers,
          allocators, and enterprise risk practitioners who need to
          stress-test a thesis against credible, articulated opposition.
          It does not produce recommendations. It produces dialogue —
          structured, attributed, and traceable to source.
        </p>

        <h2 class="font-serif text-2xl text-ink pt-8">Method</h2>
        <p>
          Each expert is grounded in a corpus of their own words. For
          living public figures with substantial written records — Warren
          Buffett's shareholder letters, Larry Fink's annual letters,
          Elon Musk's interviews and statements — we retrieve the most
          topically relevant passages at debate time and use them to
          shape the model's voice. For historical figures and others
          with sparser usable corpora, we use a hand-curated quote bank
          selected by similarity to the topic.
        </p>
        <p>
          Plato moderates. He is template-based, not generative: his
          opening, transitions, and closing follow Socratic structure
          deliberately so the dialogue remains a dialogue and not a
          summary.
        </p>
        <p>
          Aporia is the critical layer. After a dialogue concludes, it
          examines the transcript for unexamined assumptions, internal
          contradictions, and the questions that were avoided. It is
          named for the productive impasse Socrates sought — the moment
          where one realizes that what seemed certain is not.
        </p>

        <h2 class="font-serif text-2xl text-ink pt-8">Limits</h2>
        <p>
          The experts are stylistic and substantive approximations, not
          the people themselves. They are useful for stress-testing a
          framing, surfacing a counter-argument you had not constructed,
          or articulating a position from a vantage point you do not
          inhabit. They are not oracles. None of the output constitutes
          investment advice.
        </p>

        <h2 class="font-serif text-2xl text-ink pt-8">Intended use</h2>
        <p>
          Run Discourse before an investment committee meeting to
          rehearse the strongest objections to a proposed view. Use it
          to widen the frame on an enterprise risk scenario by inviting
          a non-financial voice into a financial conversation. Use it
          to find the assumption you did not know you were making.
        </p>
      </div>

      <div class="mt-12">
        <RouterLink to="/experts" class="btn-primary">
          Start a Discourse
        </RouterLink>
      </div>
    </div>
  </section>
</template>
