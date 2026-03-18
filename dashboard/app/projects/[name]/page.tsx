'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Project } from '@/lib/types';
import ActivityLog from '@/components/ActivityLog';

export default function ProjectDetailPage({ params }: { params: Promise<{ name: string }> }) {
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [projectName, setProjectName] = useState<string>('');
  const router = useRouter();

  useEffect(() => {
    params.then(p => {
      setProjectName(p.name);
      fetchProject(p.name);
    });
  }, [params]);

  const fetchProject = async (name: string) => {
    try {
      const response = await fetch(`/api/projects/${name}`);
      if (!response.ok) {
        throw new Error('Project not found');
      }
      const data = await response.json();

      // Fetch full project data from projects list
      const projectsResponse = await fetch('/api/projects');
      const projectsData = await projectsResponse.json();
      const fullProject = projectsData.projects.find((p: Project) => p.name === name);

      setProject(fullProject || data);
    } catch (error) {
      console.error('Failed to fetch project:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="animate-pulse" style={{ textAlign: 'center' }}>
          <h2 className="gradient-text" style={{ fontSize: '1.5rem', fontWeight: 700 }}>
            Loading project...
          </h2>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-error)', marginBottom: 'var(--spacing-md)' }}>
            Project not found
          </h2>
          <button className="btn btn-primary" onClick={() => router.push('/')}>
            ← Back to Dashboard
          </button>
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

          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--spacing-md)', marginBottom: 'var(--spacing-md)' }}>
            <span style={{ fontSize: '3rem' }}>{project.icon}</span>
            <div>
              <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 800 }}>
                {project.displayName}
              </h1>
              <p style={{ fontSize: '1rem', color: 'var(--color-text-secondary)' }}>
                {project.name}
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--spacing-md)', alignItems: 'center' }}>
            <span className="badge badge-info">{project.status}</span>
            <span style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
              Last updated: {project.lastUpdated}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-3" style={{ gap: 'var(--spacing-xl)' }}>
          {/* Main Content */}
          <div style={{ gridColumn: 'span 2' }}>
            {/* Activity Log */}
            <div className="card" style={{ marginBottom: 'var(--spacing-xl)' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 'var(--spacing-lg)' }}>
                📝 Activity Log
              </h2>
              <ActivityLog entries={project.activityLog} />
            </div>
          </div>

          {/* Sidebar */}
          <div>
            {/* Todo List */}
            <div className="card" style={{ marginBottom: 'var(--spacing-xl)' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 'var(--spacing-lg)' }}>
                📅 Todo List
              </h3>
              {project.todoList.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
                  {project.todoList.map((todo, index) => (
                    <div
                      key={index}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 'var(--spacing-sm)',
                        padding: 'var(--spacing-sm)',
                        background: 'var(--color-bg-tertiary)',
                        borderRadius: 'var(--radius-sm)'
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={todo.completed}
                        readOnly
                        style={{ cursor: 'default' }}
                      />
                      <span style={{
                        fontSize: '0.875rem',
                        color: todo.completed ? 'var(--color-text-muted)' : 'var(--color-text-secondary)',
                        textDecoration: todo.completed ? 'line-through' : 'none'
                      }}>
                        {todo.text}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
                  No tasks defined yet
                </p>
              )}
            </div>

            {/* Blockers */}
            {project.blockers.length > 0 && (
              <div className="card" style={{ borderColor: 'var(--color-error)' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 'var(--spacing-lg)', color: 'var(--color-error)' }}>
                  🛑 Blockers & Issues
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
                  {project.blockers.map((blocker, index) => (
                    <div
                      key={index}
                      style={{
                        padding: 'var(--spacing-sm)',
                        background: 'rgba(239, 68, 68, 0.1)',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.875rem',
                        color: 'var(--color-text-secondary)'
                      }}
                    >
                      {blocker}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
