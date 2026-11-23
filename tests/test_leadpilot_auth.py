"""Isolated auth test; never changes the user's real CRM SQLite database."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AuthSecurityTests(unittest.TestCase):
    def test_auth_flow_in_isolated_database(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'auth_smoke_tests.py')],
            cwd=ROOT, capture_output=True, text=True, timeout=50,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('isolated authentication checks', completed.stdout)

if __name__ == '__main__':
    unittest.main()
