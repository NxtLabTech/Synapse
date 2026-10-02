import git
import os
import shutil
import stat
import sys
import shutil

class GitManager:
    def __init__(self, remote_repo_url, cloning_path):
        self.remote_repo_url = remote_repo_url
        self.cloning_path = cloning_path
    
    def _remove_readonly(self, func, path, excinfo):
        """
        Error handler for shutil.rmtree.
        It clears the 'read-only' bit and retries the removal.
        """
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            # If it still fails, we ignore it to let the process continue
            pass

    def clone_repo(self):
        if os.path.exists(self.cloning_path):
            print("The cloning path already exists. Removing it to avoid conflicts.")
            # Use 'onerror' for Python < 3.12 compatibility
            if sys.version_info >= (3, 12):
                shutil.rmtree(self.cloning_path, onexc=self._remove_readonly)
            else:
                shutil.rmtree(self.cloning_path, onerror=self._remove_readonly) 
            

        try:
            print(f"Cloning repository from {self.remote_repo_url}...")
            # Added a timeout check or depth=1 if you want faster indexing later
            git.Repo.clone_from(self.remote_repo_url, self.cloning_path)
            print("Successfully cloned the repository.")
            return True
        except Exception as e:
            # Printing the actual error 'e' helps debugging significantly
            print(f"An error occurred: {e}")
            return False