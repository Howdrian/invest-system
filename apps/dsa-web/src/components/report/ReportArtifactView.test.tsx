import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ReportArtifactV1 } from '../../types/analysis';
import { ReportArtifactDiagnosticsView, ReportArtifactView } from './ReportArtifactView';

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
  analysisMode: 'LIMITED_REVIEW',
  sourceHealthV2: {
    schema: 'source_health_v2',
    overallMode: 'LIMITED_REVIEW',
    overallScore: 0.58,
    domains: {
      price: { status: 'available', coverage: 1, freshness: 'fresh', confidence: 'high', blockers: [], repairHints: [] },
      fundamentals: { status: 'missing', coverage: 0, freshness: 'missing', confidence: 'low', blockers: ['missing_verified_fact'], repairHints: ['补 SEC/公告/财务事实'] },
      news_sentiment: { status: 'degraded', coverage: 0.4, freshness: 'fresh', confidence: 'low', blockers: ['search_only'], repairHints: ['回跳公告/IR'] },
    },
    providerMatrix: [
      { provider: 'YfinanceFetcher', market: 'us', domain: 'price', status: 'success', authState: 'not_required', latencyMs: 12, sourceTier: 'free' },
      { provider: 'Tavily', market: 'global', domain: 'news_sentiment', status: 'rate_limited', authState: 'configured', fallbackTo: 'SearXNG', sourceTier: 'free_tier', recordCount: 0, errorType: 'rate_limited' },
    ],
    claimPolicy: {
      canScore: true,
      canActionableAdvice: true,
      canPositionSizing: false,
      mustShowCaveat: true,
    },
    claimEvidence: {
      schema: 'claim_evidence_v1',
      supportFactTypes: ['verified_fact', 'derived_fact'],
      positionSizingMissingCriticalThreshold: 20,
      claims: {
        score: {
          label: '评分',
          status: 'supported',
          requiredDomains: ['price', 'fundamentals', 'filings_events', 'macro'],
          evidenceIds: ['cninfo:600519:1'],
          evidenceCount: 1,
          missingDomains: ['price', 'fundamentals', 'macro'],
        },
        actionable_advice: {
          label: '交易建议',
          status: 'supported',
          requiredDomains: ['filings_events', 'macro', 'news_sentiment'],
          evidenceIds: ['cninfo:600519:1'],
          evidenceCount: 1,
          missingDomains: ['macro', 'news_sentiment'],
        },
        position_sizing: {
          label: '仓位建议',
          status: 'missing',
          requiredDomains: ['price', 'fundamentals', 'portfolio', 'macro'],
          evidenceIds: [],
          evidenceCount: 0,
          missingDomains: ['price', 'fundamentals', 'portfolio', 'macro'],
          blockers: ['missing_critical_facts_above_threshold'],
        },
      },
    },
  },
  evidenceStats: {
    schema: 'evidence_stats_v1',
    verifiedFacts: 0,
    derivedFacts: 1,
    discoveryItems: 2,
    missingFacts: 1,
    missingCriticalFacts: 84,
  },
  evidenceItems: [
    {
      id: 'cninfo:600519:1',
      domain: 'filings_events',
      factType: 'verified_fact',
      provider: 'CNINFO',
      symbol: '600519',
      value: '年度报告公告',
      asOf: '2026-06-19',
      sourceUrl: 'https://example.test/cninfo.pdf',
      confidence: 'high',
    },
    {
      id: 'gdelt:1',
      domain: 'news_sentiment',
      factType: 'discovery',
      provider: 'GDELT',
      value: '市场事件发现',
      sourceUrl: 'https://example.test/news',
      confidence: 'low',
    },
  ],
  readerV3: {
    schema: 'reader_v3_v1',
    runDate: '2026-06-19',
    timing: {
      reportDate: '2026-06-19',
      dataAsOf: '2026-06-19T08:30:00Z',
      generatedAt: '2026-06-19T09:00:00Z',
    },
    hero: {
      marketStance: '中性偏谨慎',
      portfolioAction: '保持现金，不新增仓位',
      validity: '截至下个交易日开盘前',
      dataCoverage: 'A股主要指数完整；美股为观察样本',
      action: '旧动作（不应显示）',
      status: '多市场观察简报',
      confidence: '中等可信',
      oneLine: '证据不足，暂不操作。',
      maxLimitation: '公告和基本面证据仍需补齐。',
      coverage: '旧覆盖（不应显示）',
    },
    keyReasons: ['行情可读；基本面证据不足。', '公告事实需要回跳 CNINFO。'],
    counterpoints: ['若公告确认利好，当前结论需要重评。'],
    nextSteps: ['补公告原文。', '复核估值假设。'],
    marketMatrix: [
      { market: 'CN', scopeLabel: 'A股市场', scopeType: 'market', state: '主要指数承压', headline: '上证指数 -1.85%', scopeNote: '基于宽基指数。' },
      { market: 'US', scopeLabel: '美股观察样本', scopeType: 'sample', state: '观察样本走强', headline: 'Apple +1.76%（1日）', scopeNote: '不代表美股整体。' },
    ],
    stockMatrix: [
      { symbol: '600519', name: '贵州茅台', market: 'CN', stance: '观察', lastPrice: 1258.99, currency: 'CNY', return1dPct: 0.63, return20dPct: 3.88, trend: '短中期趋势向上', fundamental: '营收同比 +6.34%', valuation: 'PE(TTM) 21.20；历史分位样本不足', latestEvent: '年度权益分派公告', eventDate: '2026-06-21', eventUrl: 'https://example.test/cninfo.pdf', watchLevels: '5日线 1228.18 / 20日线 1200.81' },
    ],
    adjudication: {
      sharedFacts: ['行情数据可读，公告事实需回跳原文。'],
      baseCase: '在证据补齐前维持观察。',
      strongestAlternative: '若公告确认实质利好，当前谨慎判断需要上调。',
      judgment: '当前不操作，等待公告和基本面复核。',
      why: '现有直接证据不足以支持行动。',
      invalidationTriggers: ['公告确认实质利好并得到基本面验证。'],
    },
    reliability: {
      label: '可用，含待确认情景',
      headlineSafe: true,
      warnings: ['1 条情景判断已改为条件式表述。'],
      supportedClaims: 3,
      hypothesisClaims: 1,
      rejectedClaims: 0,
    },
    reportSections: [
      {
        key: 'market_status',
        title: '市场状态',
        body: '市场处于震荡观察。',
        bullets: ['风险偏好一般。'],
        counterpoints: ['成交确认不足。'],
        nextActions: ['继续观察市场宽度。'],
        evidenceSamples: [{ id: 'cninfo:600519:1', label: 'raw rows: annual_report_payload', sourceName: '巨潮资讯', provider: 'CninfoFetcher', factType: '已验证事实', asOf: '2026-06-19', sourceUrl: 'https://example.test/cninfo.pdf' }],
      },
      {
        key: 'macro_geo',
        title: '宏观与地缘',
        body: '宏观背景偏中性，地缘暂无重大已验证冲击。',
        bullets: ['公告事实已纳入。'],
        counterpoints: [],
        nextActions: [],
        evidenceSamples: [],
      },
    ],
    dataConfidence: '数据可信度低；本轮主要用于观察。',
    evidenceSummary: { verifiedFacts: 0, derivedFacts: 1, discoveryItems: 2, missingCriticalFacts: 84, departmentGapItems: 2 },
    departmentCards: [
      {
        agent: 'CIOAgent',
        label: 'CIO 报告',
        conclusion: '证据不足，暂不操作。',
        keyClaims: ['行情可读，但基本面证据不足。'],
        counterpoints: ['若公告确认利好，当前结论需要重评。'],
        dataGaps: ['公告和基本面证据仍需补齐。'],
        nextAction: '补公告原文。',
        confidence: 'low',
        supportSignals: ['已纳入公告来源。'],
        evidenceSamples: [
          { id: 'cninfo:600519:1', label: 'raw rows: annual_report_payload', sourceName: '巨潮资讯', provider: 'CninfoFetcher', factType: '已验证事实', asOf: '2026-06-19', sourceUrl: 'https://example.test/cninfo.pdf' },
          { id: 'yf:600519:1', label: 'raw rows: price_payload', provider: 'YfinanceFetcher', factType: '行情事实', asOf: '2026-06-19', sourceUrl: 'javascript:alert(1)' },
        ],
      },
      {
        agent: '基本面部门',
        label: '基本面部门',
        conclusion: '上游分析材料中的持仓快照尚未提供完整持仓。',
        keyClaims: ['行业强弱排行与热门标的列表只支持观察。'],
        challengedClaims: [{
          claim: '单一季度数据证明基本面必然恶化。',
          status: '存在有效反证，未作为确定依据',
          opposingScenario: '若变化来自统计口径，主营趋势可能未变。',
          falsifier: '官方定期报告确认主营收缩。',
        }],
        counterpoints: [],
        dataGaps: [],
        nextAction: '补持仓数量、持仓市值与成本价后复核。',
        confidence: 'medium',
        supportSignals: [],
        evidenceSamples: [],
      },
    ],
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
  it('does not invent a clock time for date-only evidence', () => {
    const dateOnly = structuredClone(artifact);
    if (dateOnly.readerV3?.timing) dateOnly.readerV3.timing.dataAsOf = '2026-06-19';

    render(<ReportArtifactView artifact={dateOnly} />);

    expect(screen.getByText(/综合数据截至 2026-06-19 · 生成于 17:00/)).toBeInTheDocument();
    expect(screen.queryByText(/综合数据截至 2026-06-19 08:00/)).not.toBeInTheDocument();
  });

  it('renders product reader by default and hides engineering fields', () => {
    render(<ReportArtifactView artifact={artifact} />);

    expect(screen.getByRole('heading', { name: '2026-06-19 投研日报' })).toBeInTheDocument();
    expect(screen.getByText('研究立场')).toBeInTheDocument();
    expect(screen.getByText('中性偏谨慎')).toBeInTheDocument();
    expect(screen.getByText('组合动作')).toBeInTheDocument();
    expect(screen.getByText('保持现金，不新增仓位')).toBeInTheDocument();
    expect(screen.getByText('时效')).toBeInTheDocument();
    expect(screen.getByText('截至下个交易日开盘前')).toBeInTheDocument();
    expect(screen.getByText('覆盖')).toBeInTheDocument();
    expect(screen.getByText('A股主要指数完整；美股为观察样本')).toBeInTheDocument();
    expect(screen.getByText('可信度')).toBeInTheDocument();
    expect(screen.getAllByText('中等可信').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('多市场观察简报')).toBeInTheDocument();
    expect(screen.getByText(/综合数据截至 2026-06-19 16:30（北京时间） · 生成于 17:00/)).toBeInTheDocument();
    expect(screen.getAllByText('证据不足，暂不操作。').length).toBeGreaterThan(0);
    expect(screen.getByText('研究边界')).toBeInTheDocument();
    expect(screen.getByText('核心理由')).toBeInTheDocument();
    expect(screen.getByText('查看核心证据')).toBeInTheDocument();
    expect(screen.getByText('最大反证 / 风险')).toBeInTheDocument();
    expect(screen.getByText('基准情景与竞争情景')).toBeInTheDocument();
    expect(screen.getByText('基准情景')).toBeInTheDocument();
    expect(screen.getByText('最强竞争情景')).toBeInTheDocument();
    expect(screen.getByText('CIO 当前裁决')).toBeInTheDocument();
    expect(screen.queryByText('报告主线')).not.toBeInTheDocument();
    expect(screen.queryByText('分部门分析')).not.toBeInTheDocument();
    expect(screen.queryByText('部门卷宗')).not.toBeInTheDocument();
    expect(screen.getByText('市场范围与样本表现')).toBeInTheDocument();
    expect(screen.getByText('重点标的跟踪')).toBeInTheDocument();
    expect(screen.getAllByText('美股观察样本').length).toBeGreaterThan(0);
    expect(screen.getAllByText('贵州茅台').length).toBeGreaterThan(0);
    expect(screen.getAllByText('PE(TTM) 21.20；历史分位样本不足').length).toBeGreaterThan(0);
    expect(screen.getByText('部门研究摘要')).toBeInTheDocument();
    expect(screen.getByText('数据与方法说明')).toBeInTheDocument();
    expect(screen.getByText('CIO 报告')).toBeInTheDocument();
    expect(screen.getByText('基本面部门')).toBeInTheDocument();
    expect(screen.getByText('已识别的争议结论')).toBeInTheDocument();
    expect(screen.getByText('存在有效反证，未作为确定依据')).toBeInTheDocument();

    const cioDetails = screen.getByText('CIO 报告').closest('details');
    expect(cioDetails).not.toHaveAttribute('open');
    expect(cioDetails?.querySelector('.report-department-summary')).toBeInTheDocument();

    const body = document.body.textContent || '';
    expect(body).not.toContain('ReportArtifact');
    expect(body).not.toContain('sourceHealthV2');
    expect(body).not.toContain('providerMatrix');
    expect(body).not.toContain('RAW_AGENT');
    expect(body).not.toContain('DERIVED_FROM_ARTIFACT');
    expect(body).not.toContain('BLOCKED_BY_FATAL');
    expect(body).not.toContain('claimPolicy');
    expect(body).not.toContain('artifactId');
    expect(body).not.toContain('rate_limited');
    expect(body).not.toContain('关键数据缺失');
    expect(body).not.toContain('数据修复');
    expect(body).not.toContain('数据说明');
    expect(body).not.toContain('宏观状态 PARTIAL');
    expect(body).not.toContain('governed');
    expect(body).not.toContain('fundamental_context');
    expect(body).not.toContain('not_supported');
    expect(body).not.toContain('claim：');
    expect(body).not.toContain('basis：');
    expect(body).not.toContain('point：');
    expect(body).not.toContain('evidence_ids');
    expect(body).not.toContain('memo:');
    expect(body).not.toContain('subject:');
    expect(body).not.toContain('tavily:');
    expect(body).not.toContain('providerSummary');
    expect(body).not.toContain('sector_rankings');
    expect(body).not.toContain('hot_stocks');
    expect(body).not.toContain('originalAnalysisRefs');
    expect(body).not.toContain('portfolio_snapshot');
    expect(body).not.toContain('FundamentalAgent');
    expect(body).not.toContain('quantity');
    expect(body).not.toContain('market_value');
    expect(body).not.toContain('cost_basis');
    expect(body).not.toContain('旧动作（不应显示）');
    expect(body).not.toContain('旧覆盖（不应显示）');
    expect(body).not.toContain('CninfoFetcher');
    expect(body).not.toContain('YfinanceFetcher');
    expect(body).not.toContain('raw rows');
    expect(body).not.toContain('EVIDENCE');
    expect(body).not.toContain('CHALLENGE');
    expect(body).not.toContain('WATCH');
    expect(body).not.toContain('MARKET SCOPE');
    expect(body).not.toContain('SECURITY MONITOR');
    expect(body).not.toContain('SCENARIO ADJUDICATION');
    expect(body).not.toContain('MACRO & GEOPOLITICS');
    expect(body).not.toContain('DEPARTMENT NOTES');
  });

  it('keeps desktop tables and provides complete mobile cards below md', () => {
    render(<ReportArtifactView artifact={artifact} />);

    expect(screen.getByTestId('market-desktop-table')).toHaveClass('hidden', 'md:block');
    expect(screen.getByTestId('stock-desktop-table')).toHaveClass('hidden', 'md:block');

    const marketCards = screen.getByTestId('market-mobile-cards');
    expect(marketCards).toHaveClass('md:hidden');
    expect(within(marketCards).getByText('A股市场')).toBeInTheDocument();
    expect(within(marketCards).getByText('美股观察样本')).toBeInTheDocument();
    expect(within(marketCards).getByText('不代表美股整体。')).toBeInTheDocument();

    const stockCards = screen.getByTestId('stock-mobile-cards');
    expect(stockCards).toHaveClass('md:hidden');
    const stockCard = screen.getByTestId('stock-mobile-card-600519');
    expect(within(stockCard).getByText('标的')).toBeInTheDocument();
    expect(within(stockCard).getByText('贵州茅台')).toBeInTheDocument();
    expect(within(stockCard).getByText('价格')).toBeInTheDocument();
    expect(within(stockCard).getByText('1258.99 CNY')).toBeInTheDocument();
    expect(within(stockCard).getByText('1 / 20 日表现')).toBeInTheDocument();
    expect(within(stockCard).getByText('1日 +0.63% · 20日 +3.88%')).toBeInTheDocument();
    expect(within(stockCard).getByText('趋势 / 观察位')).toBeInTheDocument();
    expect(within(stockCard).getByText(/短中期趋势向上 · 5日线 1228.18/)).toBeInTheDocument();
    expect(within(stockCard).getByText('基本面')).toBeInTheDocument();
    expect(within(stockCard).getByText('营收同比 +6.34%')).toBeInTheDocument();
    expect(within(stockCard).getByText('官方事件')).toBeInTheDocument();
    expect(within(stockCard).getByRole('link', { name: '年度权益分派公告' })).toHaveAttribute('href', 'https://example.test/cninfo.pdf');
    expect(within(stockCard).getByText('定位')).toBeInTheDocument();
    expect(within(stockCard).getAllByText('观察').length).toBeGreaterThan(0);
  });

  it('shows only reader-safe evidence metadata and links valid source URLs', () => {
    render(<ReportArtifactView artifact={artifact} />);

    const cioDetails = screen.getByText('CIO 报告').closest('details');
    expect(cioDetails).not.toBeNull();
    const evidence = within(cioDetails as HTMLElement);
    expect(evidence.getByText('巨潮资讯')).toBeInTheDocument();
    expect(evidence.getByText('Yahoo Finance')).toBeInTheDocument();
    expect(evidence.getByText(/已验证事实 · 2026-06-19/)).toBeInTheDocument();
    expect(evidence.getByText(/行情事实 · 2026-06-19/)).toBeInTheDocument();
    expect((cioDetails as HTMLElement).querySelector('a[href="https://example.test/cninfo.pdf"]')).toHaveTextContent('巨潮资讯');
    expect((cioDetails as HTMLElement).querySelector('a[href^="javascript:"]')).toBeNull();
    expect(cioDetails).not.toHaveTextContent('CninfoFetcher');
    expect(cioDetails).not.toHaveTextContent('YfinanceFetcher');
    expect(cioDetails).not.toHaveTextContent('raw rows');
    expect(cioDetails).not.toHaveTextContent('annual_report_payload');
    expect(cioDetails).not.toHaveTextContent('price_payload');
  });

  it('removes credentials from legacy evidence and event URLs before rendering', () => {
    const unsafe = structuredClone(artifact);
    const canary = 'CANARY_READER_URL_SECRET_123456';
    const unsafeUrl = `https://user:${canary}@example.test/report?page=2&api_key=${canary}#token=${canary}`;
    const card = unsafe.readerV3?.departmentCards?.[0];
    const stock = unsafe.readerV3?.stockMatrix?.[0];
    if (card?.evidenceSamples?.[0]) {
      card.evidenceSamples[0].sourceName = '';
      card.evidenceSamples[0].provider = '';
      card.evidenceSamples[0].sourceUrl = unsafeUrl;
    }
    if (stock) {
      stock.latestEvent = '敏感事件';
      stock.eventUrl = unsafeUrl;
    }

    render(<ReportArtifactView artifact={unsafe} />);

    screen.getAllByRole('link', { name: '来源' }).forEach((link) => {
      expect(link).toHaveAttribute('href', 'https://example.test/report?page=2');
    });
    screen.getAllByRole('link', { name: '敏感事件' }).forEach((link) => {
      expect(link).toHaveAttribute('href', 'https://example.test/report?page=2');
    });
    expect(document.body.innerHTML).not.toContain(canary);
  });

  it('does not label lookalike evidence hosts as official domains', () => {
    const lookalike = structuredClone(artifact);
    const sample = lookalike.readerV3?.departmentCards?.[0]?.evidenceSamples?.[0];
    if (sample) {
      sample.sourceName = '';
      sample.provider = '';
      sample.sourceUrl = 'https://cninfo.evil.example/report';
    }

    render(<ReportArtifactView artifact={lookalike} />);

    expect(screen.getAllByRole('link', { name: '来源' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: '巨潮资讯官方公告' })).not.toBeInTheDocument();
  });

  it('keeps diagnostics out of the default reader', () => {
    render(<ReportArtifactView artifact={artifact} />);

    expect(screen.queryByText('高级诊断')).not.toBeInTheDocument();
    expect(screen.queryByText('数据源矩阵')).not.toBeInTheDocument();
    expect(screen.queryByText('YfinanceFetcher')).not.toBeInTheDocument();
    expect(screen.queryByText('rate_limited')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看高级诊断' })).not.toBeInTheDocument();
  });

  it('renders diagnostics in the dedicated diagnostics view', () => {
    render(<ReportArtifactDiagnosticsView artifact={artifact} />);

    expect(screen.getByText('修复队列')).toBeInTheDocument();
    expect(screen.getByText('等待 Tavily 配额恢复或切 fallback')).toBeInTheDocument();
    expect(screen.getByText('数据源矩阵')).toBeInTheDocument();
    expect(screen.getByText('YfinanceFetcher')).toBeInTheDocument();
    expect(screen.getByText('Tavily')).toBeInTheDocument();
    expect(screen.getAllByText('rate_limited').length).toBeGreaterThan(0);
    expect(screen.getByText('SearXNG')).toBeInTheDocument();
    expect(screen.getByText('分域健康')).toBeInTheDocument();
    expect(screen.getByText('补 SEC/公告/财务事实')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看机器 JSON' }));
    expect(screen.getByText(/schemaVersion/)).toBeInTheDocument();
  });
});
