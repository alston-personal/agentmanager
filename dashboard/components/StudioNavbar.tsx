'use client';

import React from 'react';

export default function StudioNavbar() {
  return (
    <nav 
      style={{
        width: '100%',
        height: '60px',
        background: 'rgba(10, 14, 26, 0.88)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        position: 'sticky',
        top: 0,
        zIndex: 9999,
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        boxSizing: 'border-box',
      }}
    >
      <div 
        style={{
          width: '100%',
          maxWidth: '1440px',
          margin: '0 auto',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '1rem',
          flexWrap: 'wrap',
        }}
      >
        {/* Brand & Back to Studio Portal */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <a
            href="https://studio.milkcat.org/"
            target="_top"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.25) 0%, rgba(139, 0, 0, 0.45) 100%)',
              border: '1px solid rgba(239, 68, 68, 0.5)',
              color: '#ffffff',
              textDecoration: 'none',
              fontWeight: 700,
              fontSize: '0.84rem',
              boxShadow: '0 2px 12px rgba(239, 68, 68, 0.25)',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-1px)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(239, 68, 68, 0.4)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 2px 12px rgba(239, 68, 68, 0.25)';
            }}
          >
            <span>⬅️</span>
            <span>返回官網首頁</span>
          </a>

          <span style={{ color: 'rgba(255, 255, 255, 0.15)', fontSize: '0.9rem' }}>|</span>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '1.25rem' }}>🐈‍⬛</span>
            <span 
              style={{
                fontFamily: "'Playfair Display', serif",
                fontWeight: 800,
                fontSize: '1.1rem',
                letterSpacing: '0.5px',
                background: 'linear-gradient(135deg, #ffffff 0%, #ffb3b3 50%, #8b0000 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              Milkcat Studio
            </span>
            <span style={{ fontSize: '0.75rem', padding: '2px 8px', borderRadius: '6px', background: 'rgba(99, 102, 241, 0.15)', border: '1px solid rgba(99, 102, 241, 0.3)', color: '#a5b4fc', fontWeight: 600, marginLeft: '6px' }}>
              Command Center
            </span>
          </div>
        </div>

        {/* Quick Links across Milkcat Ecosystem */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.84rem' }}>
          <a
            href="https://studio.milkcat.org/world"
            target="_top"
            style={{ color: '#94a3b8', textDecoration: 'none', padding: '6px 12px', borderRadius: '8px', transition: 'all 0.2s' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.background = 'transparent'; }}
          >
            🪐 3D世界
          </a>
          <a
            href="https://studio.milkcat.org/role-island/"
            target="_top"
            style={{ color: '#94a3b8', textDecoration: 'none', padding: '6px 12px', borderRadius: '8px', transition: 'all 0.2s' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.background = 'transparent'; }}
          >
            🏝️ 專案群島
          </a>
          <a
            href="https://studio.milkcat.org/personas/mio/"
            target="_top"
            style={{ color: '#f472b6', textDecoration: 'none', padding: '6px 12px', borderRadius: '8px', transition: 'all 0.2s' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#fbcfe8'; e.currentTarget.style.background = 'rgba(244,114,182,0.1)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#f472b6'; e.currentTarget.style.background = 'transparent'; }}
          >
            🌸 晴湖小築
          </a>
          <a
            href="https://studio.milkcat.org/tiandao/"
            target="_top"
            style={{ color: '#94a3b8', textDecoration: 'none', padding: '6px 12px', borderRadius: '8px', transition: 'all 0.2s' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.background = 'transparent'; }}
          >
            📚 連載作品
          </a>
          <a
            href="https://studio.milkcat.org/todos"
            target="_top"
            style={{ color: '#94a3b8', textDecoration: 'none', padding: '6px 12px', borderRadius: '8px', transition: 'all 0.2s' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.background = 'transparent'; }}
          >
            📋 待辦總覽
          </a>
        </div>
      </div>
    </nav>
  );
}
