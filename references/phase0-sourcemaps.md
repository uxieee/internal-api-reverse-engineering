# Phase 0 — mine before you sniff

Most SaaS frontends ship their original source to the public CDN as source maps. Reading it is
faster, more complete and safer than clicking through the UI, and it turns capture into a
confirmation step instead of a discovery step. Do all of this before opening a network tab.

Every step below names the artefact it produces. If a step produces nothing, write down why
(the negative result is a profile fact).

## 0.1 Find the bundle and test for maps (one GET)

1. Load the app once, logged in. In the tab: `[...document.scripts].map(s => s.src)` — the entry
   script is the `type=module` one; note any build-version global the shell exposes
   (`window.STATIC_VERSION`, a `?v=` query, a versioned CDN path segment). Read the shell's
   `<base href>` (scripts may live on a CDN host, not the app host) and any
   `<script type="importmap">` (bare chunk names → hashed files; without it every bare name
   resolves to the SPA's fallback page).
2. `curl -sI <bundle>.map` **and** read the bundle's tail for `//# sourceMappingURL=`. A missing
   comment is not a missing map: some builds strip the comment and still upload `<chunk>.js.map`
   beside every chunk. Test the sibling URL before recording "no maps". A 200 whose body is HTML
   is the SPA catch-all answering for a missing file, not a map (`fetch-maps.py` says so by name).
3. Record in the profile: bundle URL pattern, build-version variable, whether maps are public,
   chunk-reference idiom (`"./Name-hash.js"`, `"assets/Name-hash.js"`, or bare
   `import … from "./chunk42.js"` resolved through the importmap).

If no URL answers with JSON that has `sourcesContent`, the product ships **no maps** (ClickUp).
Phase 0 then mines the minified chunks for literals: `extract-catalogue.mjs --idiom
minified-paths,spa-routes --all-files` recovers path templates (`{e}/team/v1/team/{t}`), header
names, hosts and route paths from the chunks `fetch-maps.py` still downloads. Say so in the
profile and expect capture to carry the shapes.

## 0.2 Recover the whole tree, transitively

```bash
python3 scripts/fetch-maps.py --shell-url https://app.example.com/ --out knowledge/sniffs/bundle-<build>
# or --bundle-url https://cdn.example.com/<build>/assets/index.js
```

The main chunk is only the logic layer. Route pages, config drawers, side rails, modals and
settings screens are lazy chunks the main chunk merely references, and each has its own map.
The script walks that closure until a round adds no new chunk, writes `sourcesContent` back
under `recovered-source/`, and prints every miss by name (404 chunk, missing map, null content,
conflicting duplicate). A survey that says "the screens are not recoverable" has usually stopped
at the main chunk.

Drift: `fetch-maps.py --check` compares the shell's current main-chunk name with the capture's
manifest in one GET. Bundles rotate in days, sometimes twice in a day; date every capture
directory and never mine an old one for a "current" fact without the check.

Artefacts: `sniffs/bundle-<build>/{chunks,maps,recovered-source,manifest.json,chunk-list-all.txt}`.

## 0.3 Read the API client before any endpoint

Find the HTTP layer first — grep for `interceptors.request`, `interceptors.response`,
`axios.create`, `fetch(` wrappers, `baseURL`. One file usually answers all of these at once:

| Read for | Why it matters | Where it was on the two known products |
|---|---|---|
| Auth header name and source | tells you the executor (cookie vs bearer vs both) | ManyChat: none — cookie session + `X-Csrf-Token` from `window.__INIT__`; GHL: `Authorization: Bearer` from app state, `token-id` on the AI services |
| CSRF / bundle-version / client headers | required companions the UI always sends | ManyChat: `X-Csrf-Token`, `X-Frontend-Bundle`, `X-Requested-With`; GHL: `channel`, `source`, `version` |
| Error-format switch | changes the envelope you will parse | ManyChat: `Use-New-Error-Format: True` → `{state:false,$errors[]}` |
| Base-URL placeholder | the account/tenant prefix every path takes | ManyChat: `/:currentAccountID`, `/{pageId}`; GHL: `${config.rawURL}`, `${AppState.locationId}` |
| Status handling | which codes mean what — auth, WAF, legal block, rate limit | ManyChat: 401 → redirect to `/login`; 405 + `x-amzn-waf-action` → WAF challenge; 429 with `$errors` = business error; 451 legal |
| Success envelope | some APIs return HTTP 200 with `state:false` | ManyChat does; a 200 is not success there |

Copy the header block verbatim into the profile and into the executor (`scripts/inpage-client.js`).
Never guess a header name you could read.

Artefact: profile section "Hosts and credentials" + "Required headers" + "Error envelope".

## 0.4 Discover the request-definition idiom, then extract the catalogue

Each product defines requests in one dominant idiom, and the idiom is a fact to discover, not
assume. Grep for the client you found in 0.3 and look at ten call sites:

| Idiom | Looks like | Extractor name |
|---|---|---|
| factory | `api.account.createGet({ url: '/flow/getFlowData', schemas: X })` with a zod/yup schema file beside each index | `factory-createX` |
| call sites | `axios.get(\`${config.rawURL}/workflow/${loc}/${id}\`)`, `requests.post(...)` per service class | `axios-callsites` |
| url tables | `'/:currentAccountID/growth-tools/createWidget?widget_type=:type'` in a constants file | `url-constants` (pass `--placeholders` = the client's baseURL placeholders) |
| raw fetch | `fetch('/api/...', { method })` | `fetch-callsites` |
| GraphQL | `gql\`query …\`` documents + one `/graphql` endpoint | not shipped — write one; the catalogue rows are operation names |

```bash
node scripts/extract-catalogue.mjs --list-idioms
node scripts/extract-catalogue.mjs --src knowledge/sniffs/bundle-<build>/recovered-source \
  --idiom factory-createX,url-constants --placeholders ':currentAccountID,{pageId}' \
  --out knowledge/endpoint-catalogue-from-source.json
```

A new idiom means a new entry in `IDIOMS` (regex + parse), nothing else. The extractor prints
every candidate it saw but could not parse; read that list before trusting the count, and run
`--diff previous.json` on every regeneration — a regenerated catalogue that lost rows is wrong
until each removed row is explained.

Beside every typed request, read its **schema file**: request and response contracts, enums,
nullable fields, `looseObject` (server accepts extra keys). The schema is authoritative for
shape; only capture is authoritative for behaviour.

Artefact: `knowledge/endpoint-catalogue-from-source.json` (+ the profile's "Endpoint families" table).

## 0.5 Enums, limits, validators, i18n

Read, in this order, and cite file paths in the corpus:

1. **Type enums** — node/block/action/trigger kinds, status values, operator lists. A union in
   source is authoritative; a captured example proves one member.
2. **Constants** — max lengths, max counts, defaults the UI applies before sending (these show up
   as "the server accepted 21 characters" findings later).
3. **Client validators** — the module that produces the UI's inline errors. Every rule here is a
   candidate `C` (client-only) row for the rules ledger until the server is probed.
4. **i18n strings** — every error string implies a code path that raises it; the absence of a
   string is evidence a check does not exist. Extract the English bundle to
   `sniffs/bundle-<build>/i18n-en.json`.
5. **Feature gates** — allowlists, plan checks, `abilities`/`flags` objects. A gate in the picker
   is not a gate on the server until proven (see proof-ledger recipe R18).

Parse by normalising to JSON and `JSON.parse`, never `eval`/`new Function` — it is CDN code.
Run long regex extractors under a timeout (`perl -e 'alarm 30; exec @ARGV' node …`); a nested
`\s*` inside `+` with a lookahead hung one forever.

Artefacts: `sniffs/bundle-<build>/{enums,validators,i18n-en}.json` or a `70-research` page citing files.

## 0.6 Routes → the Phase-1 screen list

```bash
node scripts/extract-catalogue.mjs --src …/recovered-source --idiom spa-routes --out knowledge/sniffs/routes.json
```

Every `path:` in a routes file is a screen the UI can show. This list seeds
`SURFACE-CHECKLIST.md`; the UI walk in Phase 1 adds panels and modals that routes do not name.

## 0.7 What source cannot tell you (so capture must)

- whether a field the client sends is **stored**, **ignored** or **transformed**
- which layer **enforces** a rule (server vs client) and the server's exact error string
- merge vs replace vs upsert semantics of a write
- server-assigned fields, server-added keys on read, default values applied server-side
- whether an optional parameter's absence changes behaviour
- host/credential reach: the same route may answer on two hosts with different credentials
- anything gated by account state (channel connected, plan, allowlist)

Each of these has a recipe in `proof-ledger.md`.
