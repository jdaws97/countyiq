# Account workspaces

## Intended production flow

This section describes the implemented routing contract, not a live deployment.
The latest review found that app.countyiq.net returned NXDOMAIN from public DNS;
live sign-in cannot be accepted until the guarded host rollout below is applied
and verified. Local packaged routing checks do not establish that rollout.

The public product site is at https://countyiq.net. Sign in navigates to
https://app.countyiq.net/, where Cloudflare Access challenges invited testers
before the application opens. The app root opens WorkspaceHome; /app remains
a compatibility alias. All existing product routes live on the app host.

Vite builds two independent HTML entries in one frontend project: index.html
loads the marketing page and marketing.css; app.html loads the existing app
router and theme. Marketing makes no API/session requests and does not start
watch synchronization or load MapLibre. Its preview is explicitly illustrative.
The app uses relative /api/* requests on its own origin. No cross-subdomain
cookie sharing or marketing-origin CORS grant is needed.

Caddy rejects every marketing-host /api request, redirects old product deep
links to the app host (preserving the query), and rejects unknown Host values.
The app host serves app.html and carries noindex headers. Cloudflare Access
covers the entire app host, including API paths and static assets. The API
also verifies customer identity on product endpoints when a provider is
configured. Health/readiness and session discovery have deliberately separate
handling; none of them is proxied on the marketing host.

## Local preview

From frontend/, run npm run dev -- --host 127.0.0.1. The default port is 5173;
use --port 5180 --strictPort if the existing local preview occupies it.

- http://localhost:5180/ is the marketing page.
- http://app.localhost:5180/ is the workspace and product.
- Old local product links redirect to app.localhost, retaining the port.
- Start the existing API on localhost:8000, or set COUNTYIQ_DEV_API_PROXY.
- COUNTYIQ_AUTH_PROVIDER=disabled permits local product exploration only.
  It never creates a fake authenticated customer or saved server workspace.
  Production preflight rejects this mode.

The same hostname routing is installed for Vite preview. DNS is unnecessary
for the reserved .localhost hostnames in Chromium. The local browser check
does not simulate a live Cloudflare OTP challenge.

## Runtime configuration

After migrations 055/056, refresh API role grants with
pipelines/init-db/03-api-role.sh using the existing deployment role variables.

Set these values through the existing encrypted environment workflow:

- DOMAIN=countyiq.net
- COUNTYIQ_TRUSTED_HOSTS=app.countyiq.net
- COUNTYIQ_AUTH_PROVIDER=cloudflare_access
- COUNTYIQ_ACCESS_ISSUER=https://countyiq.cloudflareaccess.com
- COUNTYIQ_ACCESS_AUD=<app_access_audience OpenTofu output>
- COUNTYIQ_WORKSPACE_ORIGINS=https://app.countyiq.net
- COUNTYIQ_APP_URL=https://app.countyiq.net
- COUNTYIQ_WATCH_SYNC_ENABLED=true (when saved-work synchronization is ready)
- COUNTYIQ_PUBLIC_READY_URL=https://app.countyiq.net/api/ready

Preflight requires the exact app hostname for the app URL, write origin, and
trusted-host entry. A readiness redirect or HTML response is not success.
Configure the existing root-owned readiness curl file for Access authentication.
Infrastructure/service credentials must not become customer identities.

## Guarded hostname rollout

These changes are prepared locally, not applied to DNS, Access, or the VPS.

1. Keep publish_marketing_site=false (the default). Apply a reviewed plan
   adding app DNS, its Tunnel ingress, and a separate app Access application.
   App DNS/ingress explicitly depend on creation of the app Access gate.
   The existing apex Access application remains as a temporary gate; a moved
   block preserves its current state address.
2. Read the new app_access_audience output and update the encrypted runtime
   configuration above. Existing encrypted files are not rewritten by this
   change. Deploy the split Caddy/frontend/API release using the normal
   initial-release or recovery-verified deployment procedure.
3. Verify an invited human can sign in at the app root and open a deep link;
   an uninvited visitor is denied; server watches survive sign-out/sign-in;
   and authenticated app readiness succeeds. Verify apex /api/feed and
   /api/session are 404s even with the temporary apex Access gate satisfied.
4. Only then set publish_marketing_site=true in the reviewed environment's
   Terraform variables and apply the plan removing the temporary apex gate.
   The app Access application remains. Confirm the homepage is public and
   its Sign in action reaches the protected app host.

The flag defaults closed to avoid exposing the previous single-host origin
during migration. To roll back to a single-host origin, restore and verify
the apex Access gate before deploying the older release.

## Production sign-in boundary

Cloudflare Access remains the only implemented provider. It verifies the
signed assertion with fixed RS256, issuer, audience, expiry, and human identity
claims. Raw email headers and service tokens are not customer accounts.
See [Cloudflare JWT verification](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).

CountyIQ owns the user UUID, provider/issuer/subject identity mapping, and
workspace membership. Identity verification, optional credential discovery,
and login/logout URLs are centralized in api/lib/auth.py. Session routes and
frontend saved-work consumers use the stable /api/session contract. A future
provider must implement that boundary and any login/callback/session endpoints;
it cannot be enabled merely by changing the provider environment value today.
The hostname split, UI, and saved-work schema can remain in place.

Before public signup, decide:
- Customer identity provider and login methods; use managed identity rather
  than creating a CountyIQ password store.
- Invitation versus self-service onboarding, account recovery, and whether
  personal workspaces or teams are the initial product.
- Customer session lifecycle and verified account linking during migration.
- Product entitlements and billing independently of authentication.

Link a new identity to an existing CountyIQ UUID only through a verified
migration/linking process. Matching email addresses never auto-merge accounts.
Moving localStorage to a new origin is not automatic: existing guest/browser
work remains available through explicit export/import; server work follows
the verified CountyIQ account. Validate identity continuity between the old
and new Access applications before publishing.

## Saved-work behavior and migration

Server persistence includes watches, saved searches, comparisons and recent investigations. Event triage and visit markers remain local to the verified account's browser cache. Browser notifications are opt-in and need an open browser session; they are not email delivery.

A verified account selects its own browser storage namespace; the previous account is not restored from storage on startup. Requests carry the expected internal user ID, checked against the signed external identity. This prevents a changed Access identity from receiving the old account's pending writes. Optimistic versions reject stale cross-device overwrites.

Legacy access-code workspaces remain in the database but cannot be accessed through the retired anonymous-code API. There is no automatic email or code-based account claim. Existing browser work can be exported and explicitly imported after sign-in; guest work is not silently uploaded into whichever account signs in next. Clearing saved work retains the account identity and personal workspace.

The API verifies membership for each private request and marks private responses no-store. Source tables retain read-only role privileges. Shared/team workspaces are not exposed yet.


## Verification on 2026-09-04

- API unit suite: 103 passed; dedicated database integration suite: 42 passed.
- Frontend tests: 12 passed; TypeScript, lint and production build passed.
- Playwright: watched property survives reload and a fresh browser context; second account cannot see first account's watches/recent investigations; real organization search and directory work; desktop/mobile layouts checked including expanded settings.
- Migration 056 and limited-role grants applied to local real countyiq; real API readiness returns 200 on localhost:8000. UI localhost:5173 uses real data.
- Signed-token browser tests used localhost:5175 -> localhost:8002 and countyiq_test only. This tests the application integration; it is not a live Cloudflare OTP end-to-end test.
- No remote DNS/Access deployment or production identity-provider selection was performed. The local real API still has authentication disabled pending real Access runtime configuration.


## Host-split local verification (2026-09-04)

- Frontend: TypeScript, lint, 27 tests, and both production HTML builds passed.
  The existing map chunks still trigger Vite's size warning; marketing does not load them.
- API: 109 unit tests passed, including configured-provider protection for
  product data, anonymous local mode, and invalid-provider rejection.
- Deployment: 27 targeted non-integration checks and 5 isolated recovery
  scenarios passed; 3 loopback-bound Caddy tests verified document separation,
  public API rejection, unknown-host rejection, deep-link redirects, and chunk caching.
- Browser: desktop 1440px and mobile 390px reviewed; all three illustrative
  views, sign-in host navigation, app feed/organization requests, reloads,
  About navigation, and legacy deep links passed. Marketing issued no API calls.
- OpenTofu validation and cost policy passed. No Cloudflare apply, secret
  rewrite, production deployment, or live Access OTP test was performed.
