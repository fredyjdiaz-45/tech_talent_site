# USDA Technology Careers — Static Site

A single static **HTML page** styled with **Tailwind CSS** (compiled via the Tailwind CLI). No server, no templating engine — just files you can host anywhere (GitHub Pages, S3, Netlify, any static host).

## Structure

```
usda-tech-static/
├── index.html            The whole page
├── tailwind.config.js    USDA design tokens (colors, fonts) + preflight off
├── src/
│   └── input.css         Tailwind entry + bespoke component styles (@layer components)
├── css/
│   └── styles.css         ← COMPILED output (committed so it works with no build)
├── js/
│   └── main.js           Headline rotation + city-map interactions
├── assets/
│   └── usda-logo.png
├── image-slot.js
└── tweaks-panel.jsx
```

## View it

It already works as-is — `css/styles.css` is committed. Just open `index.html`, or:

```bash
npm run serve      # serves the folder at a localhost URL
```

## Editing styles

All styling lives in **`src/input.css`** (Tailwind directives + the bespoke component styles in `@layer components`). After editing it — or `tailwind.config.js` — recompile:

```bash
npm install        # first time only
npm run build      # writes css/styles.css
# or, while iterating:
npm run watch
```

You can also use **Tailwind utility classes** directly in `index.html` (e.g. `bg-usda-navy`, `text-usda-red`, `font-serif`, `max-w-content`) — they're scanned from `index.html` and `js/` on build. Preflight (Tailwind's reset) is intentionally **off** so the existing design renders exactly; utilities still apply.

> Why is `css/styles.css` checked in? So the page renders with zero build steps for preview/hosting. Running `npm run build` regenerates it from `src/input.css`.
