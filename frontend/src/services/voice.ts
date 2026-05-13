// Browser-native speech recognition (STT) for the proposition field.
// No backend, no network from our side. All audio work happens in the
// user's browser via the Web Speech API.
//
// Design notes:
//   - Speech recognition is webkit-prefixed in Chromium and bare in
//     newer specs; Firefox does not implement it. We expose a `supported`
//     flag and degrade silently when missing — the UI hides the mic
//     button rather than showing a broken control.
//   - Chrome's recognizer routes audio through Google for transcription;
//     this is a property of the browser API. Users who object should
//     simply type their proposition — the typed flow is the primary path.
//   - We do not provide text-to-speech. If you ever add it back, prefer
//     a centralized controller (provide/inject) over per-component
//     state so utterances never overlap.

import { onBeforeUnmount, ref } from 'vue'

// Window typings for the prefixed Chrome API. We avoid `any` so this
// composable stays type-safe in the call-sites.
type SpeechRecognitionCtor = new () => SpeechRecognitionLike

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  abort(): void
  onresult: ((e: SpeechRecognitionEventLike) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<{
    isFinal: boolean
    0: { transcript: string }
  }>
}

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition || w.webkitSpeechRecognition || null
}

export interface UseSpeechRecognitionOptions {
  lang?: string
  // Called whenever the transcript updates (interim or final). Lets the
  // caller mirror the text into a textarea in real time.
  onUpdate?: (transcript: string, isFinal: boolean) => void
}

export function useSpeechRecognition(opts: UseSpeechRecognitionOptions = {}) {
  const Ctor = getRecognitionCtor()
  const supported = ref(!!Ctor)
  const listening = ref(false)
  const transcript = ref('')
  const error = ref<string | null>(null)

  let rec: SpeechRecognitionLike | null = null

  function ensure(): SpeechRecognitionLike | null {
    if (!Ctor) return null
    if (rec) return rec
    rec = new Ctor()
    rec.lang = opts.lang ?? 'en-US'
    // continuous=false: a single utterance per click. Long-form
    // dictation is out of scope; the proposition field is one sentence.
    rec.continuous = false
    // interimResults=true: stream partial transcripts to the textarea so
    // the user sees their words appear as they speak.
    rec.interimResults = true
    rec.maxAlternatives = 1

    rec.onresult = (e) => {
      let interim = ''
      let final = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        const text = r[0].transcript
        if (r.isFinal) final += text
        else interim += text
      }
      // Prefer the finalized text, fall through to interim while the
      // recognizer hasn't committed yet.
      const combined = (final || interim).trim()
      transcript.value = combined
      opts.onUpdate?.(combined, !!final)
    }

    rec.onerror = (e) => {
      // "no-speech" and "aborted" are normal user actions, not bugs;
      // don't surface them as errors.
      if (e.error === 'no-speech' || e.error === 'aborted') {
        error.value = null
      } else {
        error.value = e.error
      }
      listening.value = false
    }

    rec.onend = () => {
      listening.value = false
    }

    return rec
  }

  function start() {
    if (!supported.value) return
    const r = ensure()
    if (!r) return
    try {
      transcript.value = ''
      error.value = null
      r.start()
      listening.value = true
    } catch {
      // Chrome throws InvalidStateError if start() is called while
      // already listening; ignore — our `listening` ref is the truth.
      listening.value = true
    }
  }

  function stop() {
    if (!rec) return
    try {
      rec.stop()
    } catch {
      // ignore
    }
    listening.value = false
  }

  function toggle() {
    if (listening.value) stop()
    else start()
  }

  onBeforeUnmount(() => {
    if (rec) {
      try { rec.abort() } catch { /* ignore */ }
      rec.onresult = null
      rec.onerror = null
      rec.onend = null
      rec = null
    }
  })

  return { supported, listening, transcript, error, start, stop, toggle }
}
