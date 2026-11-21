"""
Mode 4: Protect my brand.

Finds things that use an organisation's name but don't match its official records:
helpline numbers, job/internship posts, look-alike websites, Play Store apps and
public scam reports. Matching against official records is rule-based. Nothing is
called "fake": findings are "suspected", each with the evidence and a ready report text.
"""
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from cache import get_official, list_allowed, mark_seen, save_official
from config import EXTRACT_MAX_SITES
from evidence import EvidenceCollector
from serp_client import extract_page, google_search, jobs_search, maps_search, news as serp_news, play_search

PHONE_RE = re.compile(
    r"(?:\+91[\s\-]?|\b0)?(?:1800[\s\-]?\d{3}[\s\-]?\d{4}|1860[\s\-]?\d{3}[\s\-]?\d{4}|[6-9]\d{4}[\s\-]?\d{5}|\d{2,4}[\s\-]\d{6,8})\b"
)
FEE_RE = re.compile(r"registration fee|security deposit|training fee|processing fee|refundable deposit|pay\s*(?:rs\.?|₹|inr)\s*\d", re.I)
SENSITIVE_RE = re.compile(r"password|otp|one[- ]time password|card number|cvv|upi pin|pay now|net ?banking|aadhaar|pan card", re.I)
FREE_MAIL_RE = re.compile(r"[\w.+-]+@(?:gmail|yahoo|outlook|hotmail|rediffmail)\.com", re.I)
PLATFORMS = {
    "google.com", "play.google.com", "maps.google.com", "youtube.com", "facebook.com", "instagram.com",
    "x.com", "twitter.com", "linkedin.com", "wikipedia.org", "reddit.com", "quora.com", "justdial.com",
    "naukri.com", "indeed.com", "glassdoor.com", "glassdoor.co.in", "internshala.com", "foundit.in",
    "apna.co", "shine.com", "timesjobs.com", "ambitionbox.com", "mouthshut.com", "consumercomplaints.in",
    "jobrapido.com", "jooble.org", "careerjet.co.in", "workindia.in", "hirist.tech", "instahyre.com", "monsterindia.com",
}


def norm_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("91") and len(d) == 12:
        d = d[2:]
    if d.startswith("0") and len(d) == 11 and not d.startswith("01800"):
        d = d[1:]
    return d


def domain_of(url: str) -> str:
    try:
        host = urlparse(url if "//" in url else f"https://{url}").netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _is_official_domain(dom: str, official: List[str]) -> bool:
    return any(dom == o or dom.endswith("." + o) for o in official)


def _is_platform(dom: str) -> bool:
    return any(dom == p or dom.endswith("." + p) for p in PLATFORMS)


def _emit(cb, step, msg, pct):
    if cb:
        try:
            cb(step, msg, pct)
        except Exception:
            pass


REPORT_CHANNELS = {
    "helpline": [
        {"channel": "Google Maps / Search", "how": "Open the listing → 'Suggest an edit' → 'Remove this place' (or report the number), and ask Google Business Profile support to remove it."},
        {"channel": "Sanchar Saathi Chakshu", "how": "sancharsaathi.gov.in → Chakshu → report the number as impersonation."},
    ],
    "job_post": [
        {"channel": "Job site", "how": "Use the site's 'Report job' option and point to your official careers page."},
        {"channel": "cybercrime.gov.in", "how": "Report if money was taken; victims can also call 1930."},
    ],
    "lookalike_site": [
        {"channel": "Domain registrar / host", "how": "Send an abuse report (WHOIS lists the registrar's abuse contact)."},
        {"channel": "Google Safe Browsing", "how": "safebrowsing.google.com/safebrowsing/report_phish/"},
    ],
    "fake_app": [
        {"channel": "Google Play", "how": "Open the app listing → ⋮ → 'Flag as inappropriate' → impersonation; or Play's IP/impersonation complaint form."},
    ],
    "scam_report": [
        {"channel": "Public notice", "how": "Publish your verified official channels and link the report so users can check."},
    ],
}


def _report_text(brand: str, f: Dict[str, Any]) -> str:
    return (
        f"Subject: Suspected impersonation of {brand}\n\n"
        f"We are {brand}. The following appears to use our name but does not match our official records:\n"
        f"- Type: {f['type'].replace('_', ' ')}\n- Item: {f['value']}\n- Where found: {f.get('url') or 'see link'}\n"
        f"- Why we believe it is not ours: {f['why']}\n\n"
        f"Please review and remove it. Our official channels are listed on our website."
    )


def mode4_protect(
    query: str,
    official: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str, str, int], None]] = None,
    record_seen: bool = True,
) -> Dict[str, Any]:
    """record_seen=False (used by prewarm) leaves the 'seen' history untouched, so a later live scan still alerts."""
    from pipelines import CreditTracker  # local import avoids a cycle

    brand = query.strip()
    if re.fullmatch(r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+/?", brand.lower()):
        typed_domain = domain_of(brand)
        official = dict(official or {})
        official["domains"] = list(dict.fromkeys((official.get("domains") or []) + [typed_domain]))
        brand = typed_domain.split(".")[0]
    if official:
        save_official(brand, official)  # setup is remembered for repeat scans and the public page
    else:
        saved = get_official(brand)
        official = saved["official"] if saved else {}
    off_domains = [domain_of(d) for d in official.get("domains", []) if d]
    off_phones = {norm_phone(p) for p in official.get("phones", []) if norm_phone(p)}
    off_apps = {a.strip() for a in official.get("app_ids", []) if a and a.strip()}
    token = re.sub(r"[^a-z0-9]", "", brand.lower())

    tracker = CreditTracker()
    warnings: List[str] = []
    if not off_domains:
        warnings.append("No official website given: look-alike detection is limited.")
    if not off_phones:
        warnings.append("No official helpline numbers given: numbers found are listed for you to confirm, not flagged.")
    if not off_apps:
        warnings.append("No official app ID given: apps using your name are listed for you to confirm, not flagged.")

    _emit(progress_callback, "search", f"Searching for numbers, jobs, apps and sites using '{brand}'", 20)
    with ThreadPoolExecutor(max_workers=6) as ex:
        f1 = ex.submit(google_search, f"{brand} customer care number", tracker, "google_helpline")
        f2 = ex.submit(maps_search, f"{brand} customer care", tracker)
        f3 = ex.submit(jobs_search, f"{brand} jobs", tracker)
        f4 = ex.submit(play_search, brand, tracker)
        f5 = ex.submit(serp_news, f"{brand} scam fraud", tracker)
        f6 = ex.submit(google_search, f"{brand} official website login", tracker, "google_lookalike")
        helpline_res, w1 = f1.result()
        maps_res, w2 = f2.result()
        jobs_res, w3 = f3.result()
        apps_res, w4 = f4.result()
        scam_res, w5 = f5.result()
        site_res, w6 = f6.result()
    for w in (w1, w2, w3, w4, w5, w6):
        if w and w not in warnings:
            warnings.append(w)

    _emit(progress_callback, "evidence", "Recording evidence", 55)
    col = EvidenceCollector(max_items=200)
    col.add_generic(helpline_res, source="google_search", entity="Google Search", priority=90)
    col.add_generic(site_res, source="google_search", entity="Google Search", priority=85)
    col.add_generic(
        [{"title": m.get("title"), "snippet": f"{m.get('title', '')} · phone {m.get('phone', '')} · {m.get('address', '')}",
          "link": m.get("link") or m.get("website") or ""} for m in maps_res],
        source="google_maps", entity="Google Maps", priority=95)
    col.add_generic(
        [{"title": j.get("title"), "snippet": f"{j.get('company_name', '')} · {j.get('via', '')} · {j.get('description', '')}",
          "link": j.get("apply_link") or j.get("share_link") or ""} for j in jobs_res],
        source="google_jobs", entity="Google Jobs", priority=88)
    col.add_news_items(scam_res, entity="Google News")
    evidence_map, _ = col.build()
    by_text = {}
    for eid, ev in evidence_map.items():
        by_text.setdefault((ev["source"], ev.get("url") or "", ev.get("title") or ""), eid)

    def eid_for(source, url, title):
        return by_text.get((source, url or "", title or ""))

    _emit(progress_callback, "matching", "Comparing against your official records", 75)
    findings: List[Dict[str, Any]] = []
    seen = set()

    def add(ftype, value, title, why, severity, url, eids):
        key = (ftype, value)
        if key in seen:
            return
        seen.add(key)
        f = {"id": f"fd_{len(findings) + 1}", "type": ftype, "severity": severity, "status": "suspected",
             "title": title, "value": value, "why": why, "url": url,
             "evidence_ids": [e for e in eids if e], "report_to": REPORT_CHANNELS.get(ftype, [])}
        f["report_text"] = _report_text(brand, f)
        findings.append(f)

    # 1. Helpline numbers (search snippets + Maps listings)
    for r in helpline_res:
        for m in PHONE_RE.findall(f"{r.get('title', '')} {r.get('snippet', '')}"):
            num = norm_phone(m)
            if len(num) < 10 or num in off_phones:
                continue
            dom = domain_of(r.get("link", ""))
            if _is_official_domain(dom, off_domains):
                continue  # shown on your own site
            sev = "high" if off_phones else "info"
            why = ("Not on your official helpline list" if off_phones
                   else "Shown under your name; add your official numbers to confirm")
            add("helpline", m.strip(), f"Number shown for '{brand} customer care' on {dom or 'search'}", why, sev,
                r.get("link"), [eid_for("google_search", r.get("link"), r.get("title"))])
    for m in maps_res:
        num = norm_phone(m.get("phone", ""))
        if len(num) < 10 or num in off_phones:
            continue
        if token and token not in re.sub(r"[^a-z0-9]", "", (m.get("title") or "").lower()):
            continue
        sev = "high" if off_phones else "info"
        add("helpline", m.get("phone"), f"Maps listing '{m.get('title')}' uses your name", 
            "Maps listing with your name and a number not on your official list" if off_phones
            else "Maps listing with your name; add your official numbers to confirm", sev,
            m.get("link") or m.get("website"), [eid_for("google_maps", m.get("link") or m.get("website") or "", m.get("title"))])

    # 2. Job / internship posts
    for j in jobs_res:
        if token and token not in re.sub(r"[^a-z0-9]", "", (j.get("company_name") or "").lower()):
            continue
        desc = j.get("description") or ""
        reasons = []
        if FEE_RE.search(desc):
            reasons.append("asks applicants for a fee or deposit")
        mail = FREE_MAIL_RE.search(desc)
        if mail:
            reasons.append(f"asks applicants to write to a free email ({mail.group(0)})")
        apply_dom = domain_of(j.get("apply_link") or "")
        if off_domains and apply_dom and not _is_official_domain(apply_dom, off_domains) and not _is_platform(apply_dom):
            reasons.append(f"applications go to {apply_dom}, not your website or a known job site")
        if reasons:
            red_flag = bool(FEE_RE.search(desc) or mail)
            add("job_post", j.get("title") or "Job post", f"Job post '{j.get('title')}' uses your name",
                "; ".join(reasons).capitalize() + ("" if red_flag else " (often a job aggregator: confirm it is authorised)"),
                "high" if red_flag else "info",
                j.get("apply_link"), [eid_for("google_jobs", j.get("apply_link") or j.get("share_link") or "", j.get("title"))])

    # 3. Look-alike websites (any result domain containing the brand that isn't yours)
    if token and len(token) >= 4:
        for r in helpline_res + site_res:
            dom = domain_of(r.get("link", ""))
            flat = re.sub(r"[^a-z0-9]", "", dom)
            if dom and token in flat and not _is_official_domain(dom, off_domains) and not _is_platform(dom):
                add("lookalike_site", dom, f"Website '{dom}' contains your name",
                    "Domain contains your brand name but isn't on your official list" if off_domains
                    else "Domain contains your brand name; add your official website to confirm",
                    "high" if off_domains else "info", r.get("link"),
                    [eid_for("google_search", r.get("link"), r.get("title"))])

    # 3b. Read up to EXTRACT_MAX_SITES flagged sites: do they ask for logins, OTPs or payments?
    for f in [f for f in findings if f["type"] == "lookalike_site" and f.get("url")][:EXTRACT_MAX_SITES]:
        text, w = extract_page(f["url"], tracker=tracker)
        if w and w not in warnings:
            warnings.append(w)
        hits = sorted({m.group(0).lower() for m in SENSITIVE_RE.finditer(text or "")})
        if hits:
            f["why"] += f"; the page asks for: {', '.join(hits[:5])}"
            f["severity"] = "high"
            f["report_text"] = _report_text(brand, f)
        elif text:
            f["why"] += "; page read, no login or payment fields found"

    # 4. Play Store apps using the name
    for a in apps_res:
        flat_title = re.sub(r"[^a-z0-9]", "", (a.get("title") or "").lower())
        if not token or token not in flat_title or a.get("product_id") in off_apps:
            continue
        dev = a.get("developer") or "unknown developer"
        add("fake_app", a.get("product_id"), f"App '{a.get('title')}' by {dev}",
            f"Uses your name but isn't your official app ({', '.join(sorted(off_apps))})" if off_apps
            else "Uses your name; add your official app ID to confirm",
            "medium" if off_apps else "info", a.get("link"), [])

    # 5. Public scam reports mentioning the brand
    for eid, ev in evidence_map.items():
        if ev["source"] == "google_news" and re.search(r"scam|fraud|fake|cheat|duped", ev["text"], re.I) \
                and token in re.sub(r"[^a-z0-9]", "", ev["text"].lower()):
            add("scam_report", ev.get("title") or ev["text"][:80], "News report of a scam using your name",
                "Public report linking your name to a scam", "medium", ev.get("url"), [eid])

    # Allowlist: items the brand marked as genuine (e.g. a franchisee's number) are hidden
    allowed = {(a["type"], str(a["value"])) for a in list_allowed(brand)}
    allowed_count = sum(1 for f in findings if (f["type"], str(f["value"])) in allowed)
    findings = [f for f in findings if (f["type"], str(f["value"])) not in allowed]
    keys = [(f["type"], str(f["value"])) for f in findings]
    new_keys = mark_seen(brand, keys) if record_seen else set(keys)
    for f in findings:
        f["is_new"] = (f["type"], str(f["value"])) in new_keys

    order = {"high": 0, "medium": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    for i, f in enumerate(findings, start=1):
        f["id"] = f"fd_{i}"

    types = [("helpline", "Suspected helpline numbers"), ("job_post", "Suspicious job posts"),
             ("lookalike_site", "Look-alike websites"), ("fake_app", "Apps using your name"),
             ("scam_report", "Public scam reports")]
    breakdown = []
    for t, label in types:
        fs = [f for f in findings if f["type"] == t]
        flagged = [f for f in fs if f["severity"] != "info"]
        breakdown.append({"factor": label, "score": len(flagged), "max": max(len(fs), 1),
                          "explanation": f"{len(flagged)} flagged, {len(fs) - len(flagged)} to confirm",
                          "evidence_ids": [e for f in fs for e in f["evidence_ids"]][:5]})
    flagged_total = sum(1 for f in findings if f["severity"] != "info")
    report = {
        "scan_id": uuid.uuid4().hex[:8],
        "mode": 4,
        "query": brand,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": {"broad": brand, "specific": [f"{brand} customer care number", f"{brand} jobs", f"{brand} scam fraud"],
                     "category": "Brand protection"},
        "credits": tracker.to_dict(),
        "verdict": {"kind": "protection", "label": None, "score": None,
                    "headline": f"{flagged_total} suspected impersonation(s) and {len(findings) - flagged_total} item(s) to confirm for {brand}",
                    "breakdown": breakdown},
        "regions": [],
        "trend": None,
        "timeline": None,
        "competitors": [],
        "clusters": [],
        "opportunities": [],
        "news": [],
        "findings": findings,
        "official": {"domains": off_domains, "phones": sorted(off_phones), "app_ids": sorted(off_apps)},
        "allowed_count": allowed_count,
        "new_count": sum(1 for f in findings if f.get("is_new")),
        "evidence": evidence_map,
        "warnings": warnings,
    }
    _emit(progress_callback, "done", f"Protection scan complete: {len(findings)} item(s)", 100)
    return report
