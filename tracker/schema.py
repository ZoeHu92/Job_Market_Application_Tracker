"""Column definitions shared by the scraper, the stores and the app."""

# One row per posting in data/jobs.csv (public, written by the weekly scrape).
JOB_COLUMNS = [
    "job_id",            # "<source>:<source_id>", stable across runs
    "source",
    "source_id",
    "title",
    "institution",
    "department",
    "location",
    "country",
    "region",
    "field",             # primary business field
    "fields",            # all detected fields, "; "-separated
    "rank",              # e.g. "Assistant", "Assistant/Associate", "Open rank", "Postdoc"
    "tenure_track",      # Yes / No / Unknown
    "degree_req",        # PhD (ABD OK) / PhD required / Master's+ / Not stated
    "is_business_school",
    "deadline",          # ISO date of the earliest stated application deadline
    "review_start",      # ISO date review of applications begins
    "open_until_filled",
    "deadline_note",     # human-readable summary of the deadline language
    "start_date",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_text",
    "materials",         # requested application materials, "; "-separated
    "interview_venues",  # e.g. "FMA; AFA/ASSA; Virtual"
    "requirements",      # short extracted qualification sentences
    "categories",        # raw categories / JEL codes / keywords from the source
    "posted_date",
    "listing_expires",
    "url",
    "apply_url",
    "status",            # Open / Closed
    "status_note",
    "first_seen",
    "last_seen",
    "closed_date",
    "duplicate_of",      # job_id of the same position on another board, if detected
    "description",       # full text; only kept when settings.keep_full_description is true
]

# One row per job you are tracking, in my_data/applications.csv (private, gitignored).
APP_BOOL_COLUMNS = ["starred", "planned", "applied", "interview", "flyout", "offer", "rejected"]
APP_DATE_COLUMNS = ["applied_date", "interview_date", "flyout_date", "offer_date"]
APP_COLUMNS = ["job_id", *APP_BOOL_COLUMNS, *APP_DATE_COLUMNS, "notes", "updated_at"]

# Pipeline order, used to show the furthest stage reached.
STAGES = [
    ("offer", "Offer"),
    ("flyout", "Flyout"),
    ("interview", "Interview"),
    ("applied", "Applied"),
    ("planned", "Planned"),
    ("starred", "Starred"),
]

FIELDS = [
    "Finance",
    "Accounting",
    "Marketing",
    "Management & Strategy",
    "Organizational Behavior & HR",
    "Operations & Supply Chain",
    "Information Systems",
    "Business Analytics & Statistics",
    "Economics",
    "Real Estate",
    "Insurance & Risk",
    "Entrepreneurship & Innovation",
    "International Business",
    "Business Law & Ethics",
    "Hospitality & Tourism",
    "Other / General Business",
]

RANKS = [
    "Assistant",
    "Assistant/Associate",
    "Open rank",
    "Associate",
    "Associate/Full",
    "Full",
    "Lecturer",
    "Postdoc",
    "Visiting",
    "Clinical/Teaching",
    "Chair/Endowed",
    "Dean/Admin",
    "Unspecified",
]

REGIONS = [
    "United States",
    "Canada",
    "UK & Ireland",
    "Europe",
    "Greater China",
    "Asia-Pacific",
    "Middle East & Africa",
    "Latin America",
    "Unknown",
]
