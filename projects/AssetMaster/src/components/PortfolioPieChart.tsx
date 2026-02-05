'use client';

import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Pie } from 'react-chartjs-2';

ChartJS.register(ArcElement, Tooltip, Legend);

interface PortfolioPieChartProps {
  data: {
    symbol: string;
    currentValue: number;
  }[];
}

export function PortfolioPieChart({ data }: PortfolioPieChartProps) {
  const chartData = {
    labels: data.map(d => d.symbol),
    datasets: [
      {
        data: data.map(d => d.currentValue),
        backgroundColor: [
          'rgba(59, 130, 246, 0.8)',   // blue
          'rgba(139, 92, 246, 0.8)',   // purple
          'rgba(236, 72, 153, 0.8)',   // pink
          'rgba(245, 158, 11, 0.8)',   // amber
          'rgba(16, 185, 129, 0.8)',   // emerald
          'rgba(99, 102, 241, 0.8)',   // indigo
        ],
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: {
          color: 'rgba(255, 255, 255, 0.7)',
          font: { size: 12 },
          padding: 20,
          usePointStyle: true,
        },
      },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        padding: 12,
        titleFont: { size: 14 },
        bodyFont: { size: 13 },
        displayColors: false,
      },
    },
  };

  return (
    <div className="w-full h-full min-h-[300px] flex items-center justify-center">
      {data.length > 0 ? (
        <Pie data={chartData} options={options} />
      ) : (
        <div className="text-muted-foreground text-sm italic">No data to display</div>
      )}
    </div>
  );
}
