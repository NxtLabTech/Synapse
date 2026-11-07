import git
import inspect
import os
import shutil
import stat
from git.exc import GitError

class GitManager:
    def __init__(self, remote_repo_url, cloning_path):
        self.remote_repo_url = remote_repo_url
        self.cloning_path = cloning_path
    
    def _remove_readonly(self, func, path, _excinfo):
        """
        Error handler for shutil.rmtree.
        It clears the 'read-only' bit and retries the removal.
        """
        del _excinfo
        os.chmod(path, stat.S_IWRITE)
        func(path)

    def _remove_existing_repo(self):
        if "onexc" in inspect.signature(shutil.rmtree).parameters:
            removal_options = {"onexc": self._remove_readonly}
        else:
            removal_options = {"onerror": self._remove_readonly}
        shutil.rmtree(self.cloning_path, **removal_options)

    def clone_repo(self):
        if os.path.exists(self.cloning_path):
            print("The cloning path already exists. Removing it to avoid conflicts.")
            self._remove_existing_repo()

        try:
            print(f"Cloning repository from {self.remote_repo_url}...")
            # Added a timeout check or depth=1 if you want faster indexing later
            git.Repo.clone_from(self.remote_repo_url, self.cloning_path)
            print("Successfully cloned the repository.")
            return True
        except (GitError, OSError) as e:
            # Printing the actual error 'e' helps debugging significantly
            print(f"An error occurred: {e}")
            return False