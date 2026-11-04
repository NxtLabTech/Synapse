"""Main FastAPI application for Synapse code intelligence platform.

Exposes REST API endpoints for repository cloning, metadata extraction,
and Tree-sitter AST symbol analysis.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from app.cloner import (
    AuthenticationError,
    GitCloneError,
    GitManager,
    InvalidUrlError,
    NetworkError,
    RepositoryNotFoundError,
    gitmanager,
)
from app.metadata import extract_repository_metadata
from app.parser import parse_repository_ast
from app.schemas import (
    AnalysisResponse,
    CloneResponse,
    ExtractedSymbol,
    RepoMetadata,
    RepoRequest,
    RepositoryParseResult,
)

app = FastAPI(
    title="Synapse API",
    description="Full-stack code intelligence engine for repository cloning, metadata extraction, and AST analysis.",
    version="0.2.0",
)

# Enable CORS for local Vite development servers and containerized frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory registry for job metadata and storage paths
JOBS_STORE: Dict[str, Dict[str, Any]] = {}
STORAGE_ROOT = os.path.abspath("./cloned_repos")


@app.get("/", tags=["Health"])
async def root_status():
    """Health and service info check."""
    return {
        "service": "Synapse Code Intelligence API",
        "status": "online",
        "version": "0.2.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/clone", response_model=CloneResponse, tags=["Cloning"])
async def clone_repository(request: RepoRequest):
    """Clone a Git repository into an isolated directory and perform initial indexing.

    Preserves 100% backward compatibility with legacy clients while returning
    extended metadata, job IDs, and symbol counts.
    """
    try:
        # Initialize cloner with unique job ID and configured depth
        repo_cloner = GitManager(
            remote_repo_url=request.url,
            base_storage_dir=STORAGE_ROOT,
            depth=request.depth or 1,
        )

        # Execute non-blocking clone in a worker thread
        await repo_cloner.clone_repo_async()

        # Run metadata extraction
        metadata = extract_repository_metadata(repo_cloner.cloning_path)

        # Run AST parsing if requested
        symbols_count = 0
        ast_result = None
        if request.parse_ast:
            ast_result = parse_repository_ast(repo_cloner.cloning_path)
            symbols_count = ast_result.stats.total_symbols_extracted

        # Store in registry
        JOBS_STORE[repo_cloner.job_id] = {
            "url": request.url,
            "path": repo_cloner.cloning_path,
            "cloned_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata,
            "ast": ast_result,
        }

        return CloneResponse(
            message="Successfully cloned the repository.",
            job_id=repo_cloner.job_id,
            repo_name=metadata.repo_info.name,
            metadata=metadata,
            symbols_count=symbols_count,
        )

    except InvalidUrlError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RepositoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except NetworkError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except GitCloneError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during repository analysis: {str(e)}",
        )


@app.post("/analyze", response_model=AnalysisResponse, tags=["Analysis"])
async def analyze_repository(request: RepoRequest):
    """Full-featured analysis pipeline: clone repository, extract metadata, and parse AST symbols."""
    try:
        repo_cloner = GitManager(
            remote_repo_url=request.url,
            base_storage_dir=STORAGE_ROOT,
            depth=request.depth or 1,
        )

        await repo_cloner.clone_repo_async()

        metadata = extract_repository_metadata(repo_cloner.cloning_path)
        ast_result = parse_repository_ast(repo_cloner.cloning_path) if request.parse_ast else None

        cloned_at = datetime.now(timezone.utc).isoformat()
        JOBS_STORE[repo_cloner.job_id] = {
            "url": request.url,
            "path": repo_cloner.cloning_path,
            "cloned_at": cloned_at,
            "metadata": metadata,
            "ast": ast_result,
        }

        return AnalysisResponse(
            job_id=repo_cloner.job_id,
            repo_name=metadata.repo_info.name,
            url=request.url,
            cloned_at=cloned_at,
            metadata=metadata,
            ast_analysis=ast_result,
        )

    except InvalidUrlError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RepositoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except NetworkError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except GitCloneError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/jobs/{job_id}/metadata", response_model=RepoMetadata, tags=["Analysis"])
async def get_job_metadata(job_id: str):
    """Retrieve extracted metadata for a previously analyzed job."""
    job = JOBS_STORE.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found or has expired.",
        )
    return job["metadata"]


@app.get("/jobs/{job_id}/ast", tags=["Analysis"])
async def get_job_ast(
    job_id: str,
    language: Optional[str] = Query(None, description="Filter by language (e.g. python, javascript)"),
    type: Optional[str] = Query(None, description="Filter by symbol type (function, class, method, import)"),
):
    """Retrieve AST parsed symbols with optional language and type filtering."""
    job = JOBS_STORE.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found or has expired.",
        )

    ast_analysis: Optional[RepositoryParseResult] = job.get("ast")
    if not ast_analysis:
        return {"symbols": [], "stats": {}}

    target_lang = language.lower() if isinstance(language, str) else None
    target_type = type.lower() if isinstance(type, str) else None

    filtered_symbols = []
    for f in ast_analysis.files:
        if target_lang and f.language.lower() != target_lang:
            continue
        for sym in f.symbols:
            if target_type and sym.type.value.lower() != target_type:
                continue
            filtered_symbols.append(sym)

    return {
        "job_id": job_id,
        "total_symbols": len(filtered_symbols),
        "symbols": filtered_symbols,
        "stats": ast_analysis.stats,
    }
