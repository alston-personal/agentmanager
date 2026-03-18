'use client';

import { DashboardData } from '@/lib/types';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

interface StatusChartProps {
  data: DashboardData;
}

export default function StatusChart({ data }: StatusChartProps) {
  // Count projects by status
  const statusCounts = data.projects.reduce((acc, project) => {
    const status = project.status;
    const key = status.includes('Active') || status.includes('🟢') ? 'Active' :
      status.includes('Progress') || status.includes('🚧') ? 'In Progress' :
        status.includes('Complete') || status.includes('✅') ? 'Complete' :
          status.includes('Failed') || status.includes('❌') ? 'Failed' :
            'Other';

    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const chartData = Object.entries(statusCounts).map(([name, value]) => ({
    name,
    value,
  }));

  const COLORS = {
    'Active': '#10b981',
    'In Progress': '#f59e0b',
    'Complete': '#3b82f6',
    'Failed': '#ef4444',
    'Other': '#8b5cf6',
  };

  return (
    <div className="card" style={{ height: '400px' }}>
      <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 'var(--spacing-lg)' }}>
        Project Status Distribution
      </h3>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
            outerRadius={100}
            fill="#8884d8"
            dataKey="value"
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[entry.name as keyof typeof COLORS] || COLORS.Other} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: 'var(--color-bg-tertiary)',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-text-primary)'
            }}
          />
          <Legend
            wrapperStyle={{
              color: 'var(--color-text-secondary)'
            }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
