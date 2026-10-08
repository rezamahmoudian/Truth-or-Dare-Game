import uuid
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.chat import presence


class AppPresenceTests(SimpleTestCase):
    def test_multiple_tabs_disconnect_and_stale_heartbeat(self):
        # Separate Redis key: never touch live presence when running tests.
        key = f"test:online:{uuid.uuid4().hex}"
        client = presence._client()
        try:
            with patch.object(presence, "APP_ONLINE_KEY", key):
                with patch("apps.chat.presence.time.time", return_value=100):
                    presence.mark_app_online(11, "tab-one")
                    presence.mark_app_online(11, "tab-two")
                    presence.mark_app_online(22, "other")
                    self.assertEqual(set(presence.app_online_ids()), {11, 22})
                    presence.mark_app_offline(11, "tab-one")
                    self.assertEqual(set(presence.app_online_ids()), {11, 22})
                with patch("apps.chat.presence.time.time", return_value=130):
                    presence.mark_app_online(11, "tab-two")
                with patch("apps.chat.presence.time.time", return_value=146):
                    self.assertEqual(presence.app_online_ids(), [11])
                    presence.mark_app_offline(11, "tab-two")
                    self.assertEqual(presence.app_online_ids(), [])
        finally:
            client.delete(key)
