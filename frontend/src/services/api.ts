// Thin fetch wrapper around the FastAPI backend.
// Vite proxies /api -> http://localhost:8000 (see vite.config.ts), so we
// never hardcode an absolute origin here. Production builds should set
// VITE_API_BASE if the API lives somewhere else.

import type {
  AporiaResult,
  Persona,
  SessionStartResponse,
  Turn,
} from '@/types'

const BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
    ...init,
  })
  if (!res.ok) {
    // Try to surface FastAPI's `detail` field for readable errors.
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  listPersonas(): Promise<{ personas: Persona[] }> {
    return request('/personas')
  },

  startDiscourse(body: {
    topic: string
    persona_ids: string[]
    user_name?: string
    max_turns?: number
    socratic_mode?: boolean
  }): Promise<SessionStartResponse> {
    return request('/discourse/start', {
      method: 'POST',
      body: JSON.stringify({
        max_turns: 6,
        socratic_mode: true,
        ...body,
      }),
    })
  },

  nextTurn(sessionId: string): Promise<Turn> {
    return request(`/discourse/${sessionId}/next`, { method: 'POST' })
  },

  addUserInput(sessionId: string, content: string): Promise<Turn> {
    return request(`/discourse/${sessionId}/input`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
  },

  endDiscourse(sessionId: string): Promise<{ message: string }> {
    return request(`/discourse/${sessionId}`, { method: 'DELETE' })
  },

  runAporia(sessionId: string): Promise<AporiaResult> {
    return request(`/discourse/${sessionId}/aporia`, { method: 'POST' })
  },
}
