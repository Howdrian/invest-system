import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import { ResearchFocusList } from './ResearchFocusList';

describe('research opinions versus personal watchlist', () => {
  it('renders explicit ratings, horizon and list origins without turning opinions into observation', () => {
    render(<MemoryRouter><ResearchFocusList sourceUrl={() => null} value={{
      schema: 'reader_focus_list_v1', note: '研究评级，不自动加入自选', sectorCoverage: '',
      researchWindow: { label: '回看近1个月 · 研判未来1–2个月', lookbackStart: '2026-08-07', outlookEnd: '2026-11-07' },
      sectors: [{ market: '美股', targets: ['能源'], priority: '看好', basis: '现金流改善', watchFor: '供需反转则调整', evidenceIds: ['e'] }],
      stocks: [{ symbol: 'TEST', name: '测试公司', market: '美股', priority: '买入', reason: '催化与估值有吸引力',
        horizon: '未来两个月', listOrigin: '系统研究候选', sourceLabel: 'CIO', evidenceLabel: '存在争议',
        watchFor: '盈利下修则退出', asOf: '2026-09-04', evidenceIds: ['e'] }],
    }} /></MemoryRouter>);
    expect(screen.getByText('买入')).toBeInTheDocument();
    expect(screen.getByText('系统研究候选')).toBeInTheDocument();
    expect(screen.getByText(/研究周期：未来两个月/)).toBeInTheDocument();
    expect(screen.getByText(/2026-08-07 至 2026-11-07/)).toBeInTheDocument();
    expect(screen.getByText(/供需反转则调整/)).toBeInTheDocument();
    expect(screen.queryByText('继续观察')).not.toBeInTheDocument();
  });
});

it('uses shared reader copy for three time meanings and keeps a longer company thesis', () => {
  render(<MemoryRouter><ResearchFocusList sourceUrl={() => null} value={{
    schema: 'reader_focus_list_v1', note: '本期研究意见', sectorCoverage: '', sectors: [],
    researchWindow: { label: '聚焦本期机会，结合必要历史', asOf: '2026-09-08',
      lookbackStart: '2026-08-08', outlookEnd: '2026-11-08',
      displayLines: ['近期变化：8月至9月', '建议适用期：9月至11月', '历史参照：按实际材料'] },
    sectorPerformance: [{ market: '美股', scope: '行业代理', asOf: '2026-09-04', benchmark: 'SPY', evidenceIds: ['e1'], rows: [
      { code: 'XLK', name: '科技', asOf: '2026-09-04', sourceUrl: '', return120dPct: 12.345 }] }],
    stocks: [{ symbol: 'TEST', name: '公司', market: '美股', priority: '买入', reason: '经营改善',
      horizon: '6–12个月', watchFor: '', asOf: '', sourceLabel: 'CIO', evidenceLabel: '财报', evidenceIds: [] }],
  }} /></MemoryRouter>);
  expect(screen.getByText('近期变化：8月至9月')).toBeInTheDocument();
  expect(screen.getByText('建议适用期：9月至11月')).toBeInTheDocument();
  expect(screen.getByText('历史参照：按实际材料')).toBeInTheDocument();
  expect(screen.getByText('研究周期：6–12个月')).toBeInTheDocument();
  expect(screen.queryByText(/2026-08-08 至 2026-11-08/)).not.toBeInTheDocument();
  expect(screen.getByText('120日')).toBeInTheDocument();
  expect(screen.getByText('+12.35%')).toBeInTheDocument();
});

it('keeps a full same-run company argument separate from the original DSA report', () => {
  render(<MemoryRouter><ResearchFocusList sourceUrl={(url) => url || null} value={{
    schema: 'reader_focus_list_v1', note: '', sectorCoverage: '', sectors: [],
    stocks: [{ symbol: 'AAPL', name: 'Apple', market: '美股', priority: '买入', reason: '综合看好，当前等待止跌。',
      lead: '综合看好，当前等待止跌。', historyRecordId: 13, watchFor: '止跌后分步参与', asOf: '',
      sourceLabel: 'CIO', evidenceLabel: '研究判断', evidenceIds: [], research: [
        { department: '基本面部门', text: '财务附注完整结论，包括现金流主因。', label: '有据支持', evidenceSamples: [
          { id: 'e1', sourceName: 'SEC', sourceUrl: 'https://www.sec.gov/report', asOf: '2026-06-30', label: '经营现金流主要来自回款增长。' } ] } ] }],
  }} /></MemoryRouter>);
  expect(screen.getByText('综合研究 · 理由、反证与入场条件')).toBeInTheDocument();
  expect(screen.getByText('财务附注完整结论，包括现金流主因。')).toBeInTheDocument();
  expect(screen.getByText('经营现金流主要来自回款增长。')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /原 DSA 短线分析/ })).toHaveAttribute('href', '/reports/history:13');
  expect(screen.queryByRole('link', { name: /完整个股分析/ })).not.toBeInTheDocument();
});
