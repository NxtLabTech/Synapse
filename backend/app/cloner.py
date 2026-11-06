import git
import os
import re
import shutil
import stat


# Only allow http/https/ssh GitHub (and similar) URLs.
# This prevents path traversal and local-filesystem access via file:// or bare paths.
_ALLOWED_URL_PATTERN = re.compile(
    r"^(https?://|git@|ssh://git@)[^\s]+"
)


class GitManager:
    def __init__(self, remote_repo_url, cloning_path):
        self.remote_repo_url = remote_repo_url
        self.cloning_path = cloning_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_url(self):
        """
        Reject obviously unsafe or unsupported URL schemes before touching
        the filesystem or spawning a git subprocess.

        Returns an error string on failure, or None when the URL looks fine.
        """
        url = self.remote_repo_url.strip()
        if not url:
            return "Repository URL must not be empty."
        if not _ALLOWED_URL_PATTERN.match(url):
            return (
                "Invalid repository URL. "
                "Only https://, git@, and ssh://git@ URLs are accepted."
            )
        return None

    def _remove_readonly(self, func, path, excinfo):
        """
        Error handler for shutil.rmtree (Python 3.11 ``onerror`` signature).

        Called when rmtree cannot remove a file or directory. Attempts to
        clear the read-only bit and retry. If the retry also fails the
        exception is re-raised so the caller is aware of the failure.

        Args:
            func:    The os function that raised the error (os.unlink / os.rmdir).
            path:    The path that could not be removed.
            excinfo: The sys.exc_info() tuple (type, value, traceback).
        """
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            raise RuntimeError(
                f"Failed to remove '{path}' after clearing read-only flag: {e}"
            ) from e

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clone_repo(self):
        """
        Clone the remote repository into ``self.cloning_path``.

        Returns:
            True  – cloning succeeded.
            str   – a human-readable error message describing the failure.
        """
        # 1. Validate URL before touching the filesystem or git.
        url_error = self._validate_url()
        if url_error:
            print(f"URL validation failed: {url_error}")
            return url_error

        # 2. Remove any pre-existing clone directory.
        if os.path.exists(self.cloning_path):
            print("The cloning path already exists. Removing it to avoid conflicts.")
            try:
                # Use 'onerror' for Python 3.11 compatibility ('onexc' was added in 3.12)
                shutil.rmtree(self.cloning_path, onerror=self._remove_readonly)
            except RuntimeError as e:
                msg = f"Could not clean up existing directory: {e}"
                print(msg)
                return msg

        # 3. Clone.
        try:
            print(f"Cloning repository from {self.remote_repo_url}...")
            git.Repo.clone_from(self.remote_repo_url, self.cloning_path)
            print("Successfully cloned the repository.")
            return True
        except git.exc.GitCommandNotFound:
            msg = "Git is not installed or not on PATH."
            print(f"An error occurred: {msg}")
            return msg
        except git.exc.GitCommandError as e:
            # stderr from git is the most useful part of the message.
            stderr = (e.stderr or "").strip()
            msg = f"Git command failed: {stderr or str(e)}"
            print(f"An error occurred: {msg}")
            return msg
        except Exception as e:
            msg = f"Unexpected error during cloning: {e}"
            print(f"An error occurred: {msg}")
            return msg