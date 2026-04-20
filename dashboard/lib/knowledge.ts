import fs from 'fs';
import path from 'path';
import matter from 'gray-matter';
import { AGENT_DATA_ROOT } from './data-root';

const KNOWLEDGE_DIR = path.join(AGENT_DATA_ROOT, 'knowledge');

export interface KnowledgeItem {
  slug: string;
  title: string;
  category: string;
  tags: string[];
  lastUpdated: string;
  excerpt: string;
  content?: string;
  path: string;
}

export function getAllKnowledgeItems(): KnowledgeItem[] {
  if (!fs.existsSync(KNOWLEDGE_DIR)) return [];

  const items: KnowledgeItem[] = [];

  function walk(dir: string) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
      const fullPath = path.join(dir, file);
      if (fs.statSync(fullPath).isDirectory()) {
        walk(fullPath);
      } else if (file.endsWith('.md')) {
        const fileContent = fs.readFileSync(fullPath, 'utf-8');
        const { data, content } = matter(fileContent);
        const relativePath = path.relative(KNOWLEDGE_DIR, fullPath);
        const slug = relativePath.replace(/\.md$/, '');

        items.push({
          slug,
          title: data.title || path.basename(file, '.md'),
          category: data.category || path.dirname(relativePath),
          tags: data.tags || [],
          lastUpdated: data.last_updated || '',
          excerpt: content.slice(0, 200) + '...',
          path: relativePath
        });
      }
    }
  }

  walk(KNOWLEDGE_DIR);
  return items;
}

export function getKnowledgeItem(slug: string): KnowledgeItem | null {
  const fullPath = path.join(KNOWLEDGE_DIR, `${slug}.md`);
  if (!fs.existsSync(fullPath)) return null;

  const fileContent = fs.readFileSync(fullPath, 'utf-8');
  const { data, content } = matter(fileContent);

  return {
    slug,
    title: data.title || path.basename(fullPath, '.md'),
    category: data.category || path.dirname(slug),
    tags: data.tags || [],
    lastUpdated: data.last_updated || '',
    excerpt: '',
    content,
    path: `${slug}.md`
  };
}
