"""Benchmark for the redirect endpoint: GET /<code> -> 307.

Run it through Docker with benchmark.bat (runs with and without the Redis cache and
prints a comparison), or by hand:

    pip install locust
    locust -f locustfile.py --host http://localhost:5000

Cache on/off is a SERVER setting (CACHE_ENABLED=true|false), not a locust setting.

One short link is created up front and shared by all simulated users, because link
creation is rate-limited to 20/minute per IP and we want to measure redirects only.
"""
import logging
import os
import time

import requests
from locust import HttpUser, constant, events, task

log = logging.getLogger("benchmark")

EMAIL = os.getenv("BENCH_EMAIL", "bench@example.com")
PASSWORD = os.getenv("BENCH_PASSWORD", "benchmark-password-123")
TARGET_URL = os.getenv("BENCH_TARGET_URL", "https://example.com/benchmark")

_code: str | None = None


def _post(url: str, **kwargs) -> requests.Response:
    """POST, waiting out a 429 if a previous run used up the creation quota."""
    for _ in range(3):
        r = requests.post(url, timeout=10, **kwargs)
        if r.status_code != 429:
            return r
        wait = int(r.headers.get("Retry-After", "5")) + 1
        log.warning("Rate limited, waiting %s seconds...", wait)
        time.sleep(wait)
    return r


@events.test_start.add_listener
def create_the_link(environment, **_):
    global _code
    host = environment.host.rstrip("/")
    try:
        _post(f"{host}/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})  # 409 = already exists
        login = _post(f"{host}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        created = _post(f"{host}/api/links", json={"long_url": TARGET_URL}, headers=headers)
        created.raise_for_status()
        _code = created.json()["code"]
        log.info("Benchmarking GET /%s", _code)
    except Exception:  # noqa: BLE001
        log.exception("Could not prepare the benchmark link; is the API running?")
        if environment.runner:
            environment.runner.quit()


class RedirectUser(HttpUser):
    wait_time = constant(0)  # no think time: measure raw throughput

    @task
    def redirect(self) -> None:
        with self.client.get(
            f"/{_code}", allow_redirects=False, name="GET /[code]", catch_response=True
        ) as response:
            if response.status_code == 307:
                response.success()
            else:
                response.failure(f"expected 307, got {response.status_code}")
