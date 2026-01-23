from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
import urllib.request
import urllib.error


DEFAULT_BASE_URL = os.getenv("HUB_BASE_URL", "http://localhost:8000")
DEFAULT_ADMIN_KEY = os.getenv("INTERNAL_ADMIN_KEY", "")

DEFAULT_TIMEOUT_SECONDS = 30


def http_post(url: str, payload: dict[str, Any], admin_key: str) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Internal-Admin-Key": admin_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = ""
        print(f"HTTP {e.code} {e.reason} for {url}", file=sys.stderr)
        if body:
            print(body, file=sys.stderr)
        return {"error": {"status": e.code, "reason": e.reason, "body": body}}
    except urllib.error.URLError as e:
        print(f"Network error for {url}: {e}", file=sys.stderr)
        return {"error": {"reason": str(e)}}
    

def _infer_kind_from_filename(path: str) -> str:
    base = os.path.basename(path)
    return "geo" if base.startswith("areas_") else "enum"


def _infer_namespace_from_filename(path: str) -> str | None:
    base = os.path.basename(path)
    if base.startswith("enums_") and base.endswith(".json"):
        return base[len("enums_") : -len(".json")]
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Import destination catalogs (preview/apply).")
    p.add_argument("--destination", required=True, help="e.g. 101evler")
    p.add_argument("--file", required=True, help="path to json file")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--admin-key", default=DEFAULT_ADMIN_KEY)
    p.add_argument("--mode", choices=["preview", "apply"], default="preview")
    p.add_argument("--kind", choices=["enum", "geo"], help="optional override; inferred by file name if omitted")
    p.add_argument("--namespace", help="required for enum (e.g. currency, rooms, property_type, title_type)")
    p.add_argument("--yes", action="store_true", help="required for apply mode (safety)")
    args = p.parse_args()

    if not args.admin_key:
        print("Missing INTERNAL_ADMIN_KEY (env) or --admin-key", file=sys.stderr)
        return 2

    if args.mode == "apply" and not args.yes:
        print("Refusing to apply without --yes (safety).", file=sys.stderr)
        return 2

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            body = json.load(f)
    except Exception as e:
        print(f"Failed to read JSON file: {e}", file=sys.stderr)
        return 2

    # basic payload validation
    if not isinstance(body, dict) or "items" not in body or not isinstance(body["items"], list):
        print("Invalid payload: expected JSON object with an 'items' list.", file=sys.stderr)
        return 2

    dest = args.destination.lower().strip()
    base_url = args.base_url.rstrip("/")
    kind = args.kind or _infer_kind_from_filename(args.file)

    if kind == "enum":
        ns = args.namespace or _infer_namespace_from_filename(args.file)
        if not ns:
            print("Enum import requires --namespace or filename enums_<namespace>.json", file=sys.stderr)
            return 2

        endpoint = f"{args.base_url}/v1/admin/destinations/{dest}/catalogs/enums/{ns}:{args.mode}"
        resp = http_post(endpoint, body, args.admin_key)
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return 0 if "error" not in resp else 1

    if kind == "geo":
        endpoint = f"{args.base_url}/v1/admin/destinations/{dest}/catalogs/areas:{args.mode}"
        resp = http_post(endpoint, body, args.admin_key)
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return 0 if "error" not in resp else 1

    print(f"Unknown kind: {kind}", file=sys.stderr)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
