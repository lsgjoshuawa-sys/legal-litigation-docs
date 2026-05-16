import json
import unittest

from legal_agent_gui.plain_text_lists import (
    json_list_from_identifier_text,
    json_list_from_plain_text,
    plain_text_from_list_storage,
)


class PlainTextListTest(unittest.TestCase):
    def test_displays_legacy_json_list_as_plain_lines(self):
        self.assertEqual(plain_text_from_list_storage('["Duty", "Breach"]'), "Duty\nBreach")

    def test_saves_plain_lines_as_structured_list(self):
        self.assertEqual(json.loads(json_list_from_plain_text("Duty\nBreach\nCausation")), ["Duty", "Breach", "Causation"])

    def test_saves_identifier_text_from_commas_or_spaces(self):
        self.assertEqual(json.loads(json_list_from_identifier_text("1, 2 5")), ["1", "2", "5"])


if __name__ == "__main__":
    unittest.main()
