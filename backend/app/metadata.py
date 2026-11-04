"""Repository metadata extraction engine for Synapse.

Extracts file statistics, language distribution, dependency manifests,
Git repository metadata, and directory structure safely and efficiently.
"""

from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import git

from app.schemas import (
    DependencyItem,
    DependencyManifest,
    GitCommitInfo,
    GitRepoInfo,
    LanguageStat,
    RepoMetadata,
    RepoStats,
)

# Directories to exclude from analysis to prevent skewed metrics and performance issues
IGNORED_DIRS: Set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    "bin",
    "obj",
    ".bundle",
    "vendor",
    ".yarn",
    ".pnpm-store",
}

# Recognized binary extensions to avoid attempting text/line counting
BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat", ".iso",
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".db", ".sqlite", ".sqlite3",
}

# Mapping of file extensions to canonical language names
EXTENSION_LANGUAGE_MAP: Dict[str, str] = {
    ".py": "Python",
    ".pyw": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    ".hh": "C++",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".sass": "CSS",
    ".less": "CSS",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".toml": "TOML",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".cs": "C#",
    ".lua": "Lua",
    ".dart": "Dart",
    ".r": "R",
}

# Common readme filenames in priority order
README_CANDIDATES: List[str] = [
    "README.md",
    "README.markdown",
    "README.rst",
    "README.txt",
    "README",
]


class MetadataExtractor:
    """Extracts structural, linguistic, dependency, and Git metadata from a repository."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self.real_repo_path = os.path.realpath(self.repo_path)
        self.warnings: List[str] = []

    def _is_safe_path(self, target_path: str) -> bool:
        """Ensure a file path does not escape the repository boundary via symlinks."""
        try:
            real_target = os.path.realpath(target_path)
            # Use commonpath to check directory ancestry safely across platforms
            return os.path.commonpath([self.real_repo_path, real_target]) == self.real_repo_path
        except (ValueError, OSError):
            return False

    def _is_binary_file(self, file_path: str) -> bool:
        """Check if file has a binary extension or contains null bytes in initial chunk."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in BINARY_EXTENSIONS:
            return True

        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                return b"\0" in chunk
        except OSError:
            return True

    def _count_lines(self, file_path: str) -> Tuple[int, int, int]:
        """Count total lines, code lines, and blank lines in a text file.

        Returns (total_lines, code_lines, blank_lines).
        """
        total = 0
        blank = 0
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    total += 1
                    if not line.strip():
                        blank += 1
        except OSError as e:
            self.warnings.append(f"Could not read {file_path}: {e}")
            return (0, 0, 0)

        code = total - blank
        return (total, code, blank)

    def extract_stats(self) -> RepoStats:
        """Traverse the repository filesystem to compute structural and language metrics."""
        total_files = 0
        total_directories = 0
        total_lines = 0
        total_code_lines = 0
        total_blank_lines = 0

        extension_counts: Dict[str, int] = {}
        language_files: Dict[str, int] = {}
        language_lines: Dict[str, Tuple[int, int, int]] = {}  # total, code, blank

        visited_paths: Set[str] = set()

        if not os.path.exists(self.repo_path):
            self.warnings.append(f"Repository path does not exist: {self.repo_path}")
            return RepoStats()

        for root, dirs, files in os.walk(self.repo_path, followlinks=False):
            # Prune ignored directories in-place so os.walk does not traverse them
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".git")]
            total_directories += len(dirs)

            for file_name in files:
                file_path = os.path.join(root, file_name)

                # Skip unverified symlinks escaping repository root
                if not self._is_safe_path(file_path):
                    continue

                real_path = os.path.realpath(file_path)
                if real_path in visited_paths:
                    continue
                visited_paths.add(real_path)

                total_files += 1

                ext = os.path.splitext(file_name)[1].lower()
                extension_key = ext if ext else "[no-ext]"
                extension_counts[extension_key] = extension_counts.get(extension_key, 0) + 1

                # Language detection
                language = EXTENSION_LANGUAGE_MAP.get(ext)
                if language:
                    language_files[language] = language_files.get(language, 0) + 1

                    # Count lines for non-binary source files
                    if not self._is_binary_file(file_path):
                        f_total, f_code, f_blank = self._count_lines(file_path)
                        total_lines += f_total
                        total_code_lines += f_code
                        total_blank_lines += f_blank

                        prev_total, prev_code, prev_blank = language_lines.get(language, (0, 0, 0))
                        language_lines[language] = (
                            prev_total + f_total,
                            prev_code + f_code,
                            prev_blank + f_blank,
                        )

        # Build language distribution with percentages
        language_distribution: Dict[str, LanguageStat] = {}
        for lang, count in language_files.items():
            l_tot, l_code, l_blank = language_lines.get(lang, (0, 0, 0))
            percentage = round((l_tot / total_lines * 100), 2) if total_lines > 0 else 0.0
            language_distribution[lang] = LanguageStat(
                files=count,
                lines=l_tot,
                code_lines=l_code,
                blank_lines=l_blank,
                percentage=percentage,
            )

        return RepoStats(
            total_files=total_files,
            total_directories=total_directories,
            total_lines=total_lines,
            total_code_lines=total_code_lines,
            total_blank_lines=total_blank_lines,
            extension_counts=dict(sorted(extension_counts.items(), key=lambda item: item[1], reverse=True)),
            language_distribution=dict(sorted(language_distribution.items(), key=lambda item: item[1].lines, reverse=True)),
        )

    def extract_dependencies(self) -> List[DependencyManifest]:
        """Detect and parse dependency manifests across the repository."""
        manifests: List[DependencyManifest] = []

        if not os.path.exists(self.repo_path):
            return manifests

        for root, dirs, files in os.walk(self.repo_path, followlinks=False):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

            for file_name in files:
                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, self.repo_path).replace("\\", "/")

                if file_name == "package.json":
                    manifest = self._parse_package_json(full_path, rel_path)
                    if manifest:
                        manifests.append(manifest)

                elif file_name == "requirements.txt":
                    manifest = self._parse_requirements_txt(full_path, rel_path)
                    if manifest:
                        manifests.append(manifest)

                elif file_name == "pyproject.toml":
                    manifest = self._parse_pyproject_toml(full_path, rel_path)
                    if manifest:
                        manifests.append(manifest)

        return manifests

    def _parse_package_json(self, file_path: str, rel_path: str) -> Optional[DependencyManifest]:
        """Safely parse npm package.json for production and development dependencies."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return None

            dependencies: List[DependencyItem] = []
            for name, ver in data.get("dependencies", {}).items():
                dependencies.append(DependencyItem(name=str(name), version=str(ver), category="direct"))
            for name, ver in data.get("devDependencies", {}).items():
                dependencies.append(DependencyItem(name=str(name), version=str(ver), category="dev"))
            for name, ver in data.get("peerDependencies", {}).items():
                dependencies.append(DependencyItem(name=str(name), version=str(ver), category="peer"))

            return DependencyManifest(
                manifest_type="npm",
                file_path=rel_path,
                dependencies=dependencies,
            )
        except Exception as e:
            self.warnings.append(f"Failed to parse {rel_path}: {e}")
            return None

    def _parse_requirements_txt(self, file_path: str, rel_path: str) -> Optional[DependencyManifest]:
        """Safely parse Python requirements.txt file."""
        try:
            dependencies: List[DependencyItem] = []
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or line.startswith("-"):
                        continue

                    # Strip trailing inline comments
                    if " #" in line:
                        line = line.split(" #")[0].strip()

                    # Match package name and version specification
                    match = re.match(r"^([A-Za-z0-9_.\-]+)\s*([~>=<!=].*)?$", line)
                    if match:
                        pkg_name = match.group(1)
                        version_spec = match.group(2).strip() if match.group(2) else None
                        dependencies.append(DependencyItem(name=pkg_name, version=version_spec, category="direct"))
                    else:
                        dependencies.append(DependencyItem(name=line, version=None, category="direct"))

            return DependencyManifest(
                manifest_type="pip",
                file_path=rel_path,
                dependencies=dependencies,
            )
        except Exception as e:
            self.warnings.append(f"Failed to parse {rel_path}: {e}")
            return None

    def _parse_pyproject_toml(self, file_path: str, rel_path: str) -> Optional[DependencyManifest]:
        """Safely parse pyproject.toml for standard PEP 621 or Poetry dependencies."""
        try:
            import tomllib
            with open(file_path, "rb") as f:
                data = tomllib.load(f)

            dependencies: List[DependencyItem] = []

            # Standard PEP 621 dependencies
            project_section = data.get("project", {})
            if isinstance(project_section, dict):
                for dep in project_section.get("dependencies", []):
                    if isinstance(dep, str):
                        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*([~>=<!=].*)?$", dep.strip())
                        if match:
                            dependencies.append(DependencyItem(name=match.group(1), version=match.group(2), category="direct"))
                        else:
                            dependencies.append(DependencyItem(name=dep.strip(), version=None, category="direct"))

                for group, deps in project_section.get("optional-dependencies", {}).items():
                    if isinstance(deps, list):
                        for dep in deps:
                            if isinstance(dep, str):
                                match = re.match(r"^([A-Za-z0-9_.\-]+)\s*([~>=<!=].*)?$", dep.strip())
                                if match:
                                    dependencies.append(DependencyItem(name=match.group(1), version=match.group(2), category=f"optional:{group}"))
                                else:
                                    dependencies.append(DependencyItem(name=dep.strip(), version=None, category=f"optional:{group}"))

            # Poetry dependencies
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            if isinstance(poetry_deps, dict):
                for name, ver in poetry_deps.items():
                    if name.lower() != "python":
                        version_str = str(ver) if not isinstance(ver, dict) else str(ver.get("version", ""))
                        dependencies.append(DependencyItem(name=name, version=version_str, category="direct"))

            return DependencyManifest(
                manifest_type="pyproject",
                file_path=rel_path,
                dependencies=dependencies,
            )
        except Exception as e:
            self.warnings.append(f"Failed to parse {rel_path}: {e}")
            return None

    def extract_git_info(self) -> GitRepoInfo:
        """Extract Git repository information including branches and the latest commit."""
        repo_name = os.path.basename(self.repo_path)
        current_branch: Optional[str] = None
        default_branch: Optional[str] = None
        latest_commit: Optional[GitCommitInfo] = None

        repo = None
        try:
            repo = git.Repo(self.repo_path)

            # Determine repository name from remote origin if present
            try:
                remote_url = repo.remotes.origin.url
                clean_url = remote_url.rstrip("/").removesuffix(".git")
                repo_name = clean_url.split("/")[-1].split(":")[-1]
            except Exception:
                pass

            # Current branch (handles detached HEAD gracefully)
            try:
                current_branch = repo.active_branch.name
            except TypeError:
                current_branch = f"detached-at-{repo.head.commit.hexsha[:7]}"
            except Exception:
                current_branch = None

            # Default branch resolution
            try:
                for ref in repo.remotes.origin.refs:
                    if ref.name.endswith("/HEAD"):
                        default_branch = ref.target.name.split("/")[-1]
                        break
            except Exception:
                pass

            if not default_branch:
                # Fallback to local common names if available
                branch_names = [b.name for b in repo.branches]
                for candidate in ["main", "master", "trunk", "development"]:
                    if candidate in branch_names:
                        default_branch = candidate
                        break

            # Latest commit info
            try:
                commit = repo.head.commit
                latest_commit = GitCommitInfo(
                    hash=commit.hexsha,
                    author=str(commit.author.name or "Unknown"),
                    email=str(commit.author.email or ""),
                    date=datetime.fromtimestamp(commit.committed_date).isoformat(),
                    message=commit.message.strip(),
                )
            except Exception:
                latest_commit = None

        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            pass
        except Exception as e:
            self.warnings.append(f"Git introspection warning: {e}")
        finally:
            if repo is not None:
                repo.close()

        # Check README availability
        has_readme = False
        readme_path: Optional[str] = None
        for candidate in README_CANDIDATES:
            candidate_path = os.path.join(self.repo_path, candidate)
            if os.path.exists(candidate_path) and os.path.isfile(candidate_path):
                has_readme = True
                readme_path = candidate
                break

        return GitRepoInfo(
            name=repo_name,
            current_branch=current_branch,
            default_branch=default_branch,
            latest_commit=latest_commit,
            has_readme=has_readme,
            readme_path=readme_path,
        )

    def extract_directory_summary(self, max_depth: int = 2) -> List[str]:
        """Produce a clean summary of repository directory layout up to a maximum depth."""
        summary: List[str] = []
        if not os.path.exists(self.repo_path):
            return summary

        base_depth = self.repo_path.rstrip(os.sep).count(os.sep)

        for root, dirs, files in os.walk(self.repo_path, followlinks=False):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            current_depth = root.rstrip(os.sep).count(os.sep) - base_depth

            if current_depth > max_depth:
                continue

            rel_root = os.path.relpath(root, self.repo_path).replace("\\", "/")
            if rel_root != ".":
                summary.append(f"{rel_root}/")

            for f in sorted(files):
                # Filter out ignored internal files
                if f.startswith(".git"):
                    continue
                file_rel = os.path.relpath(os.path.join(root, f), self.repo_path).replace("\\", "/")
                summary.append(file_rel)

        return summary[:200]  # Cap to prevent excessive response payload sizes

    def extract_all(self) -> RepoMetadata:
        """Execute complete metadata extraction across the repository."""
        stats = self.extract_stats()
        repo_info = self.extract_git_info()
        dependencies = self.extract_dependencies()
        directory_summary = self.extract_directory_summary()

        return RepoMetadata(
            repo_info=repo_info,
            stats=stats,
            dependencies=dependencies,
            directory_summary=directory_summary,
            warnings=self.warnings,
        )


def extract_repository_metadata(repo_path: str) -> RepoMetadata:
    """Convenience function to extract metadata from a given repository path."""
    extractor = MetadataExtractor(repo_path)
    return extractor.extract_all()
