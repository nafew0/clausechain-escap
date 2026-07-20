This frontend template targets:
- `Node.js 24.15.x`
- `npm 11.12.1`

The project declares:
- `"packageManager": "npm@11.12.1"`
- `"engines": { "node": "24.15.x", "npm": "11.12.1" }`

Use `npm` for dependency installation and scripts.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

### Workspace data modes

The workspace uses the authenticated Django API by default. For API-off frontend work only,
regenerate the fixture from the current root-level `ui_export.zip`, then opt in explicitly:

```bash
python3 scripts/build-workspace-fixture.py
NEXT_PUBLIC_WORKSPACE_FIXTURE_MODE=1 npm run dev
```

Fixture mode is read-only and is refused by `npm run build`; API errors never silently fall
back to fixture data.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
