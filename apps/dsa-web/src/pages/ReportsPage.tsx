import type React from 'react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { historyApi } from '../api/history';
import { ReportSummary } from '../components/report/ReportSummary';
import { reportsApi } from '../api/reports';
import { ApiErrorAlert } from '../components/common/ApiErrorAlert';
import { AppPage } from '../components/common/AppPage';
import { EmptyState } from '../components/common/EmptyState';
import { Loading } from '../components/common/Loading';
import { ReportArtifactDiagnosticsView, ReportArtifactView } from '../components/report/ReportArtifactView';
import type { AnalysisReport, ReportArtifactV1 } from '../types/analysis';
import { getParsedApiError, type ParsedApiError } from '../api/error';

const artifactTypeLabel: Record<string, string> = {
  daily: '日报',
  stock_governed: '个股深评',
  market_summary: '市场复盘',
};

const ReportsPage: React.FC = () => {
  const { date } = useParams<{ date?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [artifact, setArtifact] = useState<ReportArtifactV1 | null>(null);
  const [artifacts, setArtifacts] = useState<ReportArtifactV1[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [history, setHistory] = useState<{ report: AnalysisReport; markdown: string } | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const diagnosticsRoute = location.pathname.endsWith('/diagnostics');

  useEffect(() => {
    let active = true;
    const primaryRequest = date
      ? reportsApi.getArtifact(date)
      : reportsApi.getLatest();
    Promise.all([
      primaryRequest,
      reportsApi.listArtifacts(30).catch(() => [] as ReportArtifactV1[]),
    ])
      .then(async ([nextArtifact, artifactList]) => {
        const recordId = /^history:(\d+)$/.exec(nextArtifact.artifactId)?.[1];
        const nativeReport = recordId && !diagnosticsRoute
          ? await Promise.all([historyApi.getDetail(Number(recordId)), historyApi.getMarkdown(Number(recordId))])
          : null;
        if (!active) return;
        setError(null);
        setHistory(nativeReport ? { report: nativeReport[0], markdown: nativeReport[1] } : null);
        setArtifact(nextArtifact);
        setArtifacts(artifactList);
      })
      .catch((err: unknown) => {
        if (active) setError(getParsedApiError(err));
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [date, diagnosticsRoute]);

  const reportPath = artifact ? `/reports/${encodeURIComponent(artifact.artifactId)}` : '/reports';

  return (
    <AppPage className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div>
          <span className="label-uppercase">Research</span>
          <h1 className="mt-1 text-xl font-semibold text-foreground">投研报告</h1>
        </div>
        {artifact ? (
          <nav className="flex flex-wrap gap-2 text-sm" aria-label="报告视图">
            <Link className="btn-secondary" to={reportPath}>读者版</Link>
            <Link className="btn-secondary" to={`${reportPath}/diagnostics`}>高级诊断</Link>
          </nav>
        ) : null}
      </header>
      {isLoading ? <Loading label="正在加载最新报告" /> : null}
      {error ? <ApiErrorAlert error={error} /> : null}
      {!isLoading && !error && !artifact ? (
        <EmptyState title="暂无报告" description="还没有可读取的报告数据包。" />
      ) : null}
      {artifact && !error ? (
        diagnosticsRoute ? (
          <ReportArtifactDiagnosticsView key={`${artifact.artifactId}-diagnostics`} artifact={artifact} />
        ) : history ? (
          <ReportSummary data={history.report} isHistory readerMarkdown={history.markdown} />
        ) : (
          <ReportArtifactView key={`${artifact.artifactId}-reader`} artifact={artifact} />
        )
      ) : null}
      {!isLoading && artifacts.length ? (
        <details className="rounded-xl border border-border/60 bg-card/40 px-3 py-1">
          <summary className="flex min-h-11 cursor-pointer items-center justify-between py-2 text-sm font-medium text-foreground">
            <span>历史报告</span><span className="text-xs text-info">查看近 {artifacts.length} 期</span>
          </summary>
          <div className="flex flex-wrap gap-2 border-t border-border/50 py-3">
            {artifacts.map((item) => (
              <button
                key={item.artifactId}
                type="button"
                className={item.artifactId === artifact?.artifactId ? 'btn-primary' : 'btn-secondary'}
                onClick={() => navigate(`/reports/${encodeURIComponent(item.artifactId)}`)}
              >
                {item.runDate} · {item.artifactType === 'daily' ? '综合日报' : item.title || artifactTypeLabel[item.artifactType] || '研究报告'}
              </button>
            ))}
          </div>
        </details>
      ) : null}
    </AppPage>
  );
};

export default ReportsPage;
