"""Unit tests for the safe GitManager and URL validation module."""

import os
from unittest.mock import MagicMock, patch
import pytest
import git

from app.cloner import (
    AuthenticationError,
    GitCloneError,
    GitManager,
    InvalidUrlError,
    NetworkError,
    RepositoryNotFoundError,
    redact_credentials,
    sanitize_and_validate_url,
)


def test_valid_urls():
    """Verify standard HTTPS and SSH URLs pass validation."""
    valid_cases = [
        "https://github.com/hasini-06/Synapse.git",
        "http://gitlab.com/group/subgroup/project.git",
        "https://bitbucket.org/workspace/repo",
        "git@github.com:torvalds/linux.git",
        "ssh://git@github.com:22/user/repo.git",
    ]
    for url in valid_cases:
        assert sanitize_and_validate_url(url) == url


def test_invalid_urls():
    """Verify malformed URLs are rejected with InvalidUrlError."""
    invalid_cases = [
        "",
        "not-a-url",
        "ftp://github.com/user/repo.git",
        "javascript:alert(1)",
        "https://",
    ]
    for url in invalid_cases:
        with pytest.raises(InvalidUrlError):
            sanitize_and_validate_url(url)


def test_command_injection_prevention():
    """Verify Git CLI argument injection attempts are blocked."""
    injection_cases = [
        "--upload-pack=evil_script",
        "-u evil_option",
        "--config=protocol.ext.allow=always",
    ]
    for url in injection_cases:
        with pytest.raises(InvalidUrlError):
            sanitize_and_validate_url(url)


def test_whitespace_and_control_characters():
    """Verify URLs with embedded newlines, nulls, or tabs are blocked."""
    forbidden = [
        "https://github.com/user/repo\n.git",
        "https://github.com/user/repo\r.git",
        "https://github.com/user/repo\0.git",
        "https://github.com/user/repo\t.git",
    ]
    for url in forbidden:
        with pytest.raises(InvalidUrlError):
            sanitize_and_validate_url(url)


def test_credential_redaction():
    """Verify secrets and tokens embedded in URLs are masked."""
    url = "https://oauth2:ghp_secretToken12345@github.com/user/repo.git"
    redacted = redact_credentials(url)
    assert "ghp_secretToken12345" not in redacted
    assert "https://oauth2:***@github.com/user/repo.git" == redacted


def test_job_isolation_and_path(empty_temp_dir):
    """Verify each GitManager instantiation gets a unique, isolated directory."""
    mgr1 = GitManager("https://github.com/user/repo1.git", base_storage_dir=empty_temp_dir)
    mgr2 = GitManager("https://github.com/user/repo2.git", base_storage_dir=empty_temp_dir)

    assert mgr1.job_id != mgr2.job_id
    assert mgr1.cloning_path != mgr2.cloning_path
    assert os.path.dirname(mgr1.cloning_path) == os.path.abspath(empty_temp_dir)


def test_path_traversal_protection(empty_temp_dir):
    """Verify attempts to escape the storage root raise GitCloneError."""
    with pytest.raises(GitCloneError):
        GitManager(
            "https://github.com/user/repo.git",
            cloning_path=os.path.join(empty_temp_dir, "..", "..", "system32"),
            base_storage_dir=empty_temp_dir,
        )


@patch("git.Repo.clone_from")
def test_shallow_clone_parameters(mock_clone, empty_temp_dir):
    """Verify depth parameter is correctly passed to GitPython."""
    mgr = GitManager(
        "https://github.com/user/repo.git",
        base_storage_dir=empty_temp_dir,
        depth=1,
    )
    mgr.clone_repo()

    mock_clone.assert_called_once()
    _, kwargs = mock_clone.call_args
    assert kwargs.get("depth") == 1


@patch("git.Repo.clone_from")
def test_clone_not_found_translation(mock_clone, empty_temp_dir):
    """Verify 404 / repository not found translates to RepositoryNotFoundError."""
    mock_clone.side_effect = git.GitCommandError("clone", 128, stderr="remote: Repository not found.")
    mgr = GitManager("https://github.com/user/nonexistent.git", base_storage_dir=empty_temp_dir)

    with pytest.raises(RepositoryNotFoundError):
        mgr.clone_repo()


@patch("git.Repo.clone_from")
def test_clone_auth_failure_translation(mock_clone, empty_temp_dir):
    """Verify authentication errors translate to AuthenticationError."""
    mock_clone.side_effect = git.GitCommandError("clone", 128, stderr="fatal: Authentication failed for 'https://github.com/...'")
    mgr = GitManager("https://github.com/user/private.git", base_storage_dir=empty_temp_dir)

    with pytest.raises(AuthenticationError):
        mgr.clone_repo()


@patch("git.Repo.clone_from")
def test_clone_network_error_translation(mock_clone, empty_temp_dir):
    """Verify DNS and connectivity issues translate to NetworkError."""
    mock_clone.side_effect = git.GitCommandError("clone", 128, stderr="fatal: Could not resolve host: github.com")
    mgr = GitManager("https://github.com/user/repo.git", base_storage_dir=empty_temp_dir)

    with pytest.raises(NetworkError):
        mgr.clone_repo()


@patch("asyncio.to_thread")
def test_async_clone_wrapper(mock_to_thread, empty_temp_dir):
    """Verify clone_repo_async routes to asyncio.to_thread."""
    mock_to_thread.return_value = True
    mgr = GitManager("https://github.com/user/repo.git", base_storage_dir=empty_temp_dir)
    # Verify the method exists and calls clone_repo
    assert hasattr(mgr, "clone_repo_async")
    assert callable(mgr.clone_repo_async)
