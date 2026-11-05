import { useState } from 'react';
import './App.css';

function App() {
  const [repoUrl, setRepoUrl] = useState('');
  const [status, setStatus] = useState({ message: '', type: '' }); // type: 'loading', 'success', or 'error'

  const handleClone = async (event) => {
    event.preventDefault();
    if (!repoUrl) {
      setStatus({ message: 'Please enter a URL first.', type: 'error' });
      return;
    }

    setStatus({ message: 'Cloning in progress... This may take a moment.', type: 'loading' });

    try {
      const response = await fetch('http://127.0.0.1:8000/clone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: repoUrl }),
      });

      const data = await response.json();

      if (response.ok) {
        setStatus({ message: data.message, type: 'success' });
      } else {
        // FastAPI returns errors in the 'detail' field
        setStatus({ message: data.detail || 'Cloning failed.', type: 'error' });
      }
    } catch {
      setStatus({ message: 'Cannot connect to the backend server. Is FastAPI running?', type: 'error' });
    }
  };

  return (
    <div className="container">
      <h1>Synapse</h1>
      <p className="subtitle">Enter a GitHub repository URL to begin indexing logic.</p>
      
      <form className="clone-form" onSubmit={handleClone}>
        <label htmlFor="repo-url">GitHub repository URL</label>
        <div className="input-group">
          <input
            id="repo-url"
            type="text"
            placeholder="https://github.com/user/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            disabled={status.type === 'loading'}
          />
          <button type="submit" disabled={status.type === 'loading'}>
            {status.type === 'loading' ? 'Cloning...' : 'Clone Repository'}
          </button>
        </div>
      </form>

      <div className={`status-message ${status.type}`} role="status" aria-live="polite" aria-atomic="true">
        {status.message}
      </div>
    </div>
  );
}

export default App;
