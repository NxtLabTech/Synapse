"""Unit tests for the repository metadata extraction module."""

import os
import json
import pytest

from app.metadata import MetadataExtractor, extract_repository_metadata


def test_empty_repository(empty_temp_dir):
    """Verify metadata extraction handles an empty directory without errors."""
    metadata = extract_repository_metadata(empty_temp_dir)
    assert metadata.stats.total_files == 0
    assert metadata.stats.total_lines == 0
    assert len(metadata.dependencies) == 0
    assert metadata.repo_info.has_readme is False


def test_repo_stats(temp_repo):
    """Verify file count, LOC calculation, and language breakdown."""
    extractor = MetadataExtractor(temp_repo)
    stats = extractor.extract_stats()

    assert stats.total_files >= 5
    assert stats.total_lines > 0
    assert stats.total_code_lines > 0
    assert stats.total_blank_lines > 0

    # Verify detected languages
    assert "Python" in stats.language_distribution
    assert "JavaScript" in stats.language_distribution
    assert "Markdown" in stats.language_distribution
    assert "JSON" in stats.language_distribution

    # Verify percentages sum close to 100
    total_pct = sum(stat.percentage for stat in stats.language_distribution.values())
    assert 99.0 <= total_pct <= 100.1


def test_package_json_parsing(temp_repo):
    """Verify npm dependencies and devDependencies are correctly parsed."""
    extractor = MetadataExtractor(temp_repo)
    manifests = extractor.extract_dependencies()

    npm_manifest = next((m for m in manifests if m.manifest_type == "npm"), None)
    assert npm_manifest is not None
    assert npm_manifest.file_path == "package.json"

    dep_names = {d.name: d for d in npm_manifest.dependencies}
    assert "react" in dep_names
    assert dep_names["react"].category == "direct"
    assert dep_names["react"].version == "^18.2.0"

    assert "vite" in dep_names
    assert dep_names["vite"].category == "dev"


def test_requirements_txt_parsing(temp_repo):
    """Verify Python pip requirements are parsed with versions and stripped comments."""
    extractor = MetadataExtractor(temp_repo)
    manifests = extractor.extract_dependencies()

    pip_manifest = next((m for m in manifests if m.manifest_type == "pip"), None)
    assert pip_manifest is not None

    dep_names = {d.name: d for d in pip_manifest.dependencies}
    assert "fastapi" in dep_names
    assert dep_names["fastapi"].version == ">=0.100.0"

    assert "pydantic" in dep_names
    assert dep_names["pydantic"].version == "==2.5.0"

    assert "uvicorn" in dep_names
    assert dep_names["uvicorn"].version is None

    # Comment line should be excluded
    assert "# comment" not in dep_names


def test_pyproject_toml_parsing(empty_temp_dir):
    """Verify standard PEP 621 pyproject.toml dependencies are extracted."""
    toml_content = b"""
[project]
name = "demo-pkg"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0",
    "click"
]

[project.optional-dependencies]
test = [
    "pytest>=7.0.0"
]
"""
    toml_path = os.path.join(empty_temp_dir, "pyproject.toml")
    with open(toml_path, "wb") as f:
        f.write(toml_content)

    extractor = MetadataExtractor(empty_temp_dir)
    manifests = extractor.extract_dependencies()

    toml_manifest = next((m for m in manifests if m.manifest_type == "pyproject"), None)
    assert toml_manifest is not None

    dep_map = {d.name: d for d in toml_manifest.dependencies}
    assert "requests" in dep_map
    assert dep_map["requests"].version == ">=2.28.0"
    assert "click" in dep_map
    assert "pytest" in dep_map
    assert dep_map["pytest"].category == "optional:test"


def test_git_metadata_extraction(temp_repo):
    """Verify Git commit info, author, date, and README detection."""
    extractor = MetadataExtractor(temp_repo)
    git_info = extractor.extract_git_info()

    assert git_info.latest_commit is not None
    assert git_info.latest_commit.author == "Synapse Bot"
    assert git_info.latest_commit.email == "bot@synapse.dev"
    assert "Initial test commit" in git_info.latest_commit.message
    assert git_info.has_readme is True
    assert git_info.readme_path == "README.md"


def test_malformed_json_manifest(empty_temp_dir):
    """Verify corrupted manifest files do not crash the extractor."""
    bad_json = os.path.join(empty_temp_dir, "package.json")
    with open(bad_json, "w") as f:
        f.write("{ invalid json syntax ...")

    extractor = MetadataExtractor(empty_temp_dir)
    manifests = extractor.extract_dependencies()

    # Manifest should be skipped and warning logged
    assert len(manifests) == 0
    assert len(extractor.warnings) > 0


def test_directory_summary(temp_repo):
    """Verify directory structure summary produces relative paths."""
    extractor = MetadataExtractor(temp_repo)
    summary = extractor.extract_directory_summary()

    assert "main.py" in summary
    assert "README.md" in summary
    assert "package.json" in summary

