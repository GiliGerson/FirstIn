"""Hebrew message formatting for job alerts, digests and email alerts."""

from worker.notify.telegram import esc

SOURCE_NAMES = {
    "linkedin": "LinkedIn", "gmail": "מייל", "greenhouse": "Greenhouse", "lever": "Lever",
    "ashby": "Ashby", "comeet": "Comeet", "workday": "Workday", "smartrecruiters": "SmartRecruiters",
}
JOB_TYPE_HE = {"student": "משרת סטודנט", "internship": "התמחות", "part_time": "משרה חלקית"}
STAGE_HE = {
    "received": "המועמדות התקבלה", "screening": "סינון ראשוני", "interview": "זימון לראיון",
    "home_assignment": "מטלת בית", "offer": "הצעת עבודה 🎉", "rejected": "נדחתה", "none": "עדכון",
}
# Application stages as shown on the dashboard's Pipeline screen
STAGE_HE_APP = {
    "applied": "הוגש", "screening": "סינון ראשוני", "interview": "ראיון", "home_assignment": "מטלת בית",
    "offer": "הצעה 🎉", "rejected": "נדחה", "ghosted": "לא ענו", "withdrawn": "ויתרתי",
}
NOT_RELEVANT_REASONS = {
    "loc": "מיקום", "hours": "היקף שעות", "role": "תפקיד", "company": "חברה", "other": "אחר",
}


def job_link(job: dict) -> str | None:
    """Short public link: LinkedIn alert URLs carry long tracking parameters."""
    return job.get("canonical_url") or job.get("url")


def score_badge(score: int | None) -> str:
    if score is None:
        return "⚪"
    return "🟢" if score >= 85 else "🟡" if score >= 70 else "🟠" if score >= 50 else "⚪"


def workplace_text(job: dict) -> str:
    if job.get("is_remote"):
        return " (מהבית)"
    if job.get("is_hybrid"):
        return " (היברידי)"
    return ""


def sources_text(job: dict) -> str:
    names = sorted({SOURCE_NAMES.get(s["source"], s["source"]) for s in job.get("job_sources") or []})
    return " + ".join(names)


def job_alert(job: dict) -> str:
    """Instant alert for one job (a `jobs` row joined with companies(name) and job_sources(source))."""
    company = (job.get("companies") or {}).get("name", "")
    lines = [
        f"{score_badge(job['match_score'])} <b>{job['match_score']}</b> · <b>{esc(job['title'])}</b>",
        f"🏢 {esc(company)} · 📍 {esc(job.get('location') or 'לא צוין')}{workplace_text(job)}",
    ]
    kind = JOB_TYPE_HE.get(job.get("job_type"))
    if kind or job.get("role_category"):
        lines.append("🏷 " + " · ".join(esc(x) for x in (kind, job.get("role_category")) if x))
    lines += [f"✅ {esc(r)}" for r in (job.get("match_reasons") or [])[:3]]
    lines += [f"⚠️ {esc(f)}" for f in (job.get("red_flags") or [])[:2]]
    if job.get("job_sources"):
        lines.append(f"🔎 מקור: {sources_text(job)}")
    return "\n".join(lines)


def job_buttons(job: dict) -> list[list[dict]]:
    rows = []
    if job_link(job):
        rows.append([{"text": "🔗 פתח משרה", "url": job_link(job)}])
    rows.append([
        {"text": "✅ הגשתי", "callback_data": f"a:{job['id']}"},
        {"text": "⭐ שמור", "callback_data": f"s:{job['id']}"},
        {"text": "👎 לא רלוונטי", "callback_data": f"n:{job['id']}"},
    ])
    return rows


def reason_buttons(job_id: int) -> list[list[dict]]:
    items = [{"text": label, "callback_data": f"r:{job_id}:{code}"} for code, label in NOT_RELEVANT_REASONS.items()]
    return [items[:3], items[3:]]


def digest_line(job: dict) -> str:
    company = (job.get("companies") or {}).get("name", "")
    title = esc(job["title"])
    link = f'<a href="{esc(job_link(job))}">{title}</a>' if job_link(job) else title
    reason = (job.get("match_reasons") or [""])[0]
    line = f"{score_badge(job['match_score'])} <b>{job['match_score']}</b> · {link}\n    {esc(company)} · {esc(job.get('location') or '')}"
    if reason:
        line += f"\n    <i>{esc(reason)}</i>"
    return line


def email_alert(category: str, from_name: str, subject: str, summary: str, stage: str = "none") -> str:
    if category == "recruiter_outreach":
        head = "📩 <b>פנייה ממגייס/ת</b>"
    else:
        head = f"📬 <b>עדכון על הגשה: {STAGE_HE.get(stage, 'עדכון')}</b>"
    return f"{head}\nמאת: {esc(from_name)}\nנושא: {esc(subject)}\n\n{esc(summary)}"
