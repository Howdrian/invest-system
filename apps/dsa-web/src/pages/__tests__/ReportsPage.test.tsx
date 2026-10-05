import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../api/history';
import { reportsApi } from '../../api/reports';
import type { ReportArtifactV1 } from '../../types/analysis';
import ReportsPage from '../ReportsPage';

vi.mock('../../api/history', () => ({ historyApi: { getDetail: vi.fn(), getMarkdown: vi.fn() } }));
vi.mock('../../components/report/ReportSummary', () => ({ ReportSummary: ({ readerMarkdown }: { readerMarkdown: string }) => <div>{readerMarkdown}</div> }));

vi.mock('../../api/reports', () => ({
  reportsApi: {
    getLatest: vi.fn(),
    listArtifacts: vi.fn(),
    getArtifact: vi.fn(),
  },
}));

const artifact: ReportArtifactV1 = {
  schemaVersion: 'report_artifact_v1',
  artifactId: 'latest',
  runDate: '2026-06-19',
  generatedAt: '2026-06-19T09:00:00Z',
  artifactType: 'daily',
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

function renderReportsPage(initialPath = '/reports') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/reports/:date" element={<ReportsPage />} />
        <Route path="/reports/:date/diagnostics" element={<ReportsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ReportsPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads latest ReportArtifact from API, not docs files', async () => {
    vi.mocked(reportsApi.getLatest).mockResolvedValue(artifact);
    vi.mocked(reportsApi.listArtifacts).mockResolvedValue([artifact]);

    renderReportsPage();

    expect(await screen.findByRole('heading', { name: '2026-06-19 投研日报' })).toBeInTheDocument();
    expect(reportsApi.getLatest).toHaveBeenCalledTimes(1);
    expect(reportsApi.listArtifacts).toHaveBeenCalledWith(30);
    expect(screen.getByText('等待。')).toBeInTheDocument();
    expect(screen.getByText('补数据')).toBeInTheDocument();
    expect(screen.queryByText('结论 A')).not.toBeInTheDocument();
    expect(screen.queryByText('来源 A')).not.toBeInTheDocument();
  });

  it('uses artifact list and detail endpoint for date selection', async () => {
    const older = { ...artifact, artifactId: 'daily:2026-06-18', runDate: '2026-06-18', title: '昨日报告' };
    vi.mocked(reportsApi.getLatest).mockResolvedValue(artifact);
    vi.mocked(reportsApi.listArtifacts).mockResolvedValue([artifact, older]);
    vi.mocked(reportsApi.getArtifact).mockResolvedValue(older);

    renderReportsPage();

    expect(await screen.findByRole('button', { name: /2026-06-18/ })).toBeInTheDocument();
    await screen.findByRole('heading', { name: '2026-06-19 投研日报' });
    fireEvent.click(screen.getByRole('button', { name: /2026-06-18/ }));

    expect(await screen.findByRole('heading', { name: '2026-06-18 投研日报' })).toBeInTheDocument();
    expect(reportsApi.getArtifact).toHaveBeenCalledWith('daily:2026-06-18');
  });

  it('opens a named native stock report at a stable history URL', async () => {
    const stock = { ...artifact, artifactId: 'history:7', artifactType: 'stock_governed' as const, title: '苹果（AAPL）个股分析' };
    vi.mocked(reportsApi.getArtifact).mockResolvedValue(stock);
    vi.mocked(reportsApi.listArtifacts).mockResolvedValue([stock]);
    vi.mocked(historyApi.getDetail).mockResolvedValue({ meta: { id: 7 } } as Awaited<ReturnType<typeof historyApi.getDetail>>);
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('苹果完整分析：现金流与估值的对照。');
    renderReportsPage('/reports/history:7');
    expect(await screen.findByText('苹果完整分析：现金流与估值的对照。')).toBeInTheDocument();
    expect(screen.queryByText('未提供核心理由。')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '高级诊断' })).toHaveAttribute('href', '/reports/history%3A7/diagnostics');
    expect(screen.getByRole('button', { name: /苹果.*AAPL/ })).toBeInTheDocument();
  });

  it('loads a dated report from the route and opens diagnostics route', async () => {
    vi.mocked(reportsApi.getArtifact).mockResolvedValue(artifact);
    vi.mocked(reportsApi.listArtifacts).mockResolvedValue([artifact]);

    renderReportsPage('/reports/2026-06-19/diagnostics');

    expect(await screen.findByRole('heading', { name: '最新报告 · 诊断' })).toBeInTheDocument();
    expect(reportsApi.getArtifact).toHaveBeenCalledWith('2026-06-19');
    expect(screen.getByTestId('report-diagnostics-view')).toBeInTheDocument();
    expect(screen.getByText('修复队列')).toBeInTheDocument();
  });
});
