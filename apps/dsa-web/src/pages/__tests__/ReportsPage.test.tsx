import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { reportsApi } from '../../api/reports';
import type { ReportArtifactV1 } from '../../types/analysis';
import ReportsPage from '../ReportsPage';

vi.mock('../../api/reports', () => ({
  reportsApi: {
    getLatest: vi.fn(),
  },
}));

const artifact: ReportArtifactV1 = {
  schemaVersion: 'report_artifact_v1',
  artifactId: 'latest',
  runDate: '2026-06-19',
  generatedAt: '2026-06-19T09:00:00Z',
  artifactType: 'stock_governed',
  audience: 'reader',
  title: '最新报告',
  summary: {
    oneLine: '今天不操作。',
    keyFacts: ['数据可读'],
    analysis: '证据不足。',
    finalConclusion: '等待。',
    nextSteps: ['补数据'],
  },
  sections: [
    { key: 'source', title: '数据源', kind: 'source', contentMarkdown: '来源 A' },
    { key: 'facts', title: '关键数据', kind: 'facts', contentMarkdown: '事实 A' },
    { key: 'analysis', title: '推论', kind: 'analysis', contentMarkdown: '推论 A' },
    { key: 'final', title: '总结论', kind: 'final_conclusion', contentMarkdown: '结论 A' },
    { key: 'next', title: '下一步', kind: 'next_steps', contentMarkdown: '下一步 A' },
  ],
  provenance: { origin: 'history', sourceFiles: [], generatedBy: 'test' },
  publish: {},
  quality: { completeness: 'complete', missingFields: [], validationErrors: [] },
};

describe('ReportsPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads latest ReportArtifact from API, not docs files', async () => {
    vi.mocked(reportsApi.getLatest).mockResolvedValue(artifact);

    render(<ReportsPage />);

    expect(await screen.findByRole('heading', { name: '最新报告' })).toBeInTheDocument();
    expect(reportsApi.getLatest).toHaveBeenCalledTimes(1);
    expect(screen.getByText('来源 A')).toBeInTheDocument();
  });
});
