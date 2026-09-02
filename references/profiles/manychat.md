# ManyChat — profile

Status: proven-live on a client-owned account (read-only reference now — do not touch it), bundle
490, 2026-09-02. Corpus: `Misc/manychat-internal-api-research/` (`knowledge/reference/internal-api-map.md`
is the long form; `corpus/flow-builder/40-rules.md` is the validation ledger; 20 `live-*.json` proofs).

## Hosts and credentials

| Surface | Base | Credential | Executor | Notes |
|---|---|---|---|---|
| App (everything the UI does) | `https://app.manychat.com/fb{accountId}/…` | session cookie `mc_production-main` + `X-Csrf-Token` | **in-page** (`scripts/inpage-client.js` via chrome-devtools `evaluate_script`) | `accountInstance`; `/:currentAccountID` in source |
| App, account-less | `https://app.manychat.com/…` (`agency/get`, `manychat/getSharedFlow`, `/{pageId}/…` cross-account reads) | same | in-page | `baseInstance` |
| Static bundle | `https://mccdn.me/{STATIC_VERSION}/assets/index.js` | none | curl | |
| Public API | `https://api.manychat.com/fb/…` | `Authorization: Bearer {accountId}:{token}` | Node | 34 ops, no flow building |
| Bot wall | AWS WAF on `/signin` (image CAPTCHA, `aws-waf-token` cookie ~4 days) + Cloudflare on the marketing site | human | — | only the chrome-devtools profile holds a session |

## Required headers (verbatim from `shared/api/initApi.ts`)

```
X-Csrf-Token: <window.__INIT__['app.csrf_token']>
X-Frontend-Bundle: <window.STATIC_VERSION>   # "Empty" if unknown
X-Requested-With: XMLHttpRequest
Use-New-Error-Format: True                     # switches errors to the $errors[] envelope
Accept: application/json
Content-Type: application/json                 # legacy widget create uses QUERY params, empty body
```

## Error envelope

Success: HTTP 200 `{…, state:true}`. Business error: HTTP 200 `{state:false, $errors:[{message, original_message, field?}]}`. Publish validation: HTTP 200 `{state:false, content_node_errors:{"<oid>[.prop]": msg}}` — **one error per call** (R4). Unknown route: 404 HTML. Unhandled input: 500 HTML (`condition:"regex"` on a keyword). 401 → SPA redirects to `/login`. 405 + `x-amzn-waf-action` = WAF challenge. 429 with `$errors` = business error.

## Bundle and source maps

Shell exposes `window.STATIC_VERSION`; chunks referenced as `"./Name-hash.js"`; `//# sourceMappingURL` comments present; 864 chunk maps → 12,197 sources in `knowledge/sniffs/bundle-490/recovered-source/` (main-chunk sources under `index/main/src`, lazy under `chunks/main/src`; the two trees overlap and `extract-catalogue.mjs` collapses them on `/src/`). `fetch-maps.py --bundle-url https://mccdn.me/<build>/assets/index.js` re-mines a new build.

## Request-definition idiom → extractor

`factory-createX`: `api.account|base.create{Get,Post,Put,Delete}({url, schemas})` in `shared/api/requests/<family>/index.ts`, zod contracts in the sibling `schemas.ts` (`looseObject` = server accepts extra keys). Plus `url-constants` with `--placeholders ':currentAccountID,{pageId}'` for the legacy tables (`constants/API.ts`, `managerActions.js`). Catalogue: 849 typed + 56 legacy, `knowledge/sniffs/endpoint-catalogue-from-source.json`. `spa-routes`: 156 routes.

## Where the rules live in source

Enums `common/builder/constants/*` (`BackendContentType`, `BackendMessageType`, `BackendButtonType`), `common/actions/models/Action/constants.ts` (50 action types); client validators `common/builder/selectors/builder/validationSelectors.js`, `common/builder/constants/Validation.ts`, `common/actions/models/Action/validation.js`; server stat keys named in `scripts/auto-layout.js` (`STAT` regex); abilities/flags in `window.__INIT__['app.currentAccount']`; free-plan caps in `app.freeVersionLimit`.

## Navigation

Deep links **work** — every route is served (`/{acc}/cms/files/{ns}/edit` opens the builder). Account switch = URL prefix. Route files: `apps/**/*.routes.ts`, `common/**/pages/*.routes.ts`.

## Ids and lifecycle

- Flow `ns` = `content{YYYYMMDDHHMMSS}_{6}` (server); node `_oid` = client uuid; `content_id` assigned on publish; `client_id` any string (feeds cross-tab notifications only).
- Chain: `POST cms/createFlow` → `POST flow/setDraft` (**full replace of the draft, validates nothing**: `type:"bogus"` is stored) or `flow/patchDraft` (touches only the contents sent) → `POST flow/publish` (validates; **upsert keyed by `_oid`/`content_id`**, unmentioned published nodes survive; `removed:true` deletes) → `GET flow/getFlowData` read-back (`draft_batch` null when clean).
- Targets: `{_content_oid}` before publish, `{content_id, _content_oid}` after; cross-flow `{flow_ns}`.
- Server-added keys to strip before a re-send: `stats`, `button_click_stats`, `target_stats`, `*_segment_id`, `sent_*`, `clicked_*`, `delivered_*`, `read_*`, `questions_count`, `filled_answers_count`, `waiters_*`, `bounced*`, `spam_report*`, `unsubscribed*` (R7).
- Layout = the `coordinates` map only; republish full contents with new coordinates (`scripts/auto-layout.js`). `contents:[]` + coordinates fails; a partial batch pointing at nodes not in the batch fails `Content is linked to the wrong target node`.
- Re-used `_oid`s across probe publishes corrupted a flow (duplicate `_oid` per `content_id`): mint fresh per node (R8).
- Triggers are separate objects: widget `POST growth-tools/createWidget?widget_type=feed_comment_trigger&ns=&channel=instagram` (query params, empty body; server ignores `name=`, mints its own `widget…` namespace **and** a throw-away "Opt-In Message" flow) → `growth-tools/setFlow {widget_id, flow_ns}` → `growth-tools/setWidget` (whole widget as body) → `setDraftStatus`. Keyword: `POST keywords/createDraft?client_id= {ns, channel, keyword_rules}`. Statuses: widget `initial|draft|active|archived|trash`, keyword `draft|live|trash|deleted`.

## Known ledger rows (negative knowledge first)

- `batch.triggers` on `flow/publish` is a **no-op** (R6, live-11). `growth-tools/batchCreateOrUpdateWidgets` **404s** on this account.
- `createWidget` without `channel=instagram` → `You should connect the Facebook channel…` (R10: the missing optional defaulted to Facebook).
- Comment-reply rules (R19): with a comment/story trigger attached, the ROOT node needs `private_reply:"private_reply"`, may not use `target`, and must be exactly one block with buttons/quick replies (`Message reply to comment can contain only one block…`); without a trigger attached the same shapes pass.
- Client-only (C) rules the server accepts: text ≤ 1000 (server hard cap 2000), button caption ≤ 20, valid URL on url buttons, https/JSON on external requests, quick reply after a text with buttons, ≥ 3 public replies, ≥ 1 keyword. Server (S) strings quoted in `40-rules.md`.
- `flow/setName` > 60 chars is **silently truncated** (R2); blank → `name cannot be blank.`
- Condition field formats (R9): custom field is the string `cuf_<id>` (bare id → `Wrong field format`, number → `Field must be a string`); tokens in text `{{cuf_<id>}}`, `{{gaf_<id>}}`.
- Trigger auto-tags (`Post or Reel Comments #N`) are rejected in `add_tag` (`Wrong tag`). `tags/list` requires `type=user`.
- Widget `data` accepted `post_covered_area:"bogus"` and empty keywords (C only); `specific_post` without a post → `Please select a post to track comments` (S).

## Safety

Client account: reads only unless the user says otherwise; every write a `TEST-CAP-MC-*` object; **never** `setDraftStatus active`, `keywords/setStatus live`, `followReply/switch`, `content/createPreview` (all outward-facing) without the user's word; nothing deleted, leftovers listed by id (`docs/CJ-WIZARD-BUILD.md` → "Left in place"); redact `api_key`, `publishable_key`, `public_api_access_token`, csrf from every saved response.

## Optional modules

Harvester rules: OFF (no machine consumer of the corpus yet).
