# Proof ledger — how a shape becomes a fact

A capture shows what the UI sent. A fact is what the server **did**. The ledger records, per
endpoint and per field, how far each claim has been carried, and the recipes below are the
experiments that carry it. Every recipe ends in a read-back on a separate request; a status code
is never the result.

## The ledger

`docs/PROOF-LEDGER.md` in the research folder, one row per endpoint (and per rule where rules
were probed):

| Endpoint | Level | Effect asserted | Proof file | Novelty |
|---|---|---|---|---|
| `POST /flow/setDraft` | EXECUTED | `getFlowData.draft_batch` equals the sent batch; `type:"bogus"` stored (no validation) | live-03 | NEW |
| `POST /growth-tools/batchCreateOrUpdateWidgets` | EXECUTED (negative) | 404 on this account | live-06 | NEW |
| `GET /flow/statistics` | OBSERVED | — (seen in source only) | catalogue | — |

- **EXECUTED** — built and sent from code (not the UI) and asserted on the effect.
  **OBSERVED** — sniffed or read in source, not re-issued. **EXECUTED (negative)** — the call
  was made and the negative result (404, ignored, no-op) is the finding.
- **Effect asserted** names the differential: "1-second window returns the same 20 rows as no
  filter" survives; "works" does not.
- **Novelty**: NEW · ALREADY-DOCUMENTED (cite where) · EXTENDS. Grep the existing corpus and
  catalogue before writing NEW.
- Rules carry a **layer**: **S** = server enforces (quote the exact string), **C** = client-only
  (the API accepts the violation), **S+C**. A rule with no observed message is `inferred`.

## Recipes

Each recipe is the experiment plus what to write down. Run them from the executor, one probe
per saved file, on a throwaway object named `TEST-CAP-<surface>-<NN>`.

### R1 — Field or filter differential
Same call twice, one key different (present/absent, or value A/B). Read the object or the row set
back on a separate GET. Diff the read-backs (`client.differential()` lists the paths). Equal
read-backs = the key does nothing here; record that as the finding, do not retry until it "works".

### R2 — Accepted is not applied
After every write: separate read, compare field by field, including **value equality** — a name
over the limit came back silently truncated to 60 characters with a 200. Presence is not proof.

### R3 — Find the validating layer
Draft/save endpoints often validate nothing (garbage is stored and rendered as broken nodes);
publish/commit/activate validates. Probe rules at the layer that enforces them. For each client
rule from Phase 0.5, send the violation to the validating endpoint: rejected → **S** with the
exact string; accepted → **C**. Publish-time rules that only fire when a related object is
attached need the matrix in R19.

### R4 — One error per call
When the validator reports the first failing node only, rule discovery is serial. Script the
matrix: one throwaway object per probe, one violation per object, fix-and-resend never mixed into
a discovery run. Collect `{probe → string}` into one file.

### R5 — Replace vs merge vs upsert
Three calls: (a) write `{A,B}`; (b) write `{A'}` only; (c) read back. `B` gone → replace;
`B` kept → merge; for collections, an unmentioned member that survives → upsert keyed by the id
you sent; find the deletion marker (`removed:true`, a DELETE, a missing id) and prove it the same
way. A partial PUT that merges on one product wipes fields on a full-replace product.

### R6 — Keys the UI sends that the server ignores
Send the key with a distinctive value (a new trigger, a changed name), read the object and its
neighbours back. Not created, not changed → the key is a no-op; write it as negative knowledge
on the `20-api` page (`batch.triggers` on publish is a no-op) and use the real endpoint.

### R7 — Server-added keys poison a re-send
Read an object, re-send it unchanged. If the write fails or misbehaves, bisect the key set until
the culprits are known (stats, segment ids, click counters), write the `strip()` pattern into the
profile, and use it in every read-modify-write.

### R8 — Fresh client ids per probe
Never reuse a client-generated id (`_oid`, `client_id`, uuid) across probe publishes. Re-used ids
on fresh nodes produced duplicate ids across published records; the UI still rendered the object
but every later full republish failed with a generic error. Mint per node, per probe, and record
the object as corrupted if it happens (do not delete it).

### R9 — Reference formats
For each way a field can reference another object (`cuf_<id>`, bare id, number, `{ _content_oid }`
vs `{ content_id }` vs `{ flow_ns }`), send each wrong shape once and capture its error string.
The set of strings is the format rule.

### R10 — Optional parameters default to something
Legacy query-param endpoints often live beside JSON ones. Call each with and without every
optional parameter; a missing `channel=` defaulted to a channel the account did not have and
returned a "connect X" error that reads like a permissions problem. Record the default.

### R11 — One capture per discriminator value
A discriminated union (`type`, `answer_type`, `widget_type`, `actionType`) needs a saved shape for
every member you claim. One capture pins one member and teaches the catalogue the others do not
exist. Take the member list from source (Phase 0.5), then capture each.

### R12 — Let the validator hand you the schema
Where a strict DTO validator exists, POST a near-empty body: the 422 names every violated
constraint at once, including "property X should not exist" for wrong names. Confirm afterwards
that nothing was created (roster count unchanged). Two rounds usually yield the schema.

### R13 — Companion parameters and headers
A parameter may only take effect with a switch beside it (`fromDate` needs `dateType=custom`; a
cursor needs `action=next`; a host needs `version`). Prove each parameter with its companion
present and absent; a silent default (a 30-day window, the first page again) is the finding.

### R14 — Index lag
Search/list endpoints backed by an index lag direct record reads (115 vs 117 right after a bulk
write). Direct reads are authoritative; re-check a search count minutes later before calling a
write partial.

### R15 — Legacy twins and ignored parameters
The same operation may exist as a query-param endpoint and a JSON one. Prove both, and prove which
parameters the legacy one honours: a `name=` that the server overwrote with its own value is
negative knowledge worth a row.

### R16 — Side effects of create
A create may mint more than the object (a widget create also created its own flow and its own
namespace, then needed a second call to attach to yours). Read the neighbourhood after every
create and list every new object by id in the leftovers section.

### R17 — Gate: picker-only or server?
A feature gate in the UI (plan tier, allowlist, channel not connected) may live only in the
picker. Send the gated shape from the executor on a throwaway; stored and rendered → the gate is
client-side and the profile says so; rejected → quote the string. Never enable a compliance or
billing feature to test this.

### R18 — Multi-host differential
Call the same route on each host the product uses, with each single credential, then with both.
Record the matrix. "Needs both headers" and "only on host A" are claims that need the matrix, not
one success elsewhere.

### R19 — Rules that depend on an attached neighbour
Some publish-time rules fire only when a related object is present (a comment trigger attached to
the flow made the root node need `private_reply`, forbade `target`, and limited it to one block
with buttons). Run the matrix {rule violated, rule satisfied} × {neighbour attached, detached}
and record both axes; the rule's wording (`<oid>.private_reply` as the error key) tells you what
else the validator inspects.

### R20 — Deep links, once
Navigate directly to one inner route. Works → screens can be reached by URL; 404 or a shell that
fires no XHRs → click through from `/` and never conclude "no API" from a silent deep link.

### R21 — Silent HTML failures
An HTML 404 is an unknown route; an HTML 500 is unhandled input (an unknown enum value reached
the server unvalidated). Both are findings about the validator's coverage; record the input.

## Writing the row

For every probe file: which recipe, which throwaway object (by id), what was sent, what was read
back, and the one-line differential. Leftovers go to `docs/<build>.md` → "Left in place", by id.
