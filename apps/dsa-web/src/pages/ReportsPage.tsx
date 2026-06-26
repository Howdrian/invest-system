import type React from 'react';
import { useEffect, useState } from 'react';
import { reportsApi } from '../api/reports';
import { ApiErrorAlert } from '../components/common/ApiErrorAlert';
import { AppPage } from '../components/common/AppPage';
import { EmptyState } from '../components/common/EmptyState';
import { Loading } from '../components/common/Loading';
import { ReportArtifactView } from '../components/report/ReportArtifactView';
import type { ReportArtifactV1 } from '../types/analysis';
import { getParsedApiError, type ParsedApiError } from '../api/error';

const ReportsPage: React.FC = () => {
  const [artifact, setArtifact] = useState<ReportArtifactV1 | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);

  useEffect(() => {
    let active = true;
    reportsApi.getLatest()
      .then((nextArtifact) => {
        if (active) setArtifact(nextArtifact);
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
  }, []);

  return (
    <AppPage className="space-y-5">
      <header className="space-y-2">
        <span className="label-uppercase">Reports</span>
        <h1 className="text-2xl font-semibold text-foreground">统一报告</h1>
        <p className="max-w-3xl text-sm leading-6 text-secondary-text">
          Web/App 优先读取静态日报 ReportArtifact；无日报包时回退到历史个股报告。
        </p>
      </header>
      {isLoading ? <Loading label="正在加载最新报告" /> : null}
      {error ? <ApiErrorAlert error={error} /> : null}
      {!isLoading && !error && !artifact ? (
        <EmptyState title="暂无报告" description="还没有可读取的 ReportArtifact。" />
      ) : null}
      {artifact ? <ReportArtifactView artifact={artifact} /> : null}
    </AppPage>
  );
};

export default ReportsPage;
