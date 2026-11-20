"""Fail CI when SonarCloud new-code metrics break the lab's quality contract.

- coverage on new code      >= 85 %
- duplicated lines (new)    <= 3 %
- security hotspots to review == 0
"""

import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HOST = os.environ.get("SONAR_HOST_URL", "https://sonarcloud.io")
PROJECT = "HanineKhemir_devops-sre-lab"
RULES = [
    ("new_coverage", ">=", 85.0),
    ("new_duplicated_lines_density", "<=", 3.0),
    ("new_security_hotspots", "<=", 0.0),
]


def api(path: str, **params: str) -> dict:
    if not HOST.startswith("https://"):
        raise SystemExit("SONAR_HOST_URL must be https")
    url = f"{HOST}/api/{path}?{urllib.parse.urlencode(params)}"
    token = base64.b64encode(f"{os.environ['SONAR_TOKEN']}:".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - scheme checked above
        return json.load(resp)


def main() -> int:
    scope = {"pullRequest": os.environ["PR"]} if os.environ.get("PR") else {"branch": "main"}
    keys = ",".join(k for k, _, _ in RULES)
    for _ in range(10):  # the analysis may still be processing
        comp = api("measures/component", component=PROJECT, metricKeys=keys, **scope)
        found = {}
        for m in comp["component"].get("measures", []):
            raw = m.get("period", {}).get("value", m.get("value"))
            if raw is not None:
                found[m["metric"]] = float(raw)
        if found:
            break
        time.sleep(10)
    failed = False
    for key, op, limit in RULES:
        value = found.get(key)
        if value is None:
            print(f"  {key:32} n/a (no new code)")
            continue
        ok = value >= limit if op == ">=" else value <= limit
        failed |= not ok
        print(f"{'PASS' if ok else 'FAIL'} {key:32} {value:7.2f} (required {op} {limit})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
