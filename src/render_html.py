"""
Station 5b: WRITE WEBSITE (GitHub Pages)
Generates index.html — a real client-side job board for visa-sponsoring tech roles.

All filtering/sorting/pagination runs in vanilla JS over the jobs embedded as
JSON. No external JS/CSS dependencies. Strictly black-and-white SaaS aesthetic.
Every "Apply" opens in a NEW TAB (target=_blank).

Backend contract: jobs are NOT pre-filtered by experience. Each job dict carries
yoe_min (int|None) and yoe_max (int|None); profile carries
experience_years_min/max which seed the default experience filter.
"""
import os
import re
import html
import json
import atexit
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape as _xml_esc

ET = ZoneInfo("America/New_York")
SITE_URL = "https://siddarthareddy8.github.io/JobsBuddy/"
PAGE_SIZE = 50

TIER_LABEL = {"high": "High", "medium": "Med", "low": "Low"}
TIER_RANK = {"high": 3, "medium": 2, "low": 1}

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "company"


def _company_slugs(companies):
    """Stable unique slugs for company pages (c/<slug>.html)."""
    used, out = {}, {}
    for c in companies:
        base = _slug(c)
        s = base
        n = 2
        while s in used:
            s = f"{base}-{n}"
            n += 1
        used[s] = c
        out[c] = s
    return out


# main.py rewrites sitemap.xml AFTER render_html() returns (index-only version),
# so the company-page sitemap is deferred to interpreter exit — it lands last.
_SITEMAP_DEFERRED = None
_SITEMAP_REGISTERED = False


def _defer_sitemap(slugs, today):
    global _SITEMAP_DEFERRED, _SITEMAP_REGISTERED
    _SITEMAP_DEFERRED = (slugs, today)
    if not _SITEMAP_REGISTERED:
        atexit.register(_write_deferred_sitemap)
        _SITEMAP_REGISTERED = True


def _write_deferred_sitemap():
    try:
        if _SITEMAP_DEFERRED:
            slugs, today = _SITEMAP_DEFERRED
            _write_sitemap(slugs, today)
    except Exception:
        pass


def _esc(s):
    return html.escape(str(s or ""))


def _yoe_label(j):
    """Human YOE badge. Missing values handled gracefully."""
    lo, hi = j.get("yoe_min"), j.get("yoe_max")
    if lo is None and hi is None:
        return "Not specified"
    if lo is not None and hi is not None:
        return f"{lo}\u2013{hi} yrs" if lo != hi else f"{lo} yrs"
    if lo is not None:
        return f"{lo}+ yrs"
    return f"\u2264{hi} yrs"


def _posted_label(j):
    age = j.get("age_days")
    if age is None:
        return "date unknown"
    if age <= 0:
        return "today"
    if age <= 30:
        return f"{age}d ago"
    return f"{age // 30}mo ago"


def _sponsor_badge(j):
    """(kind, label) for the sponsor badge, or (None, None) when there is no
    positive sponsorship signal — the UI then renders no badge at all,
    keeping cards calm instead of stamping "unknown" everywhere."""
    tier = j.get("sponsor_tier")
    if j.get("sponsors_visa"):
        cases = j.get("sponsor_cases")
        extra = f" \u00b7 {cases} filings" if cases else ""
        t = TIER_LABEL.get(tier, "")
        label = f"Sponsors \u00b7 {t}{extra}".strip() if t else f"Sponsors{extra}"
        return ("spon", label)
    if tier:
        return ("tier", f"Sponsor history \u00b7 {TIER_LABEL.get(tier, tier)}")
    return (None, None)


def _default_exp_preset(profile):
    """The board is YOE-agnostic: it always opens unfiltered ("any") so every
    experience level is visible; the user narrows via the filter pills."""
    return "any"


def _job_payload(j, today, slug=""):
    kind, slabel = _sponsor_badge(j)
    skills = j.get("matched_skills") or []
    return {
        "title": j.get("title", ""),
        "company": j.get("company", ""),
        "slug": slug,
        "location": j.get("location", ""),
        "url": j.get("url", ""),
        "contact_email": j.get("contact_email", ""),
        "description": j.get("description", "") or "",
        "age_days": j.get("age_days"),
        "posted_label": _posted_label(j),
        "yoe_min": j.get("yoe_min"),
        "yoe_max": j.get("yoe_max"),
        "yoe_label": _yoe_label(j),
        "sponsor_tier": j.get("sponsor_tier"),
        "sponsors_visa": bool(j.get("sponsors_visa")),
        "sponsor_kind": kind,
        "sponsor_label": slabel,
        "is_new": j.get("first_seen") == today,
        "is_closed": not j.get("open", True),
        "match_score": j.get("match_score", 0) or 0,
        "matched_skills": [str(s) for s in skills],
        "opt_friendly": bool(j.get("opt_friendly", True)),
    }


def _build_jsonld(jobs):
    """Structured data so Google can index the listings (Google for Jobs)."""
    items = []
    # cap to open jobs to keep the page light
    listed = [j for j in jobs if j.get("open", True)][:120]
    for i, j in enumerate(listed, 1):
        posting = {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": j.get("title", ""),
            "description": (f"{j.get('title','')} at {j.get('company','')}. "
                            f"US-based, visa-sponsor-friendly role, all experience levels. "
                            f"{(j.get('description','') or '')[:300]}"),
            "datePosted": j.get("first_seen", ""),
            "employmentType": "FULL_TIME",
            "hiringOrganization": {"@type": "Organization", "name": j.get("company", "")},
            "jobLocation": {"@type": "Place", "address": {
                "@type": "PostalAddress",
                "addressLocality": (j.get("location", "") or "United States").split(",")[0],
                "addressCountry": "US"}},
            "directApply": True,
            "url": j.get("url", ""),
        }
        items.append({"@type": "ListItem", "position": i, "item": posting})
    graph = {"@context": "https://schema.org/", "@type": "ItemList",
             "name": "OPT-friendly visa-sponsoring tech jobs", "itemListElement": items}
    return ('<script type="application/ld+json">'
            + json.dumps(graph, ensure_ascii=False) + '</script>')


def _py_meta_line(j):
    """Python mirror of the JS metaLine(): YOE (when known) · sponsor (when real) · age."""
    parts = []
    if j.get("yoe_min") is not None or j.get("yoe_max") is not None:
        parts.append(_yoe_label(j))
    tier = j.get("sponsor_tier")
    if j.get("sponsors_visa"):
        t = TIER_LABEL.get(tier)
        parts.append("Sponsors" + (f" ({t})" if t else ""))
    elif tier:
        t = TIER_LABEL.get(tier, tier)
        parts.append(f"Sponsor history ({t})")
    parts.append(_posted_label(j))
    return " · ".join(parts)


def _company_sponsor_line(roles):
    """'Confirmed H-1B sponsor · High tier · 143 filings' style line, or ''."""
    best, cases = None, None
    for j in roles:
        t = j.get("sponsor_tier")
        if t and TIER_RANK.get(t, 0) > TIER_RANK.get(best, 0):
            best = t
        c = j.get("sponsor_cases")
        if c and (cases is None or c > cases):
            cases = c
    if not best:
        return ""
    line = f"Confirmed H-1B sponsor · {TIER_LABEL.get(best, best)} tier"
    if cases:
        line += f" · {cases} DOL filings"
    return line


def _board_css():
    """Reuse the board's own stylesheet so company pages look like the product."""
    return _PAGE.split("<style>", 1)[1].split("</style>", 1)[0]


def _render_company_page(company, slug, roles, today):
    roles = sorted(roles, key=lambda j: (j.get("age_days") is None, j.get("age_days") or 99999))
    sline = _company_sponsor_line(roles)
    cards = []
    for j in roles:
        apply = (f'<a class="apply" href="{_esc(j.get("url"))}" target="_blank" '
                 'rel="noopener noreferrer">Apply</a>' if j.get("url") else "")
        new = '<span class="tag tag-new">NEW</span>' if j.get("first_seen") == today else ""
        cards.append(
            '<article class="card"><div class="card-top"><div>'
            f'<h3 class="job-title">{_esc(j.get("title"))}</h3>'
            f'<div class="job-sub">{_esc(j.get("location"))}</div>'
            f'<div class="meta">{_esc(_py_meta_line(j))}</div>'
            f'</div><div class="card-side">{new}{apply}</div></div></article>')
    sub = sline or "Open roles"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(company)} jobs — visa-sponsoring roles | JobsBuddy</title>
<meta name="description" content="Open software and technology roles at {_esc(company)} in India or remote worldwide. Refreshed every two hours.">
<link rel="canonical" href="{SITE_URL}c/{slug}.html">
<style>{_board_css()}
.co-hero h1{{font-size:32px}}
.back-link{{display:inline-block;margin-bottom:6px;font-size:13.5px;font-weight:600;text-decoration:none}}
.back-link:hover{{text-decoration:underline}}
</style>
</head>
<body>
<header class="nav"><div class="nav-in">
<a href="../" style="display:flex;align-items:center;gap:10px;font-size:16px;font-weight:800;text-decoration:none;margin:0"><span class="mark">JB</span>JobsBuddy</a>
<div class="nav-links"><a class="btn btn-ghost" href="../">← All jobs</a></div>
</div></header>
<div class="wrap">
<section class="hero co-hero">
<div class="eyebrow">Company · software openings</div>
<h1>{_esc(company)}</h1>
<p>{_esc(sub)}</p>
</section>
<div style="padding:26px 0 12px">
{''.join(cards) if cards else '<p style="color:var(--mut)">No open roles right now — check back soon.</p>'}
</div>
<footer>Part of <a href="../">JobsBuddy</a> — free job board for India and remote technology roles, refreshed every two hours.</footer>
</div>
</body>
</html>
"""


def _rfc822(d):
    try:
        dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=ET)
    except Exception:
        dt = datetime.now(ET)
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def _render_feed(jobs, today):
    open_jobs = [j for j in jobs if j.get("open", True)]
    newest = sorted(open_jobs,
                    key=lambda j: (j.get("age_days") is None, j.get("age_days") or 99999))[:50]
    items = []
    for j in newest:
        title = f"{j.get('title','')} — {j.get('company','')} ({j.get('location','')})"
        items.append(
            "<item>"
            f"<title>{_xml_esc(title)}</title>"
            f"<link>{_xml_esc(j.get('url') or SITE_URL)}</link>"
            f"<guid isPermaLink=\"false\">{_xml_esc(j.get('url') or title)}</guid>"
            f"<pubDate>{_rfc822(j.get('first_seen') or today)}</pubDate>"
            f"<description>{_xml_esc((j.get('description') or '')[:400])}</description>"
            "</item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel>'
            f"<title>JobsBuddy — visa-sponsoring tech jobs</title>"
            f"<link>{SITE_URL}</link>"
            "<description>India software and technology roles plus remote worldwide openings. Updated every two hours.</description>"
            f"<lastBuildDate>{_rfc822(today)}</lastBuildDate>"
            + "".join(items) + "</channel></rss>")


def _write_sitemap(slugs, today):
    urls = [(SITE_URL, today, "daily", "1.0")]
    for slug in sorted(slugs):
        urls.append((f"{SITE_URL}c/{slug}.html", today, "weekly", "0.8"))
    body = "\n".join(
        f'  <url><loc>{u}</loc><lastmod>{lm}</lastmod>'
        f'<changefreq>{cf}</changefreq><priority>{pr}</priority></url>'
        for u, lm, cf, pr in urls)
    with open(os.path.join(_REPO_ROOT, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + body + '\n</urlset>\n')


def _write_site_files(payload, slugs, jobs, today):
    """Company pages + RSS now; sitemap.xml is deferred to exit (see _defer_sitemap)."""
    cdir = os.path.join(_REPO_ROOT, "c")
    os.makedirs(cdir, exist_ok=True)
    by_company = {}
    for p, j in zip(payload, jobs):
        if j.get("open", True) and p["company"]:
            by_company.setdefault(p["company"], []).append(j)
    for company, roles in by_company.items():
        slug = slugs[company]
        with open(os.path.join(cdir, f"{slug}.html"), "w") as f:
            f.write(_render_company_page(company, slug, roles, today))
    with open(os.path.join(_REPO_ROOT, "feed.xml"), "w") as f:
        f.write(_render_feed(jobs, today))
    _defer_sitemap([slugs[c] for c in by_company], today)


def render_html(jobs, profile, today):
    now = datetime.now(ET).strftime("%b %d, %Y \u00b7 %I:%M %p ET")
    companies = sorted({j.get("company") for j in jobs if j.get("company")})
    slugs = _company_slugs(companies)
    payload = [_job_payload(j, today, slugs.get(j.get("company") or "", ""))
               for j in jobs]
    _write_site_files(payload, slugs, jobs, today)
    default_exp = _default_exp_preset(profile)

    jobs_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    companies_json = json.dumps(companies, ensure_ascii=False).replace("</", "<\\/")

    page = _PAGE
    page = page.replace("%%NOW%%", _esc(now))
    page = page.replace("%%SITE%%", SITE_URL)
    page = page.replace("%%JSONLD%%", _build_jsonld(jobs))
    page = page.replace("%%JOBS_JSON%%", jobs_json)
    page = page.replace("%%COMPANIES_JSON%%", companies_json)
    page = page.replace("%%DEFAULT_EXP%%", default_exp)
    page = page.replace("%%PAGE_SIZE%%", str(PAGE_SIZE))
    return page


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JobsBuddy — India Software, AI, Data and Remote Jobs</title>
<meta name="description" content="Free job board for software, AI, data, cloud and related roles in India and worldwide remote teams. Filter by city, experience, role, company and posting date. Updated every two hours.">
<meta name="keywords" content="India software jobs, software engineer jobs India, AI jobs India, data engineer jobs India, remote software jobs, Bengaluru jobs, Hyderabad jobs, Chennai jobs, Pune jobs, Mumbai jobs">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Siddartha Reddy Chinthala">
<link rel="canonical" href="%%SITE%%">
<meta property="og:type" content="website">
<meta property="og:url" content="%%SITE%%">
<meta property="og:title" content="JobsBuddy — Visa-Sponsoring Tech Jobs for International Students">
<meta property="og:description" content="India software, AI, data and cloud jobs plus remote worldwide roles. Updated every two hours.">
<meta property="og:site_name" content="JobsBuddy">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="JobsBuddy — Visa-Sponsoring Tech Jobs for International Students">
<meta name="twitter:description" content="India software, AI, data and cloud jobs plus remote worldwide roles. Updated every two hours.">
<meta name="theme-color" content="#000000">
<link rel="alternate" type="application/rss+xml" title="JobsBuddy — newest visa-sponsoring tech jobs" href="feed.xml">
%%JSONLD%%
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#0a0a0a;--ink2:#3d3d3d;--mut:#777;--line:#e6e6e6;--line2:#111;--bg:#fff;--soft:#fafafa}
html{-webkit-font-smoothing:antialiased}
body{background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;font-size:15px;line-height:1.55}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
a{color:inherit}
button{font-family:inherit}

/* sticky header */
header.nav{position:sticky;top:0;z-index:60;background:rgba(255,255,255,.94);backdrop-filter:blur(8px);border-bottom:1px solid var(--line2)}
.nav-in{max-width:1180px;margin:0 auto;padding:12px 22px;display:flex;align-items:center;gap:14px}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:17px;letter-spacing:-.01em;white-space:nowrap}
.mark{width:26px;height:26px;border:1.5px solid var(--ink);border-radius:7px;display:grid;place-items:center;font-size:12px;font-weight:800}
.hsearch{flex:1;max-width:460px;padding:10px 14px;border:1.5px solid var(--ink);border-radius:10px;font-size:14px}
.hsearch::placeholder{color:var(--mut)}
.nav-links{display:flex;gap:8px;align-items:center;margin-left:auto}
.btn{font-size:13px;font-weight:600;padding:8px 14px;border-radius:8px;border:1.5px solid var(--ink);text-decoration:none;white-space:nowrap;transition:.12s;background:#fff;cursor:pointer}
.btn-solid{background:var(--ink);color:#fff}.btn-solid:hover{background:#fff;color:var(--ink)}
.btn-ghost:hover{background:var(--ink);color:#fff}
#filterToggle{display:none}

/* hero — one headline, one subline, quiet stat row, then stop */
.wrap{max-width:1180px;margin:0 auto;padding:0 22px}
.hero{padding:40px 0 26px;border-bottom:1px solid var(--line)}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
.hero h1{font-size:38px;line-height:1.08;letter-spacing:-.03em;margin:12px 0;max-width:22ch}
.hero p{font-size:16px;color:var(--ink2);max-width:64ch}
.stats{display:flex;flex-wrap:wrap;row-gap:14px;margin-top:22px}
.stat{padding:2px 22px;border-left:1px solid var(--line)}
.stat:first-child{border-left:0;padding-left:0}
.stat b{font-size:22px;font-weight:800;letter-spacing:-.02em;display:block;font-family:ui-monospace,Menlo,Consolas,monospace}
.stat span{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}

/* layout */
.layout{display:flex;gap:32px;align-items:flex-start;padding:30px 0 12px}
aside.filters{width:272px;flex-shrink:0;position:sticky;top:76px;max-height:calc(100vh - 96px);overflow-y:auto;border:1.5px solid var(--line2);border-radius:14px;padding:18px;background:#fff}
main.results{flex:1;min-width:0}
.f-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
.f-head h2{font-size:15px;font-weight:800}
.clear{background:none;border:0;font-size:12.5px;font-weight:600;color:var(--ink2);text-decoration:underline;cursor:pointer}
.f-group{margin:12px 0;padding-top:12px;border-top:1px solid var(--line)}
.f-group:first-of-type{margin-top:6px}
.f-group h3{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin-bottom:8px;font-weight:700}
.pills{display:flex;flex-wrap:wrap;gap:8px}
.pill input{position:absolute;opacity:0;pointer-events:none}
.pill span{display:inline-block;font-size:12.5px;font-weight:600;padding:7px 13px;border-radius:999px;border:1.5px solid var(--ink);cursor:pointer;transition:.12s;background:#fff;white-space:nowrap}
.pill input:checked+span{background:var(--ink);color:#fff}
.pill input:focus-visible+span{outline:2px solid var(--ink);outline-offset:2px}
.f-input{width:100%;padding:9px 12px;border:1.5px solid var(--ink);border-radius:8px;font-size:13.5px}
.f-input::placeholder{color:var(--mut)}
.co-list{max-height:200px;overflow-y:auto;border:1px solid var(--line);border-radius:8px;padding:6px 10px;margin-top:8px}
.co-item{display:flex;align-items:center;gap:9px;padding:5px 2px;font-size:13.5px;cursor:pointer}
.co-item input{accent-color:#0a0a0a;width:15px;height:15px;flex-shrink:0}
.co-item .n{color:var(--mut);font-size:12px;margin-left:auto;font-family:ui-monospace,Menlo,Consolas,monospace}
.toggle-row{display:flex;align-items:center;justify-content:space-between;font-size:13.5px;font-weight:600;cursor:pointer}
.switch{position:relative;width:42px;height:24px;flex-shrink:0}
.switch input{opacity:0;width:0;height:0}
.sl{position:absolute;inset:0;border:1.5px solid var(--ink);border-radius:999px;transition:.15s;background:#fff}
.sl:before{content:"";position:absolute;width:16px;height:16px;left:3px;top:2.5px;background:var(--ink);border-radius:50%;transition:.15s}
.switch input:checked+.sl{background:var(--ink)}
.switch input:checked+.sl:before{transform:translateX(17px);background:#fff}

/* toolbar */
.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px;flex-wrap:wrap}
.sortsel{padding:9px 12px;border:1.5px solid var(--ink);border-radius:8px;font-size:13.5px;font-weight:600;background:#fff}

/* cards */
.card{border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:16px;cursor:pointer;background:#fff;transition:border-color .15s, background .15s}
.card:hover{background:var(--soft);border-color:var(--ink)}
.card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
.job-title{font-size:17px;font-weight:700;letter-spacing:-.01em}
.job-sub{font-size:13.5px;color:var(--ink2);margin-top:5px}
.job-sub .co{font-weight:700;color:var(--ink)}
.co-link{font-weight:700;color:inherit;text-decoration:none}
.co-link:hover{text-decoration:underline}
.meta{font-size:13px;color:var(--mut);margin-top:9px}
.tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:4px 10px;border-radius:999px;border:1px solid var(--ink);white-space:nowrap}
.tag-new{background:var(--ink);color:#fff;border-color:var(--ink)}
.tag-closed{border-color:var(--mut);color:var(--mut)}
.posted{font-size:12.5px;color:var(--mut)}
.card-side{display:flex;flex-direction:column;align-items:flex-end;gap:10px;flex-shrink:0}
.apply{display:inline-block;font-size:13px;font-weight:700;padding:9px 20px;border-radius:8px;background:var(--ink);color:#fff;text-decoration:none;border:1.5px solid var(--ink);transition:.12s;white-space:nowrap;flex-shrink:0}
.apply:hover{background:#fff;color:var(--ink)}
.apply::after{content:" \\2197";font-weight:500}
.more-wrap{text-align:center;padding:18px 0 8px}
#more{font-size:14px;font-weight:700;padding:12px 34px;border-radius:10px;border:1.5px solid var(--ink);background:#fff;cursor:pointer;transition:.12s}
#more:hover{background:var(--ink);color:#fff}

/* star banner + sidebar star card */
.star-banner{display:flex;align-items:center;justify-content:center;gap:8px;background:var(--soft);border:1px solid var(--line);color:var(--ink2);font-size:13px;padding:8px 44px 8px 16px;border-radius:10px;margin:16px 0 0;position:relative;text-align:center;line-height:1.45}
.star-banner a{color:var(--ink);font-weight:700;text-decoration:underline;text-underline-offset:3px;white-space:nowrap}
.star-banner button{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:0;color:var(--mut);font-size:13px;cursor:pointer;padding:8px;line-height:1}
.star-banner button:hover{color:var(--ink)}
.star-card{margin:14px 0 2px;padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--soft)}
.star-card-t{font-weight:800;font-size:14px;margin-bottom:6px}
.star-card p{font-size:12.5px;color:var(--ink2);margin-bottom:12px;line-height:1.5}
.star-card .btn{display:inline-block}

/* empty state */
.empty{display:none;text-align:center;padding:70px 20px;border:1.5px dashed var(--mut);border-radius:14px}
.empty h3{font-size:20px;margin-bottom:8px}
.empty p{color:var(--ink2);margin-bottom:18px}

/* modal */
.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:100;align-items:flex-start;justify-content:center;padding:40px 18px;overflow-y:auto}
.overlay.open{display:flex}
.modal{background:#fff;border-radius:16px;max-width:720px;width:100%;padding:30px 32px;position:relative;border:1.5px solid var(--ink)}
.modal h2{font-size:22px;letter-spacing:-.02em;padding-right:36px}
.modal .m-sub{color:var(--ink2);font-size:14px;margin:6px 0 4px}
.modal .m-meta{display:flex;align-items:center;gap:10px;margin:12px 0 4px;flex-wrap:wrap}
.m-close{position:absolute;top:16px;right:16px;width:34px;height:34px;border-radius:50%;border:1.5px solid var(--ink);background:#fff;font-size:16px;cursor:pointer;line-height:1}
.m-close:hover{background:var(--ink);color:#fff}
.m-desc{white-space:pre-wrap;font-size:14.5px;color:var(--ink2);margin:16px 0;max-height:46vh;overflow-y:auto;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:16px 0}
.m-skills{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}
.m-skills span{font-size:12px;font-weight:600;border:1px solid var(--line2);border-radius:999px;padding:4px 12px}
.m-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.m-foot .note{font-size:12px;color:var(--mut)}

footer{border-top:1px solid var(--line2);margin-top:44px;padding:26px 0 56px;color:var(--mut);font-size:12.5px}
footer a{font-weight:600}
.drawer-bg{display:none}

@media(max-width:960px){
  #filterToggle{display:inline-block}
  .nav-links .btn-ghost{display:none}
  aside.filters{position:fixed;top:0;left:0;bottom:0;width:min(320px,86vw);z-index:90;border-radius:0;border:0;border-right:1.5px solid var(--line2);max-height:none;transform:translateX(-102%);transition:transform .2s ease}
  body.drawer-open aside.filters{transform:none}
  .drawer-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:80}
  body.drawer-open .drawer-bg{display:block}
  .layout{flex-direction:column}
  main.results{width:100%}
  .hero h1{font-size:32px}
  .hsearch{max-width:none}
}
</style>
</head>
<body>

<header class="nav">
  <div class="nav-in">
    <div class="brand"><span class="mark">JB</span> JobsBuddy</div>
    <input class="hsearch" id="q" type="search" placeholder="Search title, company, or description…" autocomplete="off" aria-label="Search jobs">
    <button class="btn btn-ghost" id="filterToggle" aria-label="Open filters">Filters</button>
    <div class="nav-links">
      <a class="btn btn-ghost" href="https://github.com/SIDDARTHAREDDY8/JobsBuddy" target="_blank" rel="noopener">★ Star</a>
    </div>
  </div>
</header>

<div class="wrap">
  <div class="star-banner" id="starBanner">
    <span>JobsBuddy is free &amp; open-source — a star helps other students find it.</span>
    <a href="https://github.com/SIDDARTHAREDDY8/JobsBuddy" target="_blank" rel="noopener">★ Star on GitHub</a>
    <button id="starDismiss" aria-label="Dismiss">✕</button>
  </div>

  <section class="hero">
  <div class="eyebrow">India jobs · Software, data, cloud and AI</div>
    <h1>Software openings across India and worldwide remote roles.</h1>
    <p>Fresh public ATS postings every two hours. Filter by city, role, experience, company and remote eligibility.</p>
  </section>

  <div class="layout">
    <div class="drawer-bg" id="drawerBg"></div>
    <aside class="filters" id="sidebar" aria-label="Job filters">
      <div class="f-head">
        <h2>Filters</h2>
        <button class="clear" id="clearAll" type="button">Clear all</button>
      </div>

      <div class="f-group">
        <h3>Software role</h3>
        <select class="f-input" id="roleType" aria-label="Filter by software role"><option value="all">All software roles</option><option value="backend">Backend</option><option value="frontend">Frontend</option><option value="fullstack">Full stack</option><option value="ai">AI / Machine learning</option><option value="data">Data engineering / analytics</option><option value="devops">DevOps / Cloud / SRE</option><option value="mobile">Mobile</option><option value="qa">QA / Test automation</option><option value="security">Application security</option></select>
      </div>
      <div class="f-group">
        <h3>Experience</h3>
        <div class="pills" id="expPills" role="radiogroup" aria-label="Experience level">
          <label class="pill"><input type="radio" name="exp" value="any"><span>Any</span></label>
          <label class="pill"><input type="radio" name="exp" value="entry"><span>Entry 0–2</span></label>
          <label class="pill"><input type="radio" name="exp" value="mid"><span>Mid 2–5</span></label>
          <label class="pill"><input type="radio" name="exp" value="senior"><span>Senior 5+</span></label>
          <label class="pill"><input type="radio" name="exp" value="lead"><span>Lead 8+</span></label>
        </div>
      </div>

      <div class="f-group">
        <h3>Company</h3>
        <input class="f-input" id="coSearch" type="search" placeholder="Search companies…" autocomplete="off" aria-label="Search companies">
        <div class="co-list" id="coList"></div>
      </div>

      <div class="f-group">
        <h3>Location</h3>
        <select class="f-input" id="city" aria-label="Filter by city"><option value="">All cities</option></select>
        <input class="f-input" id="loc" type="search" placeholder="e.g. New York, remote…" autocomplete="off" aria-label="Filter by location">
      </div>

      <div class="f-group">
        <h3>Remote location</h3>
        <select class="f-input" id="remoteScope" aria-label="Remote job location"><option value="any">Any location</option><option value="india">Remote in India</option><option value="world">Remote outside India</option></select>
      </div>

      <div class="f-group"><label class="toggle-row">Startup openings <span class="switch"><input type="checkbox" id="startups"><span class="sl"></span></span></label></div>

      <div class="f-group">
        <h3>Posted within</h3>
        <div class="pills" id="postedPills" role="radiogroup" aria-label="Posted within">
          <label class="pill"><input type="radio" name="posted" value="any"><span>Any time</span></label>
          <label class="pill"><input type="radio" name="posted" value="today"><span>Today</span></label>
          <label class="pill"><input type="radio" name="posted" value="d3"><span>3 days</span></label>
          <label class="pill"><input type="radio" name="posted" value="d7"><span>7 days</span></label>
        </div>
      </div>

      <div class="f-group">
        <label class="toggle-row">Remote only
          <span class="switch"><input type="checkbox" id="remote"><span class="sl"></span></span>
        </label>
      </div>

      <div class="star-card">
        <div class="star-card-t">★ Enjoying JobsBuddy?</div>
        <p>It&apos;s free and open-source. A star helps other students discover it.</p>
        <a class="btn btn-solid" href="https://github.com/SIDDARTHAREDDY8/JobsBuddy" target="_blank" rel="noopener">Star the repo</a>
      </div>
    </aside>

    <main class="results">
      <div class="toolbar">
        <select class="sortsel" id="sort" aria-label="Sort jobs">
          <option value="new">Sort: Newest</option>
          <option value="match">Sort: Best match</option>
          <option value="az">Sort: Company A–Z</option>
        </select>
      </div>
      <div class="hint mono" id="legend" style="font-size:12px;color:var(--mut);margin-bottom:16px">
        NEW = added in the latest update
      </div>
      <div id="cards"></div>
      <div class="empty" id="empty">
        <h3>No roles match your filters</h3>
        <p>Try widening the experience range or clearing the search.</p>
        <button class="btn btn-solid" id="emptyClear" type="button">Clear all filters</button>
      </div>
      <div class="more-wrap"><button id="more" type="button" style="display:none">Load more</button></div>
    </main>
  </div>

  <footer>
    Last updated %%NOW%%. Built with a free Python scraper + GitHub Actions — no paid APIs.<br>
    Sourced from connected public ATS feeds. Recruiter emails appear only when a posting publishes one.
    &nbsp;·&nbsp; <a href="https://github.com/SIDDARTHAREDDY8/JobsBuddy" target="_blank" rel="noopener">View source on GitHub</a>
  </footer>
</div>

<div class="overlay" id="overlay">
  <div class="modal" role="dialog" aria-modal="true" id="modal"></div>
</div>

<script type="application/json" id="jobs-data">%%JOBS_JSON%%</script>
<script>
(function(){
"use strict";
var JOBS = JSON.parse(document.getElementById('jobs-data').textContent);
var COMPANIES = %%COMPANIES_JSON%%;
var DEFAULT_EXP = "%%DEFAULT_EXP%%";
var PAGE_SIZE = %%PAGE_SIZE%%;

var PRESETS = {
  any:    {min: null, max: null},
  entry:  {min: 0, max: 2},
  mid:    {min: 2, max: 5},
  senior: {min: 5, max: 8},
  lead:   {min: 8, max: null}
};
var POSTED_LIM = {any: null, today: 0, d3: 3, d7: 7};
var VALID = {
  exp: ["any","entry","mid","senior","lead"],
  spon: ["all","confirmed","high","medium","low"],
  posted: ["any","today","d3","d7"],
  sort: ["new","match","az"]
};

function esc(s){
  return String(s == null ? "" : s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

var state = {
  q: "", exp: DEFAULT_EXP, companies: null, // null = all selected
  loc: "", posted: "any", remote: false, city: "", remoteScope: "any", startups: false, roleType: "all",
  sort: "new", shown: PAGE_SIZE
};

function readHash(){
  var h = location.hash.replace(/^#/, "");
  if(!h) return;
  var p = new URLSearchParams(h);
  if(p.get("q")) state.q = p.get("q");
  if(VALID.exp.indexOf(p.get("exp")) > -1) state.exp = p.get("exp");
  if(p.get("cox") && p.get("cox").length){
    var ex = p.getAll("cox");
    var set = new Set(COMPANIES);
    ex.forEach(function(c){ set.delete(c); });
    if(set.size && set.size < COMPANIES.length) state.companies = set;
  }
  if(p.get("loc")) state.loc = p.get("loc");
  if(VALID.posted.indexOf(p.get("posted")) > -1) state.posted = p.get("posted");
  state.remote = p.get("remote") === "1";
  state.city = p.get("city") || ""; state.remoteScope = p.get("rs") || "any"; state.startups = p.get("startup") === "1";
  state.roleType = p.get("role") || "all";
  if(VALID.sort.indexOf(p.get("sort")) > -1) state.sort = p.get("sort");
}

function writeHash(){
  var p = new URLSearchParams();
  if(state.q) p.set("q", state.q);
  if(state.exp !== "any") p.set("exp", state.exp);
  if(state.companies){
    var ex = COMPANIES.filter(function(c){ return !state.companies.has(c); });
    ex.forEach(function(c){ p.append("cox", c); });
  }
  if(state.loc) p.set("loc", state.loc);
  if(state.posted !== "any") p.set("posted", state.posted);
  if(state.remote) p.set("remote", "1");
  if(state.city) p.set("city", state.city); if(state.remoteScope !== "any") p.set("rs", state.remoteScope); if(state.startups) p.set("startup", "1");
  if(state.roleType !== "all") p.set("role", state.roleType);
  if(state.sort !== "new") p.set("sort", state.sort);
  var s = p.toString();
  history.replaceState(null, "", s ? "#" + s : location.pathname + location.search);
}

function yoeOk(j){
  var pr = PRESETS[state.exp];
  if(pr.min == null && pr.max == null) return true;
  if(j.yoe_min != null && pr.max != null && j.yoe_min > pr.max) return false;
  if(j.yoe_max != null && pr.min != null && j.yoe_max < pr.min) return false;
  return true; // unknown YOE never filters a job out
}

function matches(j){
  if(state.q){
    var hay = (j.title + " " + j.company + " " + (j.description || "")).toLowerCase();
    if(hay.indexOf(state.q) < 0) return false;
  }
  if(!yoeOk(j)) return false;
  var title = (j.title || "").toLowerCase();
  var roleTests = {backend:/back.?end|server.?side/,frontend:/front.?end|ui engineer/,fullstack:/full.?stack/,ai:/\b(ai|ml|machine learning|artificial intelligence|gen.?ai|llm)\b/,data:/data engineer|analytics engineer|data platform/,devops:/devops|sre|site reliability|cloud|platform engineer/,mobile:/android|ios|mobile engineer/,qa:/\bqa\b|quality assurance|test automation|automation engineer/,security:/security engineer|application security|product security/};
  if(state.roleType !== "all" && (!roleTests[state.roleType] || !roleTests[state.roleType].test(title))) return false;
  if(state.companies && !state.companies.has(j.company)) return false;
  if(state.loc && (j.location || "").toLowerCase().indexOf(state.loc) < 0) return false;
  if(state.city && (j.location || "").toLowerCase().indexOf(state.city) < 0) return false;
  var remoteLoc = (j.location || "").toLowerCase();
  if(state.remoteScope !== "any" && remoteLoc.indexOf("remote") < 0) return false;
  if(state.remoteScope === "india" && !/india|\bin\b|bengaluru|bangalore|hyderabad|chennai|mumbai|pune|delhi|gurugram|noida/.test(remoteLoc)) return false;
  if(state.remoteScope === "world" && /india|bengaluru|bangalore|hyderabad|chennai|mumbai|pune|delhi|gurugram|noida/.test(remoteLoc)) return false;
  if(state.remoteScope.indexOf("country:") === 0 && remoteLoc.indexOf(state.remoteScope.slice(8)) < 0) return false;
  if(state.startups && !STARTUPS.has((j.company || "").toLowerCase())) return false;
  var lim = POSTED_LIM[state.posted];
  if(lim != null){
    if(j.age_days == null || j.age_days > lim) return false;
  }
  if(state.remote && (j.location || "").toLowerCase().indexOf("remote") < 0) return false;
  return true;
}

function sortJobs(list){
  var arr = list.slice();
  if(state.sort === "match"){
    arr.sort(function(a,b){ return (b.match_score||0) - (a.match_score||0); });
  } else if(state.sort === "az"){
    arr.sort(function(a,b){
      return (a.company||"").localeCompare(b.company||"") ||
             (a.title||"").localeCompare(b.title||"");
    });
  } else {
    arr.sort(function(a,b){
      var x = a.age_days == null ? 99999 : a.age_days;
      var y = b.age_days == null ? 99999 : b.age_days;
      return x - y;
    });
  }
  return arr;
}

function metaLine(j){
  // Show experience detail and posting freshness.
  var parts = [];
  if(j.yoe_min != null || j.yoe_max != null) parts.push(j.yoe_label);
  parts.push(j.posted_label);
  return parts.join(" \u00b7 ");
}

function cardHtml(j, idx){
  var pill = j.is_new ? '<span class="tag tag-new">NEW</span>' : '';
  if(j.is_closed) pill += '<span class="tag tag-closed">Closed</span>';
  var apply = j.url ? '<a class="apply" href="' + esc(j.url) +
    '" target="_blank" rel="noopener noreferrer">Apply</a>' : '';
  return '<article class="card" data-i="' + idx + '">' +
    '<div class="card-top"><div>' +
      '<h3 class="job-title">' + esc(j.title) + '</h3>' +
      '<div class="job-sub"><a class="co-link" href="c/' + esc(j.slug) + '.html">' +
        esc(j.company) + '</a> · ' + esc(j.location) + '</div>' +
      '<div class="meta">' + esc(metaLine(j)) + '</div>' +
    '</div><div class="card-side">' + pill + apply + '</div></div></article>';
}

var filtered = [];

function applyFilters(syncHash){
  filtered = sortJobs(JOBS.filter(matches));
  state.shown = PAGE_SIZE;
  render();
  if(syncHash !== false) writeHash();
}

function render(){
  var box = document.getElementById('cards');
  var slice = filtered.slice(0, state.shown);
  var html = "";
  for(var i = 0; i < slice.length; i++) html += cardHtml(slice[i], i);
  box.innerHTML = html;
  var n = filtered.length;
  document.getElementById('empty').style.display = n ? 'none' : 'block';
  document.getElementById('more').style.display = (state.shown < n) ? '' : 'none';
}

function openModal(j){
  var skills = (j.matched_skills || []).map(function(s){
    return '<span>' + esc(s) + '</span>';
  }).join('');
  var apply = j.url ? '<a class="apply" href="' + esc(j.url) +
    '" target="_blank" rel="noopener noreferrer">Apply</a>' : '';
  document.getElementById('modal').innerHTML =
    '<button class="m-close" id="mclose" aria-label="Close">\u2715</button>' +
    '<h2>' + esc(j.title) + '</h2>' +
    '<div class="m-sub"><b><a class="co-link" href="c/' + esc(j.slug) + '.html">' +
      esc(j.company) + '</a></b> · ' + esc(j.location) + '</div>' +
    '<div class="m-meta">' +
      (j.is_new ? '<span class="tag tag-new">NEW</span>' : '') +
      '<span class="meta" style="margin-top:0">' + esc(metaLine(j)) + '</span></div>' +
    (skills ? '<div class="m-skills">' + skills + '</div>' : '') +
    '<div class="m-desc">' + esc(j.description || "No description provided.") + '</div>' +
    '<div class="m-foot">' + apply +
      (j.contact_email ? '<a class="note" href="mailto:' + esc(j.contact_email) + '">Recruiter: ' + esc(j.contact_email) + '</a>' : '<span class="note">Recruiter email is not listed on this posting.</span>') + '</div>';
  document.getElementById('overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
  document.getElementById('mclose').onclick = closeModal;
}
function closeModal(){
  document.getElementById('overlay').classList.remove('open');
  document.body.style.overflow = '';
}

/* ---- sidebar: company checkboxes ---- */
var coCounts = {};
var STARTUPS = new Set(["razorpay","cred","meesho","swiggy","zepto","phonepe","groww"," meesho","sharechat","postman","freshworks"," BrowserStack"].map(function(x){return x.trim().toLowerCase();}));
JOBS.forEach(function(j){ if(j.company) coCounts[j.company] = (coCounts[j.company]||0) + 1; });
function populateCities(){ var seen = {}, countries = {}; JOBS.forEach(function(j){ var location=j.location||""; location.split(/[;,]/).forEach(function(part){ var c=part.trim(); if(c && !/remote|india|multiple locations/i.test(c) && c.length<35) seen[c]=1; }); if(/remote/i.test(location)){ var remotePart=location.split(/remote/i).slice(1).join(" ").replace(/[()\[\]]/g," ").replace(/^\s*[-,:|]+\s*/,"").trim(); if(remotePart && remotePart.length<45) countries[remotePart]=1; } }); var sel=document.getElementById('city'); Object.keys(seen).sort().forEach(function(c){var o=document.createElement('option');o.value=c.toLowerCase();o.textContent=c;sel.appendChild(o);}); var rs=document.getElementById('remoteScope'); Object.keys(countries).sort().forEach(function(c){var o=document.createElement('option');o.value='country:'+c.toLowerCase();o.textContent='Remote: '+c;rs.appendChild(o);}); }

function renderCompanies(filter){
  var list = document.getElementById('coList');
  var q = (filter || "").toLowerCase();
  var html = "";
  COMPANIES.forEach(function(c){
    if(q && c.toLowerCase().indexOf(q) < 0) return;
    var checked = !state.companies || state.companies.has(c);
    html += '<label class="co-item"><input type="checkbox" data-co="' + esc(c) + '"' +
      (checked ? ' checked' : '') + '><span>' + esc(c) + '</span>' +
      '<span class="n">' + (coCounts[c]||0) + '</span></label>';
  });
  list.innerHTML = html || '<div class="posted" style="padding:8px">No companies match.</div>';
}

/* ---- wire up ---- */
function setPill(groupId, name, val){
  document.querySelectorAll('#' + groupId + ' input[name="' + name + '"]').forEach(function(r){
    r.checked = (r.value === val);
  });
}
function pillVal(groupId, name){
  var r = document.querySelector('#' + groupId + ' input[name="' + name + '"]:checked');
  return r ? r.value : null;
}

function syncUIFromState(){
  document.getElementById('q').value = state.q;
  document.getElementById('loc').value = state.loc;
  document.getElementById('remote').checked = state.remote;
  document.getElementById('city').value = state.city; document.getElementById('remoteScope').value = state.remoteScope; document.getElementById('startups').checked = state.startups;
  document.getElementById('roleType').value = state.roleType;
  document.getElementById('sort').value = state.sort;
  setPill('expPills', 'exp', state.exp);
  setPill('postedPills', 'posted', state.posted);
  renderCompanies(document.getElementById('coSearch').value);
}

function clearAll(){
  state.q = ""; state.exp = DEFAULT_EXP; state.companies = null;
  state.loc = ""; state.posted = "any";
  state.remote = false; state.city = ""; state.remoteScope = "any"; state.startups = false; state.roleType = "all"; state.sort = "new";
  document.getElementById('coSearch').value = "";
  syncUIFromState();
  applyFilters();
}

var qTimer = null;
document.getElementById('q').addEventListener('input', function(e){
  clearTimeout(qTimer);
  qTimer = setTimeout(function(){
    state.q = e.target.value.trim().toLowerCase();
    applyFilters();
  }, 160);
});
document.getElementById('loc').addEventListener('input', function(e){
  clearTimeout(qTimer);
  qTimer = setTimeout(function(){
    state.loc = e.target.value.trim().toLowerCase();
    applyFilters();
  }, 160);
});
document.getElementById('expPills').addEventListener('change', function(){
  state.exp = pillVal('expPills', 'exp') || 'any';
  applyFilters();
});
document.getElementById('postedPills').addEventListener('change', function(){
  state.posted = pillVal('postedPills', 'posted') || 'any';
  applyFilters();
});
document.getElementById('remote').addEventListener('change', function(e){
  state.remote = e.target.checked;
  applyFilters();
});
document.getElementById('city').addEventListener('change', function(e){state.city=e.target.value;applyFilters();});
document.getElementById('roleType').addEventListener('change', function(e){state.roleType=e.target.value;applyFilters();});
document.getElementById('remoteScope').addEventListener('change', function(e){state.remoteScope=e.target.value;applyFilters();});
document.getElementById('startups').addEventListener('change', function(e){state.startups=e.target.checked;applyFilters();});
document.getElementById('sort').addEventListener('change', function(e){
  state.sort = e.target.value;
  applyFilters();
});
document.getElementById('coSearch').addEventListener('input', function(e){
  renderCompanies(e.target.value);
});
document.getElementById('coList').addEventListener('change', function(e){
  var cb = e.target.closest('input[data-co]');
  if(!cb) return;
  var set = state.companies;
  if(!set){ set = new Set(COMPANIES); state.companies = set; }
  if(cb.checked) set.add(cb.getAttribute('data-co'));
  else set.delete(cb.getAttribute('data-co'));
  if(set.size === COMPANIES.length) state.companies = null; // all = default
  applyFilters();
});
document.getElementById('clearAll').addEventListener('click', clearAll);
document.getElementById('emptyClear').addEventListener('click', clearAll);
document.getElementById('more').addEventListener('click', function(){
  state.shown += PAGE_SIZE;
  render();
  writeHash();
});

/* card -> modal (delegate; Apply links unaffected) */
document.getElementById('cards').addEventListener('click', function(e){
  if(e.target.closest('a')) return;
  var card = e.target.closest('.card');
  if(!card) return;
  var j = filtered[parseInt(card.getAttribute('data-i'), 10)];
  if(j) openModal(j);
});
document.getElementById('overlay').addEventListener('click', function(e){
  if(e.target === this) closeModal();
});
document.addEventListener('keydown', function(e){
  if(e.key === 'Escape') closeModal();
});

/* mobile drawer */
document.getElementById('filterToggle').addEventListener('click', function(){
  document.body.classList.add('drawer-open');
});
document.getElementById('drawerBg').addEventListener('click', function(){
  document.body.classList.remove('drawer-open');
});

/* star banner: dismiss persists in localStorage */
(function(){
  var KEY = "jb_star_hide";
  var banner = document.getElementById('starBanner');
  try {
    if (localStorage.getItem(KEY) === "1") banner.style.display = "none";
  } catch (e) {}
  document.getElementById('starDismiss').addEventListener('click', function(){
    banner.style.display = "none";
    try { localStorage.setItem(KEY, "1"); } catch (e) {}
  });
})();

/* init */
readHash();
populateCities();
syncUIFromState();
applyFilters(false);
writeHash();
window.setTimeout(function(){location.reload();}, 120*60*1000);
})();
</script>
</body>
</html>
"""
