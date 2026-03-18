'use client';
import { useState } from 'react';
import { Project } from '@/lib/types';
import Link from 'next/link';

interface ProjectCardProps {
  project: Project;
}

export default function ProjectCard({ project }: ProjectCardProps) {
  const [isCopied, setIsCopied] = useState(false);

  const handleStartSession = (e: React.MouseEvent) => {
    e.preventDefault();
    const prompt = `請讀取 ${project.displayName} (${project.name}) 的 README 與 STATUS.md，並準備接受新任務指令。請將本對話標題鎖定為「[${project.displayName}] 工作階段」，除非我主動要求修改。`;
    navigator.clipboard.writeText(prompt);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const getStatusBadgeClass = (status: string) => {
    if (status.includes('Active') || status.includes('🟢')) return 'badge-success';
    if (status.includes('Progress') || status.includes('🚧')) return 'badge-warning';
    if (status.includes('Complete') || status.includes('✅')) return 'badge-success';
    if (status.includes('Failed') || status.includes('❌')) return 'badge-error';
    if (status.includes('Testing') || status.includes('⚡')) return 'badge-info';
    return 'badge-info';
  };

  const completedTasks = project.todoList.filter(t => t.completed).length;
  const totalTasks = project.todoList.length;
  const progress = totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0;

  return (
    <Link href={`/projects/${project.name}`}>
      <div className="card animate-fade-in relative" style={{ height: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 'var(--spacing-md)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--spacing-sm)' }}>
            <span style={{ fontSize: '2rem' }}>{project.icon}</span>
            <div>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: 'var(--spacing-xs)' }}>
                {project.displayName}
              </h3>
              <span className={`badge ${getStatusBadgeClass(project.status)}`}>
                {project.status}
              </span>
            </div>
          </div>
          <button
            onClick={handleStartSession}
            className={`btn ${isCopied ? 'btn-success' : 'btn-primary'}`}
            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', position: 'absolute', top: '1rem', right: '1rem' }}
          >
            {isCopied ? '✅ Copied Prompt' : '🚀 Start Session'}
          </button>
        </div>

        {project.activityLog.length > 0 && (
          <div style={{ marginBottom: 'var(--spacing-md)' }}>
            <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
              {project.activityLog[0].message.substring(0, 100)}
              {project.activityLog[0].message.length > 100 ? '...' : ''}
            </p>
          </div>
        )}

        {totalTasks > 0 && (
          <div style={{ marginBottom: 'var(--spacing-md)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--spacing-xs)' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)' }}>Progress</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)' }}>
                {completedTasks}/{totalTasks}
              </span>
            </div>
            <div style={{
              width: '100%',
              height: '6px',
              background: 'var(--color-bg-tertiary)',
              borderRadius: 'var(--radius-sm)',
              overflow: 'hidden'
            }}>
              <div style={{
                width: `${progress}%`,
                height: '100%',
                background: 'var(--gradient-primary)',
                transition: 'width var(--transition-base)'
              }} />
            </div>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
          <span>📅 {project.lastUpdated}</span>
          {project.activityLog.length > 0 && (
            <span>📝 {project.activityLog.length} logs</span>
          )}
        </div>
      </div>
    </Link>
  );
}
