import { NextRequest, NextResponse } from 'next/server';
import { getAllProjects, parseDashboard } from '@/lib/markdown-parser';

export async function GET(request: NextRequest) {
  try {
    const projects = getAllProjects();
    const { services, ideas } = parseDashboard();

    return NextResponse.json({
      projects,
      services,
      ideas,
      lastSync: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Error fetching projects:', error);
    return NextResponse.json(
      { error: 'Failed to fetch projects' },
      { status: 500 }
    );
  }
}
