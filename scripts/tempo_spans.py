"""Print the spans of a Tempo trace (JSON on stdin) as a compact table."""

import json
import sys

d = json.load(sys.stdin)
for b in d.get("batches", []):
    attrs = {a["key"]: a["value"].get("stringValue") for a in b["resource"]["attributes"]}
    for ss in b.get("scopeSpans", []):
        for s in ss["spans"]:
            dur = (int(s["endTimeUnixNano"]) - int(s["startTimeUnixNano"])) / 1e6
            status = s.get("status", {}).get("code", "UNSET")
            name = s["name"]
            print(f"  span {name:<26} service={attrs.get('service.name')}  {dur:7.2f} ms  {status}")
