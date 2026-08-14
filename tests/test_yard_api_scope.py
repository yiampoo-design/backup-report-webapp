from __future__ import annotations

import unittest
from unittest.mock import patch

from yard_api import collect_drive_sharesync


class _Client:
    instances = []

    def __init__(self, url, verify_ssl=True):
        self.url = url
        self.verify_ssl = verify_ssl
        self.calls = []
        self.__class__.instances.append(self)

    def login(self, username, password):
        self.login_args = (username, password)

    def discover(self, names):
        return {name: object() for name in names}

    def call(self, api, method, params=None, version=None):
        self.calls.append((api, method, params))
        if method == "list_sync_history":
            return {"history_items": []}
        if "Connection" in api:
            return {"connections": [{"id": 1}]}
        return {"sessions": [{
            "local_share": "Backup_A",
            "remote_share": "Backup_A",
            "status": "uptodate",
            "enabled": True,
            "sync_direction": 0,
        }]}

    def logout(self):
        self.logged_out = True


class YardApiScopeTests(unittest.TestCase):
    def setUp(self):
        _Client.instances.clear()

    def test_uses_only_submitted_remote_config_and_sharesync_apis(self):
        config = {
            "url": "https://yard.example:5001",
            "username": "yard-user",
            "verify_ssl": False,
        }
        with patch("yard_api.SynologyClient", _Client):
            result = collect_drive_sharesync(config, "yard-password")
        client = _Client.instances[0]
        self.assertEqual(client.url, config["url"])
        self.assertEqual(client.login_args, ("yard-user", "yard-password"))
        self.assertEqual(result["connection_count"], 1)
        self.assertEqual(result["up_to_date_count"], 1)
        self.assertTrue(result["healthy"])
        self.assertTrue(all("SynologyDriveShareSync" in api for api, _method, _params in client.calls))


if __name__ == "__main__":
    unittest.main()
