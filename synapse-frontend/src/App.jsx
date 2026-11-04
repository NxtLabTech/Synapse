import { useState, useEffect, useMemo } from 'react';
import './App.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const LANGUAGE_COLORS = {
  Python: '#3572A5',
  JavaScript: '#F7DF1E',
  TypeScript: '#3178C6',
  'TypeScript (React)': '#2b7489',
  'JavaScript (React)': '#e3cf24',
  Java: '#B07219',
  'C++': '#F34B7D',
  C: '#555555',
  Go: '#00ADD8',
  Rust: '#DEA584',
  HTML: '#E34C26',
  CSS: '#563D7C',
  Markdown: '#083FA1',
  JSON: '#4B5563',
  YAML: '#CB171E',
  Shell: '#89E051',
  SQL: '#E38C00',
  TOML: '#9C4221',
};

const SAMPLE_REPOS = [
  { label: 'Synapse', url: 'https://github.com/hasini-06/Synapse.git' },
  { label: 'FastAPI', url: 'https://github.com/fastapi/fastapi.git' },
  { label: 'Express', url: 'https://github.com/expressjs/express.git' },
  { label: 'Flask', url: 'https://github.com/pallets/flask.git' },
];

function App() {
  const [repoUrl, setRepoUrl] = useState('');
  const [depth, setDepth] = useState(1);
  const [parseAst, setParseAst] = useState(true);
  const [status, setStatus] = useState({ message: '', type: '' });
  const [loadingStep, setLoadingStep] = useState(0);
  const [analysis, setAnalysis] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [apiOnline, setApiOnline] = useState(null);

  // AST Symbol filters
  const [symbolSearch, setSymbolSearch] = useState('');
  const [selectedLanguage, setSelectedLanguage] = useState('all');
  const [selectedType, setSelectedType] = useState('all');

  // Selected manifest for dependency tab
  const [activeManifestIdx, setActiveManifestIdx] = useState(0);
  const [copiedJson, setCopiedJson] = useState(false);

  // Ping backend API status on mount
  useEffect(() => {
    fetch(`${API_BASE_URL}/`)
      .then((res) => res.json())
      .then(() => setApiOnline(true))
      .catch(() => setApiOnline(false));
  }, []);

  // Loading stepper simulation
  useEffect(() => {
    if (status.type !== 'loading') {
      return;
    }
    const timer = setInterval(() => {
      setLoadingStep((prev) => (prev < 4 ? prev + 1 : prev));
    }, 1200);
    return () => clearInterval(timer);
  }, [status.type]);

  const handleAnalyze = async (overrideUrl) => {
    const targetUrl = overrideUrl || repoUrl;
    if (!targetUrl.trim()) {
      setStatus({ message: 'Please enter a valid Git repository URL.', type: 'error' });
      return;
    }

    setAnalysis(null);
    setLoadingStep(1);
    setStatus({ message: 'Analyzing repository...', type: 'loading' });

    try {
      const response = await fetch(`${API_BASE_URL}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: targetUrl.trim(),
          depth: depth ? Number(depth) : 1,
          parse_ast: parseAst,
        }),
      });

      const data = await response.json();

      setLoadingStep(0);
      if (response.ok) {
        setAnalysis(data);
        setStatus({ message: 'Repository analyzed successfully!', type: 'success' });
        setActiveTab('overview');
      } else {
        setStatus({
          message: data.detail || 'Analysis failed. Please check the repository URL.',
          type: 'error',
        });
      }
    } catch {
      setLoadingStep(0);
      setStatus({
        message: 'Cannot connect to backend API server at ' + API_BASE_URL + '. Ensure FastAPI is running.',
        type: 'error',
      });
    }
  };

  const handleCopyJson = () => {
    if (!analysis) return;
    navigator.clipboard.writeText(JSON.stringify(analysis, null, 2));
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  // Flatten and filter AST symbols
  const allSymbols = useMemo(() => {
    if (!analysis?.ast_analysis?.files) return [];
    const list = [];
    for (const f of analysis.ast_analysis.files) {
      for (const sym of f.symbols || []) {
        list.push({ ...sym, file_path: f.file_path, language: f.language });
      }
    }
    return list;
  }, [analysis]);

  const filteredSymbols = useMemo(() => {
    return allSymbols.filter((s) => {
      const matchesSearch =
        !symbolSearch ||
        s.name.toLowerCase().includes(symbolSearch.toLowerCase()) ||
        s.file_path.toLowerCase().includes(symbolSearch.toLowerCase());
      const matchesLang =
        selectedLanguage === 'all' || s.language.toLowerCase() === selectedLanguage.toLowerCase();
      const matchesType =
        selectedType === 'all' || s.type.toLowerCase() === selectedType.toLowerCase();
      return matchesSearch && matchesLang && matchesType;
    });
  }, [allSymbols, symbolSearch, selectedLanguage, selectedType]);

  const availableLanguages = useMemo(() => {
    const langs = new Set(allSymbols.map((s) => s.language));
    return Array.from(langs);
  }, [allSymbols]);

  const availableTypes = ['function', 'class', 'method', 'import', 'export'];

  return (
    <div className="synapse-app">
      {/* Top Navigation */}
      <header className="navbar">
        <div className="navbar-left">
          <div className="logo-badge">
            <svg className="synapse-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle cx="12" cy="12" r="3" strokeWidth="2" />
              <circle cx="4" cy="6" r="2" strokeWidth="2" />
              <circle cx="20" cy="6" r="2" strokeWidth="2" />
              <circle cx="4" cy="18" r="2" strokeWidth="2" />
              <circle cx="20" cy="18" r="2" strokeWidth="2" />
              <path d="M6 7l4 3.5M18 7l-4 3.5M6 17l4-3.5M18 17l-4-3.5" strokeWidth="1.5" />
            </svg>
            <span className="logo-text">Synapse</span>
          </div>
          <span className="version-pill">v0.2.0 Engine</span>
        </div>

        <div className="navbar-right">
          <div className={`api-status-pill ${apiOnline ? 'online' : apiOnline === false ? 'offline' : 'checking'}`}>
            <span className="status-dot"></span>
            {apiOnline ? 'API Online' : apiOnline === false ? 'API Offline' : 'Connecting...'}
          </div>
          <a
            href="https://github.com/hasini-06/Synapse"
            target="_blank"
            rel="noopener noreferrer"
            className="nav-link-btn"
          >
            <svg className="github-icon" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 0C3.58 0 0 3.58 0 8a8.01 8.01 0 005.47 7.59c.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.66 7.66 0 018 4.07c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            GitHub
          </a>
        </div>
      </header>

      {/* Main Hero & URL Input */}
      <main className="main-content">
        <section className="hero-section">
          <h1 className="hero-title">
            Codebase Intelligence & <span className="gradient-text">AST Knowledge Graph</span>
          </h1>
          <p className="hero-subtitle">
            Sub-second isolated shallow cloning, comprehensive repository metadata discovery,
            dependency manifest auditing, and Tree-sitter AST symbol indexing.
          </p>

          <div className="input-card">
            <div className="search-bar">
              <svg className="git-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <line x1="6" y1="3" x2="6" y2="15" strokeWidth="2" strokeLinecap="round" />
                <circle cx="18" cy="6" r="3" strokeWidth="2" />
                <circle cx="6" cy="18" r="3" strokeWidth="2" />
                <path d="M18 9a9 9 0 01-9 9" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <input
                type="text"
                placeholder="Paste Git repository URL (e.g. https://github.com/user/repository.git)"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                disabled={status.type === 'loading'}
              />
              {repoUrl && (
                <button
                  type="button"
                  className="clear-btn"
                  onClick={() => setRepoUrl('')}
                  title="Clear input"
                >
                  &times;
                </button>
              )}
              <button
                type="button"
                className="analyze-cta-btn"
                onClick={() => handleAnalyze()}
                disabled={status.type === 'loading'}
              >
                {status.type === 'loading' ? (
                  <>
                    <span className="spinner"></span>
                    Analyzing...
                  </>
                ) : (
                  <>
                    <svg className="play-icon" viewBox="0 0 24 24" fill="currentColor">
                      <polygon points="5 3 19 12 5 21 5 3" />
                    </svg>
                    Analyze Repository
                  </>
                )}
              </button>
            </div>

            {/* Options Bar & Quick Try Chips */}
            <div className="input-footer">
              <div className="options-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={depth === 1}
                    onChange={(e) => setDepth(e.target.checked ? 1 : 0)}
                  />
                  <span>Shallow Clone (depth=1)</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={parseAst}
                    onChange={(e) => setParseAst(e.target.checked)}
                  />
                  <span>Tree-sitter AST Analysis</span>
                </label>
              </div>

              <div className="quick-chips">
                <span className="quick-label">Try sample:</span>
                {SAMPLE_REPOS.map((sample) => (
                  <button
                    key={sample.label}
                    type="button"
                    className="chip-btn"
                    onClick={() => {
                      setRepoUrl(sample.url);
                      handleAnalyze(sample.url);
                    }}
                    disabled={status.type === 'loading'}
                  >
                    {sample.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Stepper Feedback during Loading */}
          {status.type === 'loading' && (
            <div className="loading-card">
              <div className="stepper-container">
                <div className={`step-item ${loadingStep >= 1 ? 'active' : ''}`}>
                  <div className="step-circle">{loadingStep > 1 ? '✓' : '1'}</div>
                  <span className="step-label">Validate URL</span>
                </div>
                <div className="step-divider"></div>
                <div className={`step-item ${loadingStep >= 2 ? 'active' : ''}`}>
                  <div className="step-circle">{loadingStep > 2 ? '✓' : '2'}</div>
                  <span className="step-label">Isolated Git Clone</span>
                </div>
                <div className="step-divider"></div>
                <div className={`step-item ${loadingStep >= 3 ? 'active' : ''}`}>
                  <div className="step-circle">{loadingStep > 3 ? '✓' : '3'}</div>
                  <span className="step-label">Extract Metadata</span>
                </div>
                <div className="step-divider"></div>
                <div className={`step-item ${loadingStep >= 4 ? 'active' : ''}`}>
                  <div className="step-circle">4</div>
                  <span className="step-label">Tree-sitter AST</span>
                </div>
              </div>
              <p className="loading-caption">
                Executing asynchronous pipeline in worker thread...
              </p>
            </div>
          )}

          {/* Error Message Display */}
          {status.type === 'error' && (
            <div className="alert-box error-alert">
              <svg className="alert-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <circle cx="12" cy="12" r="10" strokeWidth="2" />
                <line x1="12" y1="8" x2="12" y2="12" strokeWidth="2" strokeLinecap="round" />
                <line x1="12" y1="16" x2="12.01" y2="16" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <div className="alert-content">
                <strong>Analysis Failed</strong>
                <p>{status.message}</p>
              </div>
            </div>
          )}
        </section>

        {/* Workbench: Results & Visualizations */}
        {analysis && analysis.metadata && (
          <section className="workbench-section">
            {/* Repo Summary Header */}
            <div className="repo-header-card">
              <div className="repo-header-left">
                <div className="repo-title-row">
                  <h2 className="repo-name">{analysis.repo_name || 'Repository'}</h2>
                  {analysis.metadata.repo_info?.current_branch && (
                    <span className="branch-badge">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="branch-icon">
                        <line x1="6" y1="3" x2="6" y2="15" strokeWidth="2" />
                        <circle cx="18" cy="6" r="3" strokeWidth="2" />
                        <circle cx="6" cy="18" r="3" strokeWidth="2" />
                        <path d="M18 9a9 9 0 01-9 9" strokeWidth="2" />
                      </svg>
                      {analysis.metadata.repo_info.current_branch}
                    </span>
                  )}
                  {analysis.metadata.repo_info?.has_readme && (
                    <span className="readme-badge">
                      README Available
                    </span>
                  )}
                </div>
                <p className="repo-url-sub">{analysis.url}</p>
              </div>

              <div className="repo-header-right">
                <span className="job-id-pill">Job: <code>{analysis.job_id}</code></span>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={handleCopyJson}
                  title="Copy full JSON analysis payload"
                >
                  {copiedJson ? '✓ Copied' : 'Copy JSON'}
                </button>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="tabs-bar">
              <button
                type="button"
                className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
                onClick={() => setActiveTab('overview')}
              >
                Overview & Metrics
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'symbols' ? 'active' : ''}`}
                onClick={() => setActiveTab('symbols')}
              >
                AST Symbols ({allSymbols.length})
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'dependencies' ? 'active' : ''}`}
                onClick={() => setActiveTab('dependencies')}
              >
                Dependencies ({analysis.metadata.dependencies?.length || 0} manifests)
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'structure' ? 'active' : ''}`}
                onClick={() => setActiveTab('structure')}
              >
                Directory Structure
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'raw' ? 'active' : ''}`}
                onClick={() => setActiveTab('raw')}
              >
                Raw API Payload
              </button>
            </div>

            {/* TAB 1: OVERVIEW */}
            {activeTab === 'overview' && (
              <div className="tab-pane">
                {/* 4 Core Stat Cards */}
                <div className="stats-grid">
                  <div className="stat-card">
                    <div className="stat-icon-wrapper blue">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z" strokeWidth="2" />
                        <polyline points="13 2 13 9 20 9" strokeWidth="2" />
                      </svg>
                    </div>
                    <div className="stat-info">
                      <span className="stat-value">{analysis.metadata.stats?.total_files ?? 0}</span>
                      <span className="stat-label">Total Files ({analysis.metadata.stats?.total_directories ?? 0} dirs)</span>
                    </div>
                  </div>

                  <div className="stat-card">
                    <div className="stat-icon-wrapper purple">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <polyline points="16 18 22 12 16 6" strokeWidth="2" />
                        <polyline points="8 6 2 12 8 18" strokeWidth="2" />
                      </svg>
                    </div>
                    <div className="stat-info">
                      <span className="stat-value">{(analysis.metadata.stats?.total_lines ?? 0).toLocaleString()}</span>
                      <span className="stat-label">Lines of Code ({(analysis.metadata.stats?.total_code_lines ?? 0).toLocaleString()} code)</span>
                    </div>
                  </div>

                  <div className="stat-card">
                    <div className="stat-icon-wrapper green">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <circle cx="12" cy="12" r="3" strokeWidth="2" />
                        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" strokeWidth="2" />
                      </svg>
                    </div>
                    <div className="stat-info">
                      <span className="stat-value">{allSymbols.length}</span>
                      <span className="stat-label">AST Entities Extracted</span>
                    </div>
                  </div>

                  <div className="stat-card">
                    <div className="stat-icon-wrapper orange">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" strokeWidth="2" />
                        <polyline points="3.27 6.96 12 12.01 20.73 6.96" strokeWidth="2" />
                        <line x1="12" y1="22.08" x2="12" y2="12" strokeWidth="2" />
                      </svg>
                    </div>
                    <div className="stat-info">
                      <span className="stat-value">{analysis.metadata.dependencies?.length ?? 0}</span>
                      <span className="stat-label">Manifests Discovered</span>
                    </div>
                  </div>
                </div>

                {/* Language Distribution Progress Bar & Grid */}
                {analysis.metadata.stats?.language_distribution && (
                  <div className="content-card">
                    <h3 className="card-heading">Language Breakdown</h3>
                    
                    {/* Multi-segment Colored Bar */}
                    <div className="lang-progress-bar">
                      {Object.entries(analysis.metadata.stats.language_distribution).map(([lang, stat]) => (
                        <div
                          key={lang}
                          className="progress-segment"
                          style={{
                            width: `${Math.max(stat.percentage, 1)}%`,
                            backgroundColor: LANGUAGE_COLORS[lang] || '#8884d8',
                          }}
                          title={`${lang}: ${stat.percentage}% (${stat.lines} LOC)`}
                        />
                      ))}
                    </div>

                    {/* Language Cards Grid */}
                    <div className="lang-cards-grid">
                      {Object.entries(analysis.metadata.stats.language_distribution).map(([lang, stat]) => (
                        <div key={lang} className="lang-item-card">
                          <div className="lang-header">
                            <span
                              className="lang-color-dot"
                              style={{ backgroundColor: LANGUAGE_COLORS[lang] || '#8884d8' }}
                            />
                            <span className="lang-name">{lang}</span>
                            <span className="lang-percent">{stat.percentage}%</span>
                          </div>
                          <div className="lang-details">
                            <span>{stat.files} files</span>
                            <span>•</span>
                            <span>{stat.lines.toLocaleString()} LOC</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Latest Git Commit Card */}
                {analysis.metadata.repo_info?.latest_commit && (
                  <div className="content-card">
                    <h3 className="card-heading">Latest Git Commit</h3>
                    <div className="commit-box">
                      <div className="commit-avatar">
                        {analysis.metadata.repo_info.latest_commit.author.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="commit-details">
                        <p className="commit-message">
                          {analysis.metadata.repo_info.latest_commit.message}
                        </p>
                        <div className="commit-meta-row">
                          <span className="commit-author">
                            {analysis.metadata.repo_info.latest_commit.author}
                          </span>
                          <span className="meta-sep">•</span>
                          <span className="commit-date">
                            {new Date(analysis.metadata.repo_info.latest_commit.date).toLocaleDateString(undefined, {
                              year: 'numeric',
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </span>
                          <span className="meta-sep">•</span>
                          <code className="commit-sha">
                            {analysis.metadata.repo_info.latest_commit.hash.slice(0, 7)}
                          </code>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: AST SYMBOLS EXPLORER */}
            {activeTab === 'symbols' && (
              <div className="tab-pane">
                {/* Search & Filters */}
                <div className="filter-controls-card">
                  <div className="filter-search-box">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="search-icon">
                      <circle cx="11" cy="11" r="8" strokeWidth="2" />
                      <line x1="21" y1="21" x2="16.65" y2="16.65" strokeWidth="2" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Filter symbols by identifier name or file path..."
                      value={symbolSearch}
                      onChange={(e) => setSymbolSearch(e.target.value)}
                    />
                  </div>

                  <div className="filter-dropdowns">
                    <select
                      value={selectedLanguage}
                      onChange={(e) => setSelectedLanguage(e.target.value)}
                      className="filter-select"
                    >
                      <option value="all">All Languages ({availableLanguages.length})</option>
                      {availableLanguages.map((lang) => (
                        <option key={lang} value={lang}>
                          {lang.toUpperCase()}
                        </option>
                      ))}
                    </select>

                    <div className="type-pills">
                      <button
                        type="button"
                        className={`type-pill ${selectedType === 'all' ? 'active' : ''}`}
                        onClick={() => setSelectedType('all')}
                      >
                        All
                      </button>
                      {availableTypes.map((t) => (
                        <button
                          key={t}
                          type="button"
                          className={`type-pill ${selectedType === t ? 'active' : ''}`}
                          onClick={() => setSelectedType(t)}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Symbols Results Count */}
                <div className="results-count-bar">
                  Showing <strong>{filteredSymbols.length}</strong> of {allSymbols.length} extracted symbols
                </div>

                {/* Symbols Table */}
                {filteredSymbols.length > 0 ? (
                  <div className="symbols-table-wrapper">
                    <table className="symbols-table">
                      <thead>
                        <tr>
                          <th>Type</th>
                          <th>Identifier Name</th>
                          <th>File Path</th>
                          <th>Lines</th>
                          <th>Parameters</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSymbols.slice(0, 100).map((sym, idx) => (
                          <tr key={`${sym.file_path}-${sym.name}-${idx}`}>
                            <td>
                              <span className={`sym-type-badge ${sym.type.toLowerCase()}`}>
                                {sym.type}
                              </span>
                            </td>
                            <td>
                              <code className="sym-name">{sym.name}</code>
                            </td>
                            <td>
                              <span className="sym-path">{sym.file_path}</span>
                            </td>
                            <td>
                              <code className="sym-lines">
                                L{sym.start_line}–{sym.end_line}
                              </code>
                            </td>
                            <td>
                              {sym.parameters && sym.parameters.length > 0 ? (
                                <div className="params-list">
                                  {sym.parameters.map((p, i) => (
                                    <span key={i} className="param-pill">
                                      {p}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <span className="dim-text">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {filteredSymbols.length > 100 && (
                      <div className="table-overflow-note">
                        Displaying first 100 symbols for performance. Use search to refine.
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="empty-state-card">
                    <p>No symbols match your current search and filter criteria.</p>
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: DEPENDENCIES */}
            {activeTab === 'dependencies' && (
              <div className="tab-pane">
                {analysis.metadata.dependencies && analysis.metadata.dependencies.length > 0 ? (
                  <div className="manifest-container">
                    {/* Manifest Selector Tabs */}
                    <div className="manifest-tabs">
                      {analysis.metadata.dependencies.map((m, idx) => (
                        <button
                          key={m.file_path}
                          type="button"
                          className={`manifest-tab-btn ${activeManifestIdx === idx ? 'active' : ''}`}
                          onClick={() => setActiveManifestIdx(idx)}
                        >
                          <span className="manifest-type-pill">{m.manifest_type}</span>
                          <code>{m.file_path}</code>
                          <span className="dep-count-badge">{m.dependencies.length}</span>
                        </button>
                      ))}
                    </div>

                    {/* Selected Manifest Dependency Grid */}
                    {analysis.metadata.dependencies[activeManifestIdx] && (
                      <div className="dependency-grid">
                        {analysis.metadata.dependencies[activeManifestIdx].dependencies.map((dep, idx) => (
                          <div key={`${dep.name}-${idx}`} className="dep-item-card">
                            <div className="dep-item-header">
                              <span className="dep-name">{dep.name}</span>
                              <span className={`category-tag ${dep.category}`}>{dep.category}</span>
                            </div>
                            <div className="dep-version-row">
                              <span className="version-label">Version:</span>
                              <code className="version-val">{dep.version || 'Unspecified'}</code>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="empty-state-card">
                    <p>No dependency manifests (`package.json`, `requirements.txt`, `pyproject.toml`) were found in this repository.</p>
                  </div>
                )}
              </div>
            )}

            {/* TAB 4: DIRECTORY STRUCTURE */}
            {activeTab === 'structure' && (
              <div className="tab-pane">
                <div className="content-card">
                  <h3 className="card-heading">Directory Layout Summary</h3>
                  <div className="file-tree-view">
                    {analysis.metadata.directory_summary && analysis.metadata.directory_summary.length > 0 ? (
                      analysis.metadata.directory_summary.map((item, idx) => {
                        const isDir = item.endsWith('/');
                        return (
                          <div key={idx} className={`tree-item ${isDir ? 'is-dir' : 'is-file'}`}>
                            <span className="tree-icon">{isDir ? '📁' : '📄'}</span>
                            <code>{item}</code>
                          </div>
                        );
                      })
                    ) : (
                      <p className="dim-text">No directory summary available.</p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 5: RAW JSON */}
            {activeTab === 'raw' && (
              <div className="tab-pane">
                <div className="content-card">
                  <div className="raw-header">
                    <h3 className="card-heading">Complete API Response Payload</h3>
                    <button type="button" className="icon-btn" onClick={handleCopyJson}>
                      {copiedJson ? '✓ Copied' : 'Copy JSON'}
                    </button>
                  </div>
                  <pre className="json-code-block">
                    {JSON.stringify(analysis, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
