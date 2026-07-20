# ClauseChain Frontend — Next.js Review Console

The judge-/reviewer-facing web UI: dashboard, review workbench, run console,
consolidated RDTII dataset, decision ledger, raw-data explorer, knowledge graph.

> Optional component — the engine (`../engine`) runs standalone. See the root
> `README.md` and `README_WEB.md` (screen-by-screen guide with screenshots).

## Local setup

```bash
cd frontend
npm ci                 # Node.js 24.x
npm run dev            # http://localhost:3000  (Django backend on :8000 required)
```

The app calls `/api/*` on its own origin; in dev Next.js rewrites to the Django
server. Sign in with the public read-only demo account printed on the login
page (`viewer` / `escap-rdtii-2026`) or an account created via the backend.

## Production build

```bash
npm ci
npm run build
npm run start          # serves on :3000 — put nginx TLS in front
```

Run under systemd; nginx proxies `/` → `:3000` and `/api/` → the Django
backend. Rebuild + restart on every deploy (`npm run build` is required —
`next dev` is not for production).

Stack: Next.js (App Router) · React · Tailwind · TanStack Query · lucide icons.
