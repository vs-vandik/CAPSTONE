// Mirrors backend response shapes from backend/app/api/routes.py and the
// turn shape produced by backend/app/agents/discourse.py. Keep in sync.

export interface Persona {
  id: string
  name: string
  title: string
  icon: string
  color: string // hex from personas.py; we render it lightly tinted
  bio: string
  rag_tier: 'full' | 'curated'
}

export type TurnRole = 'plato' | 'expert' | 'user'
export type TurnType =
  | 'opening'
  | 'transition'
  | 'closing'
  | 'expert'
  | 'user_input'

export interface Turn {
  role: TurnRole
  type: TurnType
  speaker: string
  persona_id?: string
  content: string
  // /next responses include `done`; turns inside session.history do not.
  done?: boolean
}

export interface SessionStartResponse {
  session_id: string
  topic: string
  persona_ids: string[]
  user_name: string
  max_turns: number
  status: 'active' | 'done'
}

// One dialectical point within a category. Assumptions and
// contradictions have `{point, why}`; fallacies also carry a `name`
// (the established name of the reasoning error).
export interface AporiaPoint {
  point: string
  why: string
  name?: string
}

// Per-expert dialectical breakdown. Each list is 0-3 items.
export interface AporiaExpert {
  expert: string
  assumptions: AporiaPoint[]
  fallacies: AporiaPoint[]
  contradictions: AporiaPoint[]
}

// Flat back-compat view of the same content, one entry per point.
export interface AporiaFinding {
  expert?: string
  kind?: 'assumption' | 'fallacy' | 'contradiction' | string
  type?: string
  title?: string
  detail?: string
  description?: string
}

export interface AporiaResult {
  role: 'plato'
  type: 'aporia'
  // `content` and `guidance` are intentionally empty in the steady
  // state — the structured `experts[]` carries the meaning. They are
  // only populated in degraded responses (no LLM key, parse error,
  // no expert turns yet) to explain why nothing structured is here.
  content: string
  guidance: string
  speakers: string[]
  experts: AporiaExpert[]
  findings: AporiaFinding[]
}

export type DiscourseStatus =
  | 'idle'
  | 'loading'
  | 'active'
  | 'done'
  | 'error'
