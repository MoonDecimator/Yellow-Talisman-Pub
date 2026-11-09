import io
import json
import unittest
from email.message import Message
from urllib.error import HTTPError, URLError

from scripts.github_api import (
    GitHubApi,
    GitHubApiError,
    GitHubNotFoundError,
    is_fatal_api_error,
)


class FakeResponse:
    def __init__(self, document, *, headers=None):
        self._payload = (
            document if isinstance(document, bytes) else json.dumps(document).encode()
        )
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._payload


class SequenceTransport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def http_error(status, message, *, headers=None):
    response_headers = Message()
    for name, value in (headers or {}).items():
        response_headers[name] = value
    return HTTPError(
        "https://api.github.com/example",
        status,
        message,
        response_headers,
        io.BytesIO(json.dumps({"message": message}).encode()),
    )


class GitHubApiTests(unittest.TestCase):
    def test_get_uses_bearer_token_and_api_headers(self):
        transport = SequenceTransport([FakeResponse({"ok": True})])
        api = GitHubApi("test-token", transport=transport)

        self.assertEqual({"ok": True}, api.get_json("/example"))

        request = transport.requests[0]
        self.assertEqual("GET", request.get_method())
        self.assertEqual("Bearer test-token", request.get_header("Authorization"))
        self.assertEqual("2022-11-28", request.get_header("X-github-api-version"))

    def test_pagination_follows_next_link(self):
        next_url = "https://api.github.com/installation/repositories?page=2"
        transport = SequenceTransport(
            [
                FakeResponse(
                    {"repositories": [{"id": 1}]},
                    headers={"Link": f'<{next_url}>; rel="next"'},
                ),
                FakeResponse({"repositories": [{"id": 2}]}),
            ]
        )
        api = GitHubApi("test-token", transport=transport)

        repositories = list(
            api.get_paginated(
                "/installation/repositories", item_key="repositories"
            )
        )

        self.assertEqual([{"id": 1}, {"id": 2}], repositories)
        self.assertIn("per_page=100", transport.requests[0].full_url)
        self.assertEqual(next_url, transport.requests[1].full_url)

    def test_404_has_a_specific_exception(self):
        headers = Message()
        error = HTTPError(
            "https://api.github.com/missing",
            404,
            "Not Found",
            headers,
            io.BytesIO(b'{"message":"Not Found"}'),
        )
        api = GitHubApi("test-token", transport=SequenceTransport([error]))

        with self.assertRaises(GitHubNotFoundError):
            api.get_json("/missing")

    def test_raw_content_uses_raw_media_type(self):
        transport = SequenceTransport([FakeResponse(b"name: test\n")])
        api = GitHubApi("test-token", transport=transport)

        self.assertEqual("name: test\n", api.get_text("/workflow"))
        self.assertEqual(
            "application/vnd.github.raw+json",
            transport.requests[0].get_header("Accept"),
        )

    def test_retries_5xx_with_exponential_backoff_and_tracks_telemetry(self):
        sleeps = []
        transport = SequenceTransport(
            [
                http_error(500, "temporary"),
                http_error(503, "temporary"),
                FakeResponse(
                    {"ok": True},
                    headers={
                        "X-RateLimit-Remaining": "4988",
                        "X-RateLimit-Reset": "2000",
                    },
                ),
            ]
        )
        api = GitHubApi("test-token", transport=transport, sleep=sleeps.append)

        self.assertEqual({"ok": True}, api.get_json("/example"))

        self.assertEqual([1.0, 2.0], sleeps)
        self.assertEqual(3, api.telemetry.requests)
        self.assertEqual(2, api.telemetry.retries)
        self.assertEqual(4988, api.telemetry.rate_limit_remaining)
        self.assertEqual(2000, api.telemetry.rate_limit_reset)

    def test_429_prefers_retry_after_over_rate_limit_reset(self):
        sleeps = []
        transport = SequenceTransport(
            [
                http_error(
                    429,
                    "rate limited",
                    headers={
                        "Retry-After": "7",
                        "X-RateLimit-Reset": "9999",
                    },
                ),
                FakeResponse({"ok": True}),
            ]
        )
        api = GitHubApi(
            "test-token",
            transport=transport,
            sleep=sleeps.append,
            clock=lambda: 100.0,
        )

        api.get_json("/example")

        self.assertEqual([7.0], sleeps)

    def test_rate_limited_403_uses_reset_when_retry_after_is_missing(self):
        sleeps = []
        transport = SequenceTransport(
            [
                http_error(
                    403,
                    "API rate limit exceeded",
                    headers={
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": "120",
                    },
                ),
                FakeResponse({"ok": True}),
            ]
        )
        api = GitHubApi(
            "test-token",
            transport=transport,
            sleep=sleeps.append,
            clock=lambda: 100.0,
        )

        api.get_json("/example")

        self.assertEqual([20.0], sleeps)
        self.assertEqual(1, api.telemetry.retries)

    def test_non_rate_limit_403_is_not_retried(self):
        transport = SequenceTransport([http_error(403, "Resource not accessible")])
        api = GitHubApi("test-token", transport=transport, sleep=lambda _: None)

        with self.assertRaises(GitHubApiError) as context:
            api.get_json("/example")

        self.assertFalse(context.exception.rate_limited)
        self.assertEqual(1, api.telemetry.requests)
        self.assertEqual(0, api.telemetry.retries)

    def test_401_and_404_are_not_retried(self):
        for status in (401, 404):
            with self.subTest(status=status):
                api = GitHubApi(
                    "test-token",
                    transport=SequenceTransport([http_error(status, "failed")]),
                    sleep=lambda _: None,
                )

                with self.assertRaises(GitHubApiError):
                    api.get_json("/example")

                self.assertEqual(1, api.telemetry.requests)
                self.assertEqual(0, api.telemetry.retries)

    def test_timeout_is_retried_and_uses_exponential_backoff(self):
        sleeps = []
        api = GitHubApi(
            "test-token",
            transport=SequenceTransport(
                [TimeoutError("timed out"), FakeResponse({"ok": True})]
            ),
            sleep=sleeps.append,
        )

        self.assertEqual({"ok": True}, api.get_json("/example"))
        self.assertEqual([1.0], sleeps)

    def test_transport_url_error_is_retried(self):
        api = GitHubApi(
            "test-token",
            transport=SequenceTransport(
                [URLError("temporary"), FakeResponse({"ok": True})]
            ),
            sleep=lambda _: None,
        )

        self.assertEqual({"ok": True}, api.get_json("/example"))

    def test_exhausted_retry_raises_last_api_error(self):
        api = GitHubApi(
            "test-token",
            transport=SequenceTransport(
                [
                    http_error(503, "one"),
                    http_error(503, "two"),
                    http_error(503, "three"),
                ]
            ),
            sleep=lambda _: None,
        )

        with self.assertRaises(GitHubApiError) as context:
            api.get_json("/example")

        self.assertEqual(503, context.exception.status)
        self.assertEqual(3, api.telemetry.requests)
        self.assertEqual(2, api.telemetry.retries)

    def test_fatal_policy_distinguishes_scoped_failures(self):
        for status in (400, 401, 403, 429):
            with self.subTest(status=status):
                self.assertTrue(
                    is_fatal_api_error(GitHubApiError(status, "url", "failed"))
                )
        for status in (None, 404, 500, 503):
            with self.subTest(status=status):
                self.assertFalse(
                    is_fatal_api_error(GitHubApiError(status, "url", "failed"))
                )


if __name__ == "__main__":
    unittest.main()
