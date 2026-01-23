from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
import urllib.request

DEFAULT_BASE_URL = os.getenv("HUB_BASE_URL", "http://localhost:8000")
DEFAULT_ADMIN_KEY = os.getenv("INTERNAL_ADMIN_KEY", "")

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
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main() -> int:
    p = argparse.ArgumentParser(description="Import destination catalogs (preview/apply).")
    p.add_argument("--destination", required=True, help="e.g. 101evler")
    p.add_argument("--file", required=True, help="path to json file")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--admin-key", default=DEFAULT_ADMIN_KEY)
    p.add_argument("--mode", choices=["preview", "apply"], default="preview")
    p.add_argument("--kind", choices=["enum", "geo"], help="optional override; inferred by file name if omitted")
    p.add_argument("--namespace", help="required for enum (e.g. currency, rooms, property_type, title_type)")
    args = p.parse_args()

    if not args.admin_key:
        print("Missing INTERNAL_ADMIN_KEY (env) or --admin-key", file=sys.stderr)
        return 2

    with open(args.file, "r", encoding="utf-8") as f:
        body = json.load(f)

    dest = args.destination.lower().strip()
    kind = args.kind
    if not kind:
        # naive inference: areas_* => geo else enum
        kind = "geo" if os.path.basename(args.file).startswith("areas_") else "enum"

    if kind == "enum":
        ns = args.namespace
        if not ns:
            # infer from filename enums_<ns>.json
            base = os.path.basename(args.file)
            if base.startswith("enums_") and base.endswith(".json"):
                ns = base[len("enums_"):-len(".json")]
        if not ns:
            print("Enum import requires --namespace or filename enums_<namespace>.json", file=sys.stderr)
            return 2

        endpoint = f"{args.base_url}/v1/admin/destinations/{dest}/catalogs/enums/{ns}:{args.mode}"
        resp = http_post(endpoint, body, args.admin_key)
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return 0

    if kind == "geo":
        endpoint = f"{args.base_url}/v1/admin/destinations/{dest}/catalogs/areas:{args.mode}"
        resp = http_post(endpoint, body, args.admin_key)
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return 0

    print(f"Unknown kind: {kind}", file=sys.stderr)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
