"""Minimal client for York County's Tyler Records Public Access portal."""

from __future__ import annotations

import time

import requests

from countyiq.lib.parsers.tyler_recorder import (
    parse_tyler_document_detail,
    parse_tyler_search_results,
)


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class TylerRecorderClient:
    """Requests-based Tyler session wrapper.

    This client is intentionally narrow:
      - accept disclaimer / bootstrap session
      - search by parcel UPI
      - fetch a document detail page
    """

    def __init__(
        self,
        base_url: str,
        parcel_search_id: str,
        document_search_id: str,
        throttle_seconds: float = 0.25,
        session_refresh: int = 500,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.parcel_search_id = parcel_search_id
        self.document_search_id = document_search_id
        self.throttle_seconds = throttle_seconds
        self.session_refresh = session_refresh
        self.timeout_seconds = timeout_seconds

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._request_count = 0

    def __enter__(self) -> "TylerRecorderClient":
        self.bootstrap()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.session.close()

    def bootstrap(self) -> None:
        """Accept the disclaimer and initialize the self-service home page."""
        response = self.session.post(self._url("/user/disclaimer"), timeout=self.timeout_seconds)
        response.raise_for_status()
        self._sleep()

        response = self.session.post(self._url("/homeActions"), timeout=self.timeout_seconds)
        response.raise_for_status()
        self._sleep()

    def search_parcel_documents(self, recorder_upi: str) -> list[dict]:
        """Search the Tyler parcel-number search for a single UPI."""
        return self._run_with_retry(lambda: self._search_parcel_documents_once(recorder_upi))

    def fetch_document_detail(self, document_id: str) -> dict:
        """Fetch and parse one Tyler document detail page."""
        return self._run_with_retry(lambda: self._fetch_document_detail_once(document_id))

    def _search_parcel_documents_once(self, recorder_upi: str) -> list[dict]:
        self._refresh_session_if_needed()

        search_url = self._url(f"/search/{self.parcel_search_id}")
        response = self.session.get(search_url, timeout=self.timeout_seconds)
        response.raise_for_status()
        self._sleep()

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Faces-Request": "partial/ajax",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.base_url.replace("/web", ""),
            "Referer": search_url,
        }
        payload = {
            "field_ParcelID": recorder_upi,
            "field_selfservice_documentTypes": "",
            "field_UseAdvancedSearch": "",
        }
        response = self.session.post(
            self._url(f"/searchPost/{self.parcel_search_id}"),
            headers=headers,
            data=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        self._sleep()

        page_data = response.json()
        total_pages = int(page_data.get("totalPages") or 1)

        records = []
        for page_num in range(1, total_pages + 1):
            page_response = self.session.get(
                self._url(f"/searchResults/{self.parcel_search_id}?page={page_num}"),
                headers={"Referer": search_url},
                timeout=self.timeout_seconds,
            )
            page_response.raise_for_status()
            self._sleep()
            records.extend(parse_tyler_search_results(page_response.text))

        return records

    def _fetch_document_detail_once(self, document_id: str) -> dict:
        self._refresh_session_if_needed()
        response = self.session.get(
            self._url(f"/document/{document_id}?search={self.parcel_search_id}"),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        self._sleep()
        detail = parse_tyler_document_detail(response.text)
        detail["document_id"] = document_id
        detail["source_url"] = f"/document/{document_id}?search={self.parcel_search_id}"
        return detail

    def _run_with_retry(self, fn):
        try:
            return fn()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code is None or status_code < 500:
                raise
            self.bootstrap()
            return fn()

    def _refresh_session_if_needed(self) -> None:
        if self._request_count and self._request_count % self.session_refresh == 0:
            self.bootstrap()

    def _sleep(self) -> None:
        self._request_count += 1
        if self.throttle_seconds > 0:
            time.sleep(self.throttle_seconds)

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"
