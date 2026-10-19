from django.conf import settings
from django.test import SimpleTestCase

from core.api.wachalltag import MAX_ATTACHMENT_BYTES


class WachalltagUploadLimitTests(SimpleTestCase):
    def test_attachment_binary_limit_is_five_mebibytes(self):
        self.assertEqual(MAX_ATTACHMENT_BYTES, 5 * 1024 * 1024)

    def test_django_request_limit_can_carry_maximum_base64_photo(self):
        # Base64 expands binary data to 4/3 plus JSON field/header overhead.
        encoded = 4 * ((MAX_ATTACHMENT_BYTES + 2) // 3)
        required = encoded + 64 * 1024
        configured = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        self.assertIsNotNone(configured)
        self.assertGreaterEqual(
            configured,
            required,
            'DATA_UPLOAD_MAX_MEMORY_SIZE is smaller than the documented '
            '5 MiB attachment request including base64/JSON overhead.',
        )
