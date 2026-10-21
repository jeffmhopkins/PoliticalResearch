"""HTTP for portal adapters. Uses the shared fetch guard. A 403 is not retried."""

from __future__ import annotations

from lib.util import safe_request, unsafe_fetch_target


class PortalFetchError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SafePortalFetcher:
    """One attempt per URL. 403 and 429 are recorded and not requested again."""

    def __init__(self, request=safe_request) -> None:
        self._request = request
        self._blocked: set[str] = set()
        self._cookies: dict[str, str] = {}

    def fetch_html(self, url: str, *, method: str = "GET", data: str | None = None, headers: dict | None = None, timeout: int = 30):
        reason = unsafe_fetch_target(url)
        if reason:
            raise PortalFetchError(f"Refusing fetch: {reason}")
        if url in self._blocked:
            raise PortalFetchError("403 already recorded; not retried", status_code=403)
        hdrs = {"User-Agent": "PoliticalResearch-portal/0.1"}
        if headers:
            hdrs.update(headers)
        if self._cookies:
            hdrs["Cookie"] = "; ".join(f"{key}={value}" for key, value in self._cookies.items())
        try:
            response = self._request(method, url, headers=hdrs, data=data, timeout=timeout)
        except RuntimeError as exc:
            raise PortalFetchError(str(exc)) from exc
        self._absorb(response)
        status = getattr(response, "status_code", None)
        final = str(getattr(response, "url", None) or url)
        final_reason = unsafe_fetch_target(final)
        if final_reason:
            raise PortalFetchError(f"Refusing fetch: {final_reason}")
        if status in {403, 429}:
            self._blocked.add(url)
            raise PortalFetchError(f"HTTP {status}", status_code=status)
        if status is None or int(status) >= 400:
            raise PortalFetchError(f"HTTP {status}", status_code=status)
        text = getattr(response, "text", "") or ""
        if not str(text).strip():
            raise PortalFetchError("empty body", status_code=status)
        return final, str(text)

    def submit_form(self, page_url: str, post_url: str, build_body):
        _final, html = self.fetch_html(page_url)
        body = build_body(html)
        return self.fetch_html(
            post_url,
            method="POST",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def _absorb(self, response) -> None:
        jar = getattr(response, "cookies", None)
        if jar is None or not hasattr(jar, "items"):
            return
        for key, value in jar.items():
            self._cookies[str(key)] = str(value)
