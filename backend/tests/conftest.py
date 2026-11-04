"""Pytest test fixtures for Synapse test suite."""

import os
import shutil
import tempfile
import pytest
import git


@pytest.fixture
def temp_repo():
    """Create a temporary initialized Git repository with sample files."""
    temp_dir = tempfile.mkdtemp(prefix="synapse_test_repo_")
    repo = git.Repo.init(temp_dir)

    # Configure committer
    repo.config_writer().set_value("user", "name", "Synapse Bot").release()
    repo.config_writer().set_value("user", "email", "bot@synapse.dev").release()

    # Create sample files
    readme_path = os.path.join(temp_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# Sample Project\n\nThis is a sample project for testing.\n")

    py_file = os.path.join(temp_dir, "main.py")
    with open(py_file, "w", encoding="utf-8") as f:
        f.write("import os\n\ndef add(a: int, b: int) -> int:\n    return a + b\n\nclass Calculator:\n    def multiply(self, x, y):\n        return x * y\n")

    req_file = os.path.join(temp_dir, "requirements.txt")
    with open(req_file, "w", encoding="utf-8") as f:
        f.write("fastapi>=0.100.0\npydantic==2.5.0\n# comment\nuvicorn\n")

    pkg_file = os.path.join(temp_dir, "package.json")
    with open(pkg_file, "w", encoding="utf-8") as f:
        f.write('{\n  "name": "frontend",\n  "dependencies": {\n    "react": "^18.2.0"\n  },\n  "devDependencies": {\n    "vite": "^5.0.0"\n  }\n}\n')

    js_file = os.path.join(temp_dir, "index.js")
    with open(js_file, "w", encoding="utf-8") as f:
        f.write("import React from 'react';\n\nexport function App() {\n  return 'Hello';\n}\n")

    # Commit files
    repo.index.add(["README.md", "main.py", "requirements.txt", "package.json", "index.js"])
    repo.index.commit("Initial test commit")
    repo.close()

    yield temp_dir

    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def empty_temp_dir():
    """Create an empty temporary directory."""
    temp_dir = tempfile.mkdtemp(prefix="synapse_empty_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)
