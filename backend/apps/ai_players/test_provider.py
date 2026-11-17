import json
import ssl
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from django.test import SimpleTestCase, override_settings

from . import client, readiness, services
from .provider import configuration


@override_settings(
    AI_PROVIDER="anthropic", AI_PLAYERS_ENABLED=True,
    ANTHROPIC_AUTH_TOKEN="test-only", ANTHROPIC_MODEL="test-sonnet",
    ANTHROPIC_BASE_URL="https://gateway.example", ANTHROPIC_API_VERSION="2023-06-01",
    OPENAI_API_KEY="", OPENAI_EXTRA_HEADERS={"x-openai-actor-authorization": "enabled"},
    AI_MAX_OUTPUT_TOKENS=500, AI_REQUEST_TIMEOUT=30,
)
class AnthropicProviderTests(SimpleTestCase):
    def setUp(self):
        self.persona = SimpleNamespace(
            public_profile=lambda: {"first_name": "Test"}, bio="test", personality="friendly",
            speaking_style="brief", backstory="", boundaries="",
        )
        self.reply = {"action": "chat", "text": "سلام", "choice": "TRUTH"}

    def response(self, reply=None):
        return {"type": "message", "stop_reason": "tool_use", "content": [
            {"type": "tool_use", "name": "game_reply", "input": reply or self.reply}],
            "usage": {"input_tokens": 20, "output_tokens": 5}}

    def generate(self, response):
        with patch("apps.ai_players.client.urlopen") as http:
            http.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            result = client.generate(self.persona, {"allowed_actions": ["chat", "confirm"]}, "confirm")
            tls = http.call_args.kwargs["context"]
            self.assertTrue(tls.check_hostname)
            self.assertEqual(tls.verify_mode, ssl.CERT_REQUIRED)
        return result, http.call_args.args[0]

    def test_messages_contract_and_game_action(self):
        (reply, usage), request = self.generate(self.response())
        self.assertEqual(request.full_url, "https://gateway.example/v1/messages")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
        self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")
        self.assertIsNone(request.get_header("X-openai-actor-authorization"))
        body = json.loads(request.data)
        self.assertEqual(body["model"], "test-sonnet")
        self.assertEqual(body["max_tokens"], 500)
        self.assertNotIn("store", body)
        self.assertEqual(body["tool_choice"]["name"], "game_reply")
        schema = body["tools"][0]["input_schema"]
        self.assertEqual(schema["properties"]["action"]["enum"], ["chat", "confirm"])
        self.assertEqual(schema["properties"]["choice"]["enum"], ["TRUTH"])
        self.assertEqual(reply, self.reply)
        self.assertEqual(usage["input_tokens"], 20)

    @override_settings(ANTHROPIC_BASE_URL="https://gateway.example/v1/")
    def test_base_url_with_version(self):
        _, request = self.generate(self.response())
        self.assertEqual(request.full_url, "https://gateway.example/v1/messages")

    def test_refusal_truncation_wrong_tool_and_bad_actions_are_rejected(self):
        cases = [
            ({"stop_reason": "refusal"}, "refusal"),
            ({"stop_reason": "max_tokens"}, "incomplete_response"),
            ({"stop_reason": "tool_use", "content": []}, "invalid_response"),
            ({"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "other"}]}, "invalid_response"),
            (self.response({**self.reply, "action": "delete"}), "invalid_action"),
            (self.response({**self.reply, "choice": "DARE"}), "invalid_action"),
            (self.response({**self.reply, "text": ""}), "invalid_action"),
            ([], "invalid_response"),
        ]
        for response, expected in cases:
            with self.subTest(expected=expected), self.assertRaises(client.ProviderError) as caught:
                self.generate(response)
            self.assertEqual(caught.exception.code, expected)

    def test_failures_do_not_expose_provider_body(self):
        for status, retryable in [(401, False), (429, True), (503, True)]:
            with self.subTest(status=status), patch("apps.ai_players.client.urlopen", side_effect=HTTPError(
                "https://gateway.example/v1/messages", status, "secret provider details", {}, None
            )), self.assertRaises(client.ProviderError) as caught:
                client.generate(self.persona, {}, "chat")
            self.assertEqual(str(caught.exception), f"http_{status}")
            self.assertEqual(caught.exception.retryable, retryable)

    def test_availability_requires_selected_provider_credentials_and_model(self):
        self.assertTrue(services.available())
        for values in [{"ANTHROPIC_MODEL": ""}, {"ANTHROPIC_AUTH_TOKEN": ""}, {"AI_PROVIDER": "unknown"}]:
            with self.subTest(values=values), override_settings(**values):
                self.assertFalse(services.available())
                with patch("apps.ai_players.client.urlopen") as http, self.assertRaises(client.ProviderError):
                    client.generate(self.persona, {}, "chat")
                http.assert_not_called()

    def test_readiness_is_invalidated_when_provider_settings_change(self):
        original = readiness.provider_key()
        for values in [{"ANTHROPIC_MODEL": "other"}, {"ANTHROPIC_AUTH_TOKEN": "replacement"},
                       {"ANTHROPIC_BASE_URL": "https://other.example"}, {"AI_PROVIDER": "openai"}]:
            with self.subTest(values=values), override_settings(**values):
                self.assertNotEqual(readiness.provider_key(), original)

    @override_settings(AI_PROVIDER="openai", OPENAI_API_KEY="openai-test", OPENAI_MODEL="existing-model",
                       OPENAI_BASE_URL="https://openai.example/v1")
    def test_existing_openai_provider_still_works(self):
        response = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(self.reply)}]}]}
        (reply, _), request = self.generate(response)
        self.assertEqual(request.full_url, "https://openai.example/v1/responses")
        self.assertEqual(json.loads(request.data)["model"], "existing-model")
        self.assertEqual(reply, self.reply)
        self.assertEqual(configuration()["model"], "existing-model")
