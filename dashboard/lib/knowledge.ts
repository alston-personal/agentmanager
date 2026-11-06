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
    let files: string[] = [];
    try {
      files = fs.readdirSync(dir);
    } catch (e) {
      return;
    }

    for (const file of files) {
      const fullPath = path.join(dir, file);
      try {
        const stat = fs.statSync(fullPath);
        if (stat.isDirectory()) {
          walk(fullPath);
        } else if (file.endsWith('.md')) {
          const fileContent = fs.readFileSync(fullPath, 'utf-8');
          let parsedTitle = path.basename(file, '.md').replace(/[-_]/g, ' ');
          const relativePath = path.relative(KNOWLEDGE_DIR, fullPath);
          const dirCategory = path.dirname(relativePath);
          let parsedCategory = dirCategory === '.' ? 'General' : dirCategory;
          let parsedTags: string[] = [];
          let parsedLastUpdated = '';
          let parsedExcerpt = '';
          let parsedContent = fileContent;

          try {
            const { data, content } = matter(fileContent);
            parsedContent = content;
            if (data.title) parsedTitle = String(data.title);
            if (data.category) parsedCategory = String(data.category);
            if (Array.isArray(data.tags)) parsedTags = data.tags.map(String);
            if (data.last_updated) {
              const dt = new Date(data.last_updated);
              parsedLastUpdated = !isNaN(dt.getTime()) ? dt.toISOString().slice(0, 10) : String(data.last_updated);
            }
          } catch (matterErr) {
            const h1Match = fileContent.match(/^#\s+(.+)$/m);
            if (h1Match) parsedTitle = h1Match[1].trim();
          }

          if (!parsedCategory || parsedCategory === '.') {
            parsedCategory = 'General';
          }

          const slug = relativePath.replace(/\.md$/, '');
          const cleanText = parsedContent.replace(/^#+.*$/gm, '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').trim();
          parsedExcerpt = Array.from(cleanText).slice(0, 160).join('') + '...';

          items.push({
            slug,
            title: parsedTitle,
            category: parsedCategory,
            tags: parsedTags,
            lastUpdated: parsedLastUpdated,
            excerpt: parsedExcerpt,
            path: relativePath
          });
        }
      } catch (err) {
        console.error(`Error processing knowledge item ${fullPath}:`, err);
      }
    }
  }

  walk(KNOWLEDGE_DIR);
  return items;
}

export function getKnowledgeItem(slug: string): KnowledgeItem | null {
  const fullPath = path.join(KNOWLEDGE_DIR, `${slug}.md`);
  if (!fs.existsSync(fullPath)) return null;

  try {
    const fileContent = fs.readFileSync(fullPath, 'utf-8');
    let title = path.basename(fullPath, '.md').replace(/[-_]/g, ' ');
    let category = path.dirname(slug) === '.' ? 'General' : path.dirname(slug);
    let tags: string[] = [];
    let lastUpdated = '';
    let content = fileContent;

    try {
      const parsed = matter(fileContent);
      content = parsed.content;
      if (parsed.data.title) title = String(parsed.data.title);
      if (parsed.data.category) category = String(parsed.data.category);
      if (Array.isArray(parsed.data.tags)) tags = parsed.data.tags.map(String);
      if (parsed.data.last_updated) {
        const dt = new Date(parsed.data.last_updated);
        lastUpdated = !isNaN(dt.getTime()) ? dt.toISOString().slice(0, 10) : String(parsed.data.last_updated);
      }
    } catch (matterErr) {
      const h1Match = fileContent.match(/^#\s+(.+)$/m);
      if (h1Match) title = h1Match[1].trim();
    }

    return {
      slug,
      title,
      category,
      tags,
      lastUpdated,
      excerpt: '',
      content,
      path: `${slug}.md`
    };
  } catch (err) {
    console.error(`Error reading knowledge item ${fullPath}:`, err);
    return null;
  }
}
