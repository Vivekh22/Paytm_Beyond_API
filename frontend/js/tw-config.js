/* Tailwind CDN config, shared by index.html and report.html.
 * Mirrors finprob.com's design system: stone neutrals + orange-500 accent,
 * Bricolage Grotesque (display), Inter (body), JetBrains Mono (meta). */
tailwind.config = {
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'Menlo', 'monospace'],
        display: ['"Bricolage Grotesque"', '"Arial Narrow"', 'Arial', 'sans-serif']
      }
    }
  }
};
