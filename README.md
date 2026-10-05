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

## Domain owner lookup

`domain-owner/owner.mjs` finds who owns a list of domains (no deps, no API keys) and prints CSV: registrant org from RDAP, falling back to the TLS certificate's Organization when WHOIS is privacy-redacted.

- **Run in GitHub:** Actions → *Domain owners* → *Run workflow*, paste domains, download the `owners` CSV artifact (also shown in the run summary).
- **Run locally:** `node domain-owner/owner.mjs domains.txt > owners.csv`
- **Test:** `node --test domain-owner/owner.test.mjs`

A blank `owner` means the registrant is hidden behind a privacy service and the site uses a basic (DV) certificate.
