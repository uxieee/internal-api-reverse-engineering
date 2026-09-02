# Corpus contract — what a finished surface looks like on disk

One research folder per product, `<product>-internal-api-research/`, with this tree. Two
competent authors must produce structurally identical pages; the value of the corpus is that a
reader can predict where a fact lives.

```
<product>-internal-api-research/
  README.md                          # read-order, evidence index, house rules kept
  knowledge/
    SURFACE-CHECKLIST.md             # Phase-1 enumeration with coverage marks (the work-list)
    reference/internal-api-map.md    # hosts, credentials, headers, envelope, endpoint families
    endpoint-catalogue-from-source.json
    corpus/<surface>/{10-anatomy,20-api,30-types,40-rules,50-runtime,60-recipes,70-research}.md
    sniffs/bundle-<build>/…          # chunks, maps, recovered-source, manifest.json, extractors
    sniffs/live-NN-<slug>.json       # one executed probe per file, redacted
    sniffs/rNNNN-<call>.network-response   # the UI's own calls, redacted
    sniffs/snap-NN-<screen>.txt      # a11y snapshots of each screen walked
  scripts/                           # the executor and any builder written on top of the findings
  docs/PROOF-LEDGER.md               # EXECUTED vs OBSERVED per endpoint (proof-ledger.md)
  docs/<build-or-handoff>.md         # what was built, ids, how to go live, what is left in place
```

## Layers

| Layer | Holds | Required sections |
|---|---|---|
| `10-anatomy` | an object or lifecycle | what it is · envelope and field semantics · lifecycle as ordered steps · client-generated vs server-assigned · proof |
| `20-api` | an endpoint family | purpose · per endpoint: method + path, params, body, response, observed statuses **including useful failures** · quirks (companion params, rejected keys, ignored keys) · proof |
| `30-types` | one type (node, action, trigger, setting) | when used · configuration table (name · key · required · allowed · default) · stored shape (anonymised, exact) · rules and gotchas · proof · related |
| `40-rules` | a rule, limit or gate | one rule per row/section: what it forbids · what triggers it · exact error string · layer **S / C / S+C** · fix · proof |
| `50-runtime` | execution data | what exists · query shape · record fields · what is **not** obtainable · proof |
| `60-recipes` | a how-to | goal · preconditions · ordered steps · how to verify · failure modes |
| `70-research` | a dated primary source `YYYY-MM-DD-<slug>.md` | frontmatter + "what this establishes"; never rewritten, superseded ones marked `deprecated` with a pointer |

A `20-api` page may carry `40-rules` inline when the family is small (write `layer: 20-api (+40-rules inline)`).

## Frontmatter and the status floor

```yaml
---
surface: flow-builder
layer: 40-rules
status: proven-live          # the FLOOR: the weakest claim on the page
account: <test account id>   # where it was proven
bundle: <build>              # which recovered source it cites
captured: 2026-09-02
sources: [sniffs/live-05, sniffs/live-08, recovered-source/…/validationSelectors.js]
---
```

`status` ∈ `proven-live` (executed on a live account **and read back on a separate request**) ·
`source-only` (read in recovered source, not executed) · `observed` (sniffed from the UI, not
re-issued) · `unproven`/`inferred` (say from what). Claims stronger or weaker than the floor are
annotated inline: `[proven-live]`, `[source-only]`, `[inferred — from the normaliser, not executed]`.

Pages **cite** sniffs (`live-08`), they do not paste them. Every documented field names the
capture it came from. Unconfirmed items are marked, never smoothed over.

## SURFACE-CHECKLIST.md

Header: account under study, plan/channel state that gates features, bundle, date. Then the
enumeration grouped by navigation, one line per screen/panel/control/save path, each with a mark:

`[x]` captured (request + response on disk) · `[~]` partially captured · `[ ]` not opened ·
`[g]` gated (plan/channel/allowlist — say which) · `[-]` deliberately skipped (destructive or
outward-facing — say why)

Type lists (node types, block types, action types, trigger kinds) are enumerated **from source**
and marked per member (✔ captured, `[ ]`, `[g]`). The last section is "Not enumerated (out of
scope for this build)", so a reader can tell unopened from unscoped.

## reference/internal-api-map.md

Sections, in order: status line (account, date, bundle) · hosts and credentials table (surface ·
base · credential · notes) · required headers block, verbatim · error envelope (success shape,
business error shape, validation shape, what HTML 404/500 mean, what 401/405/429 do) · endpoint
families table (family · prefix · count in catalogue · proven live) · pointer to the catalogue.

## Naming and hygiene

- Throwaway objects: `TEST-CAP-<surface>-<NN>` (flows, tags, fields, widgets alike). Anything
  else you create is a deliverable and is named as one.
- Probe files: `live-NN-<what>.json`, numbered in execution order, one probe per file.
- Every saved response passes `scripts/scrub-secrets.py` (or the executor's `redact()`) before it
  is committed; the scrubber's hit list is read, not skimmed.
- Docs state the current truth. A corrected claim is replaced, not layered with "superseded"
  notes; negative knowledge ("`batchCreateOrUpdateWidgets` 404s on this account") stays because
  "don't try X" is current truth.
- Nothing is deleted from the account. `docs/<handoff>.md` ends with **"Left in place"**: every
  probe object by id, every side-effect object a create minted, marked safe to remove by hand.

## Optional module — harvester rules (GoHighLevel corpus)

The GHL corpus is machine-read: `harvest-documented-endpoints.mjs` scans every corpus `.md` and
every `METHOD /path` token it finds mints a catalogue row that ships in a plugin. A product whose
corpus feeds a harvester turns these rules on in its profile:

- Declare exactly one `Base:` per `20-api` page. Two bases make every path ambiguous and the
  harvester falls back to a prefix map, then to the default host.
- Single-segment root paths (`GET /payment-links/`) are kept only when the page states a
  **host-only** base (`Base: backend.leadconnectorhq.com`); a prefixed base drops them.
- Never write a `METHOD /path` token for an endpoint that is inferred, unproven or known to 403.
  Prose ("a bare read of `/x/{id}`") is safe; a verb token mints a row.
- One spelling per path parameter across the surface (`{id}` vs `{calendarId}` mints twins).
- Never let prose mine as a path: no ellipses (`GET /calendars/events...`), no elided prefixes.
- A research page naming endpoints on a non-default host declares the base or avoids verb tokens.
- After writing, run the harvest and **read the minted rows' hosts**; then diff every downstream
  artefact (harvest → merge → build → overlay → dist): rows added / removed, not counts. Re-run the
  shipped ranking for the intent a caller would type and check the row is in the top 10.
