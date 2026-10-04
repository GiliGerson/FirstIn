"""Normalize RawJob fields so the same job from different sources gets the same de-dup key."""

import re

# Canonical city → spellings seen in LinkedIn / ATS / Hebrew postings
CITY_ALIASES = {
    "Tel Aviv": ["tel aviv", "tel-aviv", "tel aviv-yafo", "tel aviv yafo", "tlv", "תל אביב"],
    "Herzliya": ["herzliya", "herzlia", "herzeliya", "הרצליה"],
    "Ramat Gan": ["ramat gan", "ramat-gan", "רמת גן"],
    "Givatayim": ["givatayim", "givataim", "גבעתיים"],
    "Petah Tikva": ["petah tikva", "petach tikva", "petah tiqva", "petach tikvah", "פתח תקווה", "פתח תקוה"],
    "Bnei Brak": ["bnei brak", "bnei-brak", "בני ברק"],
    "Holon": ["holon", "חולון"],
    "Bat Yam": ["bat yam", "בת ים"],
    "Ra'anana": ["ra'anana", "raanana", "ra`anana", "רעננה"],
    "Kfar Saba": ["kfar saba", "kfar sava", "כפר סבא"],
    "Hod Hasharon": ["hod hasharon", "hod ha'sharon", "הוד השרון"],
    "Rosh HaAyin": ["rosh haayin", "rosh ha'ayin", "rosh ha-ayin", "ראש העין"],
    "Rishon LeZion": ["rishon lezion", "rishon le zion", "rishon letsiyon", "ראשון לציון"],
    "Rehovot": ["rehovot", "rechovot", "רחובות"],
    "Ness Ziona": ["ness ziona", "nes ziona", "נס ציונה"],
    "Airport City": ["airport city", "קריית שדה התעופה"],
    "Or Yehuda": ["or yehuda", "אור יהודה"],
    "Ramat HaSharon": ["ramat hasharon", "ramat ha'sharon", "רמת השרון"],
    "Netanya": ["netanya", "נתניה"],
    "Modiin": ["modiin", "modi'in", "מודיעין"],
    "Haifa": ["haifa", "חיפה"],
    "Jerusalem": ["jerusalem", "ירושלים"],
    "Yokneam": ["yokneam", "yoqneam", "יקנעם"],
    "Beer Sheva": ["beer sheva", "be'er sheva", "beersheba", "באר שבע"],
    "Caesarea": ["caesarea", "קיסריה"],
    "Ashdod": ["ashdod", "אשדוד"],
    "Kiryat Gat": ["kiryat gat", "קריית גת"],
    "Migdal HaEmek": ["migdal haemek", "migdal haemeq", "מגדל העמק"],
    "Beit Shean": ["beit shean", "beit she'an", "בית שאן"],
    "Kiryat Ono": ["kiryat ono", "קריית אונו"],
    "Yehud": ["yehud", "יהוד"],
    "Givat Shmuel": ["givat shmuel", "גבעת שמואל"],
    "Lod": ["lod", "לוד"],
    "Yavne": ["yavne", "yavneh", "יבנה"],
    "Hadera": ["hadera", "חדרה"],
    "Nazareth": ["nazareth", "nazerat", "נצרת"],
    "Ashkelon": ["ashkelon", "אשקלון"],
    "Afula": ["afula", "עפולה"],
    "Karmiel": ["karmiel", "כרמיאל"],
    "Nahariya": ["nahariya", "נהריה"],
    "Tiberias": ["tiberias", "טבריה"],
    "Eilat": ["eilat", "אילת"],
    "Kiryat Shmona": ["kiryat shmona", "קריית שמונה"],
    "Dimona": ["dimona", "דימונה"],
    "Zichron Yaakov": ["zichron yaakov", "zikhron ya'akov", "זכרון יעקב"],
}
_CITY_RES = [
    (city, re.compile("|".join(rf"(?<![a-z]){re.escape(a)}(?![a-z])" for a in aliases), re.IGNORECASE))
    for city, aliases in CITY_ALIASES.items()
]


def canonical_city(location: str | None) -> str | None:
    """First known city mentioned in the location text, e.g. "Tel Aviv-Yafo, Israel" → "Tel Aviv"."""
    if not location:
        return None
    # The earliest mention wins: LinkedIn writes "Herzliya, Tel Aviv District, Israel"
    matches = [(m.start(), city) for city, pattern in _CITY_RES if (m := pattern.search(location))]
    return min(matches)[1] if matches else None


def normalize_location(location: str | None) -> str | None:
    """Location used for display and de-dup: the canonical city when known, else the cleaned text."""
    if not location:
        return None
    city = canonical_city(location)
    if city:
        return city
    cleaned = re.sub(r"\s+", " ", re.sub(r"\((hybrid|remote|on-?site)\)", "", location, flags=re.I)).strip(" ,-")
    return cleaned or None


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[/.](?:ית|ה|ת)(?=\s|$|[^\w])", "", t)     # סטודנט/ית, סטודנט.ית → סטודנט
    t = re.sub(r"[–—_\-]", " ", t)
    t = re.sub(r"[^\w\s+#]", " ", t)                       # keep c++, c#
    return re.sub(r"\s+", " ", t).strip()


_JOB_TYPE_RULES = [
    ("internship", re.compile(r"\bintern(ship)?s?\b|התמחות", re.I)),
    ("student", re.compile(r"\bstudents?\b|סטודנט", re.I)),
    ("part_time", re.compile(r"\bpart[\s-]?time\b|חלקית", re.I)),
]


def job_type(title: str, employment_type: str | None = None) -> str:
    """job_type enum value: student / internship / part_time / other."""
    for value, pattern in _JOB_TYPE_RULES:
        if pattern.search(title):
            return value
    for value, pattern in _JOB_TYPE_RULES:
        if employment_type and pattern.search(employment_type):
            return value
    return "other"


def workplace_flags(workplace: str | None, location: str | None) -> tuple[bool | None, bool | None]:
    """(is_hybrid, is_remote) from the ATS workplace field or the location text."""
    text = f"{workplace or ''} {location or ''}".lower()
    if not text.strip():
        return None, None
    hybrid = "hybrid" in text or "היברידי" in text
    remote = "remote" in text or "מהבית" in text
    if not (hybrid or remote) and not workplace:
        return None, None  # location text alone doesn't prove on-site
    return hybrid, remote
