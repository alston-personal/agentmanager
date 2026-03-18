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
      const response = await fetch('/api/projects');
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

  return (
    <main style={{ minHeight: '100vh', padding: 'var(--spacing-2xl) 0' }}>
      <div className="container">
        {/* Header */}
        <header style={{ marginBottom: 'var(--spacing-2xl)', textAlign: 'center' }}>
          <h1 className="gradient-text animate-fade-in" style={{ fontSize: '3rem', fontWeight: 800, marginBottom: 'var(--spacing-md)' }}>
            ✈️ AI Command Center
          </h1>
          <p style={{ fontSize: '1.125rem', color: 'var(--color-text-secondary)' }}>
            Flight Deck - Mission Control Dashboard
          </p>
        </header>

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
            <button className="btn btn-primary" onClick={() => router.push('/workflows')}>
              ⚡ Workflows
            </button>
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
