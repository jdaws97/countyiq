"""Shared safety bounds for public spatial queries."""

from fastapi import HTTPException

MAX_BBOX_SPAN_DEGREES = 0.25
MAX_BBOX_RESULTS = 5_000


def validate_bbox(west: float, south: float, east: float, north: float) -> None:
    """Reject inverted or excessively broad public map envelopes."""
    if west >= east or south >= north:
        raise HTTPException(
            status_code=422,
            detail="Bounding box must have west < east and south < north",
        )
    if east - west > MAX_BBOX_SPAN_DEGREES or north - south > MAX_BBOX_SPAN_DEGREES:
        raise HTTPException(
            status_code=422,
            detail=(
                "Bounding box is too large; zoom in so each span is at most "
                f"{MAX_BBOX_SPAN_DEGREES} degrees"
            ),
        )
