import unittest
from scripts.verify_release import verify_project


class ReleaseIdentityTests(unittest.TestCase):
    def test_release_identity_passes(self) -> None:
        ok, errors = verify_project()
        self.assertTrue(ok, errors)


if __name__ == '__main__':
    unittest.main()
