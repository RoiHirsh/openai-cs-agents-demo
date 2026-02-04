import os
import unittest
from unittest.mock import patch


class TestTwilioWhatsAppWebhook(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure env vars exist for config loading.
        os.environ["TWILIO_ACCOUNT_SID"] = "AC_test"
        os.environ["TWILIO_AUTH_TOKEN"] = "auth_test"
        os.environ["PUBLIC_BASE_URL"] = "https://example.com"
        os.environ["TWILIO_WHATSAPP_FROM"] = "whatsapp:+14155238886"

    def test_invalid_signature_is_rejected(self):
        from main import app
        from fastapi.testclient import TestClient

        with patch("main.validate_twilio_signature", return_value=False):
            client = TestClient(app)
            res = client.post(
                "/twilio/whatsapp/webhook",
                data={
                    "From": "whatsapp:+15551234567",
                    "To": "whatsapp:+14155238886",
                    "Body": "hello",
                    "MessageSid": "SM123",
                },
                headers={"X-Twilio-Signature": "bad"},
            )
            self.assertEqual(res.status_code, 403)

    def test_valid_signature_sends_reply_via_rest(self):
        from main import app
        from fastapi.testclient import TestClient

        with (
            patch("main.validate_twilio_signature", return_value=True),
            patch("main.send_whatsapp_message", return_value="SM_OUT") as send_mock,
            patch("server.AirlineServer.process_plaintext_message", return_value=("OK", "thread_1")),
        ):
            client = TestClient(app)
            res = client.post(
                "/twilio/whatsapp/webhook",
                data={
                    "From": "whatsapp:+15551234567",
                    "To": "whatsapp:+14155238886",
                    "Body": "hello",
                    "MessageSid": "SM123",
                },
                headers={"X-Twilio-Signature": "good"},
            )
            self.assertEqual(res.status_code, 200)
            send_mock.assert_called()
            called_kwargs = send_mock.call_args.kwargs
            self.assertEqual(called_kwargs["to"], "whatsapp:+15551234567")
            self.assertEqual(called_kwargs["body"], "OK")


class TestGreetingOrderingTemplateMimic(unittest.IsolatedAsyncioTestCase):
    async def test_first_message_injects_perry_greeting_before_user(self):
        from server import AirlineServer

        s = AirlineServer()
        assistant_text, thread_id = await s.process_plaintext_message(
            thread_id=None,
            user_text="call",
        )
        self.assertTrue(thread_id)
        # Verify state stored assistant greeting before the first user message.
        state = s._state_for_thread(thread_id)
        self.assertGreaterEqual(len(state.input_items), 2)
        self.assertEqual(state.input_items[0].get("role"), "assistant")
        self.assertIn("My name is Perry", state.input_items[0].get("content", ""))
        self.assertEqual(state.input_items[1].get("role"), "user")
        self.assertEqual(state.input_items[1].get("content"), "call")
        # Ensure we got some assistant output back.
        self.assertIsInstance(assistant_text, str)


if __name__ == "__main__":
    unittest.main()

