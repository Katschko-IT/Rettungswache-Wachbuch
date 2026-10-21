"""Parent-owned finite-number input edge regression, separate from fixed 8 tests."""
from django.test import TestCase
from django.urls import reverse
from core import test_review_acceptance as acceptance

class CryptoNumberEdges(TestCase):
    setUp = acceptance.CryptoAcceptance.setUp

    def test_overflowing_json_number_returns_400_not_500(self):
        # These are valid JSON number spellings; Python parses them as infinities.
        for body in ['{"kdf_iterations":1e999}', '{"kdf_iterations":-1e999}']:
            with self.subTest(body=body):
                response=self.client.post(reverse('crypto_setup'),body,content_type='application/json')
                self.assertEqual(response.status_code,400)
