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

export type TurnRole = 'plato' | 'expert'
export type TurnType = 'opening' | 'transition' | 'closing' | 'expert'

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
  max_turns: number
  status: 'active' | 'done'
}

export interface AporiaFinding {
  // Backend's findings shape varies; we render whatever is there generically.
  [k: string]: unknown
  type?: string
  title?: string
  detail?: string
  description?: string
  evidence?: string | string[]
}

export interface AporiaResult {
  role: 'plato'
  type: 'aporia'
  content: string
  findings: AporiaFinding[]
  guidance: string
}

export type DiscourseStatus =
  | 'idle'
  | 'loading'
  | 'active'
  | 'done'
  | 'error'
