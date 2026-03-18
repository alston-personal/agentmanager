import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { Workflow } from '@/lib/types';

const WORKFLOWS_DIR = path.join(process.cwd(), '..', '.agent', 'workflows');
const SKILLS_DIR = path.join(process.cwd(), '..', '.agent', 'skills');

export async function GET(request: NextRequest) {
  try {
    const workflows: Workflow[] = [];

    // Scan workflow files
    if (fs.existsSync(WORKFLOWS_DIR)) {
      const files = fs.readdirSync(WORKFLOWS_DIR);

      for (const file of files) {
        if (file.endsWith('.md')) {
          const filePath = path.join(WORKFLOWS_DIR, file);
          const content = fs.readFileSync(filePath, 'utf-8');

          // Parse frontmatter
          const frontmatterMatch = content.match(/^---\s*\n([\s\S]*?)\n---/);
          let description = '';

          if (frontmatterMatch) {
            const descMatch = frontmatterMatch[1].match(/description:\s*(.+)/);
            if (descMatch) {
              description = descMatch[1].trim();
            }
          }

          // Parse steps
          const stepsMatch = content.match(/---\s*\n([\s\S]*)/);
          const steps: string[] = [];
          let turbo = false;
          let turboAll = false;

          if (stepsMatch) {
            const lines = stepsMatch[1].split('\n');
            for (const line of lines) {
              if (line.trim().startsWith('//')) {
                if (line.includes('turbo-all')) turboAll = true;
                if (line.includes('turbo')) turbo = true;
              } else if (line.match(/^\d+\./)) {
                steps.push(line.trim());
              }
            }
          }

          const workflowId = file.replace('.md', '');
          workflows.push({
            id: `workflow-${workflowId}`,
            name: workflowId.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
            description,
            command: `/${workflowId}`,
            steps,
            turbo,
            turboAll,
          });
        }
      }
    }

    // Scan skills for commands
    if (fs.existsSync(SKILLS_DIR)) {
      const skillDirs = fs.readdirSync(SKILLS_DIR, { withFileTypes: true });

      for (const dir of skillDirs) {
        if (dir.isDirectory()) {
          const skillMdPath = path.join(SKILLS_DIR, dir.name, 'SKILL.md');

          if (fs.existsSync(skillMdPath)) {
            const content = fs.readFileSync(skillMdPath, 'utf-8');

            // Parse frontmatter
            const frontmatterMatch = content.match(/^---\s*\n([\s\S]*?)\n---/);
            let skillDescription = '';

            if (frontmatterMatch) {
              const descMatch = frontmatterMatch[1].match(/description:\s*(.+)/);
              if (descMatch) {
                skillDescription = descMatch[1].trim();
              }
            }

            // Look for commands section
            const commandsMatch = content.match(/##\s*(?:🚀\s*)?Commands?\s*(?:&|＆)\s*Workflows?\s*\n([\s\S]*?)(?=\n##|$)/i);

            if (commandsMatch) {
              const commandLines = commandsMatch[1].split('\n');

              for (const line of commandLines) {
                // Match patterns like: - `/plan [Goal]`: Description
                const cmdMatch = line.match(/^-\s*`(\/\w+)(?:\s*\[.*?\])?`\s*[:-]\s*(.+)/);

                if (cmdMatch) {
                  const [, command, description] = cmdMatch;

                  workflows.push({
                    id: `skill-${dir.name}-${command.substring(1)}`,
                    name: `${command.substring(1).charAt(0).toUpperCase() + command.substring(2)} (Skill)`,
                    description: description.trim(),
                    command,
                    steps: [skillDescription],
                    turbo: false,
                    turboAll: false,
                  });
                }
              }
            }
          }
        }
      }
    }

    // Sort workflows by command name
    workflows.sort((a, b) => a.command.localeCompare(b.command));

    return NextResponse.json({ workflows });
  } catch (error) {
    console.error('Error fetching workflows:', error);
    return NextResponse.json(
      { error: 'Failed to fetch workflows' },
      { status: 500 }
    );
  }
}
