"""Comprehensive data-quality audit of data/jobs.json. Finds bug-classes:
dates (relative-text leaks, future, unparseable), duplicates, missing fields,
bad URLs, per-source date reliability, filter leaks. Run: python3 src/audit.py"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freshness import age_in_days
from filter import (role_ok, experience_ok, needs_clearance, location_ok,
                    blocks_visa, company_blocked)
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
a = json.load(open(os.path.join(HERE, "data", "jobs.json")))
prof = json.load(open(os.path.join(HERE, "profile.json")))
jobs = list(a.values())
maxage = prof.get("max_posted_age_days", 7)
print(f"=== AUDITING {len(jobs)} jobs ===\n")

issues = Counter()
examples = {}
def flag(cat, j):
    issues[cat] += 1
    examples.setdefault(cat, []).append(f"{j.get('company','?')[:18]} | {j.get('title','?')[:32]} | posted={str(j.get('posted_at',''))[:18]}")

for j in jobs:
    pa = str(j.get("posted_at", ""))
    age = age_in_days(j.get("posted_at"))
    blob = f"{j.get('title','')} {j.get('description','')}"
    loc = f"{j.get('location','')} {j.get('url','')}"
    # 1. relative-text date leak (should be absolute)
    if re.search(r"posted|today|yesterday|day ago|days ago|hour", pa.lower()):
        flag("relative-date-leak", j)
    # 2. future / negative age
    if age is not None and age < 0:
        flag("future-date", j)
    # 3. absurd age (>400d) but still on board
    if age is not None and age > maxage:
        flag("stale-on-board(>window)", j)
    # 4. missing critical fields
    if not j.get("title"): flag("missing-title", j)
    if not j.get("url"): flag("missing-url", j)
    if not j.get("company"): flag("missing-company", j)
    # 5. bad URL
    if j.get("url") and not str(j["url"]).startswith("http"): flag("bad-url", j)
    # 6. filter leaks (should never be on board)
    if not role_ok(j.get("title",""), prof): flag("LEAK-role", j)
    elif not experience_ok(blob, prof): flag("LEAK-experience", j)
    elif needs_clearance(blob, prof): flag("LEAK-clearance", j)
    elif blocks_visa(blob, prof): flag("LEAK-visa/citizenship", j)
    elif company_blocked(j.get("company",""), prof): flag("LEAK-excluded-company", j)
    elif not location_ok(loc, prof): flag("LEAK-non-US", j)
    # 7. closed still present
    if not j.get("open", True): flag("closed-on-board", j)

# 8. duplicates (same company+title)
keys = [(j.get("company","").lower(), j.get("title","").strip().lower()) for j in jobs]
dupes = sum(v-1 for v in Counter(keys).values() if v > 1)
if dupes: issues["duplicate-jobs"] = dupes

# 9. per-source date health
print("DATE HEALTH BY SOURCE (dated / undated / today):")
for src in sorted(set(j.get("source") for j in jobs)):
    js = [j for j in jobs if j.get("source") == src]
    dated = sum(1 for j in js if age_in_days(j.get("posted_at")) is not None)
    print(f"  {src:16} total={len(js):4} dated={dated:4} undated={len(js)-dated:4}")
print()
print("ISSUES FOUND:")
if not issues:
    print("  ✅ none")
for cat, n in issues.most_common():
    print(f"  {cat}: {n}")
    for ex in examples.get(cat, [])[:3]:
        print(f"       - {ex}")
