# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import pytest

from fakeredis import FakeStrictRedis
from gidgethub import sansio
from gidgethub import abc as gh_abc
from gidgethub.abc import JSON_UTF_8_CHARSET
from datetime import datetime

import spackbot.workers

class MockGitHubAPI(gh_abc.GitHubAPI):
    DEFAULT_HEADERS = {
        "x-ratelimit-limit": "2",
        "x-ratelimit-remaining": "1",
        "x-ratelimit-reset": "0",
        "content-type": JSON_UTF_8_CHARSET,
    }

    def __init__(
        self,
        status_code=200,
        headers=DEFAULT_HEADERS,
        body=b"",
        *,
        cache=None,
        oauth_token=None,
        base_url=sansio.DOMAIN,
    ):
        self.response_code = status_code
        self.response_headers = headers
        self.response_body = body
        super().__init__(
            "test_abc", oauth_token=oauth_token, cache=cache, base_url=base_url
        )

    async def _request(self, method, url, headers, body=b""):
        """Make an HTTP request."""
        print(f"Making a real {method} request to {url}! Wink wink!")
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body
        response_headers = self.response_headers.copy()
        try:
            # Don't loop forever.
            del self.response_headers["link"]
        except KeyError:
            pass
        return self.response_code, response_headers, self.response_body

    async def sleep(self, seconds):  # pragma: no cover
        """Sleep for the specified number of seconds."""
        self.slept = seconds

@pytest.fixture(scope="session")
def mock_redis():
    def _init_fakeredis():
        return FakeStrictRedis()

    # Override the redis connection with fakeredis
    monkeypatch.setattr(spackbot.queue, "_init_redis_connection", _init_fakeredis)


@pytest.fixture(scope="function")
def mock_gh_event() -> sansio.Event:
    """Mock event posted by GH when an event is opened"""

    data = _gh_event("pr", action="open")
    return sansio.Event(data, event="mock_pr", delivery_id="0")


@pytest.fixture(scope="function")
def mock_gh_api():
    return MockGithubAPI

