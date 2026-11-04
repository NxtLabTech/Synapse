"""API integration tests for FastAPI endpoints."""

from unittest.mock import patch
import pytest
from fastapi import HTTPException

from app.cloner import GitManager
from app.schemas import RepoRequest
from main import (
    JOBS_STORE,
    analyze_repository,
    clone_repository,
    get_job_ast,
    get_job_metadata,
    root_status,
)


def run_sync(coro):
    """Drive a coroutine to completion synchronously without an event loop."""
    while True:
        try:
            coro.send(None)
        except StopIteration as e:
            return e.value


def test_root_health_endpoint():
    """Verify root health check endpoint returns online status."""
    res = run_sync(root_status())
    assert res["status"] == "online"
    assert "Synapse" in res["service"]
    assert "version" in res


def test_clone_invalid_url():
    """Verify malformed repository URLs raise HTTP 400."""
    with pytest.raises(HTTPException) as exc_info:
        run_sync(clone_repository(RepoRequest(url="not-a-valid-git-url")))

    assert exc_info.value.status_code == 400
    assert "Invalid Git URL format" in exc_info.value.detail


def test_clone_injection_attempt():
    """Verify Git CLI argument injection via API is blocked with HTTP 400."""
    with pytest.raises(HTTPException) as exc_info:
        run_sync(clone_repository(RepoRequest(url="--upload-pack=evil")))

    assert exc_info.value.status_code == 400
    assert "cannot begin with a dash" in exc_info.value.detail


def test_clone_and_query_flow(temp_repo):
    """Verify successful clone returns backward-compatible message, metadata, and ast."""
    async def mock_clone():
        return True

    with patch.object(GitManager, "clone_repo_async", side_effect=mock_clone):
        with patch.object(
            GitManager,
            "__init__",
            lambda self, remote_repo_url, base_storage_dir=None, depth=1, job_id="job_test_123": (
                setattr(self, "cloning_path", temp_repo) or setattr(self, "job_id", "job_test_123")
            ),
        ):
            res = run_sync(
                clone_repository(RepoRequest(url="https://github.com/hasini-06/Synapse.git", depth=1))
            )
            # Verify backward compatibility field
            assert res.message == "Successfully cloned the repository."
            assert res.job_id == "job_test_123"
            assert res.repo_name is not None
            assert res.metadata.stats.total_files >= 5
            assert res.symbols_count > 0

            # Query metadata endpoint
            metadata = run_sync(get_job_metadata("job_test_123"))
            assert metadata.stats.total_files >= 5
            assert metadata.repo_info.has_readme is True

            # Query AST symbols without filter
            all_symbols = run_sync(get_job_ast("job_test_123"))
            assert all_symbols["total_symbols"] > 0

            # Query AST symbols filtered by language
            py_symbols = run_sync(get_job_ast("job_test_123", language="python"))
            assert py_symbols["total_symbols"] > 0
            assert all(s.language == "python" for s in py_symbols["symbols"])

            # Query AST symbols filtered by type
            func_symbols = run_sync(get_job_ast("job_test_123", type="function"))
            assert all(s.type.value == "function" for s in func_symbols["symbols"])


def test_analyze_pipeline(temp_repo):
    """Verify POST /analyze runs the full pipeline."""
    async def mock_clone():
        return True

    with patch.object(GitManager, "clone_repo_async", side_effect=mock_clone):
        with patch.object(
            GitManager,
            "__init__",
            lambda self, remote_repo_url, base_storage_dir=None, depth=1, job_id="job_analyze_456": (
                setattr(self, "cloning_path", temp_repo) or setattr(self, "job_id", "job_analyze_456")
            ),
        ):
            res = run_sync(
                analyze_repository(
                    RepoRequest(url="https://github.com/hasini-06/Synapse.git", depth=1, parse_ast=True)
                )
            )
            assert res.job_id == "job_analyze_456"
            assert res.metadata.stats.total_files >= 5
            assert res.ast_analysis is not None
            assert res.ast_analysis.stats.total_symbols_extracted > 0


def test_nonexistent_job_returns_404():
    """Verify querying an unknown job ID raises HTTP 404."""
    with pytest.raises(HTTPException) as exc_info:
        run_sync(get_job_metadata("nonexistent-job-id"))

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()
