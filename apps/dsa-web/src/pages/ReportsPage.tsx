import type React from 'react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { reportsApi } from '../api/reports';
import { ApiErrorAlert } from '../components/common/ApiErrorAlert';
import { AppPage } from '../components/common/AppPage';
import { EmptyState } from '../components/common/EmptyState';
import { Loading } from '../components/common/Loading';
import { ReportArtifactDiagnosticsView, ReportArtifactView } from '../components/report/ReportArtifactView';
import type { ReportArtifactV1 } from '../types/analysis';
import { getParsedApiError, type ParsedApiError } from '../api/error';

const artifactTypeLabel: Record<string, string> = {
  daily: '日报',
  stock_governed: '个股深评',
};

const ReportsPage: React.FC = () => {
  const { date } = useParams<{ date?: string }>();
  const location = useLocation();
  const [artifact, setArtifact] = useState<ReportArtifactV1 | null>(null);
  const [artifacts, setArtifacts] = useState<ReportArtifactV1[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSelecting, setIsSelecting] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const diagnosticsRoute = location.pathname.endsWith('/diagnostics');

  useEffect(() => {
    let active = true;
    const primaryRequest = date
      ? reportsApi.getArtifact(date).catch(() => reportsApi.getArtifact(`daily:${date}`))
      : reportsApi.getLatest();
    Promise.all([
      primaryRequest,
      reportsApi.listArtifacts(5).catch(() => [] as ReportArtifactV1[]),
    ])
      .then(([nextArtifact, artifactList]) => {
        if (!active) return;
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
  }, [date]);

  const handleSelectArtifact = (artifactId: string) => {
    setIsSelecting(true);
    setError(null);
    reportsApi.getArtifact(artifactId)
      .then((nextArtifact) => setArtifact(nextArtifact))
      .catch((err: unknown) => setError(getParsedApiError(err)))
      .finally(() => setIsSelecting(false));
  };

  return (
    <AppPage className="space-y-5">
      <header className="space-y-2">
        <span className="label-uppercase">Reports</span>
        <h1 className="text-2xl font-semibold text-foreground">统一报告</h1>
        <p className="max-w-3xl text-sm leading-6 text-secondary-text">
          Web/App 只读取同一份报告数据；默认给读者看结论、依据、风险和下一步，高级诊断单独打开。
        </p>
        {artifact ? (
          <div className="flex flex-wrap gap-2 text-sm">
            <Link className="btn-secondary" to={`/reports/${artifact.runDate}`}>读者版</Link>
            <Link className="btn-secondary" to={`/reports/${artifact.runDate}/diagnostics`}>高级诊断</Link>
          </div>
        ) : null}
      </header>
      {isLoading ? <Loading label="正在加载最新报告" /> : null}
      {!isLoading && artifacts.length ? (
        <section className="rounded-2xl border border-border/60 bg-card/60 p-3">
          <div className="mb-2 text-sm font-medium text-foreground">历史报告</div>
          <div className="flex flex-wrap gap-2">
            {artifacts.map((item) => (
              <button
                key={item.artifactId}
                type="button"
                className={item.artifactId === artifact?.artifactId ? 'btn-primary' : 'btn-secondary'}
                disabled={isSelecting}
                onClick={() => handleSelectArtifact(item.artifactId)}
              >
                {item.runDate} · {artifactTypeLabel[item.artifactType] || item.artifactType}
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {isSelecting ? <Loading label="正在切换报告" /> : null}
      {error ? <ApiErrorAlert error={error} /> : null}
      {!isLoading && !error && !artifact ? (
        <EmptyState title="暂无报告" description="还没有可读取的报告数据包。" />
      ) : null}
      {artifact ? (
        diagnosticsRoute ? (
          <ReportArtifactDiagnosticsView key={`${artifact.artifactId}-diagnostics`} artifact={artifact} />
        ) : (
          <ReportArtifactView key={`${artifact.artifactId}-reader`} artifact={artifact} />
        )
      ) : null}
    </AppPage>
  );
};

export default ReportsPage;
