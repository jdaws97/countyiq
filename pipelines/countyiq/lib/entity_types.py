"""Deterministic owner-name type classification.

Shared by the owner-resolution asset and the Pass 1 cluster selector so both
agree on what counts as an organization. Owner identity is public and Pass 1
includes person-only clusters by default; operators may explicitly trade recall
for cost. This module is the single definition of that execution boundary.
"""

from __future__ import annotations

import re

GOVERNMENT_INDICATORS = re.compile(
    r"\b(COUNTY OF|COMMONWEALTH|TOWNSHIP|BOROUGH|CITY OF|"
    r"SCHOOL DIST\w*|AUTH(?:ORITY|OR)?|STATE OF|UNITED STATES)\b",
    re.IGNORECASE,
)

TRUST_INDICATORS = re.compile(
    r"\b(TRUST|ESTATE|REVOCABLE|IRREVOCABLE)\b",
    re.IGNORECASE,
)

BUSINESS_INDICATORS = re.compile(
    r"\b(LLC|INC|CORP|CORPORATION|LTD|LP|LLP|"
    r"ASSOCIATES|ASSOCIATION|FOUNDATION|PROPERTIES|REALTY|"
    r"INVESTORS?|INVESTMENTS|HOLDINGS|PARTNERS|GROUP|ENTERPRISES|"
    r"CAPITAL|MANAGEMENT|DEVELOPMENT|VENTURES|BANK|"
    r"CHURCH|SYNAGOGUE|MOSQUE|SOCIETY|CLUB|LODGE|"
    r"SCHOOL|UNIVERSITY|COLLEGE|HOSPITAL)\b",
    re.IGNORECASE,
)


def classify_entity(name: str) -> str:
    """Classify one owner-name variant as government, trust, business, or person."""
    if not name:
        return "unknown"
    if GOVERNMENT_INDICATORS.search(name):
        return "government"
    if TRUST_INDICATORS.search(name):
        return "trust"
    if BUSINESS_INDICATORS.search(name):
        return "business"
    return "person"


def is_organization_name(name: str) -> bool:
    """True for government, trust, and business names; False for people and blanks."""
    return classify_entity(name) in {"government", "trust", "business"}
