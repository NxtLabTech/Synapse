"""Safe, isolated, and non-blocking Git repository cloner for Synapse.

Provides URL sanitization, path traversal protection, isolated job workspaces,
shallow cloning (depth=1), and async execution via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import stat
import uuid
from typing import Optional, Tuple
from urllib.parse import urlparse

import git


class GitCloneError(Exception):
    """Base exception for cloning failures."""
    pass


class InvalidUrlError(GitCloneError):
    """Raised when the repository URL is invalid or malformed."""
    pass


class RepositoryNotFoundError(GitCloneError):
    """Raised when the remote repository is not found."""
    pass


class AuthenticationError(GitCloneError):
    """Raised when authentication fails for the remote repository."""
    pass


class NetworkError(GitCloneError):
    """Raised when a network or DNS failure occurs during clone."""
    pass


# Strict regex for permitted Git repository URLs
GIT_URL_PATTERNS = [
    # HTTPS / HTTP
    re.compile(r"^https?://[a-zA-Z0-9.\-_~%]+(:[0-9]+)?(/[a-zA-Z0-9.\-_~%]+)+(\.git)?/?$"),
    # SSH git@
    re.compile(r"^git@[a-zA-Z0-9.\-_~]+:[a-zA-Z0-9.\-_~%]+/[a-zA-Z0-9.\-_~%]+(\.git)?$"),
    # SSH ssh://
    re.compile(r"^ssh://[a-zA-Z0-9.\-_~%@]+(:[0-9]+)?(/[a-zA-Z0-9.\-_~%]+)+(\.git)?/?$"),
]


def sanitize_and_validate_url(url: str) -> str:
    """Validate repository URL format and prevent CLI argument injection."""
    if not url or not isinstance(url, str):
        raise InvalidUrlError("Repository URL must be a non-empty string.")

    cleaned_url = url.strip()

    # Prevent Git command option injection (e.g. --upload-pack, -u)
    if cleaned_url.startswith("-"):
        raise InvalidUrlError("Repository URL cannot begin with a dash or flag.")

    # Disallow control characters and newlines
    if any(c in cleaned_url for c in ("\n", "\r", "\0", "\t")):
        raise InvalidUrlError("Repository URL contains forbidden whitespace or control characters.")

    # Match against approved schemas
    matches = any(pattern.match(cleaned_url) for pattern in GIT_URL_PATTERNS)
    if not matches:
        raise InvalidUrlError(
            f"Invalid Git URL format: '{redact_credentials(cleaned_url)}'. "
            "Must be a valid HTTPS or SSH Git URL."
        )

    return cleaned_url


def redact_credentials(url: str) -> str:
    """Mask embedded user passwords or access tokens from URLs."""
    if not url:
        return ""
    # Redact http(s)://user:token@domain.com
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


class GitManager:
    """Manages isolated and safe Git cloning operations."""

    def __init__(
        self,
        remote_repo_url: str,
        cloning_path: Optional[str] = None,
        base_storage_dir: str = "./cloned_repos",
        depth: Optional[int] = 1,
        job_id: Optional[str] = None,
    ):
        self.raw_url = remote_repo_url
        self.validated_url = sanitize_and_validate_url(remote_repo_url)
        self.depth = depth
        self.job_id = job_id or uuid.uuid4().hex[:12]
        self.base_storage_dir = os.path.abspath(base_storage_dir)

        if cloning_path:
            self.cloning_path = os.path.abspath(cloning_path)
        else:
            self.cloning_path = os.path.abspath(os.path.join(self.base_storage_dir, self.job_id))

        self._ensure_safe_cloning_path()

    def _ensure_safe_cloning_path(self) -> None:
        """Prevent directory traversal attacks outside the designated storage root."""
        real_target = os.path.realpath(self.cloning_path)
        real_base = os.path.realpath(self.base_storage_dir)

        # Allow legacy ./cloned_repo if explicitly passed, otherwise confine to base_storage_dir
        if not real_target.startswith(real_base) and not real_target.endswith("cloned_repo"):
            raise GitCloneError(f"Target path escapes storage directory boundary: {self.cloning_path}")

    @staticmethod
    def _remove_readonly(func, path, excinfo):
        """Error handler for shutil.rmtree on Windows to clear read-only permissions."""
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    def _cleanup_target_directory(self) -> None:
        """Safely delete target directory if it already exists."""
        if os.path.exists(self.cloning_path):
            shutil.rmtree(self.cloning_path, onexc=self._remove_readonly)

    def clone_repo(self) -> bool:
        """Execute the Git clone synchronously.

        Returns True on success, raises specific GitCloneError subclasses on failure.
        """
        # Ensure parent directory exists
        parent_dir = os.path.dirname(self.cloning_path)
        os.makedirs(parent_dir, exist_ok=True)

        self._cleanup_target_directory()

        clone_kwargs = {}
        if self.depth and self.depth > 0:
            clone_kwargs["depth"] = self.depth

        repo = None
        try:
            repo = git.Repo.clone_from(
                url=self.validated_url,
                to_path=self.cloning_path,
                **clone_kwargs,
            )
            return True

        except git.GitCommandError as e:
            # Clean up partial / corrupted clone
            self._cleanup_target_directory()
            stderr = f"{e.stderr or ''} {str(e)}".lower()

            if "not found" in stderr or "repository not found" in stderr or "404" in stderr:
                raise RepositoryNotFoundError(
                    f"Repository not found at '{redact_credentials(self.validated_url)}'."
                ) from e
            elif "authentication failed" in stderr or "permission denied" in stderr or "could not read username" in stderr:
                raise AuthenticationError(
                    "Authentication failed. Please verify credentials or repository permissions."
                ) from e
            elif "could not resolve host" in stderr or "failed to connect" in stderr:
                raise NetworkError("Network error: Could not reach Git remote host.") from e
            else:
                raise GitCloneError(f"Git clone failed: {e.stderr.strip() if e.stderr else str(e)}") from e

        except Exception as e:
            self._cleanup_target_directory()
            raise GitCloneError(f"Unexpected error during cloning: {str(e)}") from e
        finally:
            if repo is not None:
                repo.close()

    async def clone_repo_async(self) -> bool:
        """Run the blocking clone_repo call inside a worker thread to keep FastAPI responsive."""
        return await asyncio.to_thread(self.clone_repo)

    def cleanup(self) -> None:
        """Clean up the isolated cloned repository directory."""
        self._cleanup_target_directory()


# Backward-compatible alias for existing imports
gitmanager = GitManager
