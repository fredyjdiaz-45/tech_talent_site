/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './js/**/*.js'],
  // The bespoke component styles (src/input.css → css/styles.css) ship their own
  // reset and own every element's look, so Tailwind's preflight is disabled to
  // avoid double-resetting. Utilities + the USDA tokens below are still available
  // for any new markup you add.
  corePlugins: { preflight: false },
  theme: {
    extend: {
      colors: {
        paper: { DEFAULT: '#FAF8F4', 2: '#F1ECE3', 3: '#E7E0D2' },
        ink: { DEFAULT: '#1A1A1A', 2: '#3A3A3A' },
        muted: '#6B6B66',
        line: { DEFAULT: '#D8D2C2', 2: '#C5BCA6' },
        usda: {
          red: '#D6202F',
          'red-dk': '#A8141F',
          navy: '#0A2240',
          'navy-2': '#0F2C50',
          gold: '#B58A2E',
          cream: '#F5EFDF',
        },
      },
      fontFamily: {
        serif: ['Merriweather', 'Georgia', 'serif'],
        sans: ['Source Sans 3', 'Public Sans', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'Menlo', 'monospace'],
      },
      maxWidth: { content: '1240px' },
    },
  },
  plugins: [],
};
