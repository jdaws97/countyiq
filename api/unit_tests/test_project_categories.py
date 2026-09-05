from api.routes import directory


def test_project_category_filter_keeps_minor_cases_out_of_development_results(monkeypatch):
    def row(key, category):
        return {"project": {"key": key, "name": key}, "event_date": "2026-08-01",
                "what_happened": "Synthetic source fact", "sources": [{"details": {"matter_category": category}}]}
    monkeypatch.setattr(directory, "fetch_feed", lambda **kwargs:
                        {"events": [row("major", "development"), row("minor", "minor_property")], "has_more": False})
    assert [p["key"] for p in directory.projects(q="", limit=20, kind="development")["projects"]] == ["major"]
    assert [p["key"] for p in directory.projects(q="", limit=20, kind="minor_property")["projects"]] == ["minor"]
    assert len(directory.projects(q="", limit=20, kind="all")["projects"]) == 2
