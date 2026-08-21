import type React from 'react';
import { useMemo, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import type {
  ReportArtifactDecision,
  ReportArtifactProviderMatrixRow,
  ReportArtifactReaderV3,
  ReportArtifactReaderV3DepartmentCard,
  ReportArtifactReaderV2EvidenceSample,
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
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
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

function readerDataAsOf(value?: string | null): string {
  if (!value) return '未标';
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? value
    : `${readerDateTime(value)}（北京时间）`;
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
    [/\bmedium\b/g, '中等'],
    [/\blow\b/g, '低'],
  ];
  return replacements.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value);
}

function modeText(artifact: ReportArtifactV1): string {
  const mode = artifact.analysisMode || artifact.sourceHealthV2?.overallMode || 'OBSERVE_ONLY';
  return modeLabel[mode] || '仅市场观察';
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

function signedPct(value?: number): string {
  return typeof value === 'number' ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}%` : '待更新';
}

function readerPrice(value?: number, currency?: string): string {
  return typeof value === 'number' ? `${value.toFixed(2)} ${currency || ''}`.trim() : '待更新';
}

function evidenceSourceName(item: ReportArtifactReaderV2EvidenceSample): string {
  const sourceName = displayText(item.sourceName);
  if (sourceName) return sourceName;

  const provider = displayText(item.provider);
  const sourceUrl = validSourceUrl(item.sourceUrl);
  if (sourceUrl) {
    const host = new URL(sourceUrl).hostname.toLowerCase();
    if (hostnameMatches(host, 'sec.gov')) return 'SEC 官方披露';
    if (hostnameMatches(host, 'cninfo.com.cn')) return '巨潮资讯官方公告';
    if (hostnameMatches(host, 'hkex.com.hk')) return '港交所官方披露';
  }
  const providerLabels: Record<string, string> = {
    akshare: 'AKShare',
    aksharefetcher: 'AKShare',
    cninfo: '巨潮资讯',
    cninfofetcher: '巨潮资讯',
    eastmoney: '东方财富',
    eastmoneyfetcher: '东方财富',
    sec: 'SEC EDGAR',
    secedgar: 'SEC EDGAR',
    yfinance: 'Yahoo Finance',
    yfinancefetcher: 'Yahoo Finance',
  };
  if (providerLabels[provider.toLowerCase()]) return providerLabels[provider.toLowerCase()];

  if (/(?:Data)?(?:Fetcher|Provider|Adapter|Client|Service)$/i.test(provider)) return '公开数据源';
  return provider || '来源';
}

const TOKEN_LIKE_URL_VALUE = /(?:sk-[a-z0-9_-]{16,}|xox[baprs]-[a-z0-9-]{16,}|gh[pousr]_[a-z0-9_]{20,})/i;
const SENSITIVE_URL_KEYS = new Set([
  'auth', 'authkey', 'code', 'credential', 'credentials', 'key', 'pass',
  'passwd', 'password', 'session', 'sessionid', 'sig', 'signature',
  'xamzcredential', 'xamzsecuritytoken', 'xamzsignature',
]);

function hostnameMatches(hostname: string, domain: string): boolean {
  const host = hostname.toLowerCase().replace(/\.$/, '');
  return host === domain || host.endsWith(`.${domain}`);
}

function isSensitiveUrlKey(key: string): boolean {
  const compact = key.toLowerCase().replace(/[^a-z0-9]/g, '');
  return SENSITIVE_URL_KEYS.has(compact)
    || /authorization|cookie|password|secret|sendkey|token(?!s)|webhook/.test(compact)
    || /(?:api|license|private)key/.test(compact);
}

function isWebhookUrl(url: URL): boolean {
  const host = url.hostname.toLowerCase();
  const path = url.pathname.toLowerCase();
  return (hostnameMatches(host, 'hooks.slack.com') && path.startsWith('/services/'))
    || ((hostnameMatches(host, 'discord.com') || hostnameMatches(host, 'discordapp.com')) && path.startsWith('/api/webhooks/'))
    || (hostnameMatches(host, 'open.feishu.cn') && path.includes('/open-apis/bot/') && path.includes('/hook/'))
    || (hostnameMatches(host, 'oapi.dingtalk.com') && path.startsWith('/robot/send'))
    || (hostnameMatches(host, 'qyapi.weixin.qq.com') && path.startsWith('/cgi-bin/webhook/send'));
}

function validSourceUrl(value?: string): string | null {
  const text = value?.trim();
  if (!text || Array.from(text).some((char) => /\s/.test(char) || char.charCodeAt(0) <= 31 || char.charCodeAt(0) === 127)) return null;
  try {
    const url = new URL(text);
    if ((url.protocol !== 'http:' && url.protocol !== 'https:') || !url.hostname) return null;
    let decodedPath = url.pathname;
    try { decodedPath = decodeURIComponent(url.pathname); } catch { /* retain encoded path */ }
    if (isWebhookUrl(url) || TOKEN_LIKE_URL_VALUE.test(decodedPath)) return null;

    url.username = '';
    url.password = '';
    url.hash = '';
    const keysToDelete: string[] = [];
    url.searchParams.forEach((itemValue, key) => {
      if (isSensitiveUrlKey(key) || TOKEN_LIKE_URL_VALUE.test(key) || TOKEN_LIKE_URL_VALUE.test(itemValue)) {
        keysToDelete.push(key);
      }
    });
    keysToDelete.forEach((key) => url.searchParams.delete(key));
    return url.toString();
  } catch {
    return null;
  }
}

function evidenceCopy(item: ReportArtifactReaderV2EvidenceSample): string {
  const label = displayText(item.label);
  if (
    !label
    || /(?:raw[_\s-]+(?:rows|payload)|\brows\s*[:=]|[_-]payload\b|\bpayload\s*[:=])/i.test(label)
    || /(?:^|\s)[a-z][a-z0-9_]{2,}\s*=/i.test(label)
  ) return '';
  return label;
}

const EvidenceSampleList: React.FC<{ items?: ReportArtifactReaderV2EvidenceSample[] }> = ({ items }) => {
  const rows = (items || []).slice(0, 4);
  if (!rows.length) return <div className="text-xs text-muted-text">未提供证据样例。</div>;
  return (
    <ul className="list-disc space-y-1 pl-5 text-xs text-secondary-text">
      {rows.map((item, index) => {
        const sourceName = evidenceSourceName(item);
        const sourceUrl = validSourceUrl(item.sourceUrl);
        const metadata = [displayText(item.factType), displayText(item.asOf)].filter(Boolean);
        const copy = evidenceCopy(item);
        return (
          <li key={item.id || `${sourceName}-${index}`}>
            {sourceUrl ? (
              <a className="font-medium text-info hover:underline" href={sourceUrl} target="_blank" rel="noreferrer">{sourceName}</a>
            ) : <span className="font-medium text-foreground">{sourceName}</span>}
            {metadata.length ? <span className="text-muted-text"> · {metadata.join(' · ')}</span> : null}
            {copy ? <span className="mt-0.5 block leading-5 text-secondary-text">{copy}</span> : null}
          </li>
        );
      })}
    </ul>
  );
};

const AdjudicationPanel: React.FC<{
  adjudication?: ReportArtifactReaderV3['adjudication'];
  fallback: string;
}> = ({ adjudication, fallback }) => {
  if (!adjudication) return null;
  const sharedFacts = shortList(adjudication.sharedFacts, 3);
  const invalidationTriggers = shortList(adjudication.invalidationTriggers, 3);
  return (
    <section className="border-b border-border/70 pb-9" data-testid="adjudication-panel">
      <div className="text-[11px] font-semibold tracking-[0.16em] text-info">情景裁决</div>
      <h2 className="mt-1 text-xl font-semibold text-foreground">基准情景与竞争情景</h2>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="border-l-2 border-info/60 bg-background/25 p-5">
          <div className="text-sm font-medium text-foreground">基准情景</div>
          <p className="mt-2 text-sm leading-6 text-secondary-text">{displayText(adjudication.baseCase || '尚未形成。')}</p>
        </div>
        <div className="border-l-2 border-warning/60 bg-background/25 p-5">
          <div className="text-sm font-medium text-foreground">最强竞争情景</div>
          <p className="mt-2 text-sm leading-6 text-secondary-text">{displayText(adjudication.strongestAlternative || '暂无形成证据链的竞争情景。')}</p>
        </div>
      </div>
      <div className="mt-5 border-l-4 border-info bg-info/5 px-5 py-4">
        <div className="text-sm font-medium text-foreground">CIO 当前裁决</div>
        <p className="mt-1 text-sm leading-6 text-secondary-text">{displayText(adjudication.judgment || fallback)}</p>
        {adjudication.why ? <p className="mt-2 text-xs leading-5 text-muted-text">为什么：{displayText(adjudication.why)}</p> : null}
      </div>
      <details className="mt-4 rounded-xl border border-border/60 px-4 py-1">
        <summary className="flex min-h-11 cursor-pointer items-center justify-between py-2 text-sm font-medium text-foreground">
          <span>共同事实与翻转信号</span><span className="text-xs text-info">展开</span>
        </summary>
        <div className="grid gap-5 border-t border-border/50 py-4 lg:grid-cols-2">
          <div><div className="text-sm font-medium text-foreground">双方共同事实</div><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-secondary-text">{sharedFacts.map((item) => <li key={item}>{item}</li>)}</ul></div>
          <div><div className="text-sm font-medium text-foreground">推翻当前裁决的信号</div><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-secondary-text">{invalidationTriggers.map((item) => <li key={item}>{item}</li>)}</ul></div>
        </div>
      </details>
    </section>
  );
};

const DepartmentDisclosure: React.FC<{ report: ReportArtifactReaderV3DepartmentCard }> = ({ report }) => (
  <details className="report-department min-w-0 rounded-xl border border-border/60 bg-background/40 text-sm">
    <summary className="min-h-11 cursor-pointer list-none px-3 py-3 [&::-webkit-details-marker]:hidden">
      <span className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <span className="font-medium text-foreground">{displayText(report.label || report.agent || '分析部门')}</span>
        <span className="flex items-center gap-2">
          {report.confidence ? <Badge variant={report.confidence === 'high' ? 'success' : report.confidence === 'low' ? 'warning' : 'info'}>{({ high: '高可信', medium: '中等可信', low: '低可信' } as Record<string, string>)[report.confidence] || displayText(report.confidence)}</Badge> : null}
          <span className="text-xs text-info">查看依据</span>
        </span>
      </span>
      <span className="report-department-summary mt-1 block min-w-0 leading-6 text-secondary-text">{displayText(report.conclusion || '本部门未给出可读结论。')}</span>
    </summary>
    <div className="space-y-3 border-t border-border/50 px-3 py-3 text-xs text-secondary-text">
      {shortList(report.nextActions || (report.nextAction ? [report.nextAction] : []), 3).length ? <div><div className="font-medium text-foreground">下一步</div><ul className="list-disc pl-5">{shortList(report.nextActions || (report.nextAction ? [report.nextAction] : []), 3).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {shortList(report.keyClaims, 4).length ? <div><div className="font-medium text-foreground">依据</div><ul className="list-disc pl-5">{shortList(report.keyClaims, 4).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {report.challengedClaims?.length ? <div><div className="font-medium text-warning">已识别的争议结论</div><div className="mt-1 space-y-2">{report.challengedClaims.slice(0, 3).map((item, index) => <div key={`${item.claim || 'challenge'}-${index}`} className="rounded-lg border border-warning/30 bg-warning/5 p-2"><div>{displayText(item.claim || '')}</div><div className="mt-1 text-warning">{displayText(item.status || '存在有效反证')}</div>{item.opposingScenario ? <div className="mt-1">反方情景：{displayText(item.opposingScenario)}</div> : null}{item.falsifier ? <div className="mt-1 text-muted-text">如何验证：{displayText(item.falsifier)}</div> : null}</div>)}</div></div> : null}
      {shortList(report.counterpoints, 3).length ? <div><div className="font-medium text-foreground">反证</div><ul className="list-disc pl-5">{shortList(report.counterpoints, 3).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {shortList(report.dataGaps, 2).length ? <div><div className="font-medium text-foreground">还需要确认</div><ul className="list-disc pl-5">{shortList(report.dataGaps, 2).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {shortList(report.supportSignals, 3).length ? <div><div className="font-medium text-foreground">支撑信号</div><ul className="list-disc pl-5">{shortList(report.supportSignals, 3).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      <div><div className="font-medium text-foreground">证据样例</div><EvidenceSampleList items={report.evidenceSamples} /></div>
    </div>
  </details>
);

export const ReportArtifactView: React.FC<ReportArtifactViewProps> = ({ artifact }) => {
  const reader = artifact.readerV3;
  const stats = reader?.evidenceSummary || artifact.evidenceStats || artifact.sourceHealthV2?.evidenceStats;
  const departmentGapItems = reader?.evidenceSummary?.departmentGapItems ?? 0;
  const hero = reader?.hero;
  const fallbackAction = actionText(artifact.decision);
  const title = `${reader?.runDate || artifact.runDate} 投研日报`;
  const timing = reader?.timing;
  const marketStance = displayText(hero?.marketStance || hero?.status || modeText(artifact));
  const portfolioAction = displayText(hero?.portfolioAction || hero?.action || fallbackAction);
  const validity = displayText(hero?.validity)
    || (timing?.dataAsOf ? `截至 ${readerDataAsOf(timing.dataAsOf)}` : '时效未标');
  const dataCoverage = displayText(hero?.dataCoverage || reader?.assessment?.dataCoverage || hero?.coverage || modeText(artifact));
  const confidence = displayText(hero?.confidence || reader?.reliability?.label || '可信度未标');
  const oneLine = displayText(hero?.oneLine || artifact.summary.finalConclusion || artifact.summary.oneLine);
  const maxLimitation = displayText(hero?.maxLimitation || caveatText(artifact) || '仍需人工复核，不自动执行交易。');
  const keyReasons = shortList(reader?.keyReasons || artifact.readerBrief?.why, 3);
  const counterpoints = shortList(reader?.counterpoints || artifact.readerBrief?.risks, 3);
  const nextSteps = shortList(reader?.nextSteps || artifact.readerBrief?.nextSteps || artifact.summary.nextSteps, 3);
  const marketGeo = shortList(reader?.marketGeo, 3);
  const adjudication = reader?.adjudication;
  const reliabilityWarnings = shortList(reader?.reliability?.warnings, 3);
  const departments = reader?.departmentCards || [];
  const featuredDepartmentNames = new Set(['CIO 报告', '风险部门', '市场部门', '持仓复核部门']);
  const featuredDepartments = departments.filter((report) => featuredDepartmentNames.has(report.label || report.agent || '')).slice(0, 4);
  const otherDepartments = departments.filter((report) => !featuredDepartments.includes(report));
  const marketMatrix = reader?.marketMatrix || [];
  const stockMatrix = reader?.stockMatrix || [];
  const coreEvidence = Array.from(
    new Map(
      departments
        .flatMap((report) => report.evidenceSamples || [])
        .map((item) => [item.id || `${item.sourceName || item.provider}-${item.asOf}-${item.label}`, item]),
    ).values(),
  ).slice(0, 6);

  return (
    <article className="report-reader mx-auto min-w-0 max-w-7xl space-y-10 pb-10" data-testid="report-artifact-view">
      <header className="border-b border-border/70 pb-8 pt-2">
        <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-text">
          <span>{displayText(hero?.status || '每日投研')}</span>
          <span>{timing?.reportDate || artifact.runDate}</span>
        </div>
        <h1 className="mt-6 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">{title}</h1>
        <p className="mt-5 max-w-5xl text-xl font-medium leading-9 text-foreground">{oneLine}</p>
        <dl className="mt-6 grid gap-5 border-y border-border/70 py-5 sm:grid-cols-2">
          {[
            ['研究立场', marketStance],
            ['组合动作', portfolioAction],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs font-medium text-muted-text">{label}</dt>
              <dd className="mt-1 text-base font-semibold leading-7 text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-text">
          <span><b className="font-medium text-foreground">可信度</b> {confidence}</span>
          <span><b className="font-medium text-foreground">时效</b> {validity}</span>
          <span><b className="font-medium text-foreground">覆盖</b> {dataCoverage}</span>
        </div>
        <p className="mt-3 text-xs leading-5 text-muted-text">
          综合数据截至 {readerDataAsOf(timing?.dataAsOf)}
          {' · '}生成于 {readerDateTime(timing?.generatedAt || artifact.generatedAt, true)}
        </p>
        <div className="mt-5 flex max-w-5xl gap-3 text-sm leading-6 text-secondary-text">
          <span className="shrink-0 font-medium text-foreground">研究边界</span>
          <span>{maxLimitation}</span>
        </div>
      </header>

      <section className="grid gap-8 border-b border-border/70 pb-9 lg:grid-cols-3">
        {[
          ['核心理由', '研究依据', keyReasons, '未提供核心理由。'],
          ['最大反证 / 风险', '反向验证', counterpoints, '未提供反证。'],
          ['下一步', '后续观察', nextSteps, '等待下一次刷新。'],
        ].map(([heading, eyebrow, items, empty]) => (
          <div key={heading as string} className="lg:border-l lg:border-border/70 lg:first:border-l-0 lg:first:pl-0 lg:pl-8">
            <div className="text-[11px] font-semibold tracking-[0.16em] text-info">{eyebrow as string}</div>
            <h2 className="mt-1 text-xl font-semibold text-foreground">{heading as string}</h2>
            {(items as string[]).length ? (
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-secondary-text">
                {(items as string[]).map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : <p className="mt-4 text-sm text-muted-text">{empty as string}</p>}
          </div>
        ))}
      </section>

      {coreEvidence.length ? (
        <details className="-mt-7 border-b border-border/70 pb-5 text-sm" data-testid="core-evidence-drawer">
          <summary className="flex min-h-11 cursor-pointer items-center justify-between py-2 font-medium text-foreground">
            <span>查看核心证据</span><span className="text-xs text-info">来源与时间</span>
          </summary>
          <div className="border-t border-border/50 pt-4"><EvidenceSampleList items={coreEvidence} /></div>
        </details>
      ) : null}

      <AdjudicationPanel adjudication={adjudication} fallback={oneLine} />

      {marketMatrix.length ? (
        <section className="border-b border-border/70 pb-9">
          <div className="text-[11px] font-semibold tracking-[0.16em] text-info">市场范围</div>
          <h2 className="mt-1 text-xl font-semibold text-foreground">市场范围与样本表现</h2>
          <div className="mt-5 grid gap-3 md:hidden" data-testid="market-mobile-cards">
            {marketMatrix.map((row, index) => (
              <article key={`${row.market}-${row.scopeLabel}-${index}`} className="rounded-xl border border-border/70 bg-background/30 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-foreground">{displayText(row.scopeLabel || row.market || '市场')}</h3>
                    <div className="mt-1 text-xs text-info">{row.scopeType === 'market' ? '市场数据' : '观察样本'}</div>
                  </div>
                  <span className="text-right text-sm font-medium text-secondary-text">{displayText(row.state || '待观察')}</span>
                </div>
                <p className="mt-4 text-sm leading-6 text-secondary-text">{displayText(row.headline || '未提供')}</p>
                {row.scopeNote ? <p className="mt-2 text-xs leading-5 text-muted-text">{displayText(row.scopeNote)}</p> : null}
              </article>
            ))}
          </div>
          <div className="mt-5 hidden overflow-x-auto md:block" data-testid="market-desktop-table">
            <table className="w-full min-w-[760px] text-left text-sm" aria-label="市场范围桌面表格">
              <thead className="text-xs text-muted-text"><tr><th className="pb-3">范围</th><th className="pb-3">状态</th><th className="pb-3">关键表现</th><th className="pb-3">如何解读</th></tr></thead>
              <tbody>
                {marketMatrix.map((row, index) => (
                  <tr key={`${row.market}-${row.scopeLabel}-${index}`} className="border-t border-border/60 align-top">
                    <td className="py-4 pr-5 font-medium text-foreground">{displayText(row.scopeLabel || row.market || '市场')}<div className="mt-1 text-xs font-normal text-info">{row.scopeType === 'market' ? '市场数据' : '观察样本'}</div></td>
                    <td className="py-4 pr-5 text-secondary-text">{displayText(row.state || '待观察')}</td>
                    <td className="py-4 pr-5 text-secondary-text">{displayText(row.headline || '未提供')}</td>
                    <td className="py-4 text-muted-text">{displayText(row.scopeNote || '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {stockMatrix.length ? (
        <section className="border-b border-border/70 pb-9">
          <div className="text-[11px] font-semibold tracking-[0.16em] text-info">标的跟踪</div>
          <h2 className="mt-1 text-xl font-semibold text-foreground">重点标的跟踪</h2>
          <p className="mt-2 text-sm text-muted-text">价格与指标来自同轮证据；定位是研究观察，不代表自动交易指令。</p>
          <div className="mt-5 grid gap-3 md:hidden" data-testid="stock-mobile-cards">
            {stockMatrix.map((row, index) => (
              <article key={`${row.symbol}-${index}`} className="rounded-xl border border-border/70 bg-background/30 p-4" data-testid={`stock-mobile-card-${row.symbol || index}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-muted-text">标的</div>
                    <h3 className="mt-1 font-semibold text-foreground">{displayText(row.name || row.symbol || '标的')}</h3>
                    {row.symbol ? <div className="mt-0.5 text-xs text-muted-text">{row.symbol}</div> : null}
                  </div>
                  <span className="rounded-full bg-info/10 px-2.5 py-1 text-xs font-medium text-info">{displayText(row.stance || '观察')}</span>
                </div>
                <dl className="mt-4 grid gap-4 text-sm">
                  <div>
                    <dt className="text-xs text-muted-text">价格</dt>
                    <dd className="mt-1 font-medium text-foreground">{readerPrice(row.lastPrice, row.currency)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-text">1 / 20 日表现</dt>
                    <dd className="mt-1 text-secondary-text">1日 {signedPct(row.return1dPct)} · 20日 {signedPct(row.return20dPct)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-text">趋势 / 观察位</dt>
                    <dd className="mt-1 leading-6 text-secondary-text">{displayText(row.trend || '趋势待确认')}{row.watchLevels ? ` · ${displayText(row.watchLevels)}` : ''}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-text">基本面</dt>
                    <dd className="mt-1 leading-6 text-secondary-text">{displayText(row.fundamental || '结构化基本面待补强')}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-text">估值</dt>
                    <dd className="mt-1 leading-6 text-secondary-text">{displayText(row.valuation || '当前估值与历史样本待补')}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-text">官方事件</dt>
                    <dd className="mt-1 leading-6 text-secondary-text">
                      {validSourceUrl(row.eventUrl) ? <a className="text-info hover:underline" href={validSourceUrl(row.eventUrl) || undefined} target="_blank" rel="noreferrer">{displayText(row.latestEvent || '官方事件')}</a> : displayText(row.latestEvent || '暂无近期官方事件摘要')}
                      {row.eventDate ? <span className="ml-2 text-xs text-muted-text">{row.eventDate}</span> : null}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-text">定位</dt>
                    <dd className="mt-1 text-secondary-text">{displayText(row.stance || '观察')}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
          <div className="mt-5 hidden overflow-x-auto md:block" data-testid="stock-desktop-table">
            <table className="w-full min-w-[1280px] text-left text-sm" aria-label="重点标的桌面表格">
              <thead className="text-xs text-muted-text"><tr><th className="pb-3">标的</th><th className="pb-3">价格 / 表现</th><th className="pb-3">趋势 / 观察位</th><th className="pb-3">基本面</th><th className="pb-3">估值</th><th className="pb-3">最新官方事件</th><th className="pb-3">定位</th></tr></thead>
              <tbody>
                {stockMatrix.map((row, index) => (
                  <tr key={`${row.symbol}-${index}`} className="border-t border-border/60 align-top">
                    <td className="py-4 pr-5"><div className="font-medium text-foreground">{displayText(row.name || row.symbol || '标的')}</div><div className="text-xs text-muted-text">{row.symbol}</div></td>
                    <td className="py-4 pr-5 text-secondary-text">{readerPrice(row.lastPrice, row.currency)}<div className="mt-1 text-xs text-muted-text">1日 {signedPct(row.return1dPct)} / 20日 {signedPct(row.return20dPct)}</div></td>
                    <td className="py-4 pr-5 text-secondary-text">{displayText(row.trend || '趋势待确认')}<div className="mt-1 max-w-xs text-xs text-muted-text">{displayText(row.watchLevels || '')}</div></td>
                    <td className="max-w-xs py-4 pr-5 leading-6 text-secondary-text">{displayText(row.fundamental || '结构化基本面待补强')}</td>
                    <td className="max-w-xs py-4 pr-5 leading-6 text-secondary-text">{displayText(row.valuation || '当前估值与历史样本待补')}</td>
                    <td className="max-w-xs py-4 pr-5 leading-6 text-secondary-text">{validSourceUrl(row.eventUrl) ? <a className="text-info hover:underline" href={validSourceUrl(row.eventUrl) || undefined} target="_blank" rel="noreferrer">{displayText(row.latestEvent || '官方事件')}</a> : displayText(row.latestEvent || '暂无近期官方事件摘要')}<div className="text-xs text-muted-text">{row.eventDate}</div></td>
                    <td className="py-4"><span className="rounded-full bg-info/10 px-2.5 py-1 text-xs font-medium text-info">{displayText(row.stance || '观察')}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {marketGeo.length ? (
        <section className="border-b border-border/70 pb-9">
          <div className="text-[11px] font-semibold tracking-[0.16em] text-info">宏观与地缘</div>
          <h2 className="mt-1 text-xl font-semibold text-foreground">市场与地缘</h2>
          <ul className="list-disc space-y-2 pl-5 text-sm text-secondary-text">{marketGeo.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      ) : null}

      <section className="min-w-0 border-b border-border/70 pb-9">
        <div className="text-[11px] font-semibold tracking-[0.16em] text-info">部门观点</div>
        <h2 className="mt-1 text-xl font-semibold text-foreground">部门研究摘要</h2>
        <p className="mb-4 text-sm text-muted-text">摘要直接可见；依据、反证、待确认项和证据默认折叠。</p>
        {departments.length ? (
          <div className="grid min-w-0 gap-2">
            {featuredDepartments.map((report) => <DepartmentDisclosure key={`${report.agent || report.label}`} report={report} />)}
            {otherDepartments.length ? (
              <details className="mt-2 rounded-xl border border-border/60 px-3 py-1">
                <summary className="flex min-h-11 cursor-pointer items-center justify-between py-2 font-medium text-foreground">
                  <span>其余 {otherDepartments.length} 个研究部门</span><span className="text-xs text-info">展开全部</span>
                </summary>
                <div className="grid gap-2 border-t border-border/50 py-3">
                  {otherDepartments.map((report) => <DepartmentDisclosure key={`${report.agent || report.label}`} report={report} />)}
                </div>
              </details>
            ) : null}
          </div>
        ) : <div className="text-sm text-muted-text">本轮未记录到分部门结论。</div>}
      </section>

      <details className="border-y border-border/70 py-1 text-sm">
        <summary className="cursor-pointer py-3 font-medium text-muted-text">数据与方法说明</summary>
        <div className="pb-4">
          <p className="mb-3 leading-7 text-secondary-text">{displayText(reader?.dataConfidence || '本轮数据可用于投研复核，仍需人工判断。')}</p>
          <div className="grid gap-3 text-secondary-text sm:grid-cols-2 lg:grid-cols-5">
            <div>已验证：<span className="text-foreground">{stats?.verifiedFacts ?? 0}</span></div>
            <div>推导：<span className="text-foreground">{stats?.derivedFacts ?? 0}</span></div>
            <div>发现线索：<span className="text-foreground">{stats?.discoveryItems ?? 0}</span></div>
            <div>关键证据缺口：<span className="text-foreground">{stats?.missingCriticalFacts ?? 0}</span></div>
            <div>部门待确认：<span className="text-foreground">{departmentGapItems}</span></div>
          </div>
          {reliabilityWarnings.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-warning">{reliabilityWarnings.map((item) => <li key={item}>{item}</li>)}</ul> : null}
        </div>
      </details>
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
