# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import pytest
import contextlib

from fakeredis import FakeStrictRedis
from gidgethub import sansio
from gidgethub import abc as gh_abc
from gidgethub.abc import JSON_UTF_8_CHARSET
from sh.contrib import git

import spackbot.workers

@pytest.fixture(scope="function")
def mock_git_repo(tmpdir):
    """Create a mock git repo"""
    with contextlib.chdir(tmpdir):
        git.init()

        # Configure the user
        git.config("user.name", "Mock User")
        git.config("user.email", "noreply@mockemail.io")

        # Add some test files
        for file in ["a", "b", "c", "d"]
            with open(f"{file}.txt", "w") as fd:
                fd.write(f"{file}")
            git.add(f"{file}.txt")

        git.commit("-m", "Initial Commit")

        yield tmpdir


@pytest.fixture(scope="function")
def mock_git_remote(mock_git_repo, tmpdir):
    """Create a mock git repo"""
    with contextlib.chdir(tmpdir):
        yield mock_git_repo


# Mock services
@pytest.fixture(scope="session")
def mock_redis():
    def _init_fakeredis():
        return FakeStrictRedis()

    # Override the redis connection with fakeredis
    monkeypatch.setattr(spackbot.queue, "_init_redis_connection", _init_fakeredis)


# GitHub API Mock
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

    def add_url_handler(match_url: str, status: int, headers: Dict[str,str], body: Any):
        self._responses.append({
            "match": re.compile(match_url),
            "status": status,
            "headers": headers,
            "body": body
        })

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


@pytest.fixture(scope="function")
def mock_gh_event() -> sansio.Event:
    """Mock event posted by GH when an event is opened"""

    data = _gh_event("pr", action="open")
    return sansio.Event(data, event="mock_pr", delivery_id="0")


@pytest.fixture(scope="function")
def mock_gh_api():
    return MockGitHubAPI()


def mock_gh_pr_files(mock_gh_api):
    """Add handler for PR files requests"""

    file_template = """
  {
    "sha": "bbcd538c8e72b8c175046e27cc8f907076331401",
    "filename": "{file_name}",
    "status": "{file_status}",
    "additions": 103,
    "deletions": 21,
    "changes": 124,
    "blob_url": "https://github.com/octocat/Hello-World/blob/6dcb09b5b57875f334f61aebed695e2e4193db5e/{file_name}",
    "raw_url": "https://github.com/octocat/Hello-World/raw/6dcb09b5b57875f334f61aebed695e2e4193db5e/{file_name}",
    "contents_url": "https://api.github.com/repos/octocat/Hello-World/contents/{file_name}?ref=6dcb09b5b57875f334f61aebed695e2e4193db5e",
    "patch": "{patch}"
  },
"""
    def _handler(data):
        if not data:
            patch = "@@ -132,7 +132,7 @@ module Test @@ -1000,7 +1000,7 @@ module Test"
            data = [
               {"file_name": "foo_added.txt",    "file_status": "added", "patch": patch},
               {"file_name": "foo_modified.txt", "file_status": "modified", "patch": patch},
               {"file_name": "foo_deleted.txt",  "file_status": "deleted", "patch": patch},
            ]
        body = "["
        for file in data:
            if "patch" not in file:
                file["patch"] = patch
            body += file_template.format(**file)
        body = "]"

        mock_gh_api.add_url_handler(
            "pulls/([0-9]+)/files$",
            200,
            None,
            body
        )

    return _handler
