"""Title keywords for student / intern / part-time jobs (the full rule filter comes in step 3)."""

import re

STUDENT_TITLE_KEYWORDS = [
    "student", "students", "intern", "interns", "internship", "internships", "part-time", "part time",
    "parttime",
    "working student", "סטודנט", "סטודנטית", "סטודנט/ית", "סטודנט.ית", "התמחות", "חלקית", "משרה חלקית",
]
_STUDENT_RE = re.compile(
    "|".join(rf"\b{re.escape(k)}\b" if k[0].isascii() else re.escape(k) for k in STUDENT_TITLE_KEYWORDS),
    re.IGNORECASE,
)


def looks_student(title: str, *extra: str | None) -> bool:
    """True if the title (or an ATS employment-type field) signals a student/intern/part-time job."""
    return any(text and _STUDENT_RE.search(text) for text in (title, *extra))
