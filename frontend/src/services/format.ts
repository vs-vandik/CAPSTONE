// Strip emojis and the decorative leading "📜 *...*" / "🜵 *...*" lines
// that backend Plato templates use. The brief calls for a clean,
// emoji-free UI; rather than rewrite plato.py we sanitize at render time.
//
// This is pragmatic, not principled: when plato.py is cleaned up
// upstream, this function becomes a no-op and can be removed.

const EMOJI_RE =
  /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}\u{1F100}-\u{1F1FF}\u{1F200}-\u{1F2FF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{2300}-\u{23FF}\u{2B00}-\u{2BFF}\u{1F100}-\u{1F1FF}\u{1F900}-\u{1F9FF}]/gu

// Catches the alchemical symbols Plato uses (e.g. 🜵 — code point U+1F735).
const SYMBOL_RE = /[\u{1F700}-\u{1F77F}]/gu

export function cleanContent(text: string): string {
  if (!text) return ''
  let out = text.replace(EMOJI_RE, '').replace(SYMBOL_RE, '')

  // Plato opens with "*The Academy gathers...*" or similar italic stage
  // directions. Drop pure-italic single-line stage directions; they read
  // as theatrical clutter in a professional UI.
  out = out
    .split('\n')
    .map((line) => line.trimEnd())
    .filter((line, idx, arr) => {
      const trimmed = line.trim()
      if (/^\*[^*]+\*$/.test(trimmed)) return false // pure stage direction
      // Drop leading empty line if present
      if (idx === 0 && trimmed === '') return false
      // Collapse triple-blanks down further
      if (
        trimmed === '' &&
        arr[idx - 1]?.trim() === '' &&
        arr[idx - 2]?.trim() === ''
      )
        return false
      return true
    })
    .join('\n')
    .trim()

  return out
}

// Very small markdown handler: bold (**x**), italic (*x*), and
// blockquotes (> x). Renders to safe HTML — no user-submitted HTML, only
// LLM/template output we already trust at the source. Still escape first.
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export function renderInline(text: string): string {
  let s = escapeHtml(text)
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  return s
}

export function renderParagraphs(text: string): string {
  const cleaned = cleanContent(text)
  const blocks = cleaned.split(/\n\s*\n/)
  return blocks
    .map((block) => {
      const trimmed = block.trim()
      if (!trimmed) return ''
      if (trimmed.startsWith('> ')) {
        const inner = trimmed
          .split('\n')
          .map((l) => l.replace(/^>\s?/, ''))
          .join(' ')
        return `<blockquote>${renderInline(inner)}</blockquote>`
      }
      return `<p>${renderInline(trimmed).replace(/\n/g, '<br/>')}</p>`
    })
    .filter(Boolean)
    .join('\n')
}
