"""Current, cited site-intake evidence; saved inquiries contain user work only."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field


class SiteInquiry(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    pidn: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    label: str = Field(min_length=1, max_length=200)
    proposed_use: str = Field(max_length=2000)
    note: str = Field(max_length=4000)
    questions: str = Field(max_length=4000)
    status: Literal["researching", "ready_for_handoff", "on_hold"]
    reviewed_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    updated_at: datetime


def intake_packet(cur, report: dict) -> dict:
    parcel = report["parcel"]
    assets = {
        "parcels_arcgis": "Parcel identity",
        "zoning_arcgis": "Mapped zoning",
        "soils_arcgis": "Soils",
        "fema_flood_zones": "FEMA mapping",
    }
    cur.execute(
        """SELECT asset_key, status, last_success_at, finished_at
        FROM meta.asset_refresh_status WHERE asset_key = ANY(%s)""",
        (list(assets),),
    )
    runs = {row["asset_key"]: row for row in cur.fetchall()}
    sources = []
    for key, label in assets.items():
        run = runs.get(key)
        last_success = run["last_success_at"] if run else None
        status = "unknown"
        if last_success:
            status = (
                "current"
                if run["status"] == "success"
                and last_success >= datetime.now(UTC) - timedelta(days=8)
                else "stale"
            )
        sources.append(
            {
                "key": key,
                "label": label,
                "status": status,
                "last_successful_run_at": last_success.isoformat()
                if last_success
                else None,
            }
        )
    cur.execute(
        """SELECT r.body_name, h.listing_status, h.checked_at
        FROM meta.municipality_source_rights r
        LEFT JOIN meta.municipality_source_health h USING (source_key)
        WHERE UPPER(r.municipality_name) = UPPER(%s) AND r.acquisition_allowed
        ORDER BY r.body_name""",
        (parcel["municipality"] or "",),
    )
    coverage = []
    for row in cur.fetchall():
        checked = row["checked_at"]
        current = checked and checked >= datetime.now(UTC) - timedelta(days=8)
        coverage.append(
            {
                "body_name": row["body_name"],
                "status": row["listing_status"] if current else "stale_or_unchecked",
                "checked_at": checked.isoformat() if checked else None,
            }
        )
    packet = {
        "report": report,
        "sources": sources,
        "municipal_collection": coverage,
        "questions": [
            "Confirm the parcel boundary and municipal reviewing authority.",
            "Check the proposed use, dimensional standards and any split zoning against the current municipal ordinance.",
            "Confirm flood mapping, soils and any site-specific investigations with the project professional.",
            "Obtain written utility service/capacity and access requirements; mapped proximity does not establish availability.",
            "Ask the municipality about uncollected applications, conditions and current review status.",
        ],
        "scope_note": "Research for an initial municipal conversation and proposal scoping. This packet does not determine permitted use, buildability, utility capacity or approval. Municipal passages are literal site associations, not a complete project history.",
    }
    encoded = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"))
    packet["revision"] = hashlib.sha256(encoded.encode()).hexdigest()
    return packet
