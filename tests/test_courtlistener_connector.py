import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from legal_agent.connectors.courtlistener_connector import DEFAULT_BASE_URL, CourtListenerConnector


class FakeHTTPResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestCourtListenerConnector(unittest.TestCase):
    def _connector(self, **kwargs):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return CourtListenerConnector(
            enabled=kwargs.pop("enabled", True),
            token=kwargs.pop("token", "test-token"),
            cache_path=f"{temp_dir.name}/cache.json",
            **kwargs,
        )

    def test_disabled_connector(self):
        connector = self._connector(enabled=False)

        result = connector.search_legal("contract damages")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["results"], [])

    def test_missing_token(self):
        connector = self._connector(token="")

        result = connector.search_legal("contract damages")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "credentials_missing")

    def test_loads_token_from_dotenv(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/.env", "w", encoding="utf-8") as env_file:
                env_file.write("COURTLISTENER_ENABLED=true\nCOURTLISTENER_API_TOKEN=dotenv-token\n")
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {}, clear=True):
                    connector = CourtListenerConnector(cache_path=f"{temp_dir}/cache.json")
            finally:
                os.chdir(original_cwd)

        self.assertTrue(connector.enabled)
        self.assertEqual(connector.token, "dotenv-token")

    def test_dotenv_overrides_empty_courtlistener_environment_values(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/.env", "w", encoding="utf-8") as env_file:
                env_file.write(
                    "COURTLISTENER_ENABLED=true\n"
                    "COURTLISTENER_API_TOKEN=dotenv-token\n"
                    "COURTLISTENER_BASE_URL=https://www.courtlistener.com/api/rest/v4\n"
                )
            try:
                os.chdir(temp_dir)
                with patch.dict(
                    os.environ,
                    {
                        "COURTLISTENER_ENABLED": "",
                        "COURTLISTENER_API_TOKEN": "",
                        "COURTLISTENER_BASE_URL": "",
                    },
                    clear=True,
                ):
                    connector = CourtListenerConnector(cache_path=f"{temp_dir}/cache.json")
            finally:
                os.chdir(original_cwd)

        self.assertTrue(connector.enabled)
        self.assertEqual(connector.token, "dotenv-token")
        self.assertEqual(connector.base_url, "https://www.courtlistener.com/api/rest/v4")

    def test_successful_search(self):
        payload = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "caseName": "Smith v. Jones",
                    "citation": ["123 Cal. 456"],
                    "court": "California Supreme Court",
                    "dateFiled": "2020-01-02",
                    "docketNumber": "S12345",
                    "absolute_url": "/opinion/1/smith-v-jones/",
                    "snippet": "A contract damages holding.",
                }
            ],
        }
        connector = self._connector()

        with patch("urllib.request.urlopen", return_value=FakeHTTPResponse(payload)) as urlopen:
            result = connector.search_legal("contract damages")

        self.assertTrue(result["ok"])
        self.assertEqual(result["raw_count"], 1)
        self.assertEqual(result["results"][0]["source"], "CourtListener")
        self.assertEqual(result["results"][0]["title"], "Smith v. Jones")
        self.assertEqual(result["results"][0]["citation"], "123 Cal. 456")
        self.assertEqual(result["results"][0]["absolute_url"], "https://www.courtlistener.com/opinion/1/smith-v-jones/")
        self.assertIn("q=contract+damages", urlopen.call_args.args[0].full_url)
        self.assertIn("type=o", urlopen.call_args.args[0].full_url)
        self.assertIn("semantic=true", urlopen.call_args.args[0].full_url)

    def test_invalid_base_url_falls_back_to_v4_default(self):
        connector = self._connector(base_url="not-a-url")

        self.assertEqual(connector.base_url, DEFAULT_BASE_URL)

    def test_citation_lookup(self):
        payload = [
            {
                "citation": "576 U.S. 644",
                "status": 200,
                "clusters": [
                    {
                        "case_name": "Obergefell v. Hodges",
                        "absolute_url": "/opinion/2812209/obergefell-v-hodges/",
                        "date_filed": "2015-06-26",
                    }
                ],
            }
        ]
        connector = self._connector()

        with patch("urllib.request.urlopen", return_value=FakeHTTPResponse(payload)) as urlopen:
            result = connector.lookup_citation(volume="576", reporter="U.S.", page="644")

        self.assertTrue(result["ok"])
        self.assertEqual(result["results"][0]["citation"], "576 U.S. 644")
        self.assertEqual(result["results"][0]["title"], "Obergefell v. Hodges")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("citation-lookup", request.full_url)

    def test_citation_lookup_no_citations_has_actionable_status(self):
        connector = self._connector()

        with patch("urllib.request.urlopen", return_value=FakeHTTPResponse([])):
            result = connector.lookup_citation(text="street contest Sacramento driver rights")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "no_citations")
        self.assertEqual(result["raw_count"], 0)
        self.assertEqual(result["results"], [])
        self.assertIn("did not find legal citations", result["message"])

    def test_citation_lookup_unmatched_status_includes_match_count(self):
        payload = [{"citation": "1 U.S. 200", "status": 404, "clusters": []}]
        connector = self._connector()

        with patch("urllib.request.urlopen", return_value=FakeHTTPResponse(payload)):
            result = connector.lookup_citation(volume="1", reporter="U.S.", page="200")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "unmatched_citations")
        self.assertEqual(result["results"][0]["citation"], "1 U.S. 200")
        self.assertEqual(result["results"][0]["lookup_status"], 404)
        self.assertEqual(result["results"][0]["match_count"], 0)

    def test_api_error_response(self):
        connector = self._connector()
        error = urllib.error.HTTPError(
            url="https://www.courtlistener.com/api/rest/v4/search/",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=error):
            result = connector.search_legal("contract damages")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "api_error")
        self.assertEqual(result["status_code"], 429)

    def test_timeout_handling(self):
        connector = self._connector()

        with patch("urllib.request.urlopen", side_effect=TimeoutError):
            result = connector.search_legal("contract damages")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "timeout")

    def test_normalization_removes_full_text_fields(self):
        payload = {
            "results": [
                {
                    "case_name": "Opinion Result",
                    "citation": "1 F.4th 1",
                    "plain_text": "Do not cache this opinion body.",
                    "html": "<p>Do not cache this either.</p>",
                    "resource_uri": "https://www.courtlistener.com/api/rest/v4/opinions/1/",
                }
            ]
        }
        connector = self._connector()

        with patch("urllib.request.urlopen", return_value=FakeHTTPResponse(payload)):
            result = connector.search_opinions("qualified immunity")

        metadata = result["results"][0]["raw_metadata"]
        self.assertNotIn("plain_text", metadata)
        self.assertNotIn("html", metadata)
        self.assertEqual(result["results"][0]["result_type"], "opinion")


if __name__ == "__main__":
    unittest.main()
