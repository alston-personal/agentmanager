'use client';

import React, { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';

export default function KnowledgeDetailPage({ params }: { params: Promise<{ slug: string[] }> }) {
  const [item, setItem] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const resolvedParams = use(params);

  useEffect(() => {
    const slug = resolvedParams.slug.join('/');
    fetch(`/api/knowledge/${slug}`)
      .then(res => res.json())
      .then(data => {
        setItem(data.item);
        setLoading(false);
      });
  }, [resolvedParams]);

  if (loading) return <div className="container" style={{padding: '4rem', textAlign: 'center'}}>Initializing Consciousness...</div>;
  if (!item) return <div className="container" style={{padding: '4rem', textAlign: 'center'}}>Memory Fragment Not Found.</div>;

  // Improved Markdown Parser with Premium UI
  const renderContent = (content: string) => {
    const lines = content.split('\n');
    return lines.map((line, i) => {
      // Headers
      if (line.startsWith('### ')) return <h3 key={i} style={{fontSize: '1.4rem', fontWeight: 700, margin: '2rem 0 0.75rem', color: '#fff'}}>{line.slice(4)}</h3>;
      if (line.startsWith('## ')) return <h2 key={i} style={{fontSize: '1.8rem', fontWeight: 800, margin: '3rem 0 1.25rem', borderLeft: '4px solid var(--color-primary)', paddingLeft: '1rem', color: '#fff'}}>{line.slice(3)}</h2>;
      if (line.startsWith('# ')) return <h1 key={i} style={{fontSize: '2.5rem', fontWeight: 900, margin: '3.5rem 0 2rem', borderBottom: '1px solid var(--color-border)', paddingBottom: '1rem'}}>{line.slice(2)}</h1>;
      
      // Horizontal Rule
      if (line.trim() === '---') return <hr key={i} style={{border: 'none', borderTop: '1px solid var(--color-border)', margin: '3rem 0'}} />;
      
      // List
      if (line.trim().startsWith('- ')) return (
        <div key={i} style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.6rem', paddingLeft: '1rem' }}>
          <span style={{ color: 'var(--color-primary)', fontWeight: 'bold' }}>•</span>
          <span style={{ flex: 1 }}>{renderInline(line.trim().slice(2))}</span>
        </div>
      );
      
      // Blockquote
      if (line.startsWith('> ')) return (
        <blockquote key={i} style={{
          borderLeft: '4px solid var(--color-accent)', 
          background: 'rgba(244, 63, 94, 0.05)', 
          padding: '1.5rem', 
          margin: '1.5rem 0', 
          borderRadius: '0 8px 8px 0',
          fontStyle: 'italic',
          color: 'var(--color-text-secondary)'
        }}>
          {line.slice(2)}
        </blockquote>
      );

      // Blank line
      if (line.trim() === '') return <div key={i} style={{height: '0.75rem'}} />;

      return <p key={i} style={{marginBottom: '1rem', fontSize: '1.1rem', lineHeight: '1.9'}}>{renderInline(line)}</p>;
    });
  };

  const renderInline = (text: string): React.ReactNode[] => {
    let parts: React.ReactNode[] = [text];
    
    // Bold: **text**
    const boldParts: React.ReactNode[] = [];
    parts.forEach(p => {
      if (typeof p !== 'string') {
        boldParts.push(p);
        return;
      }
      const split = p.split(/\*\*([^*]+)\*\*/g);
      split.forEach((s, j) => {
        if (j % 2 === 1) boldParts.push(<strong key={`b-${j}`} style={{color: '#fff', fontWeight: 700}}>{s}</strong>);
        else boldParts.push(s);
      });
    });
    parts = boldParts;

    // Code: `code`
    const codeParts: React.ReactNode[] = [];
    parts.forEach(p => {
      if (typeof p !== 'string') {
        codeParts.push(p);
        return;
      }
      const split = p.split(/`([^`]+)`/g);
      split.forEach((s, j) => {
        if (j % 2 === 1) codeParts.push(<code key={`c-${j}`} style={{background: '#1a1a2e', color: '#a855f7', padding: '0.2rem 0.5rem', borderRadius: '4px', border: '1px solid rgba(168, 85, 247, 0.2)', fontSize: '0.9em', fontFamily: 'monospace'}}>{s}</code>);
        else codeParts.push(s);
      });
    });
    
    return codeParts;
  };

  return (
    <main style={{ minHeight: '100vh', padding: 'var(--spacing-3xl) 0' }}>
      <div className="container" style={{ maxWidth: '850px' }}>
        <button 
          className="btn" 
          onClick={() => router.back()} 
          style={{ 
            marginBottom: 'var(--spacing-xl)', 
            background: 'transparent', 
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-secondary)',
            padding: '0.5rem 1.25rem',
            borderRadius: 'var(--radius-full)'
          }}
        >
          ← Back to Vault
        </button>

        <article className="glass" style={{ padding: '4rem', borderRadius: 'var(--radius-lg)' }}>
          <header style={{ marginBottom: '4rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--spacing-md)', marginBottom: 'var(--spacing-md)' }}>
              <span className="badge" style={{ background: 'var(--color-primary)', color: '#fff', padding: '0.25rem 0.75rem', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase' }}>{item.category}</span>
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>Updated {item.lastUpdated}</span>
            </div>
            <h1 className="gradient-text" style={{ fontSize: '3.5rem', fontWeight: 900, lineHeight: '1.1', marginBottom: 'var(--spacing-lg)' }}>{item.title}</h1>
            <div style={{ display: 'flex', gap: 'var(--spacing-sm)' }}>
              {item.tags.map((tag: string) => (
                <span key={tag} style={{ color: 'var(--color-primary)', fontSize: '0.9rem' }}>#{tag}</span>
              ))}
            </div>
          </header>

          <div style={{ color: 'var(--color-text-secondary)', fontSize: '1.15rem' }}>
            {renderContent(item.content)}
          </div>
        </article>
      </div>
    </main>
  );
}
