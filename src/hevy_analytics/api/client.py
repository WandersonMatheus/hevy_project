import time
from typing import Iterator

import requests


class HevyAPIError(Exception):
    pass


class HevyClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.hevyapp.com/v1",
        request_delay_seconds: float = 0.3,
        max_retries: int = 3,
    ):
        if not api_key:
            raise HevyAPIError("HEVY_API_KEY is empty — check your .env file")
        self.base_url = base_url.rstrip("/")
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"api-key": api_key})

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = HevyAPIError(f"{resp.status_code} from {url}")
                    time.sleep(self.request_delay_seconds * (2**attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(self.request_delay_seconds * (2**attempt))
        raise HevyAPIError(f"Failed GET {url} after {self.max_retries} retries: {last_error}")

    def get_workout_count(self) -> int:
        data = self._get("/workouts/count", {})
        return data["workout_count"]

    def iter_workout_events(self, since: str, page_size: int = 10) -> Iterator[dict]:
        page = 1
        while True:
            data = self._get(
                "/workouts/events",
                {"page": page, "pageSize": page_size, "since": since},
            )
            events = data.get("events", [])
            for event in events:
                yield event
            if page >= data.get("page_count", page):
                break
            page += 1
            time.sleep(self.request_delay_seconds)

    def iter_exercise_templates(self, page_size: int = 100) -> Iterator[dict]:
        page = 1
        while True:
            data = self._get(
                "/exercise_templates",
                {"page": page, "pageSize": page_size},
            )
            templates = data.get("exercise_templates", [])
            for template in templates:
                yield template
            if page >= data.get("page_count", page):
                break
            page += 1
            time.sleep(self.request_delay_seconds)

    def iter_routines(self, page_size: int = 10) -> Iterator[dict]:
        page = 1
        while True:
            data = self._get(
                "/routines",
                {"page": page, "pageSize": page_size},
            )
            routines = data.get("routines", [])
            for routine in routines:
                yield routine
            if page >= data.get("page_count", page):
                break
            page += 1
            time.sleep(self.request_delay_seconds)
