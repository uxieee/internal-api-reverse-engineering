// inpage-client.js — the executor for COOKIE-SESSION products. Paste into the logged-in tab via
// chrome-devtools `evaluate_script` (or Playwright `browser_evaluate`) and call the returned
// client from the same evaluation, or assign it to `window.__re` for follow-up evaluations.
//
// Why in-page: the session cookie is HttpOnly, so no Node process can present it; running
// `fetch` inside the tab with `credentials: 'include'` is the only executor that carries it.
// The headers below are COPIED FROM THE APP'S OWN INTERCEPTOR (references/phase0-sourcemaps.md,
// step 2) — never guessed. Fill the `profile` block from references/profiles/<product>.md.
//
// Usage inside evaluate_script (chrome-devtools):
//   async () => {
//     const client = makeClient({ prefix: '/fb' + window.__INIT__['app.currentAccount'].id, headers: () => ({
//       'X-Csrf-Token': window.__INIT__['app.csrf_token'],
//       'X-Requested-With': 'XMLHttpRequest',
//       'Use-New-Error-Format': 'True',
//       'X-Frontend-Bundle': String(window.STATIC_VERSION),
//       Accept: 'application/json',
//     }) });
//     const out = {};
//     out.read = await client.call('/tags/list?type=user');
//     out.write = await client.call('/tags/create', 'POST', { tag_name: 'TEST-CAP tag 01', path: '/', client_id: client.uuid() });
//     out.readBack = await client.call('/tags/list?type=user');          // proof = the read-back, not the 200
//     return client.redact(out);                                          // JSON-safe, secrets scrubbed
//   }
// Save the returned value with the tool's `filePath` option to knowledge/sniffs/live-NN-<slug>.json.
//
// Rules the helper enforces for you
//   * every response is returned as { status, json } or { status, text } — an HTML 404/500 body is
//     kept (truncated) because an HTML error IS a finding (unknown route / unhandled input)
//   * client ids are minted fresh per call (`uuid()`); never reuse one across probe publishes
//   * `redact()` blanks any key matching REDACT_KEYS and any JWT/Bearer-looking string
//   * nothing here deletes, activates or sends; those verbs are yours to type deliberately

function makeClient(profile) {
  const REDACT_KEYS = /^(?:.*(?:token|secret|password|passwd|api_?key|apikey|csrf|authorization|cookie|publishable_key|client_secret|access_key|private_key|card|iban|billing_address|stripe).*)$/i;
  const JWT_OR_BEARER = /\b(?:Bearer\s+)?eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g;
  const prefix = profile.prefix || '';
  const headersFn = typeof profile.headers === 'function' ? profile.headers : () => profile.headers || {};
  const log = [];

  async function call(path, method = 'GET', body, extraHeaders = {}) {
    const url = path.startsWith('http') ? path : prefix + path;
    const headers = { ...headersFn(), ...extraHeaders };
    if (body !== undefined && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    const t0 = Date.now();
    const r = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
      credentials: 'include',
    });
    const text = await r.text();
    let entry;
    try { entry = { status: r.status, ms: Date.now() - t0, json: JSON.parse(text) }; }
    catch { entry = { status: r.status, ms: Date.now() - t0, text: text.slice(0, 400), contentType: r.headers.get('content-type') }; }
    log.push({ method, url, ...(body !== undefined ? { body } : {}), status: r.status });
    return entry;
  }

  function uuid() {
    return (crypto.randomUUID && crypto.randomUUID()) || ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
  }

  function redact(o) {
    if (Array.isArray(o)) return o.map(redact);
    if (o && typeof o === 'object') {
      const r = {};
      for (const k of Object.keys(o)) r[k] = REDACT_KEYS.test(k) ? '[REDACTED]' : redact(o[k]);
      return r;
    }
    if (typeof o === 'string') return o.replace(JWT_OR_BEARER, '[REDACTED-JWT]');
    return o;
  }

  // strip server-added keys before re-sending an object you read back (stats, segment ids…);
  // the key list is PER PRODUCT — record it in the profile once you have proven which keys poison a re-send
  function strip(o, pattern) {
    if (Array.isArray(o)) return o.map((x) => strip(x, pattern));
    if (o && typeof o === 'object') {
      const r = {};
      for (const k of Object.keys(o)) { if (pattern.test(k)) continue; r[k] = strip(o[k], pattern); }
      return r;
    }
    return o;
  }

  // differential helper: run the same call with and without one key and hand back both plus a
  // flat list of paths whose value differs in the read-back — the proof a field DOES something
  async function differential(readPath, writeFn, withKey, withoutKey) {
    const a = await writeFn(withKey); const ra = await call(readPath);
    const b = await writeFn(withoutKey); const rb = await call(readPath);
    return { with: { write: a, readBack: ra }, without: { write: b, readBack: rb }, differs: diffPaths(ra.json, rb.json) };
  }

  function diffPaths(a, b, base = '', acc = []) {
    if (a === b) return acc;
    if (typeof a !== 'object' || typeof b !== 'object' || !a || !b) { acc.push(base || '(root)'); return acc; }
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) diffPaths(a[k], b[k], base ? `${base}.${k}` : k, acc);
    return acc;
  }

  return { call, uuid, redact, strip, differential, diffPaths, log };
}

// For Node/bearer-token products the same shape applies — replace `fetch(..., {credentials})` with a
// fetch that sets `Authorization` (and the product's companion headers) from the captured token file,
// and keep `redact()` on everything you write to disk.
if (typeof module !== 'undefined') module.exports = { makeClient };
