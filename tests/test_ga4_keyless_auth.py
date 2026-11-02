"""Offline auth tests: no credential files, network calls, or secrets in output."""
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts.google_measurement import GA4_SCOPE, GSC_SCOPE, lab_access_token


class KeylessAuthTests(unittest.TestCase):
    @patch.dict(os.environ, {"NEXUS_GA4_KEYLESS_IMPERSONATION": ""})
    @patch("scripts.google_measurement.access_token", return_value="adc-ci-token")
    def test_default_preserves_existing_adc(self, existing):
        self.assertEqual(lab_access_token(GA4_SCOPE), "adc-ci-token")
        existing.assert_called_once_with(GA4_SCOPE)

    @patch.dict(os.environ, {"NEXUS_GA4_KEYLESS_IMPERSONATION": "1"})
    @patch("scripts.google_measurement.os.name", "posix")
    @patch("scripts.google_measurement.fetch_json",
           return_value={"accessToken": "impersonated-ci-token"})
    @patch("scripts.google_measurement.subprocess.run")
    def test_keyless_requests_only_analytics_readonly_scope(self, run, fetch):
        run.return_value = subprocess.CompletedProcess([], 0, "short-lived-user-token\n", "")
        self.assertEqual(lab_access_token(GA4_SCOPE), "impersonated-ci-token")
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["gcloud", "auth", "print-access-token"])
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertTrue(run.call_args.kwargs["text"])
        (url,), kwargs = fetch.call_args
        self.assertIn("nexus-commerce-lab@workintech-working", url)
        self.assertEqual(kwargs["body"], {"scope": [GA4_SCOPE], "lifetime": "1800s"})
        self.assertEqual(kwargs["token"], "short-lived-user-token")

    @patch.dict(os.environ, {"NEXUS_GA4_KEYLESS_IMPERSONATION": "1"})
    @patch("scripts.google_measurement.os.name", "nt")
    @patch("scripts.google_measurement.fetch_json",
           return_value={"accessToken": "ci-only-windows-token"})
    @patch("scripts.google_measurement.subprocess.run")
    def test_windows_powershell_install_uses_gcloud_cmd(self, run, fetch):
        run.return_value = subprocess.CompletedProcess([], 0, "ci-user-token\n", "")
        self.assertEqual(lab_access_token(GA4_SCOPE), "ci-only-windows-token")
        self.assertEqual(run.call_args.args[0][0], "gcloud.cmd")

    @patch.dict(os.environ, {"NEXUS_GA4_KEYLESS_IMPERSONATION": "1"})
    def test_gsc_scope_is_not_eligible(self):
        with self.assertRaises(ValueError):
            lab_access_token(GSC_SCOPE)

    @patch.dict(os.environ, {"NEXUS_GA4_KEYLESS_IMPERSONATION": "invalid"})
    def test_invalid_opt_in_is_rejected(self):
        with self.assertRaises(ValueError):
            lab_access_token(GA4_SCOPE)

    @patch.dict(os.environ, {"NEXUS_GA4_KEYLESS_IMPERSONATION": "1"})
    @patch("scripts.google_measurement.subprocess.run")
    def test_no_user_token_on_cli_failure(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "sensitive output")
        with self.assertRaisesRegex(RuntimeError, "Active gcloud user login required") as err:
            lab_access_token(GA4_SCOPE)
        self.assertNotIn("sensitive output", str(err.exception))

    @patch.dict(os.environ, {"NEXUS_GA4_KEYLESS_IMPERSONATION": "1"})
    @patch("scripts.google_measurement.fetch_json", side_effect=OSError("sensitive"))
    @patch("scripts.google_measurement.subprocess.run")
    def test_iam_denial_is_generic_and_no_secret_is_logged(self, run, fetch):
        run.return_value = subprocess.CompletedProcess([], 0, "user-secret-token\n", "")
        with self.assertRaisesRegex(RuntimeError, "TokenCreator") as err:
            lab_access_token(GA4_SCOPE)
        self.assertNotIn("user-secret-token", str(err.exception))
        self.assertNotIn("sensitive", str(err.exception))


if __name__ == "__main__":
    unittest.main()
