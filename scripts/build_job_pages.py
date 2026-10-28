#!/usr/bin/env python3
"""Build a static, Google-readable page for every live job.

Runs on a schedule in GitHub Actions (.github/workflows/build-job-pages.yml).
Reads live jobs from the same Google Apps Script the website uses, then:
  - writes one page per job:  job-<title>-<location>-<job id>.html
  - removes pages for jobs that are no longer live
  - writes job-pages.json (job id -> page) so job tiles link to the static pages
  - adds the jobs as plain links inside the Jobs page and homepage (for search engines)
  - refreshes the job entries in sitemap.xml

Usage:  python3 scripts/build_job_pages.py            (fetch live jobs)
        python3 scripts/build_job_pages.py jobs.json  (use a saved API response, for testing)
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://thedoctornetwork.com.au"
MANIFEST = "job-pages.json"
TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=10))).date().isoformat()


def path(*p):
    return os.path.join(ROOT, *p)


def read(p):
    with open(path(p), encoding="utf-8") as f:
        return f.read()


def write(p, text):
    with open(path(p), "w", encoding="utf-8") as f:
        f.write(text)


def e(v):
    return html.escape(str(v or ""), quote=True)


def para(v):
    return e(v).replace("\n", "<br>")


def slugify(v):
    return re.sub(r"[^a-z0-9]+", "-", str(v or "").lower()).strip("-")


def iso(v):
    """'14/09/2026' or '2026-09-14' -> '2026-09-14'; anything else -> ''."""
    s = str(v or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        try:
            return dt.date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        except ValueError:
            return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    return m.group(0) if m else ""


def nice(v):
    s = str(v or "").strip()
    d = iso(s)
    if d and re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", s):
        y, mth, day = d.split("-")
        return f"{int(day)} {dt.date(2000, int(mth), 1).strftime('%b')} {y}"
    return s


def date_range(j):
    a, b = nice(j.get("startDate")), nice(j.get("endDate"))
    if a and not iso(j.get("startDate")) and not b:
        return f"Start: {a}"
    if a and b:
        return f"{a} – {b}"
    if a:
        return f"From {a}"
    if b:
        return f"Until {b}"
    return ""


def fetch_jobs():
    if len(sys.argv) > 1:
        data = json.loads(read(sys.argv[1]) if not os.path.isabs(sys.argv[1]) else open(sys.argv[1]).read())
    else:
        url = re.search(r'APPS_SCRIPT_URL:\s*"([^"]+)"', read("assets/config.js")).group(1)
        req = urllib.request.Request(url + "?action=jobs", headers={"User-Agent": "TDN-job-page-builder"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise SystemExit("Jobs feed returned an error, leaving pages unchanged: %s" % data.get("error"))
    return [j for j in data.get("jobs", []) if str(j.get("jobId", "")).strip()]


def page_name(j):
    parts = [j.get("positionTitle"), j.get("location"), j.get("jobId")]
    return "job-" + slugify("-".join(str(p) for p in parts if p)) + ".html"


def place(j):
    loc, st = str(j.get("location") or "").strip(), str(j.get("state") or "").strip()
    if loc and st and st.lower() in loc.lower().split():
        return loc
    return ", ".join(x for x in [loc, st] if x)


def employment_types(t):
    t = str(t or "").lower()
    out = []
    if "perm" in t or "full" in t:
        out.append("FULL_TIME")
    if "part" in t:
        out.append("PART_TIME")
    if any(k in t for k in ("locum", "temp", "contract")):
        out += ["TEMPORARY", "CONTRACTOR"]
    return out


def salary(v):
    s = str(v or "").lower().replace(",", "")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    if not nums:
        return None
    n = nums[0]
    if "hour" in s or "/hr" in s or re.search(r"\bph\b", s):
        unit = "HOUR"
    elif "day" in s:
        unit = "DAY"
    elif "week" in s:
        unit = "WEEK"
    elif "annual" in s or "year" in s or "pa" in s.split() or n > 10000:
        unit = "YEAR"
    else:
        return None
    value = {"@type": "QuantitativeValue", "unitText": unit}
    if len(nums) >= 2 and nums[1] > nums[0]:
        value.update(minValue=nums[0], maxValue=nums[1])
    else:
        value["value"] = n
    return {"@type": "MonetaryAmount", "currency": "AUD", "value": value}


def is_telehealth(j):
    text = " ".join(str(j.get(k) or "") for k in ("location", "positionTitle", "state")).lower()
    return "telehealth" in text or "tele-health" in text


def valid_through(j):
    """When the listing expires for Google.

    Live jobs are rebuilt every 3 hours and removed once unpublished, so the date just needs to
    stay ahead of today while a job is live: at least 30 days out, rounded up to the 1st of the
    next month (so pages only change monthly), or the placement end date if that is later.
    """
    today = dt.date.fromisoformat(TODAY)
    ahead = today + dt.timedelta(days=30)
    rolling = dt.date(ahead.year + (ahead.month == 12), ahead.month % 12 + 1, 1)
    end = iso(j.get("endDate"))
    return max(rolling.isoformat(), end) if end else rolling.isoformat()


def job_schema(j, url, posted):
    desc = "".join(
        f"<p><strong>{lbl}</strong></p><p>{para(j.get(k))}</p>" if lbl else f"<p>{para(j.get(k))}</p>"
        for lbl, k in [("", "shortSummary"), ("Overview", "overview"), ("Role details", "roleDetails"),
                       ("Why consider it", "whyConsiderIt"), ("Location", "locationInformation"),
                       ("Dates", "_dates"), ("Rate / salary", "salaryRate")]
        if j.get(k)
    )
    if not (j.get("shortSummary") or j.get("overview")):
        where = place(j)
        desc = (f"<p>{e(j.get('employmentType'))} {e(j.get('positionTitle'))} role"
                + (f" in {e(where)}" if where else "") + ", recruited by The Doctor Network. "
                "Enquire for full details in a confidential conversation.</p>") + desc
    org = j.get("organisationDisplay")
    s = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": j.get("positionTitle", ""),
        "description": desc,
        "datePosted": posted,
        "identifier": {"@type": "PropertyValue", "name": "The Doctor Network", "value": j.get("jobId", "")},
        "hiringOrganization": {"@type": "Organization",
                               "name": org if org and org != "Confidential" else "The Doctor Network",
                               "sameAs": SITE + "/", "logo": SITE + "/assets/logo-square.png"},
        "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress",
                                                      "addressLocality": j.get("location", ""),
                                                      "addressRegion": j.get("state", ""),
                                                      "addressCountry": "AU"}},
        "directApply": True,
        "url": url,
    }
    if is_telehealth(j):
        # remote role: Google's way to mark work done from anywhere in Australia
        s["jobLocationType"] = "TELECOMMUTE"
        s["applicantLocationRequirements"] = {"@type": "Country", "name": "Australia"}
        if not j.get("state"):
            del s["jobLocation"]
    if employment_types(j.get("employmentType")):
        s["employmentType"] = employment_types(j.get("employmentType"))
    if sub(j) or j.get("specialty"):
        s["occupationalCategory"] = sub(j) or j["specialty"]
    if salary(j.get("salaryRate")):
        s["baseSalary"] = salary(j.get("salaryRate"))
    if j.get("startDate") and iso(j.get("startDate")):
        s["jobStartDate"] = iso(j.get("startDate"))
    s["validThrough"] = valid_through(j) + "T23:59:59+10:00"
    return s


def set_head(h, title, desc, url, og_type="article"):
    h = re.sub(r"<title>.*?</title>", f"<title>{e(title)}</title>", h, count=1, flags=re.S)
    h = re.sub(r'<meta name="robots"[^>]*>', "", h)
    h = re.sub(r'<link rel="canonical"[^>]*>', "", h)
    for pat in [r'<meta name="description"[^>]*>', r'<meta property="og:[a-z_:]+"[^>]*>', r'<meta name="twitter:[a-z]+"[^>]*>']:
        h = re.sub(pat, "", h)
    tags = (f'<meta name="description" content="{e(desc)}">'
            f'<link rel="canonical" href="{url}">'
            f'<meta property="og:type" content="{og_type}"><meta property="og:site_name" content="The Doctor Network">'
            f'<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">'
            f'<meta property="og:url" content="{url}"><meta property="og:image" content="{SITE}/assets/og-image.jpg">'
            f'<meta name="twitter:card" content="summary_large_image">')
    return h.replace("</title>", "</title>" + tags, 1)


def sub(j):
    return (j.get("subSpecialty") or j.get("subspecialty") or "").strip()


def build_page(template, j, name, posted):
    url = f"{SITE}/{name}"
    where = place(j)
    kind = f"{j.get('employmentType')} job" if j.get("employmentType") else "Job"
    title = f"{j.get('positionTitle') or 'Medical job'} – {kind}" + (f" in {where}" if where else "")
    page_title = f"{title} | The Doctor Network"
    desc = (j.get("shortSummary") or "").strip()
    desc = (f"{desc}. " if desc and not desc.endswith(".") else (desc + " " if desc else "")) + \
        f"{j.get('employmentType', '')} {sub(j) or j.get('specialty', '') or 'medical'} role in {where}. Enquire confidentially with The Doctor Network."
    desc = re.sub(r"\s+", " ", desc).strip()[:158]

    j = dict(j, _dates=date_range(j))
    pills = "".join(f'<span class="pill">{e(x)}</span>' for x in [j.get("employmentType"), j.get("sector"), j.get("specialty"), sub(j)] if x)
    facts = [("Location", where), ("Dates", j["_dates"]), ("Rate / salary", j.get("salaryRate")),
             ("Organisation", j.get("organisationDisplay") if j.get("organisationDisplay") not in ("", "Confidential", None) else "")]
    facts_html = "".join(f"<li><strong>{lbl}:</strong> {e(v)}</li>" for lbl, v in facts if v)
    body = []
    if facts_html:
        body.append(f'<ul class="job-facts">{facts_html}</ul>')
    for lbl, k, tag in [("Overview", "overview", "h2"), ("Role details", "roleDetails", "h3"),
                        ("Why consider this role", "whyConsiderIt", "h3"), ("Location", "locationInformation", "h3")]:
        if j.get(k):
            body.append(f"<{tag}>{lbl}</{tag}><p>{para(j.get(k))}</p>")
    if len(body) <= 1:
        body.append("<p>Further details are available in a confidential conversation. Send an enquiry and we'll be in touch.</p>")
    body.append('<p class="job-back"><a class="text-link" href="opportunities.html">← See all current jobs</a></p>')

    main = (f'<section class="page-hero"><div class="shell"><div class="kicker">{e(sub(j) or j.get("specialty") or "Medical")} job · {e(j.get("state") or "Australia")}</div>'
            f'<h1>{e(j.get("positionTitle"))}</h1><p>{e(j.get("shortSummary"))}</p><div class="pills">{pills}</div></div></section>'
            f'<section class="section"><div class="shell content-grid"><article class="job-body">{"".join(body)}</article><aside>FORM</aside></div></section>')

    form = re.search(r'<form class="form-card demo-form" data-form-type="job_enquiry">.*?</form>', template, re.S).group(0)
    form = form.replace('id="enquiryJobId">', f'value="{e(j.get("jobId"))}">').replace('id="enquiryJobTitle">', f'value="{e(j.get("positionTitle"))}">')
    main = main.replace("FORM", form)

    h = set_head(template, page_title, desc, url)
    h = re.sub(r"<main>.*?</main>", lambda m: "<main>" + main + "</main>", h, count=1, flags=re.S)
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Jobs", "item": SITE + "/opportunities.html"},
        {"@type": "ListItem", "position": 3, "name": j.get("positionTitle", ""), "item": url}]}
    ld = ('<script type="application/ld+json">' + json.dumps(job_schema(j, url, posted), ensure_ascii=False) + "</script>"
          '<script type="application/ld+json">' + json.dumps(crumbs, ensure_ascii=False) + "</script>")
    return h.replace("</head>", ld + "</head>", 1)


def static_card(j, name):
    meta = " · ".join(x for x in [sub(j) or j.get("specialty"), j.get("location")] if x)
    extra = "".join(f'<div class="{c}">{e(v)}</div>' for c, v in [("job-dates", date_range(j)), ("job-rate", j.get("salaryRate"))] if v)
    pills = "".join(f'<span class="pill">{e(x)}</span>' for x in [j.get("employmentType"), j.get("sector")] if x)
    return (f'<article class="job-card"><div class="pills">{pills}</div><h3>{e(j.get("positionTitle"))}</h3>'
            f'<p>{e(j.get("shortSummary"))}</p><div class="job-meta">{e(meta)}{extra}</div>'
            f'<a class="text-link" href="{name}">View job →</a></article>')


def replace_between(text, start, end, inner):
    if start not in text:
        return text
    a = text.index(start) + len(start)
    b = text.index(end, a)
    return text[:a] + inner + text[b:]


def main():
    jobs = fetch_jobs()
    try:
        manifest = json.loads(read(MANIFEST))
    except (FileNotFoundError, ValueError):
        manifest = {}
    template = read("opportunity.html")

    new_manifest, cards, written, seen = {}, [], set(), {}
    for j in jobs:
        jid = str(j["jobId"]).strip()
        if jid in seen:
            print(f"WARNING: Job ID {jid} is used twice ({seen[jid]} and {j.get('positionTitle')} – {j.get('location')}). "
                  "Give each row its own Job ID in the sheet.")
        seen[jid] = f"{j.get('positionTitle')} – {j.get('location')}"
        name = page_name(j)
        first_seen = (manifest.get(jid) or {}).get("firstPublished") or TODAY
        posted = iso(j.get("dateAdded")) or first_seen
        write(name, build_page(template, j, name, posted))
        written.add(name)
        new_manifest[jid] = {"page": name, "title": j.get("positionTitle", ""), "firstPublished": first_seen,
                             "lastmod": iso(j.get("lastUpdated")) or posted}
        cards.append(static_card(j, name))

    # remove pages for jobs that are no longer live (or were renamed); every job-*.html page is builder-owned
    for f in sorted(os.listdir(ROOT)):
        if re.match(r"^job-[a-z0-9-]+\.html$", f) and f not in written:
            os.remove(path(f))
            print("removed", f)

    write(MANIFEST, json.dumps(new_manifest, indent=1, sort_keys=True) + "\n")

    # plain links on the Jobs page and homepage, replaced by the live tiles once the page loads
    write("opportunities.html", replace_between(read("opportunities.html"), "<!--JOBS:START-->", "<!--JOBS:END-->", "".join(cards)))
    write("index.html", replace_between(read("index.html"), "<!--JOBS:START-->", "<!--JOBS:END-->", "".join(cards[:3])))

    # sitemap job entries
    sm = read("sitemap.xml")
    entries = "".join(f"<url><loc>{SITE}/{v['page']}</loc><lastmod>{v['lastmod']}</lastmod><priority>0.7</priority></url>\n"
                      for v in new_manifest.values())
    if "<!--JOBS:START-->" not in sm:
        sm = sm.replace("</urlset>", "<!--JOBS:START--><!--JOBS:END-->\n</urlset>")
    write("sitemap.xml", replace_between(sm, "<!--JOBS:START-->", "<!--JOBS:END-->", "\n" + entries))
    print(f"built {len(new_manifest)} job page(s)")


if __name__ == "__main__":
    main()
