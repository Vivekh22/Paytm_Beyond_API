/**
 * GapScope Frontend Configuration
 * Design language follows finprob.com (stone + orange-500, Bricolage / Inter / JetBrains Mono).
 */

export const CONFIG = {
  // On HTTPS (Vercel cloud), route to same-origin /api. On local HTTP, use port 5000.
  API_BASE: (typeof window !== 'undefined' && window.location.protocol === 'https:')
    ? ''
    : `http://${(typeof window !== 'undefined' && window.location.hostname) || 'localhost'}:5000`,

  // Set to true only if backend is not running at all
  USE_MOCK: false,

  // Demo presets for one-click instant evaluation
  // Fallback only, used if /api/examples can't be reached. Must match backend DEMO_PRESETS.
  EXAMPLE_PRESETS: [
    { mode: 1, query: 'UPI expense tracker for college students', label: 'UPI Expense Tracker' },
    { mode: 1, query: 'AI tutor for JEE aspirants', label: 'AI Tutor for JEE' },
    { mode: 1, query: 'Pet care booking app in Bengaluru', label: 'Pet Care Booking' },
    { mode: 2, query: 'Dunzo', label: 'Dunzo' },
    { mode: 2, query: 'Swiggy Instamart', label: 'Swiggy Instamart' },
    { mode: 2, query: 'Cult.fit', label: 'Cult.fit' },
    { mode: 3, query: 'Personal Finance', label: 'Personal Finance' },
    { mode: 3, query: 'EdTech', label: 'EdTech' },
    { mode: 3, query: 'Healthcare', label: 'Healthcare' },
    { mode: 4, query: 'Blue Dart', label: 'Blue Dart' },
    { mode: 4, query: 'IRCTC', label: 'IRCTC' }
  ],

  // Source styling tokens (outlined mono pills, one tint per source)
  SOURCE_METAS: {
    play_store:  { name: 'Play Store',   letter: 'P', pillClass: 'border-green-700 text-green-800',                 textClass: 'text-green-800' },
    reddit:      { name: 'Reddit',       letter: 'R', pillClass: 'border-orange-600 text-orange-700',               textClass: 'text-orange-700' },
    google_news: { name: 'Google News',  letter: 'N', pillClass: 'border-blue-700 text-blue-800',                   textClass: 'text-blue-800' },
    you_web:     { name: 'You.com Web',  letter: 'Y', pillClass: 'border-violet-700 bg-violet-50 text-violet-800',  textClass: 'text-violet-800' },
    you_news:    { name: 'You.com News', letter: 'Y', pillClass: 'border-dashed border-violet-600 text-violet-700', textClass: 'text-violet-700' },
    google_search: { name: 'Google Search', letter: 'G', pillClass: 'border-sky-700 text-sky-800',    textClass: 'text-sky-800' },
    google_maps:   { name: 'Google Maps',   letter: 'M', pillClass: 'border-emerald-700 text-emerald-800', textClass: 'text-emerald-800' },
    google_jobs:   { name: 'Google Jobs',   letter: 'J', pillClass: 'border-indigo-700 text-indigo-800', textClass: 'text-indigo-800' },
    app_store:     { name: 'App Store',     letter: 'A', pillClass: 'border-stone-700 text-stone-800',  textClass: 'text-stone-800' }
  },

  // Scoring thresholds
  THRESHOLDS: {
    BUILD_MIN: 65,
    PIVOT_MIN: 40
  }
};
