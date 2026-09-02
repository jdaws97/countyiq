from api.lib.evidence import normalize_source_evidence, signal_evidence_items


def test_signal_citation_resolves_to_source_facts_and_method():
    items = signal_evidence_items(
        {
            "growth_area": {
                "source_id": "GA-7",
                "source_url": "https://example.com/growth",
                "validation_status": "confirmed",
                "adjusted_significance": "high",
                "evidence": {"ga_type": "PGA", "detail_url": "https://example.com/growth/GA-7"},
            }
        },
        ["growth_area"],
        scope="parcel:1:brief",
        pidn="1",
        observed_at="2026-08-31T12:00:00Z",
    )

    assert len(items) == 1
    item = items[0]
    assert item["citation_key"] == "signal:growth_area"
    assert item["source_record_id"] == "GA-7"
    assert item["url"] == "https://example.com/growth/GA-7"
    assert item["internal_url"] == "/property/1"
    assert item["details"]["ga_type"] == "PGA"
    assert item["details"]["validation_status"] == "confirmed"
    assert "validated" in item["method"].lower()


def test_feed_source_is_upgraded_to_evidence_receipt():
    item = normalize_source_evidence(
        {
            "label": "Township minutes",
            "url": "https://example.com/meetings",
            "document_url": "https://example.com/minutes.pdf",
            "excerpt": "The board approved the plan.",
            "details": {"decision": "approved"},
        },
        scope="event:development:1",
        index=0,
        source_kind="proceeding_extraction",
        source_record_id="44",
        effective_at="2026-08-01",
        observed_at="2026-08-02T10:00:00Z",
        interpretation_kind="llm",
        confidence=0.91,
    )

    assert item["citation_key"] == "source:1"
    assert item["source_record_id"] == "44"
    assert item["details"] == {"decision": "approved"}
    assert item["confidence"] == 0.91
    assert "verified" in item["method"].lower()


def test_arcgis_layer_url_becomes_record_deep_link():
    from api.lib.evidence import arcgis_record_url, evidence_item

    layer = "https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0"
    url = arcgis_record_url(layer, "PIDN", ["26000050001B0"])
    assert url == layer + "/query?where=PIDN%3D%2726000050001B0%27&outFields=%2A&f=html"

    # Numeric keys are unquoted and lists become IN (...).
    structures = "https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/BLDG_Footprint/FeatureServer/0"
    assert "where=OBJECTID+IN+%2812%2C34%29" in arcgis_record_url(structures, "OBJECTID", [12, 34])

    # Not a layer endpoint, unsafe value, or unsafe field -> no rewrite.
    assert arcgis_record_url("https://example.com/listing.pdf", "PIDN", ["1"]) is None
    assert arcgis_record_url(layer, "PIDN", ["1' OR 1=1"]) is None
    assert arcgis_record_url(layer, "PIDN; DROP", ["1"]) is None

    item = evidence_item(
        scope="parcel:1", citation_key="parcel:1", label="Parcel", source_kind="official_parcel_record",
        url=layer, method="m", record_query=("PIDN", ["1"]),
    )
    assert item["url"].endswith("/query?where=PIDN%3D%271%27&outFields=%2A&f=html")

    # An all-digit PIDN stays quoted: PIDN is a text field.
    assert arcgis_record_url(layer, "PIDN", ["9400002006900"]).endswith(
        "where=PIDN%3D%279400002006900%27&outFields=%2A&f=html"
    )

    # FEMA rows store the service root; the flood layer index is appended first.
    from api.lib.evidence import NFHL_FLOOD_HAZARD_LAYER, with_arcgis_layer
    fema = with_arcgis_layer("https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer", NFHL_FLOOD_HAZARD_LAYER)
    assert fema.endswith("/NFHL/MapServer/28")
    assert arcgis_record_url(fema, "FLD_AR_ID", ["42133C_1"]).endswith("where=FLD_AR_ID%3D%2742133C_1%27&outFields=%2A&f=html")

    # A document URL is left alone even when a record query is supplied.
    untouched = evidence_item(
        scope="parcel:1", citation_key="tax:1", label="Tax", source_kind="official_tax_listing",
        url="https://county.example/listing.pdf", method="m", record_query=("PIDN", ["1"]),
    )
    assert untouched["url"] == "https://county.example/listing.pdf"


def test_signal_receipt_deep_links_known_layers_when_no_detail_url():
    items = signal_evidence_items(
        {
            "active_subdivision": {
                "source_id": "2021-045",
                "source_url": "https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/PLANNING_Subdivisions/FeatureServer/0",
                "evidence": {"plan_title": "Ridge View"},
            }
        },
        ["active_subdivision"],
        scope="parcel:1:brief",
        pidn="1",
    )
    assert items[0]["url"].endswith("/query?where=SEQU_NUM%3D%272021-045%27&outFields=%2A&f=html")
