# ClickUp — profile (draft, source-only)

Status: Phase 0 only, 2026-09-03; no account touched. Corpus: `Misc/clickup-internal-api-research/`.
Fill every `unprobed` row from a logged-in tab before relying on this profile.

## Hosts and credentials

| Surface | Base | Credential | Executor | Notes |
|---|---|---|---|---|
| App shell | `https://app.clickup.com/` | — | — | `<base href="https://app-cdn.clickup.com/">` |
| API | runtime `apiUrlBase` (`{e}/…` in source); literal `https://api.clickup.com/v1/team/` seen once | unprobed — cookies `cu_jwt` (short-lived), `cu_refresh` (long-lived), header names `X-CSRF`, `X-Workspace-ID` in source | undecided (read the interceptor first) | |
| Realtime | `/graphql-ws`, `/shard/v1/handshake/{r}` | unprobed | — | sharded |
| Identity | `https://id.app.clickup.com`, `/login/sso` | human | — | |

## Required headers
unprobed (candidates: `X-CSRF`, `X-Workspace-ID`).

## Error envelope
unprobed.

## Bundle and source maps
Entry `main-<hash>.js` (47 bytes) → `main14-<hash>.js` → 3,132 chunks; bare names resolve through `<script type="importmap">` (1,566 entries). **No public source maps** (every `.js.map` is the SPA fallback page). `fetch-maps.py --shell-url https://app.clickup.com/` handles the base href and the importmap; expect ~250 chunks per transitive round.

## Request-definition idiom → extractor
No recovered source → `extract-catalogue.mjs --idiom minified-paths,spa-routes --all-files` over `chunks/`. 61 path templates + 69 routes from 8 chunks; run the full closure for the automations builder chunk.

## Where the rules live in source
unprobed (minified; look for i18n JSON chunks and enum-like object literals in the automations chunk).

## Navigation
Deep links: unprobed. Routes: `/home`, `:team/:task`, `/{team}/inbox/b/{o}`, `:teamId/app-center`, `{e}/ai/agents`, template routes.

## Ids and lifecycle
unprobed.

## Known ledger rows
- Bare chunk names and every `.js.map` URL answer HTTP 200 with the SPA fallback HTML — a 200 is not a file here.

## Safety
Establish whose workspace the stored session belongs to before any write. First write chain: one `TEST-CAP-*` task in a private list, read back on a separate GET. Never enable billing/plan/entitlement endpoints (`plan/*`, `tax/*`, `entitlements/*`) for testing. Nothing deleted.

## Optional modules
Harvester rules: OFF.
