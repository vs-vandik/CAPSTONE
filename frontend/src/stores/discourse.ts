import { defineStore } from 'pinia'
import { api } from '@/services/api'
import type {
  AporiaResult,
  DiscourseStatus,
  Persona,
  Turn,
} from '@/types'

interface State {
  // Catalog
  personas: Persona[]
  personasLoaded: boolean
  personasLoading: boolean

  // Setup flow (persists across the Personas -> Topic -> Discourse pages)
  selectedPersonaIds: string[]
  userName: string
  topic: string

  // Active session
  sessionId: string | null
  maxTurns: number
  turns: Turn[]
  status: DiscourseStatus
  error: string | null
  aporia: AporiaResult | null
}

// In-flight persona fetch promise, shared across concurrent callers so
// e.g. PersonasView + DiscourseView mounting in quick succession don't
// each fire their own request.
let personasInflight: Promise<void> | null = null

export const useDiscourseStore = defineStore('discourse', {
  state: (): State => ({
    personas: [],
    personasLoaded: false,
    personasLoading: false,
    selectedPersonaIds: [],
    userName: '',
    topic: '',
    sessionId: null,
    maxTurns: 6,
    turns: [],
    status: 'idle',
    error: null,
    aporia: null,
  }),

  getters: {
    selectedPersonas(state): Persona[] {
      const map = new Map(state.personas.map((p) => [p.id, p]))
      return state.selectedPersonaIds
        .map((id) => map.get(id))
        .filter((p): p is Persona => Boolean(p))
    },
    isReadyForTopic(state): boolean {
      return state.selectedPersonaIds.length === 2
    },
    isReadyToStart(state): boolean {
      return (
        state.selectedPersonaIds.length === 2 &&
        state.userName.trim().length > 0 &&
        state.topic.trim().length > 0
      )
    },
    canAdvance(state): boolean {
      return (
        state.status === 'active' || state.status === 'idle'
      )
    },
    /**
     * Persona about to speak on the next /next call, when that turn
     * will be an expert turn. Returns null if Plato is up next (opening,
     * transition, closing) or if we don't have enough state to decide.
     *
     * Mirrors the backend rotation in `backend/app/agents/discourse.py`:
     *   - empty history             -> Plato opens
     *   - last turn was Plato       -> the matching expert speaks
     *   - last turn was an expert,
     *     hit max_turns budget      -> Plato closes
     *   - last turn was an expert,
     *     under budget              -> Plato transitions (template, fast)
     *
     * So the only state in which we want to surface an expert name in
     * the "thinking" indicator is when the most recent turn is from
     * Plato and an expert is queued. Order of `selectedPersonas` is
     * authoritative; round-robin index is `expertTurnsSoFar % n`.
     */
    nextExpertSpeaker(state): Persona | null {
      const personas = (this as unknown as { selectedPersonas: Persona[] })
        .selectedPersonas
      if (personas.length === 0) return null

      const history = state.turns
      if (history.length === 0) return null // Plato opens

      const last = history[history.length - 1]
      // If last turn was Plato (opening or transition), an expert is next.
      // After an expert speaks, Plato always interjects (transition or
      // closing) before the next expert, so we never need to predict the
      // *expert-after-Plato-after-expert* hop here.
      if (last.role !== 'plato') return null

      const expertTurnsSoFar = history.filter((t) => t.role === 'expert').length
      const idx = expertTurnsSoFar % personas.length
      return personas[idx] ?? null
    },
  },

  actions: {
    async loadPersonas(opts: { force?: boolean } = {}) {
      // Already have a usable catalog -> done.
      if (this.personasLoaded && this.personas.length > 0 && !opts.force) {
        return
      }
      // Coalesce concurrent callers onto the same in-flight request, so
      // we don't fire two /personas requests when PersonasView mounts
      // right after a route guard has already kicked one off.
      if (personasInflight) {
        return personasInflight
      }

      this.personasLoading = true
      this.error = null

      // Retry with a short backoff: the most common reason the very
      // first load fails is the dev backend cold-starting (numpy
      // import + embeddings load can stretch past a fetch timeout, and
      // the Vite proxy occasionally returns ECONNREFUSED for ~100ms
      // while uvicorn binds the port). Three attempts is more than
      // enough to bridge that without making real failures feel slow.
      const attempt = async (): Promise<void> => {
        const delays = [0, 600, 1500]
        let lastErr: unknown = null
        for (let i = 0; i < delays.length; i++) {
          if (delays[i] > 0) {
            await new Promise((r) => setTimeout(r, delays[i]))
          }
          try {
            const { personas } = await api.listPersonas()
            // Defensive: treat an empty list as a failure too, so the
            // user never sees a silent "no cards" screen. The backend
            // ships six personas; zero means the response was malformed
            // or the route is misbehind a proxy.
            if (!Array.isArray(personas) || personas.length === 0) {
              throw new Error('Empty personas response')
            }
            this.personas = personas
            this.personasLoaded = true
            this.error = null
            return
          } catch (e) {
            lastErr = e
            // keep looping
          }
        }
        // Out of retries: surface the last error.
        this.error = (lastErr as Error)?.message ?? 'Failed to load personas'
      }

      personasInflight = attempt().finally(() => {
        this.personasLoading = false
        personasInflight = null
      })
      return personasInflight
    },

    togglePersona(id: string) {
      const i = this.selectedPersonaIds.indexOf(id)
      if (i >= 0) {
        this.selectedPersonaIds.splice(i, 1)
        return
      }
      // Cap at 2: if already 2 selected, replace the older one.
      if (this.selectedPersonaIds.length >= 2) {
        this.selectedPersonaIds.shift()
      }
      this.selectedPersonaIds.push(id)
    },

    setTopic(topic: string) {
      this.topic = topic
    },

    setUserName(userName: string) {
      this.userName = userName
    },

    async start(): Promise<string | null> {
      if (!this.isReadyToStart) return null
      this.status = 'loading'
      this.error = null
      this.turns = []
      this.aporia = null
      try {
        const res = await api.startDiscourse({
          topic: this.topic.trim(),
          persona_ids: [...this.selectedPersonaIds],
          user_name: this.userName.trim(),
        })
        this.sessionId = res.session_id
        this.userName = res.user_name
        this.maxTurns = res.max_turns
        this.status = 'idle'
        return res.session_id
      } catch (e) {
        this.error = (e as Error).message
        this.status = 'error'
        return null
      }
    },

    async addUserInput(content: string) {
      if (!this.sessionId) return
      if (this.status === 'done' || this.status === 'loading') return
      this.status = 'loading'
      this.error = null
      try {
        const turn = await api.addUserInput(this.sessionId, content)
        this.turns.push(turn)
        this.status = turn.done ? 'done' : 'active'
      } catch (e) {
        this.error = (e as Error).message
        this.status = 'error'
      }
    },

    async nextTurn() {
      if (!this.sessionId) return
      if (this.status === 'done' || this.status === 'loading') return
      this.status = 'loading'
      this.error = null
      try {
        const turn = await api.nextTurn(this.sessionId)
        this.turns.push(turn)
        this.status = turn.done ? 'done' : 'active'
      } catch (e) {
        this.error = (e as Error).message
        this.status = 'error'
      }
    },

    async runAporia() {
      if (!this.sessionId) return
      this.error = null
      try {
        this.aporia = await api.runAporia(this.sessionId)
      } catch (e) {
        this.error = (e as Error).message
      }
    },

    closeAporia() {
      this.aporia = null
    },

    async end() {
      if (this.sessionId) {
        try {
          await api.endDiscourse(this.sessionId)
        } catch {
          // ignore — session may already be gone server-side
        }
      }
      this.sessionId = null
      this.maxTurns = 6
      this.turns = []
      this.status = 'idle'
      this.error = null
      this.aporia = null
    },

    resetAll() {
      this.selectedPersonaIds = []
      this.userName = ''
      this.topic = ''
      this.end()
    },
  },
})
