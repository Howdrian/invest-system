import type React from 'react';
import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react';
import type { ReportArtifactDecision, ReportArtifactSection, ReportArtifactV1 } from '../../types/analysis';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { JsonViewer } from '../common/JsonViewer';

interface ReportArtifactViewProps {
  artifact: ReportArtifactV1;
}

const sectionOrder = ['source', 'facts', 'analysis', 'final_conclusion', 'next_steps', 'risk', 'evidence'];

const sectionLabel: Record<string, string> = {
  source: '数据源',
  facts: '关键数据',
  analysis: '推论',
  final_conclusion: '总结论',
  next_steps: '下一步',
  risk: '风险',
  evidence: '证据链',
};

const decisionActionLabel: Record<ReportArtifactDecision['action'], string> = {
  buy: '买入候选',
  sell: '卖出候选',
  hold: '持有/复核',
  watch: '观察',
  no_action: '不操作',
};

const gateStatusLabel: Record<ReportArtifactDecision['gateStatus'], string> = {
  passed: '门控通过',
  blocked: '已阻断',
  watch: '等待观察',
};

function sortSections(sections: ReportArtifactSection[]): ReportArtifactSection[] {
  return [...sections]
    .filter((section) => section.kind !== 'raw')
    .sort((a, b) => {
      const ai = sectionOrder.indexOf(a.kind);
      const bi = sectionOrder.indexOf(b.kind);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
}

function humanConfidence(value?: string): string {
  if (value === 'high') return '高可信';
  if (value === 'medium') return '中等可信';
  if (value === 'low') return '低可信';
  return '可信度未标';
}

function displayStatus(value?: string): string {
  if (!value) return '未标明';
  const normalized = value.toLowerCase();
  if (normalized === 'trade_review_limited' || normalized === 'usable_limited') return '交易审查受限';
  if (normalized === 'can_score') return '可评分';
  if (normalized.includes('degraded') || normalized.includes('partial')) return '降级可用';
  if (normalized.includes('failed')) return '失败';
  if (normalized.includes('blocked')) return '已阻断';
  if (normalized.includes('available')) return '可用';
  if (normalized.includes('refreshed')) return '已刷新';
  return value;
}

function artifactTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    daily: '日报',
    market_summary: '大盘摘要',
    macro_review: '宏观复盘',
    source_health: '数据源健康',
    screening_funnel: '筛选漏斗',
    deep_review_queue: '深评队列',
    preliminary_review: '初步深评',
    market_strategy: '市场策略',
    stock_governed: '个股 Governed',
    agent_memo: 'Agent 卷宗',
    run_status: '运行状态',
  };
  return labels[value] || value;
}

function artifactSourceLabel(artifact: ReportArtifactV1): string {
  const origin = artifact.provenance?.origin || '';
  if (origin.includes('static') || artifact.artifactType === 'daily') return 'Static Daily Report';
  return 'History Stock Report';
}

function isDegradedSourceHealth(sourceHealth: ReportArtifactV1['sourceHealth']): boolean {
  const text = [
    sourceHealth?.status,
    sourceHealth?.verdict,
    sourceHealth?.decisionImpact,
  ].filter(Boolean).join(' ').toLowerCase();
  return ['degraded', 'partial', 'limited', 'failed', 'unavailable', '不可作为满血'].some((token) => text.includes(token));
}

function renderMarkdownLite(content?: string): React.ReactNode {
  if (!content?.trim()) {
    return <p className="text-sm text-muted-text">未提供。</p>;
  }
  return (
    <div className="whitespace-pre-wrap text-sm leading-7 text-secondary-text">
      {content}
    </div>
  );
}

const SectionCard: React.FC<{ section: ReportArtifactSection }> = ({ section }) => {
  const title = sectionLabel[section.kind] || section.title;
  return (
    <Card className="border border-border/60 bg-card/72" padding="md">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        <Badge variant={section.blocking ? 'danger' : 'info'}>{humanConfidence(section.confidence)}</Badge>
      </div>
      {renderMarkdownLite(section.contentMarkdown)}
      {section.sourceRefs?.length ? (
        <div className="mt-3 text-xs text-muted-text">
          来源：{section.sourceRefs.join('、')}
        </div>
      ) : null}
    </Card>
  );
};

export const ReportArtifactView: React.FC<ReportArtifactViewProps> = ({ artifact }) => {
  const [showAuditJson, setShowAuditJson] = useState(false);
  const sections = useMemo(() => sortSections(artifact.sections || []), [artifact.sections]);
  const decision = artifact.decision;
  const sourceHealth = artifact.sourceHealth;
  const gateBlocked = decision?.gateStatus === 'blocked';
  const degradedSourceHealth = isDegradedSourceHealth(sourceHealth);

  return (
    <article className="space-y-5" data-testid="report-artifact-view">
      <Card variant="gradient" padding="lg">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">ReportArtifact v1</Badge>
              <Badge variant={artifact.artifactType === 'daily' ? 'success' : 'info'}>
                {artifactSourceLabel(artifact)}
              </Badge>
              <Badge variant={artifact.quality.completeness === 'complete' ? 'success' : artifact.quality.completeness === 'failed' ? 'danger' : 'warning'}>
                {artifact.quality.completeness === 'complete' ? '完整' : artifact.quality.completeness === 'failed' ? '失败' : '部分完整'}
              </Badge>
            </div>
            <h1 className="text-2xl font-semibold text-foreground">{artifact.title}</h1>
            <p className="text-base leading-7 text-secondary-text">{artifact.summary.oneLine}</p>
          </div>
          <div className="rounded-2xl border border-border/60 bg-background/45 px-4 py-3 text-sm text-secondary-text">
            <div>日期：{artifact.runDate}</div>
            <div>类型：{artifactTypeLabel(artifact.artifactType)}</div>
            <div>生成：{new Date(artifact.generatedAt).toLocaleString()}</div>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Source Health" className="border border-border/60 bg-card/72">
          <div className="space-y-2 text-sm text-secondary-text">
            <div>状态：{displayStatus(sourceHealth?.status)}</div>
            <div>结论影响：{displayStatus(String(sourceHealth?.decisionImpact || sourceHealth?.verdict || ''))}</div>
            <div>可评分：{sourceHealth?.canScore ? '是' : '否/未确认'}</div>
            <div>可交易审查：{sourceHealth?.canTradeReview ? '是' : '否/未确认'}</div>
            {degradedSourceHealth ? (
              <div className="rounded-xl border border-warning/40 bg-warning/10 px-3 py-2 text-warning">
                数据源降级，可观察，不可作为满血交易依据
              </div>
            ) : null}
          </div>
        </Card>
        <Card title="Governance gate" className="border border-border/60 bg-card/72">
          <div className="flex items-start gap-3 text-sm text-secondary-text">
            {gateBlocked ? <ShieldAlert className="mt-1 h-5 w-5 text-danger" /> : <CheckCircle2 className="mt-1 h-5 w-5 text-success" />}
            <div className="space-y-2">
              <div>{gateStatusLabel[decision?.gateStatus || 'watch']}</div>
              <div>动作：{decision ? decisionActionLabel[decision.action] : '未生成'}</div>
              <div>评分：{typeof decision?.score === 'number' ? `${decision.score}/10` : '未评分'}</div>
              <div>目标仓位：{typeof decision?.targetPct === 'number' ? `${decision.targetPct}%` : '未标'}</div>
            </div>
          </div>
        </Card>
        <Card title="Agent origin" className="border border-border/60 bg-card/72">
          <div className="space-y-2 text-sm text-secondary-text">
            <div>真实 Agent：{artifact.agentOrigins?.raw ?? 0}</div>
            <div>回填审计：{artifact.agentOrigins?.derived ?? 0}</div>
            <div>未运行：{artifact.agentOrigins?.missing ?? 0}</div>
            {(artifact.agentOrigins?.missing ?? 0) > 0 ? (
              <div className="flex items-center gap-2 text-warning"><AlertTriangle className="h-4 w-4" />有 Agent 缺失</div>
            ) : null}
          </div>
        </Card>
      </div>

      <Card title="关键事实" className="border border-border/60 bg-card/72">
        <ul className="list-disc space-y-2 pl-5 text-sm text-secondary-text">
          {artifact.summary.keyFacts.map((fact) => <li key={fact}>{fact}</li>)}
        </ul>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {sections.map((section) => <SectionCard key={section.key} section={section} />)}
      </div>

      <Card title="审计详情" subtitle="JSON 只用于追溯" className="border border-border/60 bg-card/72">
        <button type="button" className="btn-secondary" onClick={() => setShowAuditJson((value) => !value)}>
          {showAuditJson ? '隐藏审计 JSON' : '查看审计 JSON'}
        </button>
        {showAuditJson ? <JsonViewer data={artifact as unknown as Record<string, unknown>} className="mt-4" /> : null}
      </Card>
    </article>
  );
};
