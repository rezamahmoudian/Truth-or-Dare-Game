import unittest

from preflight import validate


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "DJANGO_SECRET_KEY": "a-random-test-secret-12345678901234567890",
            "DATABASE_URL": "postgresql://test:secret@db:5432/test",
            "REDIS_URL": "redis://:secret@redis:6379/0",
            "ALLOWED_HOSTS": "example.com",
            "CSRF_TRUSTED_ORIGINS": "https://example.com",
        }

    def test_valid_configuration(self):
        self.assertEqual(validate(self.env), [])

    def test_missing_variables_have_actionable_errors(self):
        errors = " ".join(validate({}))
        for name in self.env:
            self.assertIn(name, errors)

    def test_rejects_development_settings(self):
        for name, value in (("DEBUG", "True"), ("ALLOWED_HOSTS", "*"),
                            ("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me"),
                            ("UVICORN_WORKERS", "0"), ("CELERY_CONCURRENCY", "33")):
            with self.subTest(name=name):
                self.assertTrue(validate({**self.env, name: value}))

    def test_rejects_wrong_services_without_echoing_credentials(self):
        for name in ("DATABASE_URL", "REDIS_URL"):
            errors = validate({**self.env, name: "https://test:private-password@host"})
            self.assertTrue(errors)
            self.assertNotIn("private-password", " ".join(errors))


if __name__ == "__main__":
    unittest.main()
