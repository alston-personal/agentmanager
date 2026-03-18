'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Workflow } from '@/lib/types';

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const router = useRouter();

  useEffect(() => {
    fetchWorkflows();
    const savedToken = localStorage.getItem('auth_token');
    if (savedToken) {
      setToken(savedToken);
    }
  }, []);

  const fetchWorkflows = async () => {
    try {
      const response = await fetch('/api/workflows');
      const data = await response.json();
      setWorkflows(data.workflows);
    } catch (error) {
      console.error('Failed to fetch workflows:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (response.ok) {
        const data = await response.json();
        setToken(data.token);
        localStorage.setItem('auth_token', data.token);
        setShowLogin(false);
        setPassword('');
      } else {
        alert('Invalid credentials');
      }
    } catch (error) {
      console.error('Login failed:', error);
      alert('Login failed');
    }
  };

  const handleLogout = () => {
    setToken(null);
    localStorage.removeItem('auth_token');
  };

  const executeWorkflow = async (workflowId: string) => {
    if (!token) {
      setShowLogin(true);
      return;
    }

    setExecuting(workflowId);
    try {
      const response = await fetch('/api/workflows/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ workflowId }),
      });

      const data = await response.json();
      alert(data.message || 'Workflow execution started');
    } catch (error) {
      console.error('Execution failed:', error);
      alert('Execution failed');
    } finally {
      setExecuting(null);
    }
  };

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="animate-pulse" style={{ textAlign: 'center' }}>
          <h2 className="gradient-text" style={{ fontSize: '1.5rem', fontWeight: 700 }}>
            Loading workflows...
          </h2>
        </div>
      </div>
    );
  }

  return (
    <main style={{ minHeight: '100vh', padding: 'var(--spacing-2xl) 0' }}>
      <div className="container">
        {/* Header */}
        <div style={{ marginBottom: 'var(--spacing-2xl)' }}>
          <button
            className="btn btn-secondary"
            onClick={() => router.push('/')}
            style={{ marginBottom: 'var(--spacing-lg)' }}
          >
            ← Back to Dashboard
          </button>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: 'var(--spacing-sm)' }}>
                ⚡ Workflows
              </h1>
              <p style={{ fontSize: '1rem', color: 'var(--color-text-secondary)' }}>
                Manage and execute automation workflows
              </p>
            </div>

            {token ? (
              <button className="btn btn-secondary" onClick={handleLogout}>
                🚪 Logout
              </button>
            ) : (
              <button className="btn btn-primary" onClick={() => setShowLogin(true)}>
                🔐 Login
              </button>
            )}
          </div>
        </div>

        {/* Login Modal */}
        {showLogin && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}>
            <div className="glass" style={{
              padding: 'var(--spacing-2xl)',
              borderRadius: 'var(--radius-xl)',
              maxWidth: '400px',
              width: '100%'
            }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 'var(--spacing-lg)' }}>
                🔐 Login Required
              </h2>
              <form onSubmit={handleLogin}>
                <div style={{ marginBottom: 'var(--spacing-md)' }}>
                  <label style={{ display: 'block', marginBottom: 'var(--spacing-xs)', fontSize: '0.875rem' }}>
                    Username
                  </label>
                  <input
                    type="text"
                    className="input"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                  />
                </div>
                <div style={{ marginBottom: 'var(--spacing-lg)' }}>
                  <label style={{ display: 'block', marginBottom: 'var(--spacing-xs)', fontSize: '0.875rem' }}>
                    Password
                  </label>
                  <input
                    type="password"
                    className="input"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                <div style={{ display: 'flex', gap: 'var(--spacing-md)' }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>
                    Login
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowLogin(false)}
                    style={{ flex: 1 }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
              <p style={{ marginTop: 'var(--spacing-md)', fontSize: '0.75rem', color: 'var(--color-text-muted)', textAlign: 'center' }}>
                Default: admin / admin
              </p>
            </div>
          </div>
        )}

        {/* Workflows Grid */}
        <div className="grid grid-cols-2">
          {workflows.map((workflow, index) => (
            <div
              key={workflow.id}
              className="card animate-fade-in"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 'var(--spacing-sm)' }}>
                  {workflow.name}
                </h3>
                <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                  {workflow.description}
                </p>
              </div>

              {workflow.steps.length > 0 && (
                <div style={{ marginBottom: 'var(--spacing-md)' }}>
                  <h4 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: 'var(--spacing-sm)', color: 'var(--color-text-tertiary)' }}>
                    Steps:
                  </h4>
                  <ol style={{ paddingLeft: 'var(--spacing-lg)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                    {workflow.steps.slice(0, 3).map((step, i) => (
                      <li key={i} style={{ marginBottom: 'var(--spacing-xs)' }}>{step}</li>
                    ))}
                    {workflow.steps.length > 3 && (
                      <li style={{ color: 'var(--color-text-tertiary)' }}>
                        ... and {workflow.steps.length - 3} more steps
                      </li>
                    )}
                  </ol>
                </div>
              )}

              <div style={{ display: 'flex', gap: 'var(--spacing-sm)', alignItems: 'center' }}>
                <button
                  className="btn btn-primary"
                  onClick={() => executeWorkflow(workflow.id)}
                  disabled={executing === workflow.id}
                  style={{ flex: 1 }}
                >
                  {executing === workflow.id ? '⏳ Executing...' : '▶️ Execute'}
                </button>
                <code style={{
                  fontSize: '0.75rem',
                  color: 'var(--color-text-muted)',
                  background: 'var(--color-bg-tertiary)',
                  padding: 'var(--spacing-xs) var(--spacing-sm)',
                  borderRadius: 'var(--radius-sm)'
                }}>
                  {workflow.command}
                </code>
              </div>
            </div>
          ))}
        </div>

        {workflows.length === 0 && (
          <div style={{ textAlign: 'center', padding: 'var(--spacing-2xl)', color: 'var(--color-text-muted)' }}>
            No workflows found
          </div>
        )}
      </div>
    </main>
  );
}
