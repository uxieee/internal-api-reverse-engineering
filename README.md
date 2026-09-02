# internal-api-reverse-engineering

An agent skill for mapping the **undocumented internal API** behind a web SaaS's own UI — the
calls the app makes to itself — so you can automate what the public API cannot reach, or build
API documentation, an MCP server or a client on top of what you find.

Works with Claude Code, Codex and any runtime that follows the [agent skills spec](https://agentskills.io).
Product-agnostic: the method is generic, and everything product-specific lives in a per-product
profile. GoHighLevel and ManyChat profiles ship with it, both proven live.

## Install

```bash
npx skills add uxieee/internal-api-reverse-engineering
```

Or clone this repo into your skills directory (`~/.claude/skills/`, `~/.codex/skills/`, or a
project's `.claude/skills/`). Scripts need `python3` and Node 18+; the capture phase needs a
browser MCP (chrome-devtools or Playwright) on a logged-in tab.

## What it does

The agent treats any request ("how does it save a flow?") as the entry point to a **surface**, not
as the scope, and works it in five phases:

0. **Mine before you sniff.** Most SaaS frontends ship their source to the public CDN as source
   maps. `scripts/fetch-maps.py` recovers the whole tree transitively (lazy-loaded screens included,
   `<base href>` and importmaps honoured, sibling `.js.map` tried when the comment is missing).
   The agent reads the HTTP client and interceptors first — auth header, CSRF, companion headers,
   error envelope — then `scripts/extract-catalogue.mjs` turns the request definitions into a
   machine catalogue of every endpoint the UI can call. Enums, limits, client validators, i18n
   strings and route paths come next. No maps at all? It mines the minified chunks instead.
1. **Enumerate before you capture.** Every screen, panel, control and save path goes into a
   checklist first, so coverage is measurable.
2. **Capture, breadth-first.** Pick the executor the credential model dictates (in-page `fetch`
   for cookie sessions via `scripts/inpage-client.js`, Node for bearer tokens), act in the UI,
   record the real request, follow every neighbour (list vs detail, save, edit, delete, settings, logs).
3. **Prove by differential.** A captured shape is not a fact. Each field and rule is proven by
   read-back on a separate request. Twenty-one recipes cover the traps that recur: drafts that
   store anything while publish validates, one error per call, replace vs merge vs upsert, keys the
   server silently ignores, server-added keys that break re-sends, id reuse that corrupts objects,
   optional parameters that default wrongly, rules that only fire when a neighbour object is attached.
4. **Completeness check.** Written questions about what was never opened, pressed, varied or
   sent to the validating layer. The session ends after two consecutive rounds that find nothing new.
5. **Write it down.** A fixed corpus layout with a status floor per page, a surface checklist, an
   API map, the machine catalogue, redacted proof files, and a ledger of what was executed versus
   merely observed. Downstream consumers — docs, an MCP server, an engine — take only proven rows.

The phases are a floor for rigor, not a fence for curiosity: a "where things hide" list names the
places (bootstrap globals, realtime channels, export paths, version history, hidden controls, other
clients on the same backend) that held the field that mattered on past products.

## Safety

Reads by default. Writes go only to throwaway `TEST-CAP-*` objects on a test account. Nothing is
activated, published, sent or purchased without the user's word. Nothing is deleted; leftovers are
listed by id. Tokens, cookies, keys and billing data are scrubbed (`scripts/scrub-secrets.py`)
before any capture is saved. CAPTCHAs and bot walls are left to the human. Inspect only accounts
you own or are authorised to test, and check the product's terms first.

## Layout

```
SKILL.md                         the method: stance, five phases, hunt list, non-negotiables, red flags
references/
  phase0-sourcemaps.md           bundle mining, API client first, idiom discovery, enums/i18n, routes
  auth-executors.md              cookie vs bearer vs dual; in-page vs Node; bot walls; cookie-store check
  proof-ledger.md                the ledger format and recipes R1–R21
  corpus-contract.md             tree, layers, status floor, checklist marks, optional harvester module
  profiles/                      README (template) · gohighlevel · manychat
scripts/
  fetch-maps.py                  transitive public-source-map miner
  extract-catalogue.mjs          pluggable endpoint-catalogue extractor (--list-idioms)
  inpage-client.js               executor template for cookie-session products
  scrub-secrets.py               redacts secrets in saved captures
```

## Adding a product profile

Copy the template in `references/profiles/README.md` to `references/profiles/<product>.md`. Phase 0
fills most of it; every row that is not yet proven says `unprobed`. Pull requests with new profiles
are welcome as long as they contain no account identifiers, tokens or customer data.

## License

MIT — see `LICENSE`.
