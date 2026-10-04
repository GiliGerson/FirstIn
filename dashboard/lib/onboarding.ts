/** Choices offered during onboarding. City names must match worker/pipeline/normalize.py. */

export const ROLE_OPTIONS = [
  "Software Developer / Student Developer",
  "AI / ML Engineer",
  "Data Analyst / Data Science",
  "Product (Product Analyst / Student PM)",
  "QA / Test Automation",
  "DevOps / Cloud / IT",
  "Cybersecurity",
  "Hardware / Embedded",
  "UX / UI Design",
  "Marketing / Growth",
];

export const JOB_TYPE_OPTIONS = [
  { value: "student", label: "Student position" },
  { value: "internship", label: "Internship" },
  { value: "part_time", label: "Part-time" },
];

export const CITY_GROUPS: { label: string; cities: string[] }[] = [
  {
    label: "Tel Aviv & Gush Dan",
    cities: ["Tel Aviv", "Ramat Gan", "Givatayim", "Bnei Brak", "Holon", "Bat Yam", "Or Yehuda", "Kiryat Ono",
             "Yehud", "Givat Shmuel", "Airport City"],
  },
  {
    label: "Sharon",
    cities: ["Herzliya", "Ra'anana", "Kfar Saba", "Hod Hasharon", "Ramat HaSharon", "Netanya"],
  },
  {
    label: "Center & south",
    cities: ["Petah Tikva", "Rosh HaAyin", "Rishon LeZion", "Rehovot", "Ness Ziona", "Lod", "Modiin", "Beer Sheva"],
  },
  { label: "Jerusalem & north", cities: ["Jerusalem", "Haifa", "Yokneam", "Caesarea"] },
];

export const LANGUAGE_OPTIONS = ["English", "Hebrew", "Arabic", "Russian", "French", "Spanish"];

export const YEAR_OPTIONS = [
  { value: 1, label: "1st year" },
  { value: 2, label: "2nd year" },
  { value: 3, label: "3rd year" },
  { value: 4, label: "4th year" },
  { value: 5, label: "Master's" },
];

/** Same defaults the worker uses (worker/settings.py) */
export const DEFAULT_INCLUDE_KEYWORDS = ["student", "סטודנט", "סטודנטית", "intern", "internship", "part-time",
  "part time", "חלקית", "משרה חלקית"];
export const DEFAULT_QUIET_HOURS = { start: "23:00", end: "08:00", override_score: 90 };
