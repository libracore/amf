from __future__ import unicode_literals

import unittest

from amf.amf.utils.client_description_metadata_cleanup_2026 import clean_client_description


class TestClientDescriptionMetadataCleanup2026(unittest.TestCase):
	def test_original_generated_markup(self):
		value = (
			"<!-- AMF:PURCHASED:CLIENT START -->"
			"<div><strong>RVM mini</strong></div>"
			"<!-- AMF:PURCHASED:FACTS START --><div>Valve body.</div>"
			"<!-- AMF:PURCHASED:FACTS END -->"
			"<!-- AMF:PURCHASED:BASIS START -->researched"
			"<!-- AMF:PURCHASED:BASIS END -->"
			"<div><br></div><div><strong>Item reference:</strong> RVM.1</div>"
			"<!-- AMF:PURCHASED:CLIENT END -->"
		)
		self.assertEqual(
			"<div><strong>RVM mini</strong></div><div>Valve body.</div>"
			"<div><br></div><div><strong>Item reference:</strong> RVM.1</div>",
			clean_client_description(value),
		)

	def test_sanitized_legacy_variants(self):
		self.assertEqual(
			"<div>Name</div><div>Facts</div><div><br></div><div>Item reference: 1</div>",
			clean_client_description(
				"<div>Name</div><div>Facts</div>erp-catalog"
				"<div><br></div><div>Item reference: 1</div>"
			),
		)
		self.assertEqual(
			"<div>Name</div><div>Facts</div><div>Item reference: 1</div>",
			clean_client_description(
				"<div>Name</div><div>Facts</div><div>self-fallback</div>"
				"<div>Item reference: 1</div>"
			),
		)

	def test_clean_text_is_unchanged_and_reruns_are_stable(self):
		value = "<div>Custom product name</div><div>Customer-specific details.</div>"
		self.assertEqual(value, clean_client_description(value))
		self.assertEqual(value, clean_client_description(clean_client_description(value)))


if __name__ == "__main__":
	unittest.main()
