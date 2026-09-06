"""Conservative, deterministic document metadata review; never interprets decisions."""

from datetime import date
from urllib.parse import parse_qs
import hashlib
import re
from urllib.parse import unquote, urlsplit
from countyiq.lib.county_config import municipality_name_from_body
from countyiq.lib.parsers.public_proceedings import _DATE_PATTERNS, _MONTH_MAP

VERSION = "proceeding-metadata-6"
AGENDA_HEADING = re.compile(
    r"^[ \t]*(?:[A-Z][A-Z \t/-]{0,80}[ \t]+)?AGENDA[ \t]*$", re.I | re.M
)
TYPE_BY_CONFIG = {
    "board_of_supervisors": "supervisors",
    "borough_council": "council",
    "city_council": "council",
    "planning_commission": "planning_commission",
    "zoning_hearing": "zoning_hearing",
    "board_of_commissioners": "commissioners",
    "county_commissioners": "commissioners",
}
ROLE_PATTERNS = [
    (
        "other",
        r"library board|board of governors|recreation board|(?:sewer|water|municipal|redevelopment) authority|fire and rescue commission",
    ),
    ("planning_commission", r"planning\s+commission"),
    ("zoning_hearing", r"zoning\s+hearing\s+board"),
    ("commissioners", r"board\s+of\s+commissioners|commissioners.{0,8}meeting"),
    ("supervisors", r"board\s+of\s+supervisors"),
    ("council", r"(?:borough|city)\s+council\b|council\s+meeting"),
]


def exact_dates(text):
    found = []
    for pattern, handler in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            value = handler(match)
            try:
                if value:
                    date.fromisoformat(value)
                    found.append((match.start(), value))
            except ValueError:
                pass
    return sorted(set(found))


def has_meeting_cancellation(text, meeting_date):
    """Keep ambiguous cancellation notices; exclude explicitly different dates."""
    normalized = re.sub(r"\s+", " ", text[:1000])
    months = "January February March April May June July August September October November December".split()
    month_numbers = {name.lower(): i for i, name in enumerate(months, 1)}
    named_date = (
        r"(?P<month>"
        + "|".join(months)
        + r") +(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,? +(?P<year>\d{4}))?"
    )
    # Only a date grammatically attached to the cancelled meeting may exempt
    # the notice. An unrelated earlier date elsewhere in the sentence cannot.
    dated_notice = re.compile(
        r"(?:meeting(?: to have been held| scheduled| planned)?(?: on| for)? +"
        + named_date
        + r" +(?:was |is |has been |will be )?cancel(?:l)?ed)",
        re.I,
    )
    date_first_notice = re.compile(
        named_date
        + r" +(?:public )?meeting +(?:was |is |has been |will be )?cancel(?:l)?ed",
        re.I,
    )
    if meeting_date:
        current = date.fromisoformat(meeting_date)

        def retain_same_or_uncertain(match):
            month = month_numbers[match["month"].lower()]
            day = int(match["day"])
            year = int(match["year"]) if match["year"] else current.year
            try:
                referenced = date(year, month, day)
            except ValueError:
                return match[0]
            # Without a source year, compare month/day only; do not publish an
            # inferred full date or assume a different year for the same day.
            different = (
                referenced != current
                if match["year"]
                else (month, day) != (current.month, current.day)
            )
            return " " if different else match[0]

        normalized = dated_notice.sub(retain_same_or_uncertain, normalized)
        normalized = date_first_notice.sub(retain_same_or_uncertain, normalized)
    return bool(
        re.search(
            r"meeting.{0,50}cancel(?:l)?ed|cancel(?:l)?ed.{0,50}meeting",
            normalized,
            re.I,
        )
    )


def municipality_key(body):
    return re.sub(
        r"\bboro\b",
        "borough",
        re.sub(
            r"\btwp\b", "township", (municipality_name_from_body(body) or body).lower()
        ),
    )


def source_fingerprint(row):
    import json

    return hashlib.sha256(
        json.dumps(
            {
                key: row.get(key)
                for key in (
                    "id",
                    "body_name",
                    "meeting_date",
                    "proceeding_type",
                    "source_url",
                    "document_url",
                    "content_hash",
                    "raw_text",
                )
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


def review_metadata(row, entries, excluded_domains=(), *, today=None):
    """Returns proposed metadata and explicit blockers, without altering source text."""
    today = today or date.today()
    text = row.get("raw_text") or ""
    issues = []
    domains = {
        (urlsplit(row.get(key) or "").hostname or "").removeprefix("www.")
        for key in ("source_url", "document_url")
    }
    if domains.intersection(excluded_domains):
        return {
            "version": VERSION,
            "status": "quarantined",
            "issues": ["wrong_jurisdiction_source"],
            "meeting_date": None,
            "body_name": row["body_name"],
            "proceeding_type": row["proceeding_type"],
            "date_basis": None,
        }

    # Stop before agenda business so previous-meeting approval dates are not headers.
    header = text[:800]
    cutoff = re.search(
        r"approval of|approve.{0,15}minutes|public comment|members\s+present|roll call|call to order",
        header,
        re.I,
    )
    if cutoff:
        header = header[: cutoff.start()]
    # Attendance starts meeting business for date extraction, but may still
    # identify the primary board. Keep that identity evidence in `header`.
    attendance = re.search(
        r"\b(?:supervisors?|borough council)\s+present\b|"
        r"^\s*present\s*:|attendance was as\s+follows",
        header,
        re.I | re.M,
    )
    date_header = header[: attendance.start()] if attendance else header
    # A numbered agenda item can contain a prior approval or future event date.
    # Only the title/date block before business identifies this meeting.
    agenda_heading = AGENDA_HEADING.search(date_header)
    if agenda_heading:
        first_item = re.search(
            r"(?m)^[ \t]*\d+[.)][ \t]+\S", date_header[agenda_heading.end() :]
        )
        if first_item:
            date_header = date_header[: agenda_heading.end() + first_item.start()]
    dates = exact_dates(date_header)
    values = sorted({v for _, v in dates})
    filename = unquote(
        urlsplit(row.get("document_url") or "").path.rstrip("/").rsplit("/", 1)[-1]
    )
    filename = parse_qs(urlsplit(row.get("document_url") or "").query).get(
        "dn", [filename]
    )[0]
    filename_values = sorted({v for _, v in exact_dates(filename)})
    filename_date = filename_values[0] if len(filename_values) == 1 else None
    if len(filename_values) > 1:
        issues.append("conflicting_filename_dates")
    if len(values) == 1:
        meeting_date, basis = values[0], "document_header"
        if filename_date and filename_date != meeting_date:
            issues.append("header_filename_date_conflict")
    elif len(values) > 1:
        meeting_date, basis = None, None
        issues.append("conflicting_header_dates")
    else:
        meeting_date, basis = (
            filename_date,
            "document_filename" if filename_date else None,
        )
    if basis == "document_filename":
        # A yearless header cannot establish the year, but can contradict the
        # filename's month/day. Never manufacture a year to hide that conflict.
        partial_dates = re.finditer(
            r"\b(" + "|".join(_MONTH_MAP) + r")[\s_-]*(\d{1,2})(?:st|nd|rd|th)?(?!\d)",
            date_header,
            re.I,
        )
        expected = date.fromisoformat(meeting_date)
        if any(
            (int(_MONTH_MAP[match[1].lower()]), int(match[2]))
            != (expected.month, expected.day)
            for match in partial_dates
        ):
            issues.append("header_filename_date_conflict")
    if not meeting_date:
        issues.append("exact_meeting_date_unverified")
    # A verified future date is valid metadata. The extraction query waits until
    # that date; marking it permanently "review_required" would strand agendas.

    if re.search(r"(?i)committee.{0,45}meeting", header[:500]):
        issues.append("committee_meeting")
    if re.search(r"(?i)joint[\s/-]+(?:meeting|workshop|session)", header[:500]):
        issues.append("joint_meeting")
    role_mentions = sorted(
        (m.start(), m.end(), kind)
        for kind, pattern in ROLE_PATTERNS
        for m in re.finditer(pattern, header[:500], re.I)
    )
    for first, second in zip(role_mentions, role_mentions[1:]):
        if first[2] != second[2] and re.fullmatch(
            r"\s*(?:/|&|and)\s*", header[first[1] : second[0]], re.I
        ):
            if "joint_meeting" not in issues:
                issues.append("joint_meeting")
    role = role_mentions[0][2] if role_mentions else None
    municipal = municipality_key(row["body_name"])
    matches = [
        (name, url, kind)
        for name, url, kind in entries
        if municipality_key(name) == municipal and TYPE_BY_CONFIG.get(kind) == role
    ]
    body, proceeding_type = row["body_name"], row["proceeding_type"]
    if role == "other":
        issues.append("unrelated_board")
    elif role is None:
        issues.append("primary_board_unverified")
    elif len(matches) != 1:
        issues.append("primary_board_not_configured")
    else:
        body, _, kind = matches[0]
        proceeding_type = TYPE_BY_CONFIG[kind]

    # Whole packets cannot be interpreted under one date or decision stage.
    # Qualified agenda titles must occur before meeting business. Minutes often
    # contain a later "Consent Agenda" section that is not a separate document.
    has_agenda = bool(agenda_heading or re.search(r"(?im)^[ \t]*AGENDA[ \t]*$", text))
    minutes_headings = re.finditer(
        r"(?im)^[ \t]*(?:MINUTES OF\b[^\n]*|(?:[A-Z ]+ )?MEETING MINUTES)[ \t]*$", text
    )
    has_minutes = any(
        not re.search(
            r"\b(?:approv\w*|amend\w*|adopt\w*|consideration)\b", match[0], re.I
        )
        for match in minutes_headings
    )
    # Combined packets sometimes title the recorded meeting "Financial Review"
    # rather than "Minutes". An explicit agenda/minutes filename also holds it.
    filename_words = set(re.findall(r"[a-z]+", filename.lower()))
    if (has_agenda and has_minutes) or {"agenda", "minutes"} <= filename_words:
        issues.append("mixed_agenda_minutes_packet")
    if has_meeting_cancellation(text, meeting_date):
        issues.append("cancelled_meeting")
    if re.search(
        r"(?i)(meeting\s+(?:schedule|calendar)|(?:annual|yearly).{0,20}minutes)",
        text[:500] + " " + filename,
    ):
        issues.append("calendar_or_annual_bundle")
    page_headers = [page[:250] for page in text.split("\f")]
    meeting_headers = [
        h
        for h in page_headers
        if re.search(
            r"(?i)(meeting minutes|minutes of.{0,80}meeting|regular meeting)", h
        )
    ]
    if len({d for h in meeting_headers for _, d in exact_dates(h)}) > 1:
        issues.append("multiple_meetings")
    if len(text.strip()) < 500:
        issues.append("insufficient_document_text")
    return {
        "version": VERSION,
        "status": "review_required" if issues else "ready",
        "issues": issues,
        "meeting_date": meeting_date,
        "body_name": body,
        "proceeding_type": proceeding_type,
        "date_basis": basis,
    }
