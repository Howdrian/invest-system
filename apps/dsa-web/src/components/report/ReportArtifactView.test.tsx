import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ReportArtifactV1 } from '../../types/analysis';
import { ReportArtifactView } from './ReportArtifactView';

const artifact: ReportArtifactV1 = {
  schemaVersion: 'report_artifact_v1',
  artifactId: 'stock-600519-2026-06-19',
  runDate: '2026-06-19',
  generatedAt: '2026-06-19T09:00:00Z',
  artifactType: 'stock_governed',
  audience: 'reader',
  title: '贵州茅台 governed 报告',
  summary: {
    oneLine: '证据不足，暂不操作。',
    keyFacts: ['行情源刷新成功', '评分 5.5/10'],
    analysis: '宏观降级，只能做背景参考；个股证据链不足。',
    finalConclusion: '不操作，等待补证据。',
    nextSteps: ['补公告原文', '复核估值假设'],
  },
  sections: [
    { key: 'source', title: '数据源', kind: 'source', contentMarkdown: '行情：Eastmoney；公告：CNINFO。', confidence: 'medium' },
    { key: 'facts', title: '关键数据', kind: 'facts', contentMarkdown: '- 当前价可用\n- 宏观状态 PARTIAL', confidence: 'medium' },
    { key: 'analysis', title: '推论', kind: 'analysis', contentMarkdown: '证据不足，不能升级为交易。', confidence: 'low' },
    { key: 'final', title: '总结论', kind: 'final_conclusion', contentMarkdown: '不操作。', confidence: 'medium' },
    { key: 'next', title: '下一步', kind: 'next_steps', contentMarkdown: '- 等公告\n- 等承接', confidence: 'medium' },
  ],
  sourceHealth: {
    status: 'DEGRADED',
    verdict: 'trade_review_limited',
    canScore: false,
    canTradeReview: false,
  },
  decision: {
    action: 'no_action',
    gateStatus: 'blocked',
    score: 5.5,
    targetPct: 0,
    blockedReasons: ['score_below_6'],
  },
  agentOrigins: { raw: 2, derived: 4, missing: 1 },
  provenance: { origin: 'history', sourceFiles: ['reports/report_20260619.md'], generatedBy: 'test' },
  publish: {},
  quality: { completeness: 'partial', missingFields: [], validationErrors: [] },
};

describe('ReportArtifactView', () => {
  it('renders human report sections before audit JSON', () => {
    render(<ReportArtifactView artifact={artifact} />);

    expect(screen.getByRole('heading', { name: '贵州茅台 governed 报告' })).toBeInTheDocument();
    expect(screen.getByText('History Stock Report')).toBeInTheDocument();
    expect(screen.getByText('证据不足，暂不操作。')).toBeInTheDocument();
    expect(screen.getByText('数据源')).toBeInTheDocument();
    expect(screen.getByText(/行情：Eastmoney/)).toBeInTheDocument();
    expect(screen.getByText('关键数据')).toBeInTheDocument();
    expect(screen.getByText('推论')).toBeInTheDocument();
    expect(screen.getByText('总结论')).toBeInTheDocument();
    expect(screen.getByText('下一步')).toBeInTheDocument();
    expect(screen.getByText(/Source Health/)).toBeInTheDocument();
    expect(screen.getByText('数据源降级，可观察，不可作为满血交易依据')).toBeInTheDocument();
    expect(screen.getByText(/Agent origin/)).toBeInTheDocument();
    expect(screen.getAllByText(/不操作/).length).toBeGreaterThan(0);
    expect(screen.queryByText('schemaVersion')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看审计 JSON' }));
    expect(screen.getByText(/schemaVersion/)).toBeInTheDocument();
  });
});
