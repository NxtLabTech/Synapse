import { useState } from 'react';
import './App.css';

// VITE_API_URL is set at build time (or dev-server time) via a .env file or
// the Docker Compose `environment:` block.  It falls back to the local
// FastAPI address so plain `npm run dev` still works without any configuration.
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

function App() {
  const [repoUrl, setRepoUrl] = useState('');
  const [status, setStatus] = useState({ message: '', type: '' }); // type: 'loading', 'success', or 'error'

  const handleClone = async () => {
    if (!repoUrl.trim()) {
      setStatus({ message: 'Please enter a URL first.', type: 'error' });
      return;
    }

    setStatus({ message: 'Cloning in progress... This may take a moment.', type: 'loading' });

    try {
      const response = await fetch(`${API_BASE}/clone`, {
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
      
      <div className="input-group">
        <input
          type="text"
          placeholder="https://github.com/user/repo"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          disabled={status.type === 'loading'}
        />
        <button 
          onClick={handleClone} 
          disabled={status.type === 'loading'}
        >
          {status.type === 'loading' ? 'Cloning...' : 'Clone Repository'}
        </button>
      </div>

      {status.message && (
        <div className={`status-message ${status.type}`}>
          {status.message}
        </div>
      )}
    </div>
  );
}

export default App;