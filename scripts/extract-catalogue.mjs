#!/usr/bin/env node
// extract-catalogue.mjs — turn recovered frontend source into a machine catalogue of the
// endpoints the UI can call. Pluggable per request-definition idiom; the idiom is DISCOVERED
// per product (read the API client first — see references/phase0-sourcemaps.md), then named here.
//
//   node extract-catalogue.mjs --src <recovered-source root> --idiom <name>[,<name>] --out catalogue.json
//   node extract-catalogue.mjs --diff previous.json --out catalogue.json      (regeneration must be diffed)
//   node extract-catalogue.mjs --list-idioms
//
// Idioms shipped
//   factory-createX    api.<instance>.create<Get|Post|Put|Patch|Delete>({ url: '…', schemas: X })
//                      (ManyChat: instance = account|base; zod schemas beside each index.ts)
//   axios-callsites    axios.<get|post|put|patch|delete>(`…`) / requests.<m>(…) / http.<m>(…)
//                      call sites with a string or template-literal first argument
//                      (GoHighLevel: per-service calls; `${config.rawURL}` style prefixes kept as-is)
//   url-constants      string literals that look like placeholder-prefixed paths, e.g.
//                      '/:currentAccountID/flow/publish' or '/{pageId}/tags/list' (legacy tables)
//   fetch-callsites    fetch('…') / fetch(`…`) with a literal first argument
//
// Every row: { idiom, method, url, instance?, name?, schemas?, files[] }. Rows are deduped on
// (idiom, instance, method, url) with files merged. File paths are made relative to the last
// `/src/` segment so a bundle recovered into two trees (main chunk + lazy chunks) collapses.
//
// Loud by design: every file that fails to read and every candidate the regex saw but could
// not parse is printed to stderr BY NAME. A bare catch{} hid two missing entries once.
import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative, extname } from 'node:path';

const args = new Map();
for (let i = 2; i < process.argv.length; i++) {
  const a = process.argv[i];
  if (a.startsWith('--')) { const v = process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[++i] : true; args.set(a.slice(2), v); }
}

const EXT = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.vue']);
const METHODS = ['get', 'post', 'put', 'patch', 'delete'];

const IDIOMS = {
  'factory-createX': {
    describe: 'api.<instance>.create<Method>({ url, schemas }) factories (ManyChat)',
    // instance may be a chain (api.account) or a bare identifier (accountApi.createGet)
    re: /\b(?:api\.)?([A-Za-z_$][\w$]*)\.create(Get|Post|Put|Patch|Delete)\s*\(\s*\{([\s\S]*?)\}\s*\)/g,
    parse(m) {
      const body = m[3];
      const url = /\burl\s*:\s*(['"`])([^'"`]*)\1/.exec(body);
      if (!url) return { skip: `no literal url in create${m[2]} body: ${body.slice(0, 80).replace(/\s+/g, ' ')}` };
      const schemas = /\bschemas\s*:\s*([\w$.]+)/.exec(body);
      return { instance: m[1], method: m[2].toUpperCase(), url: url[2], schemas: schemas ? schemas[1] : undefined };
    },
    // the property name the factory result is assigned to, e.g. `getFlowData: api.account.createGet(`
    nameBefore: /([A-Za-z_$][\w$]*)\s*:\s*$/,
  },
  'axios-callsites': {
    describe: 'axios/requests/http.<method>(<literal>) call sites (GoHighLevel)',
    re: /\b(axios|Axios|requests|http|client|api|mcApi|instance|apiClient)\.(get|post|put|patch|delete)\s*(?:<[^>]*>)?\s*\(\s*(['"`])((?:\\.|(?!\3)[^\\])*)\3/g,
    parse(m) {
      const raw = m[4];
      const url = raw.replace(/\$\{([^}]+)\}/g, (_, e) => `{${e.trim()}}`);
      if (!/[\/{]/.test(url)) return { skip: `first arg has no path shape: ${raw.slice(0, 80)}` };
      return { instance: m[1], method: m[2].toUpperCase(), url };
    },
  },
  'fetch-callsites': {
    describe: 'fetch(<literal>, { method }) call sites',
    re: /\bfetch\s*\(\s*(['"`])((?:\\.|(?!\1)[^\\])*)\1\s*(?:,\s*\{([\s\S]{0,300}?)\})?/g,
    parse(m) {
      const url = m[2].replace(/\$\{([^}]+)\}/g, (_, e) => `{${e.trim()}}`);
      if (!/^(https?:)?\/|^\{/.test(url)) return { skip: `fetch arg not a url/path: ${m[2].slice(0, 60)}` };
      const meth = m[3] && /\bmethod\s*:\s*['"`]([A-Za-z]+)['"`]/.exec(m[3]);
      return { method: meth ? meth[1].toUpperCase() : 'GET', url };
    },
  },
  'url-constants': {
    describe: "placeholder-prefixed path literals: '/:param/…' or '/{param}/…' (legacy url tables). --placeholders ':currentAccountID,{pageId}' restricts to the API client's own baseURL placeholders; without it SPA ROUTE paths ('/:acc_id/cms/:mode?') are swept in too",
    re: /(['"`])(\/(?::[A-Za-z_]\w*|\{[A-Za-z_]\w*\})\/[^'"`\s]*)\1/g,
    parse(m) {
      const url = m[2];
      if (PLACEHOLDERS && !PLACEHOLDERS.some((p) => url.startsWith('/' + p + '/'))) return { skip: `placeholder not in --placeholders: ${url}` };
      return { method: null, url };
    },
  },
  'minified-paths': {
    describe: 'NO-SOURCE-MAP fallback: template/string literals in minified chunks that look like API paths (`${e}/team/v1/team/${t}`, "/api/v2/…"); ${expr} is kept as {expr}',
    re: /(['"`])((?:[^'"`\n\\]|\\.){0,60}?\/(?:api|v\d)\/(?:[^'"`\n\\]|\\.){1,140})\1/g,
    parse(m) {
      const url = m[2].replace(/\$\{([^}]+)\}/g, (_, e) => `{${e.trim()}}`);
      if (/\.(js|css|png|svg|json|html|woff2?)(\?|$)/i.test(url)) return { skip: `asset, not an endpoint: ${url.slice(0, 60)}` };
      if (/^https?:\/\/(help|www|feedback|university|docs)\./i.test(url)) return { skip: `marketing/help url: ${url.slice(0, 60)}` };
      return { method: null, url };
    },
  },
  'spa-routes': {
    describe: "route definitions (`path: '…'`) in files whose name contains 'route' — the Phase-1 screen list, not endpoints. --all-files lifts the filename filter (minified bundles)",
    fileFilter: /route/i,
    re: /\bpath\s*:\s*(['"`])([^'"`\n]+)\1/g,
    parse(m) { return { method: 'ROUTE', url: m[2] }; },
  },
};
const PLACEHOLDERS = args.has('placeholders') ? String(args.get('placeholders')).split(',').map((s) => s.trim()).filter(Boolean) : null;

if (args.has('list-idioms')) {
  for (const [k, v] of Object.entries(IDIOMS)) console.log(`${k.padEnd(18)} ${v.describe}`);
  process.exit(0);
}

const out = args.get('out');
if (!out) { console.error('--out <file> is required'); process.exit(1); }

function walk(dir, acc) {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    let st; try { st = statSync(p); } catch (err) { console.error(`! stat failed ${p}: ${err.message}`); continue; }
    if (st.isDirectory()) { if (e !== 'node_modules') walk(p, acc); }
    else if (EXT.has(extname(e))) acc.push(p);
  }
  return acc;
}

function relSrc(p, root) {
  const i = p.lastIndexOf('/src/');
  return i >= 0 ? p.slice(i + 5) : relative(root, p);
}

function extract(srcRoot, idiomNames) {
  const files = walk(srcRoot, []);
  const rows = new Map();
  const skipped = [];
  let readFail = 0;
  for (const f of files) {
    let text;
    try { text = readFileSync(f, 'utf8'); } catch (err) { readFail++; console.error(`! read failed ${f}: ${err.message}`); continue; }
    const rel = relSrc(f, srcRoot);
    for (const name of idiomNames) {
      const idiom = IDIOMS[name];
      if (idiom.fileFilter && !args.has('all-files') && !idiom.fileFilter.test(rel)) continue;
      idiom.re.lastIndex = 0;
      let m;
      while ((m = idiom.re.exec(text))) {
        const r = idiom.parse(m);
        if (r.skip) { skipped.push(`${rel}: [${name}] ${r.skip}`); continue; }
        let fnName;
        if (idiom.nameBefore) { const before = text.slice(Math.max(0, m.index - 80), m.index); const nm = idiom.nameBefore.exec(before); if (nm) fnName = nm[1]; }
        const key = [name, r.instance ?? '', r.method ?? '', r.url].join('|');
        const row = rows.get(key) ?? { idiom: name, ...(r.instance ? { instance: r.instance } : {}), method: r.method, url: r.url, ...(fnName ? { name: fnName } : {}), ...(r.schemas ? { schemas: r.schemas } : {}), files: [] };
        if (!row.files.includes(rel)) row.files.push(rel);
        if (!row.name && fnName) row.name = fnName;
        rows.set(key, row);
      }
    }
  }
  return { rows: [...rows.values()].sort((a, b) => (a.idiom + a.url).localeCompare(b.idiom + b.url)), skipped, files: files.length, readFail };
}

function rowKey(r) { return [r.idiom ?? '', r.instance ?? '', r.method ?? '', r.url].join('|'); }

function diff(prevRows, nextRows) {
  const p = new Map(prevRows.map((r) => [rowKey(r), r]));
  const n = new Map(nextRows.map((r) => [rowKey(r), r]));
  const added = [...n.keys()].filter((k) => !p.has(k));
  const removed = [...p.keys()].filter((k) => !n.has(k));
  const changed = [...n.keys()].filter((k) => p.has(k) && JSON.stringify({ ...p.get(k), files: undefined }) !== JSON.stringify({ ...n.get(k), files: undefined }));
  return { added, removed, changed };
}

let result;
if (args.has('src')) {
  const idiomNames = String(args.get('idiom') ?? 'factory-createX,axios-callsites,url-constants').split(',').map((s) => s.trim()).filter(Boolean);
  for (const n of idiomNames) if (!IDIOMS[n]) { console.error(`unknown idiom ${n}; --list-idioms`); process.exit(1); }
  const src = args.get('src');
  if (!existsSync(src)) { console.error(`--src not found: ${src}`); process.exit(1); }
  const { rows, skipped, files, readFail } = extract(src, idiomNames);
  result = { generatedAt: new Date().toISOString(), src, idioms: idiomNames, filesScanned: files, rows };
  console.log(`scanned ${files} files (${readFail} unreadable) → ${rows.length} rows`);
  for (const n of idiomNames) console.log(`  ${n}: ${rows.filter((r) => r.idiom === n).length}`);
  if (skipped.length) { console.error(`-- ${skipped.length} candidates seen but not parsed:`); for (const s of skipped) console.error(`   ${s}`); }
} else if (!args.has('diff')) {
  console.error('give --src <dir> (extract) and/or --diff <previous.json>'); process.exit(1);
}

if (args.has('diff')) {
  const prevPath = args.get('diff');
  const prev = JSON.parse(readFileSync(prevPath, 'utf8'));
  const prevRows = prev.rows ?? [...(prev.typed ?? []).map((r) => ({ idiom: 'factory-createX', ...r })), ...(prev.legacy ?? []).map((r) => ({ idiom: 'url-constants', method: null, ...r }))];
  const nextRows = result ? result.rows : JSON.parse(readFileSync(out, 'utf8')).rows;
  const d = diff(prevRows, nextRows);
  console.log(`diff vs ${prevPath}: +${d.added.length} added, -${d.removed.length} removed, ~${d.changed.length} changed`);
  for (const k of d.added) console.log(`  + ${k}`);
  for (const k of d.removed) console.log(`  - ${k}`);
  for (const k of d.changed) console.log(`  ~ ${k}`);
  if (d.removed.length) console.log('!! NOT purely additive — read every removed row before shipping this catalogue');
}

if (result) { writeFileSync(out, JSON.stringify(result, null, 2)); console.log(`wrote ${out}`); }
