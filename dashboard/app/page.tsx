'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardData } from '@/lib/types';
import ProjectCard from '@/components/ProjectCard';
import StatusChart from '@/components/StatusChart';

export default function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const router = useRouter();

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const response = await fetch('/dashboard/api/projects');
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="animate-pulse" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '3rem', marginBottom: 'var(--spacing-md)' }}>✈️</div>
          <h2 className="gradient-text" style={{ fontSize: '1.5rem', fontWeight: 700 }}>
            Loading AI Command Center...
          </h2>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-error)' }}>
            Failed to load data
          </h2>
        </div>
      </div>
    );
  }

  const filteredProjects = data.projects.filter(project => {
    const matchesSearch = project.displayName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      project.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFilter = filterStatus === 'all' || project.status.includes(filterStatus);
    return matchesSearch && matchesFilter;
  });

  const stats = {
    total: data.projects.length,
    active: data.projects.filter(p => p.status.includes('Active') || p.status.includes('🟢')).length,
    inProgress: data.projects.filter(p => p.status.includes('Progress') || p.status.includes('🚧')).length,
    complete: data.projects.filter(p => p.status.includes('Complete') || p.status.includes('✅')).length,
  };

  const status = data.agentosStatus;

  return (
    <main style={{ minHeight: '100vh', padding: 'var(--spacing-2xl) 0' }}>
      <div className="container">
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--spacing-2xl)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--spacing-md)', justifyContent: 'center', marginBottom: 'var(--spacing-xs)' }}>
              <span style={{ fontSize: '2.5rem' }}>✈️</span>
              <h1 className="gradient-text" style={{ fontSize: '3rem', fontWeight: 900, textAlign: 'center' }}>
                AI Command Center
              </h1>
            </div>
            <p style={{ textAlign: 'center', color: 'var(--color-text-secondary)', fontSize: '1rem' }}>
              Flight Deck - Mission Control Dashboard
            </p>
          </div>
          <div style={{ display: 'flex', gap: 'var(--spacing-sm)' }}>
            <button 
              className="btn btn-primary" 
              onClick={() => router.push('/knowledge')}
              style={{ padding: '0.75rem 1.5rem', borderRadius: '2rem', display: 'flex', alignItems: 'center', gap: 'var(--spacing-xs)', background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)', border: 'none', boxShadow: '0 4px 15px rgba(168, 85, 247, 0.4)' }}
            >
              🧠 Knowledge Vault
            </button>
            <button className="btn btn-primary" style={{ padding: '0.75rem 1.5rem', borderRadius: '2rem', display: 'flex', alignItems: 'center', gap: 'var(--spacing-xs)', background: 'linear-gradient(90deg, #f59e0b, #ef4444)' }}>
              🚀 Start Session
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 animate-fade-in" style={{ marginBottom: 'var(--spacing-2xl)' }}>
          <div className="glass" style={{ padding: 'var(--spacing-lg)', borderRadius: 'var(--radius-lg)', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-accent-primary)' }}>{stats.total}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--color-text-tertiary)' }}>Total Projects</div>
          </div>
          <div className="glass" style={{ padding: 'var(--spacing-lg)', borderRadius: 'var(--radius-lg)', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-success)' }}>{stats.active}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--color-text-tertiary)' }}>Active</div>
          </div>
          <div className="glass" style={{ padding: 'var(--spacing-lg)', borderRadius: 'var(--radius-lg)', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-warning)' }}>{stats.inProgress}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--color-text-tertiary)' }}>In Progress</div>
          </div>
          <div className="glass" style={{ padding: 'var(--spacing-lg)', borderRadius: 'var(--radius-lg)', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-info)' }}>{stats.complete}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--color-text-tertiary)' }}>Complete</div>
          </div>
        </div>

        {/* AgentOS Status Center */}
        <section className="glass animate-fade-in" style={{ padding: 'var(--spacing-xl)', borderRadius: 'var(--radius-xl)', marginBottom: 'var(--spacing-2xl)', background: 'linear-gradient(180deg, rgba(26, 31, 58, 0.82) 0%, rgba(10, 14, 39, 0.9) 100%)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--spacing-lg)', flexWrap: 'wrap', marginBottom: 'var(--spacing-lg)' }}>
            <div>
              <p style={{ fontSize: '0.75rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: 'var(--spacing-xs)' }}>
                System Overview
              </p>
              <h2 style={{ fontSize: '1.75rem', fontWeight: 800, marginBottom: 'var(--spacing-xs)' }}>
                AgentOS Status Center
              </h2>
              <p style={{ color: 'var(--color-text-secondary)' }}>
                Roles, projects, specs, memory systems, and improvement watchlist in one glance.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 'var(--spacing-sm)', flexWrap: 'wrap', alignItems: 'flex-start' }}>
              <span className="badge badge-info">🧠 {status.roleCount} Roles</span>
              <span className="badge badge-success">📦 {status.projectCount} Projects</span>
              <span className="badge badge-warning">📐 {status.specCount} Specs</span>
              <span className="badge badge-info">🗂️ {status.memorySystems.length} Memory Systems</span>
            </div>
          </div>

          <div className="grid grid-cols-4" style={{ marginBottom: 'var(--spacing-lg)' }}>
            <div className="card">
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-accent-primary)' }}>{status.roleCount}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>Roles</div>
            </div>
            <div className="card">
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-success)' }}>{status.projectCount}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>Projects</div>
            </div>
            <div className="card">
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-warning)' }}>{status.specCount}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>Specs</div>
            </div>
            <div className="card">
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-info)' }}>{status.memorySystems.length}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>Memory Systems</div>
            </div>
          </div>

          <div className="grid grid-cols-2" style={{ gap: 'var(--spacing-lg)' }}>
            <div className="card">
              <h3 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: 'var(--spacing-md)' }}>
                🧭 Watchlist
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
                {status.watchlist.length > 0 ? status.watchlist.map((item, index) => (
                  <div
                    key={index}
                      style={{
                      padding: 'var(--spacing-sm) var(--spacing-md)',
                      background: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-text-secondary)',
                      lineHeight: 1.5,
                    }}
                  >
                    {item}
                  </div>
                )) : (
                  <div style={{ color: 'var(--color-text-muted)' }}>No watchlist items.</div>
                )}
              </div>
            </div>

            <div className="card">
              <h3 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: 'var(--spacing-md)' }}>
                🧠 Memory Systems
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)', maxHeight: '280px', overflowY: 'auto', paddingRight: 'var(--spacing-xs)' }}>
                {status.memorySystems.slice(0, 8).map((system) => (
                  <div key={system.path} style={{ padding: 'var(--spacing-sm)', background: 'rgba(255,255,255,0.03)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--spacing-sm)', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontWeight: 700 }}>{system.name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{system.kind}</div>
                      </div>
                      <span className={`badge ${system.status === 'present' ? 'badge-success' : 'badge-warning'}`}>
                        {system.status}
                      </span>
                    </div>
                    <div style={{ marginTop: 'var(--spacing-xs)', fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                      {system.items} items {system.sizeBytes > 0 ? `• ${system.sizeBytes} B` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {status.legacySpecCount > 0 && (
            <div style={{ marginTop: 'var(--spacing-lg)', color: 'var(--color-warning)', fontSize: '0.875rem' }}>
              Legacy / unstructured specs detected: {status.legacySpecCount}
            </div>
          )}
        </section>

        {/* Chart */}
        <div style={{ marginBottom: 'var(--spacing-2xl)' }}>
          <StatusChart data={data} />
        </div>

        {/* Search and Filter */}
        <div className="glass animate-fade-in" style={{ padding: 'var(--spacing-lg)', borderRadius: 'var(--radius-lg)', marginBottom: 'var(--spacing-xl)' }}>
          <div style={{ display: 'flex', gap: 'var(--spacing-md)', flexWrap: 'wrap' }}>
            <input
              type="text"
              placeholder="🔍 Search projects..."
              className="input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ flex: 1, minWidth: '250px' }}
            />
            <select
              className="input"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              style={{ minWidth: '200px' }}
            >
              <option value="all">All Status</option>
              <option value="Active">🟢 Active</option>
              <option value="Progress">🚧 In Progress</option>
              <option value="Complete">✅ Complete</option>
              <option value="Testing">⚡ Testing</option>
            </select>
          </div>
        </div>

        {/* Projects Grid */}
        <div className="grid grid-cols-3">
          {filteredProjects.map((project, index) => (
            <div key={project.name} style={{ animationDelay: `${index * 50}ms` }}>
              <ProjectCard project={project} />
            </div>
          ))}
        </div>

        {filteredProjects.length === 0 && (
          <div style={{ textAlign: 'center', padding: 'var(--spacing-2xl)', color: 'var(--color-text-muted)' }}>
            No projects found matching your criteria
          </div>
        )}

        {/* Services */}
        {data.services.length > 0 && (
          <div style={{ marginTop: 'var(--spacing-2xl)' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 'var(--spacing-lg)' }}>
              ⚙️ System Services
            </h2>
            <div className="grid grid-cols-2">
              {data.services.map((service, index) => (
                <div key={index} className="card animate-fade-in" style={{ animationDelay: `${index * 50}ms` }}>
                  <h3 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: 'var(--spacing-sm)' }}>
                    {service.name}
                  </h3>
                  <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', marginBottom: 'var(--spacing-sm)' }}>
                    {service.role}
                  </p>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                    <span style={{ color: 'var(--color-text-muted)' }}>{service.path}</span>
                    <span>{service.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
