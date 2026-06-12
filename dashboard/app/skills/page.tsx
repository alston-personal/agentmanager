'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Capability } from '@/lib/types';

export default function SkillsPage() {
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  // Form State
  const [sourcePath, setSourcePath] = useState('');
  const [skillName, setSkillName] = useState('');
  const [description, setDescription] = useState('');
  const [role, setRole] = useState('虎掌');
  
  const [promoting, setPromoting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetchCapabilities();
  }, []);

  const fetchCapabilities = async () => {
    try {
      const response = await fetch('/dashboard/api/skills');
      const data = await response.json();
      setCapabilities(data.capabilities || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handlePromote = async (e: React.FormEvent) => {
    e.preventDefault();
    setPromoting(true);
    setMessage('');
    setError('');

    try {
      const res = await fetch('/dashboard/api/skills', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ sourcePath, skillName, description, role })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Promotion failed');

      setMessage(data.message || 'Skill promoted successfully!');
      setSourcePath('');
      setSkillName('');
      setDescription('');
      setRole('虎掌');
      
      // Refresh list
      fetchCapabilities();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setPromoting(false);
    }
  };

  if (loading) return <div className="container" style={{padding: '4rem'}}>Loading Capabilities Vault...</div>;

  return (
    <main style={{ minHeight: '100vh', padding: 'var(--spacing-2xl) 0' }}>
      <div className="container">
        <div style={{ marginBottom: 'var(--spacing-2xl)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--spacing-xl)' }}>
          <button className="btn btn-secondary" onClick={() => router.push('/')} style={{ marginBottom: 'var(--spacing-lg)' }}>
            ← Back to Dashboard
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--spacing-md)' }}>
            <span style={{ fontSize: '3rem' }}>🧬</span>
            <h1 className="gradient-text" style={{ fontSize: '3.5rem', fontWeight: 900 }}>Skill Promotion</h1>
          </div>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '1.2rem', marginTop: 'var(--spacing-xs)' }}>
            Promote scripts into reusable AgentOS capabilities (LCS-Synthesis).
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--spacing-2xl)' }}>
          {/* Left Column: Form */}
          <div className="card" style={{ padding: 'var(--spacing-xl)' }}>
            <h2 style={{ fontSize: '1.5rem', marginBottom: 'var(--spacing-lg)' }}>Promote New Skill</h2>
            <form onSubmit={handlePromote} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
              <div>
                <label style={{ display: 'block', marginBottom: 'var(--spacing-xs)', color: 'var(--color-text-secondary)' }}>Source Path (Absolute)</label>
                <input 
                  type="text" 
                  value={sourcePath}
                  onChange={e => setSourcePath(e.target.value)}
                  placeholder="/home/ubuntu/agentmanager/scripts/my_script.py"
                  required
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '0.5rem', background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: 'var(--spacing-xs)', color: 'var(--color-text-secondary)' }}>Skill Name (Directory name)</label>
                <input 
                  type="text" 
                  value={skillName}
                  onChange={e => setSkillName(e.target.value)}
                  placeholder="data_parser"
                  required
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '0.5rem', background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: 'var(--spacing-xs)', color: 'var(--color-text-secondary)' }}>Role Assigned</label>
                <input 
                  type="text" 
                  value={role}
                  onChange={e => setRole(e.target.value)}
                  placeholder="虎掌"
                  required
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '0.5rem', background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: 'var(--spacing-xs)', color: 'var(--color-text-secondary)' }}>Description</label>
                <textarea 
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="Briefly describe what this capability does..."
                  required
                  rows={3}
                  style={{ width: '100%', padding: '0.75rem', borderRadius: '0.5rem', background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', color: 'var(--color-text)', resize: 'vertical' }}
                />
              </div>

              {error && <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', borderRadius: '0.5rem', border: '1px solid rgba(239, 68, 68, 0.2)' }}>{error}</div>}
              {message && <div style={{ padding: '1rem', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', borderRadius: '0.5rem', border: '1px solid rgba(16, 185, 129, 0.2)' }}>{message}</div>}

              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={promoting}
                style={{ marginTop: 'var(--spacing-md)', padding: '1rem', borderRadius: '0.5rem', background: 'linear-gradient(135deg, #10b981 0%, #3b82f6 100%)', border: 'none', fontWeight: 'bold' }}
              >
                {promoting ? 'Promoting...' : '🚀 Synthesize & Promote Skill'}
              </button>
            </form>
          </div>

          {/* Right Column: Existing Skills */}
          <div>
            <h2 style={{ fontSize: '1.5rem', marginBottom: 'var(--spacing-lg)' }}>Registered Capabilities</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
              {capabilities.length === 0 ? (
                <p style={{ color: 'var(--color-text-secondary)' }}>No capabilities found.</p>
              ) : (
                capabilities.map((cap, i) => (
                  <div key={i} className="card hover-glow" style={{ padding: 'var(--spacing-md)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--spacing-xs)' }}>
                      <h3 style={{ fontSize: '1.2rem', color: 'var(--color-primary)' }}>{cap.name}</h3>
                      <span className="badge badge-success">{cap.status}</span>
                    </div>
                    <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem', marginBottom: 'var(--spacing-sm)' }}>
                      <code>{cap.path}</code> • 🧑‍💻 {cap.role}
                    </p>
                    <p style={{ fontSize: '0.95rem' }}>{cap.description}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
