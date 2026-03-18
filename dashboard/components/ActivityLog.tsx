'use client';

import { ActivityLogEntry } from '@/lib/types';

interface ActivityLogProps {
  entries: ActivityLogEntry[];
}

export default function ActivityLog({ entries }: ActivityLogProps) {
  const getLogIcon = (level: ActivityLogEntry['level']) => {
    switch (level) {
      case 'DONE': return '✅';
      case 'INFO': return 'ℹ️';
      case 'WARNING': return '⚠️';
      case 'ERROR': return '❌';
      default: return 'ℹ️';
    }
  };

  const getLogColor = (level: ActivityLogEntry['level']) => {
    switch (level) {
      case 'DONE': return 'var(--color-success)';
      case 'INFO': return 'var(--color-info)';
      case 'WARNING': return 'var(--color-warning)';
      case 'ERROR': return 'var(--color-error)';
      default: return 'var(--color-text-secondary)';
    }
  };

  if (entries.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 'var(--spacing-xl)', color: 'var(--color-text-muted)' }}>
        No activity logs yet
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
      {entries.map((entry, index) => (
        <div
          key={index}
          className="animate-slide-in"
          style={{
            display: 'flex',
            gap: 'var(--spacing-md)',
            padding: 'var(--spacing-md)',
            background: 'var(--color-bg-tertiary)',
            borderRadius: 'var(--radius-md)',
            borderLeft: `3px solid ${getLogColor(entry.level)}`,
            animationDelay: `${index * 50}ms`
          }}
        >
          <div style={{ fontSize: '1.25rem', flexShrink: 0 }}>
            {getLogIcon(entry.level)}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--spacing-xs)' }}>
              <span style={{ fontSize: '0.875rem', fontWeight: 600, color: getLogColor(entry.level) }}>
                {entry.level}
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                {entry.timestamp}
              </span>
            </div>
            <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
              {entry.message}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
