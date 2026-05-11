# Frontend Design — Bare Minimum

Plan only. No code yet. Update this doc when reality changes.

## Goal

Demo a Socratic debate between AI personas. The user picks a topic and 2
personas, watches Plato moderate a turn-by-turn discussion, then optionally
triggers an Aporia critique.

## Stack (proposed)

- Vue 3 + Vite + TypeScript
- Pinia (one store: `discourse`)
- Tailwind CSS
- `fetch` wrappers in `src/services/api.ts`
- Dev server on `:5173` (already in backend CORS)

## Screens (3)

### 1. Setup

User configures and starts a discourse.

Inputs:
- Topic — text input, required
- Personas — multi-select from `GET /api/v1/personas`, min 2, max 6
- Max turns — number, default 6
- "Start" button → `POST /api/v1/discourse/start`

On success, route to Discourse view with `session_id`.

### 2. Discourse

The main stage. Shows the running transcript and drives the loop.

Layout:
- Header: topic, participating personas (icon + name + color chip)
- Transcript: scrollable list of turns, newest at bottom, auto-scroll
  - Plato turns styled distinctly (centered? muted? italic?)
  - Expert turns as chat bubbles, color-tinted by `persona.color`,
    with name + icon
- Footer controls:
  - "Next turn" button → `POST /api/v1/discourse/{id}/next`
    (disabled while loading; auto-disables when `done: true`)
  - "Auto-play" toggle (optional v2): keeps calling /next every ~1s
  - "Aporia" button (enabled once history is non-empty)
  - "End" button → `DELETE /api/v1/discourse/{id}`, back to Setup

States:
- `idle` (just-loaded, no turns yet) → only "Next turn" available
- `loading` (a /next call is in flight) → spinner, controls disabled
- `active` (turns coming in)
- `done` (response had `done: true`) → "Next turn" disabled, prompt to
  trigger Aporia or end
- `error` (network / 503 missing API key) → inline banner, retry

### 3. Aporia panel

Not a separate route. A side panel or modal over the Discourse view.

- Triggered by Aporia button → `POST /api/v1/discourse/{id}/aporia`
- Renders `content`, `findings[]`, `guidance` from response
- Closeable; transcript stays underneath

## API contract (matches backend, do not invent)

Base URL: `http://localhost:8000/api/v1`

| Method | Path                              | Used by    | Notes                                  |
|--------|-----------------------------------|------------|----------------------------------------|
| GET    | `/personas`                       | Setup      | Populates persona picker               |
| GET    | `/personas/{id}`                  | (optional) | Detail hover/tooltip                   |
| POST   | `/discourse/start`                | Setup      | Body: `{topic, persona_ids, max_turns, socratic_mode}` |
| POST   | `/discourse/{id}/next`            | Discourse  | Returns one turn + `done: bool`        |
| GET    | `/discourse/{id}`                 | Discourse  | Hydrate on reload (optional)           |
| DELETE | `/discourse/{id}`                 | Discourse  | "End" button                           |
| POST   | `/discourse/{id}/aporia`          | Discourse  | Returns `{content, findings, guidance}`|
| GET    | `/aporia/button`                  | Discourse  | Button label/icon config (optional)    |
| GET    | `/health`                         | (optional) | Connection check                       |

### Turn shape

```
{
  "role": "plato" | "expert",
  "type": "opening" | "transition" | "closing" | "expert",
  "speaker": "Plato" | persona.name,
  "persona_id"?: string,    // expert turns only
  "content": string,
  "done": bool               // only on /next responses, not in /discourse history
}
```

## Pinia store sketch (`stores/discourse.ts`)

State:
- `personas: Persona[]`
- `sessionId: string | null`
- `topic: string`
- `selectedPersonaIds: string[]`
- `turns: Turn[]`
- `status: 'idle' | 'loading' | 'active' | 'done' | 'error'`
- `error: string | null`
- `aporia: AporiaResult | null`

Actions:
- `loadPersonas()`
- `start({topic, personaIds, maxTurns})`
- `nextTurn()` — appends to `turns`, flips `status` to `done` on `done: true`
- `runAporia()`
- `end()` — DELETE + reset

## Visual design (Figma pass before coding)

Goal: produce one source of truth for layout, color, and type before
touching Tailwind. Output transfers 1:1 into `tailwind.config.js`.

### Frames to create (8 total)

Setup screen:
1. Empty / initial load
2. Personas selected, valid → Start enabled
3. Validation error (e.g. only 1 persona picked)

Discourse screen:
4. Just started (Plato opening rendered, no expert turns yet)
5. Mid-debate (~4 turns, mix of Plato + experts, scrolled)
6. Loading state (Next-turn button spinning)
7. Done state (Plato closing, Next-turn disabled, Aporia highlighted)

Aporia:
8. Aporia panel open over a finished discourse

### Tokens to define in Figma (then port to Tailwind)

Color styles:
- `bg`, `surface`, `border`, `text`, `text-muted`, `accent`
- Persona accents come from API (`persona.color`) — do NOT redefine
  in Figma; just reference them in mockups using the actual hex values
  from `backend/app/core/personas.py`

Type styles:
- `display` (screen titles)
- `body` (turn content, the workhorse)
- `label` (persona names, controls)
- `mono` (optional, for `type` tags like "transition" / "opening")

Spacing: Tailwind defaults. Do not invent a custom scale.

### Decisions to lock during this pass

- Plato rendering: centered narrator banner vs. another bubble
- Persona chip: color dot + initial, or larger avatar with name
- Aporia placement: modal overlay vs. right-side panel vs. inline-after
- Desktop-first; mobile out of scope unless trivially free

### Definition of done for Phase 0.5

- All 8 frames exist with real persona names and a real sample topic
- Color + type styles defined and applied (no raw hex outside styles,
  except the persona-color references)
- One reviewer (you, an advisor, anyone) has looked at the frames and
  signed off before Phase 1 scaffold begins

## Out of scope (for now)

- Auth, multi-user, persistence beyond the current session
- Streaming token-by-token output (backend is non-streaming)
- Persona detail page
- Editing a debate mid-flight
- Saving/exporting transcripts

## Definition of done (frontend MVP)

1. Pick a topic and 2+ personas, click Start.
2. Click "Next turn" repeatedly; transcript fills in correctly with
   Plato opening, alternating expert + transition turns, Plato closing.
3. Click "Aporia"; panel renders findings.
4. Click "End"; back to Setup with state cleared.
5. Network errors and missing-API-key (503) surface as readable messages,
   not console traces.
