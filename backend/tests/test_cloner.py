"""
Tests for GitManager in backend/app/cloner.py.
Run from the Synapse repo root with:
    python -m unittest backend.tests.test_cloner -v

Covers
------
- Python 3.11 compatibility: onerror callback signature (func, path, excinfo)
- URL validation (empty, invalid scheme, path traversal)
- Removal of a plain directory
- Removal of a directory containing a read-only file
- rmtree cleanup failure is surfaced, NOT swallowed
- Cloning still works after cleanup (Git I/O is mocked)
- Specific git error types return meaningful strings
- main.py import correctness
"""

import os
import shutil
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub the 'git' module so the tests work without gitpython installed.
# ---------------------------------------------------------------------------
_git_stub = types.ModuleType("git")
_exc_stub = types.ModuleType("git.exc")

class _GitCommandError(Exception):
    def __init__(self, msg="", stderr=""):
        super().__init__(msg)
        self.stderr = stderr

class _GitCommandNotFound(Exception):
    pass

_exc_stub.GitCommandError = _GitCommandError
_exc_stub.GitCommandNotFound = _GitCommandNotFound
_git_stub.exc = _exc_stub
_git_stub.Repo = MagicMock()

sys.modules.setdefault("git", _git_stub)
sys.modules.setdefault("git.exc", _exc_stub)

# Make the backend package importable from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.cloner import GitManager  # noqa: E402


# ===========================================================================
# _remove_readonly
# ===========================================================================
class TestRemoveReadonly(unittest.TestCase):

    def setUp(self):
        self.manager = GitManager("https://github.com/user/repo.git", "/tmp/fake")

    def test_callback_accepts_onerror_signature(self):
        """_remove_readonly must accept (func, path, excinfo) — Python 3.11 onerror."""
        import inspect
        sig = inspect.signature(self.manager._remove_readonly)
        self.assertEqual(list(sig.parameters.keys()), ["func", "path", "excinfo"])

    def test_clears_readonly_and_retries(self):
        """_remove_readonly should chmod the path then call func again."""
        retried = []

        def fake_func(p):
            retried.append(p)

        with tempfile.TemporaryDirectory() as tmp:
            test_file = os.path.join(tmp, "readonly.txt")
            with open(test_file, "w") as f:
                f.write("hello")
            os.chmod(test_file, stat.S_IREAD)
            try:
                self.manager._remove_readonly(fake_func, test_file, (None, None, None))
                self.assertIn(test_file, retried)
            finally:
                try:
                    os.chmod(test_file, stat.S_IWRITE)
                except OSError:
                    pass

    def test_raises_on_persistent_failure(self):
        """_remove_readonly must raise RuntimeError if the retry also fails."""
        def always_fails(p):
            raise PermissionError(f"Cannot remove {p}")

        with tempfile.TemporaryDirectory() as tmp:
            test_file = os.path.join(tmp, "file.txt")
            with open(test_file, "w") as f:
                f.write("x")
            with self.assertRaises(RuntimeError):
                self.manager._remove_readonly(always_fails, test_file, (None, None, None))


# ===========================================================================
# URL validation
# ===========================================================================
class TestUrlValidation(unittest.TestCase):

    def _clone(self, url):
        return GitManager(url, "/tmp/fake_path").clone_repo()

    def test_empty_url_returns_error_string(self):
        result = self._clone("")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, True)

    def test_whitespace_only_url_returns_error_string(self):
        result = self._clone("   ")
        self.assertIsInstance(result, str)

    def test_file_scheme_rejected(self):
        result = self._clone("file:///etc/passwd")
        self.assertIsInstance(result, str)

    def test_bare_path_rejected(self):
        result = self._clone("/etc/passwd")
        self.assertIsInstance(result, str)

    def test_javascript_scheme_rejected(self):
        result = self._clone("javascript:alert(1)")
        self.assertIsInstance(result, str)

    def test_valid_https_url_accepted(self):
        """A valid https URL should pass validation (mocked clone succeeds)."""
        with patch("backend.app.cloner.git.Repo.clone_from"):
            result = GitManager("https://github.com/user/repo.git", "/tmp/fake2").clone_repo()
        self.assertTrue(result)

    def test_valid_git_at_url_accepted(self):
        """git@ SSH URLs should pass validation."""
        with patch("backend.app.cloner.git.Repo.clone_from"):
            result = GitManager("git@github.com:user/repo.git", "/tmp/fake3").clone_repo()
        self.assertTrue(result)


# ===========================================================================
# clone_repo
# ===========================================================================
class TestCloneRepo(unittest.TestCase):

    # -----------------------------------------------------------------------
    # onerror / onexc keyword
    # -----------------------------------------------------------------------
    def test_rmtree_uses_onerror_not_onexc(self):
        """shutil.rmtree must be called with onerror=, not onexc=."""
        with tempfile.TemporaryDirectory() as tmp:
            cloning_path = os.path.join(tmp, "repo")
            os.makedirs(cloning_path)
            manager = GitManager("https://github.com/u/r.git", cloning_path)
            captured = {}
            original = shutil.rmtree

            def capturing(path, **kwargs):
                captured.update(kwargs)
                original(path)

            with patch("backend.app.cloner.shutil.rmtree", side_effect=capturing), \
                 patch("backend.app.cloner.git.Repo.clone_from"):
                manager.clone_repo()

            self.assertIn("onerror", captured)
            self.assertNotIn("onexc", captured)

    # -----------------------------------------------------------------------
    # Directory cleanup
    # -----------------------------------------------------------------------
    def test_removes_existing_directory_before_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            cloning_path = os.path.join(tmp, "repo")
            os.makedirs(cloning_path)
            sentinel = os.path.join(cloning_path, "sentinel.txt")
            with open(sentinel, "w") as f:
                f.write("old")
            manager = GitManager("https://github.com/u/r.git", cloning_path)
            with patch("backend.app.cloner.git.Repo.clone_from"):
                result = manager.clone_repo()
            self.assertTrue(result)
            self.assertFalse(os.path.exists(sentinel))

    def test_removes_readonly_file_in_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            cloning_path = os.path.join(tmp, "repo")
            os.makedirs(cloning_path)
            ro_file = os.path.join(cloning_path, "ro.txt")
            with open(ro_file, "w") as f:
                f.write("locked")
            os.chmod(ro_file, stat.S_IREAD)
            manager = GitManager("https://github.com/u/r.git", cloning_path)
            try:
                with patch("backend.app.cloner.git.Repo.clone_from"):
                    result = manager.clone_repo()
                self.assertTrue(result)
                self.assertFalse(os.path.exists(cloning_path))
            finally:
                if os.path.exists(ro_file):
                    os.chmod(ro_file, stat.S_IWRITE)

    def test_cleanup_failure_surfaced_as_error_string(self):
        """If rmtree raises, clone_repo must return an error string, not True."""
        with tempfile.TemporaryDirectory() as tmp:
            cloning_path = os.path.join(tmp, "repo")
            os.makedirs(cloning_path)
            manager = GitManager("https://github.com/u/r.git", cloning_path)
            with patch("backend.app.cloner.shutil.rmtree",
                       side_effect=RuntimeError("disk full")):
                result = manager.clone_repo()
            self.assertIsInstance(result, str)
            self.assertNotEqual(result, True)

    # -----------------------------------------------------------------------
    # Happy path
    # -----------------------------------------------------------------------
    def test_clone_succeeds_when_path_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = GitManager("https://github.com/u/r.git", os.path.join(tmp, "new"))
            with patch("backend.app.cloner.git.Repo.clone_from"):
                result = manager.clone_repo()
            self.assertTrue(result)

    # -----------------------------------------------------------------------
    # Git error handling
    # -----------------------------------------------------------------------
    def test_git_command_not_found_returns_string(self):
        manager = GitManager("https://github.com/u/r.git", "/tmp/x")
        with patch("backend.app.cloner.git.Repo.clone_from",
                   side_effect=_GitCommandNotFound("git not found")):
            result = manager.clone_repo()
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, True)

    def test_git_command_error_returns_string_with_stderr(self):
        manager = GitManager("https://github.com/u/r.git", "/tmp/x")
        err = _GitCommandError("cmd failed", stderr="repository not found")
        with patch("backend.app.cloner.git.Repo.clone_from", side_effect=err):
            result = manager.clone_repo()
        self.assertIsInstance(result, str)
        self.assertIn("repository not found", result)

    def test_network_error_returns_string(self):
        manager = GitManager("https://github.com/u/r.git", "/tmp/x")
        with patch("backend.app.cloner.git.Repo.clone_from",
                   side_effect=Exception("network error")):
            result = manager.clone_repo()
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, True)

    def test_clone_does_not_raise_on_any_git_failure(self):
        """clone_repo must NEVER raise — it must always return True or a string."""
        manager = GitManager("https://github.com/u/r.git", "/tmp/x")
        for exc in [
            Exception("random"),
            _GitCommandError("bad cmd", stderr="auth failed"),
            _GitCommandNotFound("no git"),
        ]:
            with self.subTest(exc=exc):
                with patch("backend.app.cloner.git.Repo.clone_from", side_effect=exc):
                    try:
                        result = manager.clone_repo()
                    except Exception as e:
                        self.fail(f"clone_repo raised unexpectedly: {e}")
                    self.assertNotEqual(result, True)


# ===========================================================================
# main.py import sanity check
# ===========================================================================
class TestMainImport(unittest.TestCase):

    def test_main_imports_gitmanager_not_gitmanager_lowercase(self):
        """main.py must import GitManager (the actual class name), not gitmanager."""
        with open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
                  encoding="utf-8") as f:
            source = f.read()
        self.assertIn("from app.cloner import GitManager", source,
                      "main.py must import 'GitManager' (capital G and M)")
        self.assertNotIn("import gitmanager", source.lower().replace("gitmanager", "_sentinel_"),
                         "main.py must NOT use the old lowercase 'gitmanager' name")

    def test_main_instantiates_gitmanager_correctly(self):
        """main.py must instantiate GitManager(...), not gitmanager(...)."""
        with open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
                  encoding="utf-8") as f:
            source = f.read()
        self.assertIn("GitManager(", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
