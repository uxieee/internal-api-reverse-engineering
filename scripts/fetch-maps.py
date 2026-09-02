#!/usr/bin/env python3
"""fetch-maps.py — transitive public-source-map miner for any SPA bundle.

Recovers a web app's original sources from the source maps its CDN serves next to
its JavaScript chunks. Works on every Vite/Rollup/webpack layout seen so far:

  * main bundle  -> `//# sourceMappingURL=index-<hash>.js.map` (or an absolute URL)
  * lazy chunks  -> referenced from the main bundle as "./Name-<hash>.js" (Vite relative)
                    or "assets/Name-<hash>.js" (Vite absolute) — both idioms are matched
  * each chunk has its own `.map`; the closure is walked until no new chunk is referenced

Usage
  fetch-maps.py --bundle-url https://cdn.example.com/490/assets/index.js --out ./bundle-490
  fetch-maps.py --shell-url https://app.example.com/            --out ./bundle-<date>
      (reads the SPA shell HTML, picks the first <script type=module src=…> as the main bundle)
  fetch-maps.py --check --shell-url … --out ./bundle-490
      (one GET: compares the shell's main-bundle name with manifest.json; exit 2 on drift)

Options
  --max-rounds N     stop after N transitive rounds (default 8)
  --concurrency N    parallel downloads (default 12)
  --only REGEX       restrict chunk names (case-insensitive) — for a targeted re-fetch
  --limit N          cap the number of chunks fetched (smoke tests)
  --user-agent UA    some CDNs 403 an empty UA; a browser UA is sent by default

Guarantees (each was lost once by hand on an earlier capture)
  * NEVER deletes and NEVER overwrites a recovered source that already exists with different
    content — a mismatch is written to manifest.json as a conflict (two chunks disagree; that
    is a finding, not a merge).
  * Every miss is printed BY NAME: chunks that 404, maps that are missing or unparseable,
    sources whose `sourcesContent` is null. A silent skip is how two triggers went missing once.
  * Talks only to the public CDN. No cookies, no tokens, nothing of the account is sent.

Output tree
  <out>/chunks/<name>.js        the JavaScript as served (evidence)
  <out>/maps/<name>.js.map      the map as served
  <out>/recovered-source/…      `sourcesContent` written back under the map's `sources` paths
  <out>/manifest.json           bundle url, main chunk, rounds, counts, and every miss by name
  <out>/chunk-list-all.txt      every chunk name reached
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

# Chunk references, every idiom seen so far:
#   "./Name-hash.js" (Vite relative) | "assets/Name-hash.js" (Vite absolute) | import{x}from"./main14.js"
#   (plain ES-module chunks without a hash, e.g. ClickUp). A false positive costs one 404, printed by name.
CHUNK_REF = re.compile(r"""["'`]\.?/?(?:assets/)?([A-Za-z0-9_][A-Za-z0-9_.\-]*\.js)["'`]""")
MAP_URL = re.compile(r"sourceMappingURL=([^\s*]+)")
SHELL_SCRIPT = re.compile(r"""<script[^>]+src=["']([^"']+\.js)["']""", re.I)
# <base href="https://app-cdn.example.com/"> — the shell's scripts resolve against it, not the page URL
BASE_HREF = re.compile(r"""<base[^>]+href=["']([^"']+)["']""", re.I)


def get(url, ua, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
            with urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except HTTPError as e:
            return e.code, b""
        except URLError as e:
            last = e
            time.sleep(1 + attempt)
    print(f"  ! network error {url}: {last}", file=sys.stderr)
    return 0, b""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle-url")
    ap.add_argument("--shell-url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-rounds", type=int, default=8)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--user-agent", default=DEFAULT_UA)
    a = ap.parse_args()
    if not a.bundle_url and not a.shell_url:
        ap.error("give --bundle-url or --shell-url")

    ua = a.user_agent
    out = a.out
    manifest_path = os.path.join(out, "manifest.json")

    # ---- resolve the main bundle ------------------------------------------------------------
    bundle_url = a.bundle_url
    if not bundle_url:
        status, html = get(a.shell_url, ua)
        if status != 200:
            print(f"shell {a.shell_url} -> HTTP {status}", file=sys.stderr)
            sys.exit(1)
        text = html.decode("utf-8", "ignore")
        scripts = SHELL_SCRIPT.findall(text)
        if not scripts:
            print("no <script src=…js> in the shell; pass --bundle-url", file=sys.stderr)
            sys.exit(1)
        # the app's entry is usually the LAST script tag (polyfills/vendor come first); honour <base href>
        base_m = BASE_HREF.search(text)
        resolve_from = urljoin(a.shell_url, base_m.group(1)) if base_m else a.shell_url
        entry = next((s for s in scripts if re.search(r"(?:^|/)(main|index|app)[.-]", s)), scripts[-1])
        bundle_url = urljoin(resolve_from, entry)
        print(f"main bundle from shell: {bundle_url}" + (f"  (via <base href={base_m.group(1)}>)" if base_m else ""))
        if len(scripts) > 1:
            print(f"  other shell scripts: {', '.join(s for s in scripts if s != entry)}")

    main_name = os.path.basename(urlparse(bundle_url).path)
    base = bundle_url[: bundle_url.rfind("/") + 1]

    # <script type="importmap"> in the shell maps bare chunk names to hashed files
    # ("./chunk42.js" -> "./chunk42-4431172026.js", ClickUp: 1,566 entries). Without it every bare
    # name resolves to the SPA fallback page. Applied to every reference before fetching.
    importmap = {}
    if a.shell_url:
        try:
            status, html = get(a.shell_url, ua)
            im = re.search(r"""<script[^>]+type=["']importmap["'][^>]*>(.*?)</script>""", html.decode("utf-8", "ignore"), re.S)
            if im:
                for k, v in (json.loads(im.group(1)).get("imports") or {}).items():
                    importmap[os.path.basename(k)] = os.path.basename(v)
                print(f"importmap: {len(importmap)} entries")
        except Exception as e:  # noqa: BLE001 — a broken importmap must not stop the capture
            print(f"  ! importmap unreadable: {e}", file=sys.stderr)

    def resolve(name):
        return importmap.get(name, name)

    if a.check:
        if not os.path.exists(manifest_path):
            print(f"no manifest at {manifest_path}; nothing to compare")
            sys.exit(1)
        prev = json.load(open(manifest_path))
        if prev.get("mainChunk") == main_name:
            print(f"UP TO DATE: {main_name}")
            sys.exit(0)
        print(f"DRIFT: captured {prev.get('mainChunk')} but the shell now serves {main_name}")
        sys.exit(2)

    os.makedirs(os.path.join(out, "chunks"), exist_ok=True)
    os.makedirs(os.path.join(out, "maps"), exist_ok=True)
    src_root = os.path.join(out, "recovered-source")
    os.makedirs(src_root, exist_ok=True)

    only = re.compile(a.only, re.I) if a.only else None
    misses = {"chunk404": [], "mapMissing": [], "mapUnparseable": [], "nullContent": [], "conflicts": []}
    convention_hits = []  # chunks whose map was found ONLY by the sibling-URL convention (no comment)
    seen = {main_name}
    queue = [main_name]
    fetched = 0
    rounds = 0
    map_paths = []

    def work(name):
        nonlocal fetched
        js_path = os.path.join(out, "chunks", name)
        if not os.path.exists(js_path) or os.path.getsize(js_path) == 0:
            status, body = get(base + name, ua)
            if status != 200:
                return name, None, [], f"HTTP {status}"
            if body.lstrip()[:1] == b"<":
                return name, None, [], "HTTP 200 but HTML (SPA fallback page — not a chunk)"
            open(js_path, "wb").write(body)
        src = open(js_path, errors="ignore").read()
        refs = [resolve(r) for r in CHUNK_REF.findall(src)]
        refs = [r for r in refs if r != name]
        # A missing `//# sourceMappingURL` comment is NOT proof there is no map: some builds strip the
        # comment and still upload `<chunk>.js.map` beside the chunk (GoHighLevel's builder does).
        # Try the comment first, then the conventional sibling URL, and record which one answered.
        m = MAP_URL.search(src[-2000:]) or MAP_URL.search(src)
        candidates = []
        if m:
            map_name = m.group(1)
            candidates.append(("comment", map_name if map_name.startswith("http") else base + map_name, os.path.basename(map_name)))
        candidates.append(("convention", base + name + ".map", name + ".map"))
        tried = []
        for how, map_url, fname in candidates:
            mp = os.path.join(out, "maps", fname)
            if os.path.exists(mp):
                return name, mp, refs, None
            status, body = get(map_url, ua)
            if status == 200 and body.lstrip()[:1] == b"{":
                open(mp, "wb").write(body)
                if how == "convention" and not m:
                    convention_hits.append(name)
                return name, mp, refs, None
            # a 200 that is not JSON is the SPA's catch-all shell answering for a missing file
            tried.append(f"{how} HTTP {status}" + (" but not JSON (SPA fallback page)" if status == 200 else ""))
        return name, None, refs, "no map (" + ", ".join(tried) + ")"

    while queue and rounds < a.max_rounds:
        rounds += 1
        batch = [n for n in queue if not only or n == main_name or only.search(n)]
        if a.limit is not None:
            room = max(0, a.limit - fetched)
            batch = batch[:room]
            if not batch:
                break
        with ThreadPoolExecutor(a.concurrency) as ex:
            results = list(ex.map(work, batch))
        fetched += len(batch)
        new = []
        for name, mp, refs, err in results:
            if err and err.startswith("HTTP"):
                misses["chunk404"].append(f"{name} ({err})")
            elif err:
                misses["mapMissing"].append(f"{name}: {err}")
            if mp:
                map_paths.append(mp)
            for r in refs:
                if r not in seen:
                    seen.add(r)
                    new.append(r)
        print(f"round {rounds}: fetched {len(batch)}, new refs {len(new)}, total known {len(seen)}")
        queue = new

    # ---- write sourcesContent back -----------------------------------------------------------
    written = same = 0
    for mp in sorted(set(map_paths)):
        try:
            m = json.load(open(mp))
        except Exception as e:
            misses["mapUnparseable"].append(f"{os.path.basename(mp)}: {e}")
            continue
        sources = m.get("sources") or []
        contents = m.get("sourcesContent") or []
        for i, s in enumerate(sources):
            c = contents[i] if i < len(contents) else None
            rel = re.sub(r"^(\.\./)+", "", str(s)).lstrip("/")
            if c is None:
                misses["nullContent"].append(f"{os.path.basename(mp)} :: {rel}")
                continue
            if rel.startswith("\0") or "node_modules/" in rel:
                continue
            dest = os.path.normpath(os.path.join(src_root, rel))
            if not dest.startswith(os.path.abspath(src_root)) and not dest.startswith(src_root):
                misses["conflicts"].append(f"{rel} (escapes tree — skipped)")
                continue
            if os.path.exists(dest):
                if open(dest, errors="ignore").read() == c:
                    same += 1
                else:
                    misses["conflicts"].append(f"{rel} (exists with different content — NOT overwritten; from {os.path.basename(mp)})")
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "w").write(c)
            written += 1

    open(os.path.join(out, "chunk-list-all.txt"), "w").write("\n".join(sorted(seen)))
    manifest = {
        "bundleUrl": bundle_url,
        "mainChunk": main_name,
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rounds": rounds,
        "chunksKnown": len(seen),
        "chunksFetched": fetched,
        "mapsParsed": len(set(map_paths)),
        "sourcesWritten": written,
        "sourcesAlreadyPresent": same,
        "mapsFoundByConventionOnly": convention_hits,
        "misses": misses,
    }
    json.dump(manifest, open(manifest_path, "w"), indent=2)

    print(f"maps {len(set(map_paths))}, sources written {written}, already present {same}")
    if convention_hits:
        print(f"-- {len(convention_hits)} map(s) had no sourceMappingURL comment but exist at <chunk>.js.map (recorded in manifest)")
    for k, v in misses.items():
        if v:
            print(f"-- {k}: {len(v)}")
            for line in v[:50]:
                print(f"   {line}")
            if len(v) > 50:
                print(f"   … {len(v) - 50} more in manifest.json")
    if queue and rounds >= a.max_rounds:
        print(f"!! stopped at --max-rounds {a.max_rounds} with {len(queue)} chunks still unfetched — raise it", file=sys.stderr)


if __name__ == "__main__":
    main()
