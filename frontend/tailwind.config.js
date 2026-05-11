/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Calm, professional, near-monochrome palette.
        // Background ladder: page -> surface -> surface-2 (raised cards).
        bg: '#FAFAF7',
        surface: '#FFFFFF',
        'surface-2': '#F3F2EE',
        border: '#E4E2DB',
        'border-strong': '#C9C6BC',
        ink: '#1A1A1A',
        'ink-muted': '#5C5A52',
        'ink-faint': '#8A8880',
        accent: '#1F3A5F', // restrained navy
        'accent-hover': '#162A45',
      },
      fontFamily: {
        // Prompt is the single typeface across the brand. Loaded from
        // Google Fonts in index.html. Both `font-sans` and `font-serif`
        // resolve to Prompt so existing class usage continues to work
        // without per-component edits; hierarchy is carried by weight
        // and size, not by family.
        sans: [
          'Prompt',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
        serif: [
          'Prompt',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
        mono: [
          '"SF Mono"',
          'Menlo',
          'Consolas',
          '"Liberation Mono"',
          'monospace',
        ],
      },
      maxWidth: {
        prose: '68ch',
        page: '1100px',
      },
      letterSpacing: {
        tightish: '-0.01em',
      },
    },
  },
  plugins: [],
}
