# CountyIQ Frontend

React, TypeScript, and Vite client for the CountyIQ investor/developer product.
The browser talks to the FastAPI application through relative `/api/*` URLs;
production routing and CORS are documented in `docs/api/api.md`.

## Local Development

Use Node 22 and the committed npm lockfile:

```bash
npm ci
npm run dev
```

## Verification

```bash
npm run typecheck
npm run lint
npm run build
```

The application uses route-level lazy loading. MapLibre and deck.gl belong on
the `/map` route and should not be pulled back into the initial application
chunk. Run a Playwright route walkthrough after meaningful UI changes; a
successful TypeScript or Vite build is not a browser verification.
