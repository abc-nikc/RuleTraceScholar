"""Safety and serialization checks for the read-only inspection API."""

import unittest

from app.routers.inspection import _filter_for_paper


class InspectionTests(unittest.TestCase):
    def test_paper_filter_uses_json_escaping(self):
        expression = _filter_for_paper('paper" || paper_id != "safe')
        self.assertEqual(expression, 'paper_id == "paper\\\" || paper_id != \\\"safe"')


if __name__ == "__main__":
    unittest.main()
