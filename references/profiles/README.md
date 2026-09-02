# Product profiles

A profile is the product-specific half of the method: everything the generic phases need to know
that differs between products. The skill reads the profile at the start of a session; a session
on a product without one produces the profile as its first deliverable (Phase 0 fills most of it).

Profiles here: `gohighlevel.md` and `manychat.md` (both proven-live).
A new product gets `<product>.md` in this folder, and the research folder's
`reference/internal-api-map.md` is its long form.

The `Corpus:` line in each profile points at the research folder the profile was distilled from.
Those folders are the author's local research and are not shipped with the skill; the profile is
written to stand on its own, and the pointer tells you what a full corpus for that product looks
like if you have access to one.

## Template

```markdown
# <Product> — profile
Status: <proven-live on <test account> | source-only | draft>, bundle <build>, <date>. Corpus: <path>.

## Hosts and credentials
| Surface | Base | Credential | Executor | Notes |
(one row per host/prefix; a route that answers on two hosts gets two rows)

## Required headers (verbatim from the interceptor)
## Error envelope
(success shape · business-error shape · validation shape · what HTML 404/500 mean · 401/405/429 behaviour)

## Bundle and source maps
(shell URL · bundle URL pattern · build-version variable · maps public? · chunk-ref idiom · sourceMappingURL comment present? · recovered tree path · drift check command)

## Request-definition idiom → extractor
(idiom name(s) for extract-catalogue.mjs · placeholders · schema convention · legacy tables · catalogue path + counts)

## Where the rules live in source
(enum files · constants · client validators · i18n bundle · feature gates)

## Navigation
(deep links yes/no · how to reach a screen · account/tenant switch · route files)

## Ids and lifecycle
(client-minted vs server-assigned ids · id formats · draft/publish layers · replace/merge/upsert per endpoint · deletion marker · server-added keys to strip)

## Known ledger rows (negative knowledge first)
(ignored keys · legacy twins and their defaults · gates that are picker-only · endpoints that 404 · index lag)

## Safety
(test account · throwaway naming · outward-facing verbs never to call without the user's word · bot wall · what to redact)

## Optional modules
(harvester rules on/off · catalogue consumers)
```

## What makes a profile complete

Every row in "Hosts and credentials" has an executor and at least one EXECUTED proof file behind
it. "Ids and lifecycle" states replace/merge/upsert per write endpoint with the recipe (R5) that
proved it. "Known ledger rows" names the file that proved each negative. A profile with a blank
section says `unprobed`, never nothing.
