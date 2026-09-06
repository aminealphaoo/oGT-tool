from django.test import Client, TestCase, override_settings


@override_settings(CRON_SECRET="test-cron-secret")
class CronEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_ping_root_is_public(self):
        response = self.client.get("/ping/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "awake")

    def test_api_cron_ping_is_public(self):
        response = self.client.get("/api/cron/ping/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "awake")

    def test_stale_without_secret_is_forbidden(self):
        response = self.client.get("/api/cron/stale/")
        self.assertEqual(response.status_code, 403)

    def test_stale_with_secret_ok(self):
        response = self.client.get(
            "/api/cron/stale/",
            HTTP_X_CRON_SECRET="test-cron-secret",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["task"], "stale")

    def test_public_intake_is_reachable_without_login(self):
        response = self.client.get("/public/")
        self.assertEqual(response.status_code, 200)
