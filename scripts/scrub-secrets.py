#!/usr/bin/env python3
"""scrub-secrets.py — redact credentials and billing data inside saved captures before they are
committed or shared. Walks a directory (default: knowledge/sniffs), inspects every .json / .txt /
.md / .network-request / .network-response / .har file, and replaces the VALUES of sensitive keys
and any JWT / Bearer / cookie-looking string with a marker.

  scrub-secrets.py knowledge/sniffs               # dry run: prints every hit by file + key/path
  scrub-secrets.py knowledge/sniffs --write       # rewrite files in place (a .bak is NOT kept — git is the backup)
  scrub-secrets.py knowledge/sniffs --extra-key session_hash --extra-key fb_exchange_token

Never deletes a file. Never touches directories named recovered-source, chunks or maps (that is
the vendor's public code, not your data). Prints a summary count per file so a "0 hits" run is
visible as such, not silent.

What counts as sensitive (key match is case-insensitive, on the key name only)
  token, secret, password, passwd, api_key, apikey, csrf, authorization, cookie, set-cookie,
  publishable_key, client_secret, access_key, private_key, refresh_token, id_token, session_id,
  card, card_number, last4, iban, cvc, billing_address, stripe_customer, payment_method
String-shape matches (anywhere in a value or free text)
  JWTs (eyJ….eyJ….sig), `Bearer <token>`, `token-id: <value>`, Cookie header values,
  Stripe keys (sk_live_/pk_live_/sk_test_/pk_test_/rk_live_), AWS keys (AKIA…)
"""
import argparse
import json
import os
import re
import sys

KEY_RE_PARTS = [
    r"token", r"secret", r"passw(or)?d", r"api_?key", r"csrf", r"authorization", r"set-cookie", r"cookie",
    r"publishable_key", r"client_secret", r"access_key", r"private_key", r"refresh_token", r"id_token",
    r"session_id", r"card(_number)?", r"last4", r"iban", r"cvc", r"billing_address", r"stripe_customer",
    r"payment_method",
]
SKIP_DIRS = {"recovered-source", "chunks", "maps", "node_modules", ".git"}
COUNTER_KEY = re.compile(r"(?i)(count|total|limit|max|min|used|remaining|expires?_?(in|at)?|ttl|enabled|present|is_)")
EXTS = {".json", ".txt", ".md", ".network-request", ".network-response", ".har", ".log"}

STRING_PATTERNS = [
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[REDACTED-JWT]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(token-id\s*[:=]\s*)[A-Za-z0-9._~+/=-]{16,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:^|[\s\"'])cookie\s*[:=]\s*)[^\n\"']{8,}"), r"\1[REDACTED]"),
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}"), "[REDACTED-STRIPE-KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED-AWS-KEY]"),
]


def key_regex(extra):
    parts = KEY_RE_PARTS + [re.escape(k) for k in extra]
    return re.compile(r"(?i)(^|[_\-.\s])(" + "|".join(parts) + r")($|[_\-.\s])|^(" + "|".join(parts) + r")$")


def scrub_value(v, hits, path):
    if isinstance(v, str):
        new = v
        for rx, rep in STRING_PATTERNS:
            new, n = rx.subn(rep, new)
            if n:
                hits.append(f"{path} (string pattern ×{n})")
        return new
    return v


def scrub_json(obj, key_rx, hits, path=""):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if key_rx.search(k) and isinstance(v, (bool, int, float)) and COUNTER_KEY.search(k):
                out[k] = v  # `token_count`, `tokens_total`: a number about tokens, not a token
            elif key_rx.search(k) and v not in (None, "", [], {}) and not isinstance(v, (dict, list)):
                out[k] = "[REDACTED]"
                hits.append(p)
            elif key_rx.search(k) and isinstance(v, (dict, list)):
                # a `billing` or `card` object: redact its leaves wholesale
                out[k] = redact_leaves(v)
                hits.append(f"{p} (object)")
            else:
                out[k] = scrub_json(v, key_rx, hits, p)
        return out
    if isinstance(obj, list):
        return [scrub_json(x, key_rx, hits, f"{path}[{i}]") for i, x in enumerate(obj)]
    return scrub_value(obj, hits, path)


def redact_leaves(o):
    if isinstance(o, dict):
        return {k: redact_leaves(v) for k, v in o.items()}
    if isinstance(o, list):
        return [redact_leaves(x) for x in o]
    if isinstance(o, (str, int, float)) and o not in ("", 0):
        return "[REDACTED]"
    return o


def scrub_text(text, key_rx, hits):
    new = text
    for rx, rep in STRING_PATTERNS:
        new, n = rx.subn(rep, new)
        if n:
            hits.append(f"(text: {rx.pattern[:30]}… ×{n})")
    # `"api_key": "value"` inside non-JSON text (HAR fragments, pasted headers)
    def kv(m):
        if key_rx.search(m.group(1)):
            hits.append(f"(text key {m.group(1)})")
            return f'{m.group(0)[:m.start(2) - m.start(0)]}[REDACTED]'
        return m.group(0)
    new = re.sub(r'"([A-Za-z0-9_\-]+)"\s*:\s*"([^"\n]{6,})"', kv, new)
    return new


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default="knowledge/sniffs")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--extra-key", action="append", default=[])
    a = ap.parse_args()
    key_rx = key_regex(a.extra_key)

    total_files = total_hits = changed = 0
    for dirpath, dirnames, filenames in os.walk(a.root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTS:
                continue
            p = os.path.join(dirpath, fn)
            total_files += 1
            try:
                raw = open(p, encoding="utf-8", errors="replace").read()
            except Exception as e:
                print(f"! cannot read {p}: {e}", file=sys.stderr)
                continue
            hits = []
            new_text = None
            if ext == ".json" or ext == ".har":
                try:
                    data = json.loads(raw)
                    scrubbed = scrub_json(data, key_rx, hits)
                    if hits:
                        new_text = json.dumps(scrubbed, indent=2, ensure_ascii=False) + "\n"
                except json.JSONDecodeError:
                    new_text = scrub_text(raw, key_rx, hits)
            else:
                new_text = scrub_text(raw, key_rx, hits)
            if hits:
                total_hits += len(hits)
                print(f"{p}: {len(hits)} hit(s)")
                for h in hits[:40]:
                    print(f"   - {h}")
                if len(hits) > 40:
                    print(f"   … {len(hits) - 40} more")
                if a.write and new_text is not None and new_text != raw:
                    open(p, "w", encoding="utf-8").write(new_text)
                    changed += 1
    mode = "WROTE" if a.write else "DRY RUN"
    print(f"{mode}: {total_files} files scanned, {total_hits} hits, {changed} files rewritten")
    if not a.write and total_hits:
        print("re-run with --write to apply")


if __name__ == "__main__":
    main()
