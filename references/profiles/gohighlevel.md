# GoHighLevel — profile

Status: proven-live on the designated sandbox sub-account (never a client's); builder bundle
`index-2T8eXTPB.js` on 2026-09-03 (rotates within days). Corpus: `Misc/gohighlevel/knowledge/`
(corpus, sniffs, catalogue) and the `uxie-ghl-factory` plugin's `ghl-reverse-engineering` skill,
whose `references/internal-api-map.md` is the long form of this page. The compiled catalogue is
`search_endpoints` / `describe_endpoint` on `uxie-ghl-internal-mcp`: read a row before a bundle,
and a bundle before the network.

## Hosts and credentials

| Surface | Base | Credential | Executor | Notes |
|---|---|---|---|---|
| Workflow builder, oauth/session, most agency/location data | `backend.leadconnectorhq.com` | `Authorization: Bearer <LeadConnector JWT>` | Node (the internal MCP gateway adds auth + companions) | UID = `authClassId`; company id from `/list` |
| AI services: Conversation AI, Voice AI, Agent Studio, knowledge base | `services.leadconnectorhq.com` | Bearer **and** `token-id` (Google securetoken RS256) together | Node, `host:"ai"` on the gateway = origin switch + second credential | never set either by hand through the MCP |
| Smart lists `/contacts/smartlist/*` | both hosts | `services` + `token-id` alone (what the UI sends) **or** `backend` + Bearer alone | Node | proven by multi-host differential (R18): neither needs both |
| Agent Logs `/agent-logs/*` | `services` | Bearer **or** `token-id` — **either alone** (R18-proven) | Node, `host:"ai"` | the page itself sends only `token-id`; Bearer + `x-internal-dashboard` is GHL's staff mode |
| Funnels `/funnels/*` | `backend` | `token-id`, not Bearer | Node | A/B proven; auth is per surface |
| Memberships/courses | `backend` (live-proven); `services` unproven | Bearer | Node | member rail needs `source: PORTAL_USER` + `version: 2023-02-21` |
| Public API | `services.leadconnectorhq.com` (v2/v3) | Private Integration Token | `@uxieee/ghl-mcp` | ToS-clean rail; workflow builder is not on it |

Both browser credentials live ~1 h; the gateway renews both before expiry (from 0.45.0) and cold-starts from a 30-day refresh token (0.46.0).

## Required headers (verbatim from `utils/auth-header-interceptor.ts`)

`Authorization: Bearer …` plus `channel: APP`, `source: WEB_USER`, `version: <date>` — the three companions are required outside `/workflow/*`; 21 of 39 probed prefixes answered 401 with body `version header was not found` without them. That 401 is not an auth failure.

## Error envelope

Strict DTO validators on several services return 422 listing every violated constraint at once, including `property X should not exist` (R12). `GET /lists/dynamic/{loc}` with a wrong `objectKey` returns a bare 500, not a validation error. A 200 on a write proves nothing — read the object back.

## Bundle and source maps

- Shell `https://client-app-automation-workflows.leadconnectorhq.com/` → `/assets/index-<hash>.js`; lazy chunks referenced as `assets/Name-<hash>.js`. ~215 chunks.
- Maps are public at `<chunk>.js.map` (6.2 MB main). The `//# sourceMappingURL` comment is **absent** on the current build; `fetch-maps.py` finds the maps by the sibling convention.
- Recovered tree: `knowledge/sniffs/bundle-2026-08-21-2/recovered-source/src` (1,867 files incl. the page layer). Drift: `fetch-maps.py --check --shell-url …` or `node sniffs/recapture.mjs --check`.
- **Federated remotes** (the AI apps) are listed in a PUBLIC build manifest:
  `https://production.app-manifest.leadconnectorhq.com/latest/manifest.json` → `federatedApps` gives
  every remote and its build number, e.g. `appcdn.leadconnectorhq.com/ai/agent-logs/615/remoteEntry.js`.
  **The build number is part of the path** — the same URL without it 404s. Chunk names come from the
  webpack `.u` function inside `remoteEntry.js`. These remotes ship **no source maps** (all 14
  agent-logs chunks 404 on `.js.map`), so mine the minified chunks: the API client, its interceptors,
  the filter table, the enums and the i18n bundle are all still readable.
- The AI apps and the memberships builder have their own bundles; memberships is recovered under `sniffs/memberships-builder-2026-08-24/`. The AI apps have no recovered *source tree* (no maps, see above) — mine their minified remotes directly, as the Agent Logs pass did.

## Request-definition idiom → extractor

`axios-callsites` (288 rows on the builder tree): `axios.get(\`${config.rawURL}/…\`)`, `requests.post(…)`, `Axios.get(…)` across `services/*.ts` and `services/api/*.ts`; base placeholders `{config.rawURL}`, `{AppConfig.appEngineURL}`, `{AppState.locationId}`. No schema files; shapes come from `models/*`, `types/api/*` and the corpus. `spa-routes` yields 21 builder routes.

## Where the rules live in source

- Registries: `actions` is a data literal; `TriggerMaster` is not (extract entries individually). `conv_ai_trigger` cannot be parsed from source — carry it forward.
- Validators: guard functions parsed to a data-only AST (`guard-ast.mjs`), never `new Function`. Validator-finding regexes must be order-agnostic (`field:` before/after `result:` — half were skipped otherwise).
- i18n: `sniffs/bundle-*/i18n-en.json`.
- Gates: `utils/loop.helper.ts → isLoopActionEnabled()` is a 36-location allowlist and **picker-only** — the server stores a loop node on a non-allowlisted location (R17).
- `attributes.type` on the wire is bimodal per step (0 % or ≥ 90 %); an interface's `type` member is a TS discriminant, not wire evidence.

## Navigation

Deep links **404**: only `/` is served and a direct inner URL renders a partial shell that fires no XHRs (reads exactly like "no API" — it is not). Reach every screen by clicking: `/` → Sub-Accounts → the account → switch → the section. `locationId` from `localStorage` (`activeLocations`).

## Ids and lifecycle

- Workflow: create → auto-save → trigger sequence; steps live in a versioned Firebase Storage blob (`fileUrl`), not the PUT body. GHL never emits `parentKey: null`. Trigger WRITE shape is camelCase (`workflowId`); READ shape is snake (`workflow_id`). Never retry a trigger write on an abort — verify via export or you duplicate the trigger.
- Update semantics differ per product: Conversation AI `PUT` **merges**; Voice AI and Agent Studio `PUT` **full-replace**; smart-list update/delete on `/:id` not captured — do not assume.
- Sub-resources are separate objects (`POST /ai-employees/actions`, `POST /voice-ai/actions`) exposed in typed buckets on the parent.
- Cross-references are by id except literal values (`fromPhoneNumber` as E.164).

## Known ledger rows (negative knowledge first)
- **Agent Logs** `/agent-logs/*`: paging offset is capped at 500 (`(page-1)*limit`); `limit` is uncapped
  and `pageToken` walks past the cap — but **only when `page` is omitted**, and the cursor is keyed on
  timestamp so any other `sortBy` loops forever. `asc` is inclusive, `desc` exclusive. The service
  validates **types** (422) but never **values** — a bogus `timeRange`/`sortBy` is silently ignored.
  On `/spans`, do **not** send `conversationId`: it drops the `ai_splitter` span. `filter-values`
  accepts only `agentName, channel, contactName, voiceName`.

- `/workflows/logs/v2` ignores `fromDate`/`toDate` unless `dateType=custom`; cursor needs `action=next`; otherwise a day-snapped ~30-day default (R13). `get_workflow_logs` does **not** drop `skipped` rows.
- workflow-with-filter's cursor is **inclusive** (limit=1 never advances) and it rejects `dateType`.
- Folder list needs `type=directory` (`type=folder` returns count 0, not an error); the batch move cannot reach root — only `PUT /move-directory/{id}` accepts null.
- `validate-assets` checks references only (a deleted `startAfter` validates clean; a bogus `calendarId` passes).
- Contact search index lags direct reads (115 vs 117 after a bulk write, R14).
- `dataType` on custom fields is a per-account dialect. `/customFields` is contact-only → `/customFields/search?model=all` for opportunity fields.
- `update_field_data` with an empty value is a no-op, not a clear (`clear_field_data` is).
- Public funnel URLs resolve from the `funnel_lookup` routing table; moving a path needs three calls or the route silently stays.

## Safety

Live-fire only on your agency's designated sandbox sub-account, never a client location; for refusal tests use another owned account as the "foreign" target and make it a READ. Writes are `TEST-CAP-*` drafts: never publish, never enrol a real contact, never place a call, never buy numbers, never enable compliance/KYC features. Nothing is deleted; leftovers listed by id. Redact both JWTs everywhere; the harvest-fed repos have leaked client data five times — hash-gate names **and** known ids before pushing (do not shape-match 20–24-char ids).

## Optional modules

**Harvester rules: ON** (`corpus-contract.md` → optional module). Corpus pages mint catalogue rows that ship in the plugin; declare one `Base:` per `20-api` page, one path-param spelling, no verb tokens for unproven paths, diff every downstream artefact.
