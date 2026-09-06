"""Heuristic source inventory for operator review, never generated projects.

Matching named anchors does not prove complete recall or semantic correctness.
Only explicit item identities/narratives count; citing a neighboring paragraph
does not cover every matter mentioned in it.
"""

import hashlib
import re

_ADDRESS = re.compile(
    r"\b\d{1,6}(?:\s*[-&]\s*\d{1,6})?\s+"
    r"(?:[NSEW]\.?\s+)?(?:[A-Za-z][A-Za-z.'-]*\s+){1,4}?"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl|Trail|Tr)\b\.?",
    re.I,
)
_CASE = re.compile(
    r"\b(?:(?:SD|LD|CUH|ZHB|ZDA)[ -]+\d[\w-]*|\d{1,3}-\d{4}-Z-[A-Z-]+)\b", re.I
)
_TOPIC = re.compile(
    r"plan|subdivis|permit|construction|project|addition|"
    r"remov|withdraw|road|street|sewer|solar|ordinance|bid|hearing|variance|improvement|lot\b",
    re.I,
)
_HEADING = re.compile(
    r"^\s*(?:[a-z0-9]+[.)]\s*)?([^:\n–—]{3,85}?)(?:\s+[-–—]\s*|:\s*)(.*)$", re.I
)
_GENERIC = re.compile(
    r"^(?:public|new business|old business|engineer|solicitor|"
    r"administrative|reports?|committee|call to|adjourn|minutes|"
    r"meeting|upcoming|phone|fax|page|next|motion|vote|zoning officer|code officer|"
    r"project manager|minimum municipal|park rules|SLDO|\d{4}/\d{4} winter service)\b",
    re.I,
)


def _normal(value):
    return " ".join(re.findall(r"\w+", str(value).casefold()))


def inventory_anchors(source_text):
    """Return exact source spans, including a bounded review list downstream."""
    anchors, seen = [], set()
    offset = 0
    for line in source_text.splitlines(keepends=True):
        stripped = line.strip()
        # Addresses in meeting locations/contact blocks are not property matters.
        boilerplate = (offset < 650 and not _CASE.search(line)) or re.search(
            r"next.{0,30}case|meeting.{0,80}(?:held|building|chambers)|"
            r"municipal (?:office|building)|township community building|"
            r"phone|fax|www\.|https?://",
            line,
            re.I,
        )
        found = (
            []
            if boilerplate
            else [
                (
                    m[0],
                    "address" if pattern is _ADDRESS else "application",
                    m.start(),
                    m.end(),
                )
                for pattern in (_ADDRESS, _CASE)
                for m in pattern.finditer(line)
                if not (
                    pattern is _ADDRESS
                    and re.search(r"lot\s*#?\s*$", line[: m.start()], re.I)
                )
            ]
        )
        cleaned = re.sub(r"^[\s•➢\uf0b7]+|^(?:o\s+)", "", stripped)
        heading = _HEADING.match(cleaned)
        if heading and not re.search(
            r"next.{0,30}case|phone|fax|https?://", line, re.I
        ):
            name, topic = heading.groups()
            name = re.sub(r"^\d+(?:\.\d+)?[.)]?\s+", "", name).strip()
            if re.fullmatch(r"discussion request|plan review", name, re.I):
                name = re.split(r"\s+[-–—]\s+", topic)[0].strip()
            if (
                _TOPIC.search(topic)
                and name[0].isupper()
                and not _GENERIC.search(name)
                and 1 <= len(name.split()) <= 9
                and not name.isdigit()
            ):
                start = line.find(name)
                found.append((name, "named_heading", start, start + len(name)))
        for text, kind, start, end in found:
            key = (kind, _normal(text))
            if key in seen:
                continue
            seen.add(key)
            anchors.append(
                {
                    "kind": kind,
                    "text": text,
                    "start": offset + start,
                    "end": offset + end,
                    "context": stripped,
                }
            )
        offset += len(line)
    return anchors


def review_coverage(source_text, extractions, *, limit=40):
    """Unmatched anchors request review; they never trigger paid retries."""
    texts = []
    for item in extractions:
        values = [
            item.get(k) or ""
            for k in (
                "project_name",
                "project_reference",
                "applicant_name",
                "what_happened",
            )
        ]
        values.extend(item.get("application_ids") or [])
        values.extend(item.get("parcel_references") or [])
        texts.append(" " + _normal(" ".join(values)) + " ")
    anchors = inventory_anchors(source_text)
    unmatched = [
        a
        for a in anchors
        if not any(" " + _normal(a["text"]) + " " in text for text in texts)
    ]
    return {
        "version": 1,
        "source_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "candidate_count": len(anchors),
        "matched_count": len(anchors) - len(unmatched),
        "unmatched_count": len(unmatched),
        "needs_review": bool(unmatched),
        "unmatched_anchors": unmatched[:limit],
        "truncated": len(unmatched) > limit,
        "limitation": "Heuristic named-anchor check; not a completeness or accuracy score.",
    }
