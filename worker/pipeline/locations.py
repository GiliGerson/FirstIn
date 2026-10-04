"""Is a job location in Israel?"""

import re

ISRAEL_PLACES = [
    "israel", "ישראל", "tel aviv", "tel-aviv", "תל אביב", "herzliya", "herzlia", "הרצליה",
    "ramat gan", "רמת גן", "givatayim", "petah tikva", "petach tikva", "petah tiqva", "פתח תקווה",
    "bnei brak", "holon", "bat yam", "ra'anana", "raanana", "רעננה", "kfar saba", "כפר סבא",
    "hod hasharon", "rosh haayin", "rosh ha'ayin", "rishon lezion", "rishon le zion", "rehovot",
    "ness ziona", "nes ziona", "airport city", "or yehuda", "haifa", "חיפה", "jerusalem", "ירושלים",
    "yokneam", "yoqneam", "beer sheva", "be'er sheva", "beersheba", "netanya", "נתניה",
    "caesarea", "modiin", "modi'in", "kiryat gat", "ashdod", "migdal haemek", "migdal haemeq",
    "ramat hasharon", "center district", "central district",
]
_PLACES_RE = re.compile("|".join(re.escape(p) for p in ISRAEL_PLACES), re.IGNORECASE)


def is_israel(*values: str | None, country: str | None = None) -> bool:
    if country and country.strip().upper() in ("IL", "ISR", "ISRAEL"):
        return True
    return any(v and _PLACES_RE.search(v) for v in values)
