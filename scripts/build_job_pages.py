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
    more = []
    if is_psych(j) and str(j.get("state") or "").upper() in {c for c, _, _, _ in STATES}:
        st = str(j["state"]).upper()
        more.append(f'<a class="text-link" href="{state_page(st)}">More psychiatry jobs in {st} →</a>')
    for key, fname, label, _ in SUBSPECIALTIES:
        if sub(j) == key:
            more.append(f'<a class="text-link" href="{fname}">More {label.lower()} →</a>')
    if more:
        body.append('<p class="job-more">' + "<br>".join(more) + "</p>")
    body.append('<p class="job-back"><a class="text-link" href="opportunities.html">← See all current jobs</a></p>')

    main = (f'<section class="page-hero"><div class="shell"><div class="reveal"><div class="kicker">{e(sub(j) or j.get("specialty") or "Medical")} job · {e(j.get("state") or "Australia")}</div>'
            f'<h1>{e(j.get("positionTitle"))}</h1><p>{e(j.get("shortSummary"))}</p><div class="pills">{pills}</div>'
            f'<div class="hero-actions"><a class="button coral" href="#enquire">Enquire about this role →</a></div></div></div></section>'
            f'<section class="section"><div class="shell content-grid"><article class="job-body reveal">{"".join(body)}</article><aside id="enquire" class="reveal delay-1">FORM</aside></div></section>')

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


# ---------------------------------------------------------------------------
# Hub pages: one page per state, per psychiatry sub-specialty, plus a pay-rates
# page, all rebuilt from the live jobs on every run.
# ---------------------------------------------------------------------------

STATES = [
    ("NSW", "New South Wales", "nsw",
     "Locum psychiatry work in New South Wales ranges from busy Sydney metro services to regional hubs like the Hunter, Illawarra, Central West and Northern Rivers, plus rural and remote sites in the far west. Regional roles often include travel and accommodation."),
    ("VIC", "Victoria", "vic",
     "Victorian locum psychiatry roles span Melbourne's metro mental health services and regional centres such as Geelong, Ballarat, Bendigo, Gippsland and the north-east. Many regional placements include travel and accommodation."),
    ("QLD", "Queensland", "qld",
     "Queensland has a steady flow of locum psychiatry work, from Brisbane and the Gold and Sunshine Coasts to regional centres like Townsville, Cairns, Mackay and Rockhampton, and remote outreach across the north and west."),
    ("WA", "Western Australia", "wa",
     "Western Australia offers locum psychiatry roles in Perth's metro services and right across the regions, from the South West and Great Southern to the Pilbara and Kimberley. Regional packages commonly cover flights, accommodation and a car."),
    ("SA", "South Australia", "sa",
     "South Australian locum psychiatry roles are based mainly in Adelaide's metro services, with regional work in centres such as Mount Gambier, Whyalla, Port Augusta and the Riverland."),
    ("TAS", "Tasmania", "tas",
     "Tasmania's locum psychiatry roles are spread across Hobart, Launceston and the north-west coast, and suit doctors looking for a change of pace with genuine variety in their caseload."),
    ("NT", "Northern Territory", "nt",
     "Northern Territory locum psychiatry work is centred on Darwin and Alice Springs, with outreach to remote communities. It's rewarding work with a strong focus on culturally safe care, and roles usually include travel and accommodation."),
    ("ACT", "the ACT", "act",
     "Locum psychiatry roles in the ACT are based in Canberra's public and private mental health services, and suit doctors who want metro-style work in a smaller city."),
]

SUBSPECIALTIES = [
    ("General Adult Psychiatry", "general-adult-psychiatry-jobs.html", "General adult psychiatry jobs",
     "General adult psychiatry roles cover acute inpatient units, community teams and outpatient clinics. They're the backbone of most mental health services, and there's steady demand for both locum and permanent consultants."),
    ("Community Psychiatry", "community-psychiatry-jobs.html", "Community psychiatry jobs",
     "Community psychiatry roles work with adult community mental health teams, continuing care and crisis or acute care teams outside hospital, often with a mix of clinic, home visits and team leadership."),
    ("Child & Adolescent Psychiatry", "child-adolescent-psychiatry-jobs.html", "Child and adolescent psychiatry jobs",
     "Child and adolescent psychiatry (CAMHS / CYMHS) roles cover infant, child and youth mental health in community clinics, inpatient units and consultation services. Experienced child psychiatrists are in short supply, especially outside the capitals."),
    ("Older Persons Psychiatry", "older-persons-psychiatry-jobs.html", "Older persons psychiatry jobs",
     "Older persons (old age) psychiatry roles cover inpatient, community and residential aged care work, often alongside geriatric medicine. Demand is growing as the population ages."),
    ("Consultation-Liaison Psychiatry", "consultation-liaison-psychiatry-jobs.html", "Consultation-liaison psychiatry jobs",
     "Consultation-liaison psychiatry roles support general hospital wards and emergency departments, assessing patients with mental health needs alongside medical and surgical teams."),
    ("Forensic Psychiatry", "forensic-psychiatry-jobs.html", "Forensic psychiatry jobs",
     "Forensic psychiatry roles span secure units, prison and custodial health, court liaison and community forensic teams."),
    ("Addiction / Drug & Alcohol Psychiatry", "addiction-psychiatry-jobs.html", "Addiction psychiatry jobs",
     "Addiction psychiatry roles cover drug and alcohol services, withdrawal units, opioid treatment programs and consultation to other teams."),
    ("Rehabilitation & Neuropsychiatry", "rehabilitation-neuropsychiatry-jobs.html", "Rehabilitation and neuropsychiatry jobs",
     "Rehabilitation and neuropsychiatry roles support people with complex, longer-term needs, including brain injury and neurodevelopmental conditions, often in specialist inpatient or community programs."),
]

PAY_PAGE = "locum-psychiatrist-pay-rates.html"


def state_page(code):
    return f"locum-psychiatrist-jobs-{code.lower()}.html"


def is_psych(j):
    return "psychiatr" in str(j.get("specialty") or "").lower()


def is_consultant(j):
    t = str(j.get("positionTitle") or "").lower()
    return not any(k in t for k in ("registrar", "trainee", "medical officer", "cmo", "resident", "junior"))


def day_rate(j):
    """'$2750 per day' / 'Up to $2800 per day' / '$2700 - $2900 per day' -> midpoint dollars; else None."""
    s = str(j.get("salaryRate") or "").lower().replace(",", "")
    if "day" not in s:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s) if 500 <= float(x) <= 10000]
    if not nums:
        return None
    return (nums[0] + nums[1]) / 2 if len(nums) >= 2 else nums[0]


def money(n):
    return "${:,.0f}".format(n)


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def hub_shell(template, fname, title, desc, kicker, h1, intro, body, crumb_name):
    url = f"{SITE}/{fname}"
    h = set_head(template, title, desc, url, og_type="website")
    h = re.sub(r'<meta name="robots"[^>]*>', "", h)
    main = (f'<section class="page-hero"><div class="shell"><div class="kicker">{e(kicker)}</div><h1>{e(h1)}</h1>'
            f'<p>{intro}</p><div class="hero-actions"><a class="button coral" href="join.html">Join the Network →</a>'
            f'<a class="button outline" href="opportunities.html">All jobs</a></div></div></section>{body}')
    h = re.sub(r"<main>.*?</main>", lambda m: "<main>" + main + "</main>", h, count=1, flags=re.S)
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Jobs", "item": SITE + "/opportunities.html"},
        {"@type": "ListItem", "position": 3, "name": crumb_name, "item": url}]}
    return h.replace("</head>", '<script type="application/ld+json">' + json.dumps(crumbs, ensure_ascii=False) + "</script></head>", 1)


def job_grid(items, empty_msg):
    if not items:
        return (f'<p class="hub-empty">{empty_msg} New roles are added most days. '
                f'<a class="text-link" href="join.html">Join the Network</a> and we\'ll let you know when something suitable comes up.</p>')
    return '<div class="jobs-grid">' + "".join(static_card(j, n) for j, n in items) + "</div>"


def browse_links(current=None):
    st = "".join(f'<a class="pill hub-link" href="{state_page(c)}">{c}</a>' for c, _, _, _ in STATES if state_page(c) != current)
    sp = "".join(f'<a class="pill hub-link" href="{f}">{e(label.replace(" jobs", ""))}</a>' for _, f, label, _ in SUBSPECIALTIES if f != current)
    pay = "" if current == PAY_PAGE else f'<p><a class="text-link" href="{PAY_PAGE}">Locum psychiatrist pay rates →</a></p>'
    return (f'<section class="section white"><div class="shell"><div class="section-heading"><div class="kicker">Browse</div>'
            f'<h2>More psychiatry jobs.</h2></div><h3>By state</h3><div class="spec-pills">{st}</div>'
            f'<h3 style="margin-top:28px">By sub-specialty</h3><div class="spec-pills">{sp}</div>{pay}</div></section>')


def build_hubs(template, items):
    """items: list of (job, page_name) for live psychiatry jobs. Returns list of (filename, lastmod)."""
    out = []
    today_nice = dt.date.fromisoformat(TODAY).strftime("%-d %B %Y")

    for code, name, _, intro in STATES:
        fname = state_page(code)
        mine = [(j, n) for j, n in items if str(j.get("state") or "").upper() == code]
        n = len(mine)
        subs = sorted({sub(j) for j, _ in mine if sub(j)})
        count_line = (f"<p><strong>{n} psychiatry role{'s' if n != 1 else ''} live in {code}</strong> right now"
                      + (f", including {', '.join(s.lower() for s in subs[:4])}" if subs else "") + ".</p>") if n else ""
        body = (f'<section class="section"><div class="shell">{count_line}'
                f'{job_grid(mine, f"There are no psychiatry roles live in {name} right now.")}</div></section>'
                + browse_links(fname))
        title = f"Locum Psychiatrist Jobs {code} | Psychiatry Jobs in {name.replace('the ', '')} | The Doctor Network"
        desc = (f"{n} current locum and permanent psychiatry jobs in {name}. " if n else f"Locum and permanent psychiatry jobs in {name}. ") + \
            "Consultant psychiatrist roles in metro and regional services, updated daily."
        write(fname, hub_shell(template, fname, title, desc[:158], f"Psychiatry jobs · {code}",
                               f"Locum psychiatrist jobs in {name}", e(intro), body, f"Psychiatry jobs {code}"))
        out.append(fname)

    for key, fname, label, intro in SUBSPECIALTIES:
        mine = [(j, n) for j, n in items if sub(j) == key]
        n = len(mine)
        states = sorted({str(j.get("state") or "").upper() for j, _ in mine if j.get("state")})
        count_line = (f"<p><strong>{n} {label.lower().replace(' jobs', '')} role{'s' if n != 1 else ''} live</strong>"
                      + (f" across {', '.join(states)}" if states else "") + ".</p>") if n else ""
        body = (f'<section class="section"><div class="shell">{count_line}'
                f'{job_grid(mine, f"There are no {label.lower()} live right now.")}</div></section>' + browse_links(fname))
        title = f"{label.title().replace('And', 'and')} Australia | Locum and Permanent | The Doctor Network"
        desc = (f"{n} current {label.lower()} across Australia. " if n else f"Current {label.lower()} across Australia. ") + \
            "Locum and permanent consultant roles, updated daily."
        write(fname, hub_shell(template, fname, title, desc[:158], "Psychiatry jobs", f"{label} in Australia",
                               e(intro), body, label))
        out.append(fname)

    # pay rates page, from consultant day rates on the board right now
    rated = [(j, day_rate(j)) for j, _ in items if is_consultant(j)]
    rated = [(j, r) for j, r in rated if r]
    rows, all_rates = [], [r for _, r in rated]
    for code, name, _, _ in STATES:
        rs = [r for j, r in rated if str(j.get("state") or "").upper() == code]
        if len(rs) >= 2:
            rows.append(f'<tr><td><a class="text-link" href="{state_page(code)}">{code}</a></td><td>{len(rs)}</td>'
                        f'<td>{money(median(rs))}</td><td>{money(min(rs))} – {money(max(rs))}</td></tr>')
        elif len(rs) == 1:
            rows.append(f'<tr><td><a class="text-link" href="{state_page(code)}">{code}</a></td><td>1</td>'
                        f'<td>{money(rs[0])}</td><td>–</td></tr>')
    if all_rates:
        summary = (f"<p>Across the <strong>{len(all_rates)} consultant locum roles</strong> with a quoted day rate on our board "
                   f"as at {today_nice}, the median rate is <strong>{money(median(all_rates))} per day</strong>, ranging from "
                   f"{money(min(all_rates))} to {money(max(all_rates))}.</p>")
        table = ('<div class="rate-table-wrap"><table class="rate-table"><thead><tr><th>State</th><th>Roles</th>'
                 '<th>Median day rate</th><th>Range</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")
    else:
        summary, table = "<p>We don't have enough quoted day rates on the board right now to show a meaningful figure.</p>", ""
    faq = [
        ("How much does a locum psychiatrist earn per day in Australia?",
         (f"Based on the consultant locum roles currently on our board, the median quoted rate is {money(median(all_rates))} per day. "
          if all_rates else "")
         + "Rates vary with location, setting, on-call, urgency and whether travel and accommodation are included."),
        ("Why do locum psychiatry rates vary so much?",
         "Remote and regional roles, short-notice cover, heavy on-call and hard-to-fill sub-specialties usually pay more. "
         "Metro roles and longer bookings tend to sit lower, but are often easier to fit around life."),
        ("Are travel and accommodation included?",
         "For most regional and remote locums, yes: flights, accommodation and often a car are covered on top of the day rate. "
         "Check each role, as packages differ."),
        ("Do registrars and CMOs earn the same?",
         "No. These figures are for consultant roles only. Registrar, trainee and career medical officer locums are paid at different rates."),
    ]
    faq_html = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in faq)
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    body = (f'<section class="section white"><div class="shell policy">{summary}{table}'
            '<p class="hub-note">These figures come from the live roles on our jobs board and update automatically. '
            'They\'re a guide only: hourly-rate roles, permanent salaries and roles without a quoted rate aren\'t included, '
            'and the right rate for a particular booking depends on the details.</p></div></section>'
            f'<section class="section"><div class="shell"><div class="section-heading"><div class="kicker">Common questions</div>'
            f'<h2>Locum psychiatry pay, explained.</h2></div><div class="faq">{faq_html}</div></div></section>' + browse_links(PAY_PAGE))
    title = "Locum Psychiatrist Pay Rates Australia | Day Rates by State | The Doctor Network"
    desc = (f"What do locum psychiatrists earn per day in Australia? Live median day rates by state from "
            f"{len(all_rates)} current consultant roles, updated daily.")[:158]
    h = hub_shell(template, PAY_PAGE, title, desc, "Pay rates", "Locum psychiatrist pay rates in Australia",
                  "What consultant psychiatrists are being offered for locum work right now, by state, from the live roles on our jobs board.",
                  body, "Locum psychiatrist pay rates")
    h = h.replace("</head>", '<script type="application/ld+json">' + json.dumps(faq_ld, ensure_ascii=False) + "</script></head>", 1)
    write(PAY_PAGE, h)
    out.append(PAY_PAGE)
    return out


def hub_links_html():
    st = "".join(f'<a class="pill hub-link" href="{state_page(c)}">{c}</a>' for c, _, _, _ in STATES)
    sp = "".join(f'<a class="pill hub-link" href="{f}">{e(label.replace(" jobs", ""))}</a>' for _, f, label, _ in SUBSPECIALTIES)
    return (f'<div class="hub-browse"><p><strong>Psychiatry jobs by state:</strong></p><div class="spec-pills">{st}</div>'
            f'<p style="margin-top:18px"><strong>By sub-specialty:</strong></p><div class="spec-pills">{sp}</div>'
            f'<p style="margin-top:18px"><a class="text-link" href="{PAY_PAGE}">Locum psychiatrist pay rates →</a></p></div>')


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

    new_manifest, cards, written, seen, psych_items = {}, [], set(), {}, []
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
        if is_psych(j):
            psych_items.append((j, name))

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
    # state, sub-specialty and pay-rate pages, plus links to them
    hub_template = read("about.html")
    hubs = build_hubs(hub_template, psych_items)
    for page in ("opportunities.html", "psychiatry-recruitment.html"):
        write(page, replace_between(read(page), "<!--HUBS:START-->", "<!--HUBS:END-->", hub_links_html()))
    sm = read("sitemap.xml")
    if "<!--HUBS:START-->" not in sm:
        sm = sm.replace("<!--JOBS:START-->", "<!--HUBS:START--><!--HUBS:END-->\n<!--JOBS:START-->")
    hub_entries = "".join(f"<url><loc>{SITE}/{f}</loc><lastmod>{TODAY}</lastmod><priority>0.8</priority></url>\n" for f in hubs)
    write("sitemap.xml", replace_between(sm, "<!--HUBS:START-->", "<!--HUBS:END-->", "\n" + hub_entries))
    print(f"built {len(new_manifest)} job page(s) and {len(hubs)} hub page(s)")


if __name__ == "__main__":
    main()
