import type React from 'react';
import { useMemo, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import type {
  ReportArtifactDecision,
  ReportArtifactProviderMatrixRow,
  ReportArtifactSourceHealthDomain,
  ReportArtifactV1,
} from '../../types/analysis';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { JsonViewer } from '../common/JsonViewer';

interface ReportArtifactViewProps {
  artifact: ReportArtifactV1;
  defaultDiagnosticsOpen?: boolean;
}

const modeLabel: Record<string, string> = {
  FULL_REVIEW: '完整复盘',
  LIMITED_REVIEW: '有限复盘',
  SCREEN_ONLY: '仅筛选观察',
  OBSERVE_ONLY: '仅市场观察',
  BLOCKED: '数据不足，暂停结论',
};

const decisionActionLabel: Record<ReportArtifactDecision['action'], string> = {
  buy: '买入候选',
  sell: '卖出候选',
  hold: '持有/复核',
  watch: '观察',
  no_action: '不操作',
};

function readerDateTime(value?: string | null, timeOnly = false): string {
  if (!value) return '未标';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const options: Intl.DateTimeFormatOptions = timeOnly
    ? { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Shanghai' }
    : {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'Asia/Shanghai',
      };
  return new Intl.DateTimeFormat('zh-CN', options).format(parsed).replaceAll('/', '-');
}

function diagnosticsText(value?: string | null): string {
  if (!value) return '';
  const replacements: Array<[RegExp, string]> = [
    [
      /数据健康\s*中\s*(?:portfolio|持仓\/组合)\s*域的覆盖率(?:（覆盖率）)?\s*为\s*[0-9.]+，状态为\s*(?:partial|部分可用).*?(?:未能成功加载或关联。|$)/gi,
      '本次运行没有拿到可用于组合暴露分析的结构化持仓；如果系统里已有持仓，也没有被本次日报正确关联。',
    ],
    [/FULL_REVIEW/g, '完整复盘'],
    [/LIMITED_REVIEW/g, '有限复盘'],
    [/SCREEN_ONLY/g, '仅筛选观察'],
    [/OBSERVE_ONLY/g, '仅市场观察'],
    [/BLOCKED_BY_FATAL/g, '暂不行动'],
    [/\bBLOCKED\b/g, '暂不行动'],
    [/ReportArtifact/g, '报告数据包'],
    [/SourceHealth/g, '数据健康'],
    [/sourceHealthV2/g, '数据健康快照'],
    [/providerMatrix/g, '数据源矩阵'],
    [/claimPolicy/g, '结论门禁'],
    [/artifactId/g, '报告编号'],
    [/\bcoverage\b/gi, '覆盖率'],
    [/\bpartial\b/gi, '部分可用'],
    [/\bprovider\b/gi, '数据源'],
    [/\berrorType\b/g, '错误类型'],
    [/no_action/g, '不操作'],
    [/target_pct/g, '目标仓位'],
    [/DERIVED_FROM_ARTIFACT/g, '历史材料整理'],
    [/回填审计：/g, ''],
    [/有限信息结论：/g, ''],
    [/source health/gi, '数据健康'],
    [/source_health/g, '数据健康'],
    [/sourceHealth/g, '数据健康'],
    [/agent_reported_data_gap/g, '部门指出待确认项'],
    [/dailyUniverse/g, '日报标的池'],
    [/market_stats/g, '市场统计'],
    [/\bportfolio\b/gi, '持仓/组合'],
    [/price \/ fundamentals \/ filings \/ macro/g, '行情、基本面、公告、宏观'],
    [/DEEP_REVIEW_WAIT_ENTRY/g, '等待深评入场条件'],
    [/OVERHEATED_WAIT_ENTRY/g, '短线过热，等待承接'],
    [/ScoringAgent/g, '评分复核'],
    [/TradeDecisionGate/g, '交易前复核'],
    [/EvidenceGate/g, '证据复核'],
    [/评分复核未通过（总分4\.0\/10）/g, '综合判断偏弱，暂不支持行动'],
    [/评分门控未通过（总分4\.0\/10）/g, '综合判断偏弱，暂不支持行动'],
    [/financial_statement_refs/g, '财报原文引用不足'],
    [/valuation_peer_refs/g, '同业估值引用不足'],
    [/\bscore\s*=\s*/gi, '综合评分 '],
    [/signal=/g, '信号：'],
    [/confidence=/g, '置信度：'],
    [/decision_type=/g, '决策类型：'],
    [/sentiment_score=/g, '综合评分：'],
    [/analysis_summary=/g, '分析摘要：'],
    [/operation_advice=/g, '操作建议：'],
    [/governed/gi, '深评'],
    [/\bhigh\b/g, '高'],
    [/\bmedium\b/g, '中'],
    [/\blow\b/g, '低'],
  ];
  return replacements.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value);
}

function modeText(artifact: ReportArtifactV1): string {
  const mode = artifact.analysisMode || artifact.sourceHealthV2?.overallMode || 'OBSERVE_ONLY';
  return modeLabel[mode] || '仅市场观察';
}

function confidenceText(score?: number): string {
  if (typeof score !== 'number') return '可信度未标';
  if (score >= 0.85) return '高可信';
  if (score >= 0.6) return '中等可信';
  return '低可信';
}

function actionText(decision?: ReportArtifactDecision): string {
  if (!decision) return '等待报告生成';
  return decisionActionLabel[decision.action] || '观察';
}

function caveatText(artifact: ReportArtifactV1): string | null {
  const policy = artifact.claimPolicy || artifact.sourceHealthV2?.claimPolicy;
  if (artifact.analysisMode === 'BLOCKED' || artifact.sourceHealthV2?.overallMode === 'BLOCKED') return '数据不足，本报告只保留诊断摘要。';
  if (policy?.mustShowCaveat) return '数据仍有缺口，本报告需带限制条件阅读。';
  if (artifact.sourceHealth?.decisionImpact && artifact.sourceHealth.decisionImpact !== '数据源可用于常规审查') return artifact.sourceHealth.decisionImpact;
  return null;
}

const DomainRow: React.FC<{ name: string; domain: ReportArtifactSourceHealthDomain }> = ({ name, domain }) => (
  <div className="rounded-xl border border-border/60 bg-background/40 p-3 text-sm text-secondary-text">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="font-medium text-foreground">{domain.label || name}</span>
      <Badge variant={domain.status === 'available' ? 'success' : domain.status === 'blocked' ? 'danger' : 'warning'}>{domain.status}</Badge>
    </div>
    <div className="mt-2">覆盖：{Math.round((domain.coverage || 0) * 100)}%</div>
    {domain.blockers?.length ? <div className="mt-1 text-xs text-warning">{domain.blockers.join('、')}</div> : null}
    {domain.repairHints?.length ? <div className="mt-1 text-xs text-muted-text">{domain.repairHints.join('、')}</div> : null}
  </div>
);

function providerRepairQueue(rows?: ReportArtifactProviderMatrixRow[]) {
  const priority: Record<string, number> = { auth_missing: 1, failed: 2, empty: 3, not_supported: 4, rate_limited: 5, partial: 6 };
  return [...(rows || [])]
    .filter((row) => row.status !== 'success')
    .map((row, index) => ({
      key: `${row.provider}-${row.operation || row.domain}-${row.status}-${index}`,
      priority: priority[row.status] ?? 9,
      label: row.status === 'auth_missing'
        ? `配置 ${row.provider} key`
        : row.status === 'rate_limited'
          ? `等待 ${row.provider} 配额恢复或切 fallback`
          : row.status === 'not_supported'
            ? `${row.provider} 当前样例无适配标的`
            : row.status === 'empty'
              ? `检查 ${row.provider} 是否无结果`
              : `修复 ${row.provider} 返回`,
      detail: `${row.status} · ${row.operation || row.domain || 'source'} · ${row.errorType || 'no_error_type'}`,
    }))
    .sort((a, b) => a.priority - b.priority || a.label.localeCompare(b.label));
}

const ProviderRow: React.FC<{ row: ReportArtifactProviderMatrixRow }> = ({ row }) => (
  <tr className="border-t border-border/40">
    <td className="px-3 py-2 font-medium text-foreground">{row.provider}</td>
    <td className="px-3 py-2">{row.market || '未标'}</td>
    <td className="px-3 py-2">{row.domain || '未标'}</td>
    <td className="px-3 py-2">{row.operation || '未标'}</td>
    <td className="px-3 py-2">{row.status}</td>
    <td className="px-3 py-2">{row.authState || '未标'}</td>
    <td className="px-3 py-2">{row.recordCount ?? '未标'}</td>
    <td className="px-3 py-2">{row.errorType || '无'}</td>
    <td className="px-3 py-2">{row.fallbackTo || '无'}</td>
    <td className="px-3 py-2">{row.sourceTier || '未标'}</td>
  </tr>
);

function displayText(value?: string | null): string {
  if (!value) return '';
  return value
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*\*/g, '')
    .replace(/^\s*[-•]\s*/, '')
    .replace(/`/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function shortList(items?: string[], limit = 3): string[] {
  return [...new Set((items || []).map(displayText).filter(Boolean))].slice(0, limit);
}

const EvidenceSampleList: React.FC<{ items?: Array<{ id?: string; label?: string; provider?: string; factType?: string; sourceUrl?: string }> }> = ({ items }) => {
  const rows = (items || []).slice(0, 4);
  if (!rows.length) return <div className="text-xs text-muted-text">未提供证据样例。</div>;
  return (
    <ul className="list-disc space-y-1 pl-5 text-xs text-secondary-text">
      {rows.map((item) => (
        <li key={item.id || item.label}>
          <span className="font-medium text-foreground">{displayText(item.provider || '证据')}</span>
          {item.factType ? <span className="text-muted-text"> · {displayText(item.factType)}</span> : null}
          <span>：{displayText(item.label || item.id || '')}</span>
          {item.sourceUrl ? <a className="ml-1 text-info hover:underline" href={item.sourceUrl} target="_blank" rel="noreferrer">来源</a> : null}
        </li>
      ))}
    </ul>
  );
};

export const ReportArtifactView: React.FC<ReportArtifactViewProps> = ({ artifact }) => {
  const reader = artifact.readerV3;
  const stats = reader?.evidenceSummary || artifact.evidenceStats || artifact.sourceHealthV2?.evidenceStats;
  const departmentGapItems = reader?.evidenceSummary?.departmentGapItems ?? 0;
  const hero = reader?.hero;
  const fallbackAction = actionText(artifact.decision);
  const fallbackConfidence = confidenceText(artifact.sourceHealthV2?.overallScore);
  const title = `${reader?.runDate || artifact.runDate} 投研日报`;
  const timing = reader?.timing;
  const action = displayText(hero?.action || fallbackAction);
  const confidence = displayText(hero?.confidence || fallbackConfidence);
  const status = displayText(hero?.status || modeText(artifact));
  const oneLine = displayText(hero?.oneLine || artifact.summary.finalConclusion || artifact.summary.oneLine);
  const maxLimitation = displayText(hero?.maxLimitation || caveatText(artifact) || '仍需人工复核，不自动执行交易。');
  const coverage = displayText(hero?.coverage);
  const keyReasons = shortList(reader?.keyReasons || artifact.readerBrief?.why, 3);
  const counterpoints = shortList(reader?.counterpoints || artifact.readerBrief?.risks, 3);
  const nextSteps = shortList(reader?.nextSteps || artifact.readerBrief?.nextSteps || artifact.summary.nextSteps, 3);
  const marketGeo = shortList(reader?.marketGeo, 3);
  const adjudication = reader?.adjudication;
  const sharedFacts = shortList(adjudication?.sharedFacts, 3);
  const invalidationTriggers = shortList(adjudication?.invalidationTriggers, 3);
  const reliabilityWarnings = shortList(reader?.reliability?.warnings, 3);
  const departments = reader?.departmentCards || [];

  return (
    <article className="report-reader min-w-0 max-w-full space-y-5" data-testid="report-artifact-view">
      <Card variant="gradient" padding="lg">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={action === '不操作' ? 'warning' : 'info'}>{action}</Badge>
              <Badge variant="info">数据覆盖：{status}</Badge>
              <Badge variant={confidence.includes('高') ? 'success' : confidence.includes('低') ? 'warning' : 'info'}>结论可信度：{confidence}</Badge>
            </div>
            <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
            <p className="text-xs text-muted-text">
              报告日期 {timing?.reportDate || artifact.runDate}
              {' · '}综合数据截至 {readerDateTime(timing?.dataAsOf)}（北京时间）
              {' · '}生成于 {readerDateTime(timing?.generatedAt || artifact.generatedAt, true)}
            </p>
            {coverage ? <p className="text-xs text-muted-text">{coverage}</p> : null}
            <p className="text-base leading-7 text-secondary-text">{oneLine}</p>
          </div>
          <div className="rounded-2xl border border-border/60 bg-background/45 px-4 py-3 text-sm text-secondary-text">
            <div className="font-medium text-foreground">最大限制</div>
            <div className="mt-1 max-w-xs leading-6">{maxLimitation}</div>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="核心理由" className="border border-border/60 bg-card/72">
          {keyReasons.length ? (
            <ul className="list-disc space-y-2 pl-5 text-sm text-secondary-text">{keyReasons.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : <div className="text-sm text-muted-text">未提供核心理由。</div>}
        </Card>
        <Card title="最大反证 / 风险" className="border border-border/60 bg-card/72">
          {counterpoints.length ? (
            <ul className="list-disc space-y-2 pl-5 text-sm text-secondary-text">{counterpoints.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : <div className="text-sm text-muted-text">未提供反证。</div>}
        </Card>
        <Card title="下一步" className="border border-border/60 bg-card/72">
          {nextSteps.length ? (
            <ul className="list-disc space-y-2 pl-5 text-sm text-secondary-text">{nextSteps.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : <div className="text-sm text-muted-text">等待下一次刷新。</div>}
        </Card>
      </div>

      {adjudication ? (
        <Card title="基准情景、竞争情景与 CIO 裁决" className="border border-border/60 bg-card/72">
          {sharedFacts.length ? (
            <div className="mb-4">
              <div className="text-sm font-medium text-foreground">双方共同事实</div>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-secondary-text">
                {sharedFacts.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl bg-background/35 p-4">
              <div className="text-sm font-medium text-foreground">基准情景</div>
              <p className="mt-2 text-sm leading-6 text-secondary-text">{displayText(adjudication.baseCase || '尚未形成。')}</p>
            </div>
            <div className="rounded-xl bg-background/35 p-4">
              <div className="text-sm font-medium text-foreground">最强竞争情景</div>
              <p className="mt-2 text-sm leading-6 text-secondary-text">{displayText(adjudication.strongestAlternative || '暂无形成证据链的竞争情景。')}</p>
            </div>
          </div>
          <div className="mt-4 border-l-2 border-info pl-4">
            <div className="text-sm font-medium text-foreground">CIO 当前裁决</div>
            <p className="mt-1 text-sm leading-6 text-secondary-text">{displayText(adjudication.judgment || oneLine)}</p>
            {adjudication.why ? <p className="mt-2 text-xs leading-5 text-muted-text">为什么：{displayText(adjudication.why)}</p> : null}
          </div>
          {invalidationTriggers.length ? (
            <div className="mt-4">
              <div className="text-sm font-medium text-foreground">推翻当前裁决的信号</div>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-secondary-text">
                {invalidationTriggers.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}
        </Card>
      ) : null}

      {marketGeo.length ? (
        <Card title="市场与地缘" className="border border-border/60 bg-card/72">
          <ul className="list-disc space-y-2 pl-5 text-sm text-secondary-text">{marketGeo.map((item) => <li key={item}>{item}</li>)}</ul>
        </Card>
      ) : null}

      <Card title="部门摘要" className="min-w-0 border border-border/60 bg-card/72">
        <p className="mb-4 text-sm text-muted-text">摘要直接可见；依据、反证、待确认项和证据默认折叠。</p>
        {departments.length ? (
          <div className="grid min-w-0 gap-2">
            {departments.slice(0, 12).map((report) => (
              <details key={`${report.agent || report.label}`} className="report-department min-w-0 rounded-xl border border-border/60 bg-background/40 text-sm">
                <summary className="cursor-pointer list-none px-3 py-3 [&::-webkit-details-marker]:hidden">
                  <span className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-foreground">{displayText(report.label || report.agent || '分析部门')}</span>
                    {report.confidence ? <Badge variant={report.confidence === 'high' ? 'success' : report.confidence === 'low' ? 'warning' : 'info'}>{displayText(report.confidence)}</Badge> : null}
                  </span>
                  <span className="report-department-summary mt-1 block min-w-0 leading-6 text-secondary-text">{displayText(report.conclusion || '本部门未给出可读结论。')}</span>
                </summary>
                <div className="space-y-3 border-t border-border/50 px-3 py-3 text-xs text-secondary-text">
                    {shortList(report.nextActions || (report.nextAction ? [report.nextAction] : []), 3).length ? (
                      <div>
                        <div className="font-medium text-foreground">下一步</div>
                        <ul className="list-disc pl-5">
                          {shortList(report.nextActions || (report.nextAction ? [report.nextAction] : []), 3).map((item) => <li key={item}>{item}</li>)}
                        </ul>
                      </div>
                    ) : null}
                    {shortList(report.keyClaims, 4).length ? <div><div className="font-medium text-foreground">依据</div><ul className="list-disc pl-5">{shortList(report.keyClaims, 4).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
                    {report.challengedClaims?.length ? (
                      <div>
                        <div className="font-medium text-warning">已识别的争议结论</div>
                        <div className="mt-1 space-y-2">
                          {report.challengedClaims.slice(0, 3).map((item, index) => (
                            <div key={`${item.claim || 'challenge'}-${index}`} className="rounded-lg border border-warning/30 bg-warning/5 p-2">
                              <div>{displayText(item.claim || '')}</div>
                              <div className="mt-1 text-warning">{displayText(item.status || '存在有效反证')}</div>
                              {item.opposingScenario ? <div className="mt-1">反方情景：{displayText(item.opposingScenario)}</div> : null}
                              {item.falsifier ? <div className="mt-1 text-muted-text">如何验证：{displayText(item.falsifier)}</div> : null}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {shortList(report.counterpoints, 3).length ? <div><div className="font-medium text-foreground">反证</div><ul className="list-disc pl-5">{shortList(report.counterpoints, 3).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
                    {shortList(report.dataGaps, 2).length ? <div><div className="font-medium text-foreground">还需要确认</div><ul className="list-disc pl-5">{shortList(report.dataGaps, 2).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
                    {shortList(report.supportSignals, 3).length ? <div><div className="font-medium text-foreground">支撑信号</div><ul className="list-disc pl-5">{shortList(report.supportSignals, 3).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
                    <div><div className="font-medium text-foreground">证据样例</div><EvidenceSampleList items={report.evidenceSamples} /></div>
                </div>
              </details>
            ))}
          </div>
        ) : <div className="text-sm text-muted-text">本轮未记录到分部门结论。</div>}
      </Card>

      <Card title="证据摘要" className="border border-border/60 bg-card/72">
        <p className="mb-3 text-sm leading-7 text-secondary-text">{displayText(reader?.dataConfidence || '本轮数据可用于投研复核，仍需人工判断。')}</p>
        <div className="grid gap-3 text-sm text-secondary-text sm:grid-cols-2 lg:grid-cols-4">
          <div>已验证：<span className="text-foreground">{stats?.verifiedFacts ?? 0}</span></div>
          <div>推导：<span className="text-foreground">{stats?.derivedFacts ?? 0}</span></div>
          <div>发现线索：<span className="text-foreground">{stats?.discoveryItems ?? 0}</span></div>
          <div>关键证据缺口：<span className="text-foreground">{stats?.missingCriticalFacts ?? 0}</span></div>
          <div>部门待确认：<span className="text-foreground">{departmentGapItems}</span></div>
        </div>
        {reliabilityWarnings.length ? (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-warning">
            {reliabilityWarnings.map((item) => <li key={item}>{item}</li>)}
          </ul>
        ) : null}
      </Card>
    </article>
  );
};

export const ReportArtifactDiagnosticsView: React.FC<{ artifact: ReportArtifactV1 }> = ({ artifact }) => {
  const [showRaw, setShowRaw] = useState(false);
  const repairQueue = useMemo(() => providerRepairQueue(artifact.sourceHealthV2?.providerMatrix), [artifact.sourceHealthV2?.providerMatrix]);

  return (
    <article className="space-y-5" data-testid="report-diagnostics-view">
      <Card variant="gradient" padding="lg">
        <div className="space-y-2">
          <Badge variant="warning">高级诊断</Badge>
          <h1 className="text-2xl font-semibold text-foreground">{diagnosticsText(artifact.title)} · 诊断</h1>
          <p className="text-sm leading-6 text-secondary-text">只给维护者排障：数据源、证据、模型、运行快照。默认报告页不展示这些字段。</p>
        </div>
      </Card>

      <Card title="修复队列" className="border border-border/60 bg-card/72">
        {repairQueue.length ? (
          <ol className="list-decimal space-y-2 pl-5 text-sm text-secondary-text">
            {repairQueue.slice(0, 12).map((item) => <li key={item.key}><span className="font-medium text-foreground">{item.label}</span><span className="text-muted-text"> — {item.detail}</span></li>)}
          </ol>
        ) : <div className="text-sm text-muted-text">暂无需修复的数据源。</div>}
      </Card>

      <Card title="数据源矩阵" className="border border-border/60 bg-card/72">
        {artifact.sourceHealthV2?.providerMatrix?.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs text-secondary-text">
              <thead>
                <tr>
                  <th className="px-3 py-2">Provider</th><th className="px-3 py-2">Market</th><th className="px-3 py-2">Domain</th><th className="px-3 py-2">Operation</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Auth</th><th className="px-3 py-2">Records</th><th className="px-3 py-2">Error</th><th className="px-3 py-2">Fallback</th><th className="px-3 py-2">Tier</th>
                </tr>
              </thead>
              <tbody>{artifact.sourceHealthV2.providerMatrix.map((row, index) => <ProviderRow key={`${row.provider}-${row.domain}-${row.operation || 'op'}-${row.status}-${index}`} row={row} />)}</tbody>
            </table>
          </div>
        ) : <div className="text-sm text-muted-text">未提供数据源矩阵。</div>}
      </Card>

      <Card title="分域健康" className="border border-border/60 bg-card/72">
        <div className="grid gap-3">
          {Object.entries(artifact.sourceHealthV2?.domains || {}).map(([name, domain]) => <DomainRow key={name} name={name} domain={domain} />)}
        </div>
      </Card>

      <Card title="运行快照" className="border border-border/60 bg-card/72">
        <div className="grid gap-3 text-sm text-secondary-text sm:grid-cols-2 lg:grid-cols-4">
          <div>模式：<span className="text-foreground">{artifact.analysisMode || artifact.sourceHealthV2?.overallMode || 'unknown'}</span></div>
          <div>可信度：<span className="text-foreground">{artifact.sourceHealthV2?.overallScore ?? 'unknown'}</span></div>
          <div>证据：<span className="text-foreground">{artifact.evidenceItems?.length ?? 0}</span></div>
          <div>日期：<span className="text-foreground">{artifact.runDate}</span></div>
        </div>
      </Card>

      <div className="flex items-center gap-2 text-sm text-warning"><AlertTriangle className="h-4 w-4" />机器数据仅用于排障，不作为默认阅读入口。</div>
      <button type="button" className="btn-secondary" onClick={() => setShowRaw((value) => !value)}>
        {showRaw ? '隐藏机器 JSON' : '查看机器 JSON'}
      </button>
      {showRaw ? <JsonViewer data={artifact as unknown as Record<string, unknown>} className="mt-4" /> : null}
    </article>
  );
};
