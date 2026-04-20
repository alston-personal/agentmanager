'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

interface KnowledgeItem {
  slug: string;
  title: string;
  category: string;
  tags: string[];
  lastUpdated: string;
  excerpt: string;
}

export default function KnowledgePage() {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    fetch('/api/knowledge')
      .then(res => res.json())
      .then(data => {
        setItems(data.items || []);
        setLoading(false);
      })
      .catch(err => console.error(err));
  }, []);

  if (loading) return <div className="container" style={{padding: '4rem'}}>Loading knowledge vault...</div>;

  // Group items by category
  const categories: Record<string, KnowledgeItem[]> = {};
  items.forEach(item => {
    if (!categories[item.category]) categories[item.category] = [];
    categories[item.category].push(item);
  });

  return (
    <main style={{ minHeight: '100vh', padding: 'var(--spacing-2xl) 0' }}>
      <div className="container">
        <div style={{ marginBottom: 'var(--spacing-2xl)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--spacing-xl)' }}>
          <button className="btn btn-secondary" onClick={() => router.push('/')} style={{ marginBottom: 'var(--spacing-lg)' }}>
            ← Back to Dashboard
          </button>
          <h1 className="gradient-text" style={{ fontSize: '3.5rem', fontWeight: 900 }}>🧠 Knowledge Vault</h1>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '1.2rem' }}>The crystallized consciousness of AgentOS.</p>
        </div>

        {Object.entries(categories).map(([category, catItems]) => (
          <section key={category} style={{ marginBottom: 'var(--spacing-3xl)' }}>
            <h2 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: 'var(--spacing-xl)', color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: 'var(--spacing-sm)' }}>
              <span style={{ width: '4px', height: '1.75rem', background: 'var(--color-primary)', borderRadius: '2px' }}></span>
              {category.toUpperCase()}
            </h2>
            <div className="grid grid-cols-2" style={{ gap: 'var(--spacing-xl)' }}>
              {catItems.map((item) => (
                <div key={item.slug} className="card clickable" onClick={() => router.push(`/knowledge/${item.slug}`)} style={{ transition: 'transform 0.2s', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '4px', background: 'linear-gradient(90deg, var(--color-primary), var(--color-secondary))' }}></div>
                  <div style={{ marginBottom: 'var(--spacing-md)' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>📅 {item.lastUpdated}</span>
                  </div>
                  <h3 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 'var(--spacing-sm)', color: 'var(--color-text-primary)' }}>{item.title}</h3>
                  <p style={{ fontSize: '0.95rem', color: 'var(--color-text-secondary)', lineHeight: '1.5', marginBottom: 'var(--spacing-md)' }}>{item.excerpt}</p>
                  <div style={{ display: 'flex', gap: 'var(--spacing-xs)', flexWrap: 'wrap' }}>
                    {item.tags.map(tag => (
                      <span key={tag} className="badge" style={{ fontSize: '0.7rem', background: 'rgba(99, 102, 241, 0.1)', color: 'var(--color-primary)' }}>#{tag}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
