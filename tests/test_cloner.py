import stat
from pathlib import Path

from backend.app.cloner import GitManager, git


def test_clone_repo_removes_existing_readonly_directory(tmp_path, monkeypatch):
    clone_path = tmp_path / "clone"
    clone_path.mkdir()

    old_file = clone_path / "readonly.txt"
    old_file.write_text("old content")
    old_file.chmod(stat.S_IREAD)

    def fake_clone_from(remote_url, cloning_path):
        path = Path(cloning_path)
        assert not path.exists(), "Existing directory was not removed"
        path.mkdir()
        (path / "new.txt").write_text("new clone")

    monkeypatch.setattr(git.Repo, "clone_from", fake_clone_from)

    manager = GitManager(
        "https://example.invalid/repo.git",
        str(clone_path),
    )

    assert manager.clone_repo() is True
    assert (clone_path / "new.txt").read_text() == "new clone"
    assert not (clone_path / "readonly.txt").exists()
