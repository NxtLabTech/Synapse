
import git
import os
import shutil
import stat
import sys


class GitManager:
    def __init__(self, remote_repo_url, cloning_path):
        self.remote_repo_url = remote_repo_url
        self.cloning_path = cloning_path

    def _remove_readonly(self, func, path, excinfo):
        """
        Error handler for shutil.rmtree.
        Clears the read-only bit and retries removal.
        """
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    def clone_repo(self):
        if os.path.exists(self.cloning_path):
            print("The cloning path already exists. Removing it to avoid conflicts.")

            if sys.version_info >= (3, 12):
                def onexc(func, path, exc):
                    self._remove_readonly(func, path, exc)

                shutil.rmtree(self.cloning_path, onexc=onexc)
            else:
                shutil.rmtree(
                    self.cloning_path,
                    onerror=self._remove_readonly
                )

        try:
            print(f"Cloning repository from {self.remote_repo_url}...")

            git.Repo.clone_from(
                self.remote_repo_url,
                self.cloning_path
            )

            print("Successfully cloned the repository.")
            return True

        except Exception as e:
            print(f"An error occurred: {e}")
            return False
