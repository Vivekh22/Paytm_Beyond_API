/**
 * GapScope Frontend Configuration
 * Design language follows finprob.com (stone + orange-500, Bricolage / Inter / JetBrains Mono).
 */

const isBrowser = typeof window !== 'undefined';
const isLocal = isBrowser && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export const CONFIG = {
  // Live Backend URL (auto-detects port 5000 for direct origin or defaults to http://localhost:5000)
  API_BASE: (typeof window !== 'undefined' && window.location.port === '5000')
    ? ''
    : (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'))
    ? 'http://localhost:5000'
    : '',

  // Mock-first flag: false attempts live Python backend first, with resilient instant fallback
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
      query: 'Travel',
      label: 'Travel',
      badge: '⚡ instant',
      category: 'Travel & Hospitality'
    },
    {
      mode: 3,
      query: 'Personal Finance',
      label: 'Personal Finance',
      badge: '⚡ instant',
      category: 'Finance'
    },
    {
      mode: 3,
      query: 'EdTech',
      label: 'EdTech',
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

  // Cache duration in milliseconds (72 hours)
  CACHE_TTL_MS: 72 * 60 * 60 * 1000
};
