"""Shared ArcGIS-to-GeoJSON geometry conversion helpers.

ArcGIS REST features carry geometry in three shapes that we care about:
- Polygon:  ``{"rings": [[[x, y], ...], ...]}`` — outer rings are clockwise,
  inner rings (holes) are counter-clockwise. We convert to GeoJSON
  ``MultiPolygon`` to round-trip multi-part polygons cleanly.
- Polyline: ``{"paths": [[[x, y], ...], ...]}`` — converted to GeoJSON
  ``MultiLineString``.
- Point:    ``{"x": float, "y": float}`` — converted to GeoJSON ``Point``.

These were previously inlined in 14 ArcGIS asset modules; consolidated here
so the SCD2 geometry helper in :mod:`countyiq.lib.scd` can rely on a single
implementation.
"""


def _is_clockwise(ring: list[list[float]]) -> bool:
    """Return True if ``ring`` is wound clockwise (shoelace formula).

    ArcGIS uses clockwise outer rings and counter-clockwise inner rings,
    which we use to split a flat ring list into multipolygon coordinates.
    """
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        total += (x2 - x1) * (y2 + y1)
    return total > 0


def rings_to_multipolygon_geojson(rings: list) -> dict | None:
    """Convert ArcGIS polygon rings to a GeoJSON ``MultiPolygon`` dict.

    A new outer polygon starts whenever a clockwise ring is encountered;
    counter-clockwise rings are appended to the current polygon as holes.
    Returns ``None`` if ``rings`` is falsy.
    """
    if not rings:
        return None
    polygons: list[list] = []
    current_polygon: list = []
    for ring in rings:
        if not current_polygon:
            current_polygon.append(ring)
        elif _is_clockwise(ring):
            polygons.append(current_polygon)
            current_polygon = [ring]
        else:
            current_polygon.append(ring)
    if current_polygon:
        polygons.append(current_polygon)
    return {"type": "MultiPolygon", "coordinates": polygons}


def paths_to_multilinestring_geojson(paths: list) -> dict | None:
    """Convert ArcGIS polyline ``paths`` to a GeoJSON ``MultiLineString`` dict.

    Returns ``None`` if ``paths`` is falsy.
    """
    if not paths:
        return None
    return {"type": "MultiLineString", "coordinates": paths}


def point_to_geojson(x: float | None, y: float | None) -> dict | None:
    """Convert ArcGIS ``(x, y)`` to a GeoJSON ``Point`` dict.

    Returns ``None`` if either coordinate is missing.
    """
    if x is None or y is None:
        return None
    return {"type": "Point", "coordinates": [x, y]}
