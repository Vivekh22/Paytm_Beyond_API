/**
 * GapScope Frontend Configuration
 * Design language follows finprob.com (stone + orange-500, Bricolage / Inter / JetBrains Mono).
 */

export const CONFIG = {
  // Backend runs locally on port 5000 (same machine, or the laptop's IP when opened from a phone on the same Wi-Fi)
  API_BASE: `http://${window.location.hostname || 'localhost'}:5000`,

  // Local only (no hosted deployment). Set to true only to build the UI without the backend running.
  USE_MOCK: false,

  // Demo presets for one-click instant evaluation
  EXAMPLE_PRESETS: [
    {
      mode: 1,
      query: 'UPI expense tracker for college students',
      label: 'UPI expense tracker',
      badge: '⚡ instant',
      category: 'Finance'
    },
    {
      mode: 2,
      query: 'Dunzo',
      label: 'Dunzo',
      badge: '⚡ instant',
      category: 'Quick-commerce'
    },
    {
      mode: 3,
      query: 'Personal Finance',
      label: 'Personal Finance',
      badge: '⚡ instant',
      category: 'Finance'
    },
    {
      mode: 1,
      query: 'AI career coach for engineering graduates',
      label: 'AI career coach',
      badge: '⚡ instant',
      category: 'EdTech'
    },
    {
      mode: 2,
      query: 'Cult.fit',
      label: 'Cult.fit',
      badge: '⚡ instant',
      category: 'Health'
    }
  ],

  // Source styling tokens (outlined mono pills, one tint per source)
  SOURCE_METAS: {
    play_store:  { name: 'Play Store',   letter: 'P', pillClass: 'border-green-700 text-green-800',                 textClass: 'text-green-800' },
    reddit:      { name: 'Reddit',       letter: 'R', pillClass: 'border-orange-600 text-orange-700',               textClass: 'text-orange-700' },
    google_news: { name: 'Google News',  letter: 'N', pillClass: 'border-blue-700 text-blue-800',                   textClass: 'text-blue-800' },
    you_web:     { name: 'You.com Web',  letter: 'Y', pillClass: 'border-violet-700 bg-violet-50 text-violet-800',  textClass: 'text-violet-800' },
    you_news:    { name: 'You.com News', letter: 'Y', pillClass: 'border-dashed border-violet-600 text-violet-700', textClass: 'text-violet-700' }
  },

  // Scoring thresholds
  THRESHOLDS: {
    BUILD_MIN: 65,
    PIVOT_MIN: 40
  }
};
