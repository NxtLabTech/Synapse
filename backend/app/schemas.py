"""Pydantic schemas for Synapse code intelligence platform.

Defines structured models for repository metadata, AST parsed symbols,
and API request/response payloads.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Metadata Schemas
# ============================================================================

class LanguageStat(BaseModel):
    """Aggregated statistics for a specific programming or markup language."""
    files: int = 0
    lines: int = 0
    blank_lines: int = 0
    code_lines: int = 0
    percentage: float = 0.0


class DependencyItem(BaseModel):
    """A detected software package dependency."""
    name: str
    version: Optional[str] = None
    category: str = "direct"  # direct, dev, peer, optional


class DependencyManifest(BaseModel):
    """Dependencies discovered within a single manifest file."""
    manifest_type: str  # npm, pip, pyproject, etc.
    file_path: str
    dependencies: List[DependencyItem] = Field(default_factory=list)


class GitCommitInfo(BaseModel):
    """Metadata regarding the most recent Git commit."""
    hash: str
    author: str
    email: Optional[str] = None
    date: str
    message: str


class GitRepoInfo(BaseModel):
    """High-level repository version control information."""
    name: str
    current_branch: Optional[str] = None
    default_branch: Optional[str] = None
    latest_commit: Optional[GitCommitInfo] = None
    has_readme: bool = False
    readme_path: Optional[str] = None


class RepoStats(BaseModel):
    """Aggregated numerical statistics of the repository."""
    total_files: int = 0
    total_directories: int = 0
    total_lines: int = 0
    total_code_lines: int = 0
    total_blank_lines: int = 0
    extension_counts: Dict[str, int] = Field(default_factory=dict)
    language_distribution: Dict[str, LanguageStat] = Field(default_factory=dict)


class RepoMetadata(BaseModel):
    """Complete metadata payload for an analyzed repository."""
    repo_info: GitRepoInfo
    stats: RepoStats
    dependencies: List[DependencyManifest] = Field(default_factory=list)
    directory_summary: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ============================================================================
# AST Parsing Schemas
# ============================================================================

class SymbolType(str, Enum):
    """Types of extracted source code entities."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    IMPORT = "import"
    EXPORT = "export"


class ExtractedSymbol(BaseModel):
    """A single symbol (function, class, import, etc.) discovered in AST."""
    name: str
    type: SymbolType
    file_path: str
    start_line: int
    end_line: int
    parameters: Optional[List[str]] = None
    language: str


class FileParseResult(BaseModel):
    """Parse results and extracted symbols for a single source file."""
    file_path: str
    language: str
    symbols: List[ExtractedSymbol] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ParseStats(BaseModel):
    """Summary metrics of the AST parsing operation."""
    total_files_parsed: int = 0
    total_symbols_extracted: int = 0
    symbols_by_type: Dict[str, int] = Field(default_factory=dict)
    symbols_by_language: Dict[str, int] = Field(default_factory=dict)


class RepositoryParseResult(BaseModel):
    """Comprehensive AST parse outcome for an entire repository."""
    stats: ParseStats
    files: List[FileParseResult] = Field(default_factory=list)
    unsupported_files: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


# ============================================================================
# API Requests & Responses
# ============================================================================

class RepoRequest(BaseModel):
    """Incoming request to clone and analyze a repository."""
    url: str = Field(..., description="Remote Git repository URL")
    depth: Optional[int] = Field(default=1, description="Shallow clone depth (1 by default)")
    parse_ast: bool = Field(default=True, description="Whether to run AST symbol extraction")


class CloneResponse(BaseModel):
    """Response returned upon completion of clone / initial indexing."""
    message: str
    job_id: Optional[str] = None
    repo_name: Optional[str] = None
    metadata: Optional[RepoMetadata] = None
    symbols_count: Optional[int] = None


class AnalysisResponse(BaseModel):
    """Full repository analysis response."""
    job_id: str
    repo_name: str
    url: str
    cloned_at: str
    metadata: RepoMetadata
    ast_analysis: Optional[RepositoryParseResult] = None

