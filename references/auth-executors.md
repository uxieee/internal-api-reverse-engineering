# Auth executors — where a call has to run from

Capturing a request tells you its shape. Proving it means re-issuing it from code you control.
Which process can hold the credential decides where that code runs. Decide this once per
product, from the API client you read in Phase 0.3, and record it in the profile.

## The decision

| Credential model (from the interceptor) | Executor | Why |
|---|---|---|
| **Cookie session** (`credentials`, HttpOnly cookie, CSRF header from a page global) | **In-page**: `evaluate_script` in the logged-in tab, `fetch(url, { credentials: 'include', headers })` | No other process can present an HttpOnly cookie. The page already has the CSRF/bundle values the interceptor reads. |
| **Bearer token** in a header, token readable from storage or an auth call | **Node** (or curl) with the captured token and the interceptor's companion headers | Runs outside the browser, scriptable, no tab needed. Token lifetime is a profile fact (GHL: ~1 h, renewable). |
| **Dual credentials** (bearer + a second header on some hosts) | Node, host-aware: attach the second credential only where the interceptor does | A token valid on one host is not valid on the next; treat every host as its own rail until a differential says otherwise. |
| **Signed requests / per-request nonce** | In-page, calling the app's own signer if exported, else capture-only | Reimplementing a signer is out of scope until its source is recovered. |

An auth model is a property of a **surface**, not of the product: one product carried plain
Bearer on the builder host and Bearer + `token-id` on the AI host, and one route answered on two
hosts on two different single credentials. Prove reach per host by differential before writing
"needs X".

## In-page executor (cookie products)

Template: `scripts/inpage-client.js`. Paste it into `evaluate_script` (chrome-devtools MCP) or
`browser_evaluate` (Playwright MCP), build the client with the header block copied from the
interceptor, run the probe, and `return client.redact(result)`. Persist the returned object
with the tool's file option (`filePath` on chrome-devtools) to `knowledge/sniffs/live-NN-<slug>.json`
— that file IS the proof; a value that lived only in the tool response is an observation.

Rules the template bakes in: every response comes back as `{status, json}` or `{status, text}`
(an HTML 404/500 body is a finding — unknown route, unhandled input); client ids are minted per
call; `redact()` runs on everything you save; `strip()` removes server-added keys before a re-send;
`differential()` runs the with/without pair and reports the read-back paths that differ.

One evaluation per probe file. A long script that fails halfway leaves you with nothing on disk.

## Node executor (token products)

Read the token from the browser session's own network history (any authenticated call shows the
header) or from the product's token endpoint; write it to a gitignored file; never into a doc.
Send every companion header the interceptor sends — a 401 whose body names a missing
`version`/`channel` header is a header problem, not an auth problem, and re-capturing the token
will not fix it. Read the object back on a separate request after every write.

## Bot walls are for the human

AWS WAF image CAPTCHAs, Cloudflare challenges, hCaptcha: say which wall it is, wait for the user
to clear it in the browser profile the executor uses, then continue. Never attempt to solve or
bypass one. A wall on the sign-in page appears once per browser profile and its cookie then
lasts days (ManyChat: `aws-waf-token`, ~4 days).

## Before asking for a login: check what the browser profiles already hold

Two browser profiles exist on this machine and they do not share cookies:

| Profile | Path | Behaviour |
|---|---|---|
| chrome-devtools MCP | `~/.cache/chrome-devtools-mcp/chrome-profile/` | persists across sessions; `SingletonLock` present while Chrome runs |
| Playwright MCP | `~/Library/Caches/ms-playwright/mcp-chrome-<hash>/` | one directory per session; the active one is locked; cookies do not carry to the next hash |

Cookie stores are SQLite and locked while the browser runs, so copy first:

```bash
cp ~/.cache/chrome-devtools-mcp/chrome-profile/Default/Cookies /tmp/ck.sqlite
sqlite3 /tmp/ck.sqlite "select host_key, name, datetime(expires_utc/1000000-11644473600,'unixepoch') from cookies where host_key like '%<product>%'"
```

Read **names and expiry only**, never values. A live session cookie for the host means the
in-page executor can run now in that profile; an expired auth cookie next to a long-lived
refresh cookie usually means the app will re-authenticate itself on load — open it and check
before asking the user to sign in. Deep-link behaviour is tested here too: navigate once to an
inner route; if it 404s or renders a shell that fires no XHRs, record "deep links: no, click
through" in the profile and reach every screen by clicking from `/`.

## Redaction is part of the executor

Anything that leaves the process — a saved response, a report line, a message — has passed
through `redact()` or `scripts/scrub-secrets.py`. Claim *names* and counts are fine; token
values, cookie values, API keys, publishable keys and billing fields never are. Run the scrubber
over `knowledge/sniffs/` before any commit and read its per-file hit list; a "0 hits" line is a
result, not silence.
