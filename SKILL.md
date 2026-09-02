---
name: internal-api-reverse-engineering
description: "Use when the user wants to reverse-engineer, sniff, capture, trace or map the undocumented internal API behind a web SaaS's own UI — to automate what the public API cannot reach, extend an engine to a new object, re-sweep a surface with partial coverage, or write a per-product profile. Product-agnostic (GoHighLevel and ManyChat profiles ship with it; ClickUp, SamCart or any SPA-backed app work the same way). This is a MAPPING skill: it finishes when the surface is exhausted, not when the first endpoint is found."
---

# Internal API reverse-engineering

Map the internal API a SaaS UI talks to — every host, endpoint, field, rule and quirk of one
feature surface — prove what each part does, and write it into a corpus another agent can build
on. Inspecting your own account's traffic is permitted on every product this has been used on;
confirm the terms for a new one before the first capture.

## The stance

**You are mapping a surface, not answering a question.** A request phrased as one endpoint
("how does it save a flow?") is the entry point to a surface, never its scope. The scope is the
whole feature: every screen, panel, control, save path, list-vs-detail difference and error state.

1. **Mine before you sniff.** The frontend's source usually sits on a public CDN. Read the API
   client, the request definitions, the enums and the validators before opening a network tab.
2. **Enumerate before you capture.** You cannot know what you missed if you never wrote down
   what exists.
3. **Follow every neighbour.** Anything you find has a list view, a settings panel, an edit path,
   a delete path and a log somewhere. Check them before moving on.
4. **Accepted is not proven.** A 200 proves the request parsed. Only a read-back on a separate
   request, compared field by field, proves the write did something.
5. **Stop on evidence, not on satisfaction.** Two consecutive rounds that surface nothing new end
   the session — not the original question being answered.

**The phases are a floor for rigor, not a fence for curiosity.** They say how a discovery becomes
a fact and where it gets written. They do not say what you may look at. Anything you notice —
an odd header, a chunk name, a disabled button, a websocket frame, a route nobody mentioned — is
yours to chase, and whatever you chase is proven the same way. Finishing the phases is not
finishing the job; running out of things to try is.

## Start: the profile

Read `references/profiles/<product>.md` if it exists — it names the hosts, the credential model,
the executor, the deep-link behaviour, the source-map location and the negative knowledge already
paid for. If it does not exist, the session produces it (template in `references/profiles/README.md`),
and Phase 0 fills most of it. Grep the existing corpus and catalogue before calling anything new.

## Phase 0 — mine what the product already published

`references/phase0-sourcemaps.md`. In order, each step naming its artefact:

1. Find the bundle (honour `<base href>` and any `<script type="importmap">`); test for a public
   map with one GET **including the sibling `<chunk>.js.map` URL when the comment is missing**.
   A 200 that is HTML is the SPA fallback, not a map. Record the build-version variable.
2. `scripts/fetch-maps.py` — recover the tree transitively (the main chunk is only the logic layer;
   the screens are lazy chunks with their own maps). Date the capture; `--check` detects drift.
   No maps at all → mine the minified chunks (`--idiom minified-paths`) and lean on capture.
3. Read the **API client and its interceptors** first: auth header, CSRF, bundle header,
   error-format switch, base-URL placeholder, status handling. This decides the executor.
4. Discover the **request-definition idiom** (factory, call sites, url tables, GraphQL), then
   `scripts/extract-catalogue.mjs --idiom …` → `endpoint-catalogue-from-source.json`. Read the
   skipped-candidates list; `--diff` every regeneration.
5. Enums, limits, client validators, i18n strings, feature gates. **An error string implies a code
   path; its absence is evidence a check does not exist.**
6. `--idiom spa-routes` → the screen list that seeds Phase 1.

A union in source is authoritative for the member list; a captured example proves one member.
Source cannot tell you what is stored, ignored, enforced server-side or defaulted — capture can.

## Phase 1 — enumerate the surface (before any capture)

Write `knowledge/SURFACE-CHECKLIST.md` from the route list plus a UI walk: every screen and tab;
every panel, drawer and modal (including ones behind a row action); every button, menu item and
overflow action; every settings toggle; every empty and error state; every list view and its
detail view; the save, publish, duplicate, move, rename, archive and delete paths; anything gated
(marked `[g]`, not skipped). Marks: `[x] [~] [ ] [g] [-]` (`references/corpus-contract.md`).
Type lists come from the enums in Phase 0 and are marked per member.

## Phase 2 — capture, breadth-first

1. **Pick the executor** from the profile (`references/auth-executors.md`): in-page `fetch` with
   `credentials:'include'` for cookie sessions (`scripts/inpage-client.js`), Node for bearer
   tokens, host-aware Node for dual credentials. Check both browser profiles' cookie stores by
   host before asking for a login; bot walls are for the human.
2. **Test deep links once.** They work on some products and 404 into a silent shell on others;
   a silent deep link is never proof of "no API".
3. **Act, then read the network.** One UI action → list requests filtered to the service → open
   the one call → method, URL, headers (names only), request body, response body. Save the a11y
   snapshot of each screen. One capture per checklist item beats three of the first item.
4. **Record negative results**: a control that fires nothing, a save that changes nothing, a
   screen with no backing endpoint.

The neighbour rule, before leaving anything you captured:

| | |
|---|---|
| **List vs detail** | Which fields does one return that the other does not? |
| **Save** | Whole object or diff? Which layer validates — draft or publish? |
| **Edit** | Same endpoint as create, or a different one? Replace, merge or upsert? |
| **Delete** | Soft or hard? Cascades? What marks removal inside a batch? |
| **Settings** | Is there a settings panel for this object, and what does it send? |
| **Logs** | Is there a runtime/history/log view, and what does it read? |

Anything answered "I don't know" goes on the checklist.

## Where things hide — ideas, not a checklist

Places that held the field, the endpoint or the rule that mattered, and that no phase names:

- **Bootstrap globals** (`window.__INIT__`, `AppState`, a config JSON in the shell): feature flags,
  abilities, plan caps, csrf, account ids, attachment policies.
- **Settings, admin and account pages** for the object you are mapping — they often write to the
  same record through a different endpoint with different field names.
- **Realtime**: websocket and SSE frames, `centrifuge`/`socket.io` handshakes, "shard" or "presence"
  endpoints. They carry object shapes the REST layer never returns whole.
- **Export, import, clone, duplicate, template, share** paths: they serialise the entire object,
  which is the cheapest way to learn its full stored shape.
- **Version history, undo, revisions, audit and activity logs**: diffs of what a save actually
  changed, and negative results (a field that never appears in a diff).
- **Bulk and batch endpoints** beside the single ones; they often skip validation the single path has.
- **Disabled and hidden controls**, gated menu items, "coming soon" panels: the source still ships
  the call they would make.
- **The public API's swagger or SDK** for the same product: naming clues, enum values and ids that
  the internal API shares.
- **Other clients on the same backend**: the mobile app, browser extension, embed widget, Zapier or
  Make integration, the marketing site's forms. Same API, different call shapes.
- **Error strings and i18n bundles**: every message is a code path; grep them for verbs you have not
  seen a request for.
- **URL parameters and localStorage keys** the UI sets: `?debug=`, `?preview=`, view ids, cursors.
- **Empty states and first-run onboarding**: they call create/seed endpoints nothing else does.

Anything here that turns up something goes on the checklist and then through Phase 3 like
everything else.

## Phase 3 — prove it, by differential

`references/proof-ledger.md` holds the recipes; the ones that recur on every product:

- **R1/R2** same call with and without the field, read back separately, compare values (a 60-char
  name came back silently truncated with a 200).
- **R3/R4** find the validating layer (draft stores garbage; publish validates), then script the
  probe matrix — one throwaway object per violation, because the validator reports one error per
  call. Record each rule as **S** (server, exact string) or **C** (client-only, API accepts it).
- **R5** replace vs merge vs upsert, proven by the three-call read-back; find the deletion marker.
- **R6** keys the UI sends that the server ignores — send a distinctive value, read the neighbourhood.
- **R7/R8** strip server-added keys before a re-send; mint fresh client ids per probe (re-use
  corrupted a flow).
- **R9/R10** capture the error string for each wrong reference format; probe legacy query-param
  endpoints with and without every optional parameter (a missing `channel=` defaulted wrong).
- **R11** one capture per discriminator value. **R17** a UI gate may be picker-only. **R18** the
  same route on every host with every credential. **R19** rules that fire only when a neighbour
  object is attached need the 2×2 matrix.

Every probe is one saved, redacted file: `sniffs/live-NN-<slug>.json`. Every claim lands in
`docs/PROOF-LEDGER.md` as EXECUTED (effect asserted) or OBSERVED, with novelty NEW /
ALREADY-DOCUMENTED / EXTENDS.

## Phase 4 — completeness check (before reporting)

Answer in writing; the answers are the next round's checklist:

- Which screens on the Phase-1 list did I never open? Which buttons did I never press?
- Which endpoints did I see in source, the catalogue or a response, but never call?
- Which fields did I observe but never **vary**? Which discriminator values have no capture?
- Which rules are still **C** because I never sent the violation to the validating layer?
- What did I assume because it was obvious?
- Which items on the "where things hide" list did I never try on this product?

**Stop condition:** two consecutive rounds where this list produces nothing new. A quiet round
means you ran out of things to try, not that you reached the end of a list.

## Phase 5 — write it down

`references/corpus-contract.md`. Findings go on the surface's page under the matching layer
(`10-anatomy … 70-research`) with a `status` floor per page and inline annotations for claims
that differ from it. Deliverables of a finished surface: the corpus pages,
`knowledge/SURFACE-CHECKLIST.md`, `knowledge/reference/internal-api-map.md`, the machine
catalogue, the proof files, `docs/PROOF-LEDGER.md`, and the product profile (new or updated).
Pages cite sniffs, never paste them. Docs state current truth — replace a corrected claim, keep
negative knowledge, no history blocks. Products whose corpus feeds a harvester turn on the
optional harvester module.

**Where it leads.** The corpus is the middle, not the end. Its consumers are API documentation
someone can code against, the machine catalogue, an MCP server or client library over the proven
endpoints (the GHL internal MCP is the worked example), and engines that build objects. Each
consumes only `proven-live` rows; anything weaker ships marked as such or not at all. Building one
is a separate session — but write the corpus so that session needs nothing you did not record.

## Non-negotiables

- **Test account or throwaway objects only.** Writes go to `TEST-CAP-<surface>-<NN>` objects on a
  designated test account; never a client's live object. Feature-gated? Find an account where it
  is already on; never enable compliance, billing or KYC features to test.
- **Nothing outward-facing without the user's word**: no activating triggers, no publishing to
  users, no sends, no previews to real recipients, no calls, no purchases. Drafts only.
- **Nothing is deleted.** Probe objects and the side effects a create minted stay in place, named,
  and are listed by id under "Left in place" in the handoff.
- **Redact before it leaves the process.** Tokens, cookies, API keys, publishable keys, billing:
  `client.redact()` in the executor, `scripts/scrub-secrets.py` over `sniffs/` before any commit.
  Names and counts are fine; values never.
- **Ground every claim** in a named capture. Mark unconfirmed items; never smooth them over.
- **Bot walls are for the human.** Name the wall, wait, never solve or bypass.

## Red flags — stop and re-read the phase

| Thought | Reality |
|---|---|
| "Define the surface narrowly to stay focused" | The question is the entry point; the neighbour rule sets the scope. |
| "No source maps — the comment is missing" | Try `<chunk>.js.map`. One product strips the comment and ships the maps. |
| "Deep link showed nothing, so this screen has no API" | A silent shell is a navigation failure. Click through from `/`. |
| "It returned 200, so the field works" | Read it back on a separate request and compare values. |
| "The draft saved it, so the shape is valid" | Drafts store garbage. Probe the validating layer. |
| "The UI sends this key, so the server uses it" | Prove it (R6). One publish key was a no-op. |
| "I'll reuse these ids for the next probe" | Fresh ids per probe; reuse corrupted a flow. |
| "I'll clean up the test objects at the end" | Nothing is deleted. List them by id. |
| "Done with X — what next?" | Report the whole surface: covered, uncovered, remaining. |
| "I did all five phases, so I'm finished" | The phases are the floor. Finished means you ran out of things to try. |
| "That's outside the surface I was asked about" | If it touches the same objects, it is the surface. Chase it, then prove it. |
| "Nothing in the phases says to look there" | The phases never say where to look. The hunt list and your own hunches do. |
| "Counts match, the regenerated catalogue is fine" | Diff rows added/removed; read every removed row. |

## Knowledge

- `references/phase0-sourcemaps.md` — bundle mining, API client first, idiom discovery, enums/i18n, routes
- `references/auth-executors.md` — cookie vs bearer vs dual; in-page vs Node; profile cookie check; bot walls
- `references/proof-ledger.md` — the ledger format and recipes R1–R21
- `references/corpus-contract.md` — tree, layers, status floor, checklist marks, harvester module
- `references/profiles/` — `README.md` (template), `gohighlevel.md`, `manychat.md`
- `scripts/` — `fetch-maps.py`, `extract-catalogue.mjs`, `inpage-client.js`, `scrub-secrets.py`
