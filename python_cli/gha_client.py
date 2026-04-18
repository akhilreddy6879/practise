# python_cli/gha_client.py
import os
import time
import requests
from requests.adapters import HTTPAdapter, Retry
from typing import Optional


GITHUB_API = "https://api.github.com"

class GitHubActionsClient:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN not set")

        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def _request(self, method: str, path: str, **kwargs):
        url = f"{GITHUB_API}{path}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        resp = self.session.request(method, url, headers=headers, **kwargs)

        # Basic rate-limit handling
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = resp.headers.get("X-RateLimit-Reset")
            if reset:
                sleep_for = max(int(reset) - int(time.time()), 1)
                time.sleep(sleep_for)
                return self.session.request(method, url, headers=headers, **kwargs)

        resp.raise_for_status()
        return resp.json() if resp.text else {}