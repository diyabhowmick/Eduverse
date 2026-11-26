"""The catalogue's shape: two tracks (textbooks, exams), three levels (school, degree, competitive).
Lists here are what the forms offer; any value typed in by the Super Admin is still accepted."""

TRACKS = {"textbook": "Textbooks", "exam": "Exam preparation"}
LEVELS = {"school": "School", "degree": "Degree college", "competitive": "Competitive exam"}

NATIONAL_BOARDS = ["CBSE", "ICSE", "ISC", "NIOS"]
STATE_BOARDS = [
    "Andhra Pradesh State Board", "Assam State Board", "Bihar State Board", "Chhattisgarh State Board", "Goa State Board",
    "Gujarat State Board", "Haryana State Board", "Himachal Pradesh State Board", "Jammu and Kashmir State Board",
    "Jharkhand State Board", "Karnataka State Board", "Kerala State Board", "Madhya Pradesh State Board",
    "Maharashtra State Board", "Manipur State Board", "Meghalaya State Board", "Mizoram State Board", "Nagaland State Board",
    "Odisha State Board", "Punjab State Board", "Rajasthan State Board", "Tamil Nadu State Board", "Telangana State Board",
    "Tripura State Board", "Uttar Pradesh State Board", "Uttarakhand State Board", "West Bengal State Board",
]
BOARDS = NATIONAL_BOARDS + STATE_BOARDS
GRADES = [str(g) for g in range(1, 13)]

BOARD_EXAMS = ["Class 10 Board", "Class 12 Board"]
DEGREE_EXAMS = ["Semester exam", "Final year exam"]
COMPETITIVE_EXAMS = ["JEE Main", "JEE Advanced", "NEET UG", "CUET UG", "BITSAT", "KCET", "TNEA", "MHT CET", "AP EAPCET", "TS EAMCET"]

MEDIUMS = ["English", "Tamil", "Kannada", "Hindi", "Malayalam", "Telugu", "Marathi", "Bengali"]
ORG_KINDS = {"school": "School", "college": "Degree college", "coaching": "Coaching centre", "other": "Other organisation"}

# Past paper windows the student can pick in an exam pack.
YEAR_WINDOWS = [10, 20, 0]  # 0 = every year we have


def all_():
    return {"tracks": TRACKS, "levels": LEVELS, "boards": BOARDS, "national_boards": NATIONAL_BOARDS, "state_boards": STATE_BOARDS,
            "grades": GRADES, "exams": {"school": BOARD_EXAMS, "degree": DEGREE_EXAMS, "competitive": COMPETITIVE_EXAMS},
            "mediums": MEDIUMS, "org_kinds": ORG_KINDS, "year_windows": YEAR_WINDOWS}


# Marks for a right answer and marks taken off for a wrong one, for objective questions. Defaults for mock tests;
# check them each year against the exam's own notice. Exams not listed use each question's own marks, no negative.
MARKING = {
    "JEE Main": (4, 1), "JEE Advanced": (3, 1), "NEET UG": (4, 1), "CUET UG": (5, 1), "BITSAT": (3, 1),
    "KCET": (1, 0), "TNEA": (1, 0), "MHT CET": (1, 0), "AP EAPCET": (1, 0), "TS EAMCET": (1, 0),
}


def marking_for(exam: str):
    for k, v in MARKING.items():
        if (exam or "").strip().lower() == k.lower():
            return {"correct": v[0], "wrong": v[1]}
    return None
