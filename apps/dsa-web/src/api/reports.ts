import apiClient from './index';
import { toCamelCase } from './utils';
import type { ReportArtifactV1 } from '../types/analysis';

export const reportsApi = {
  getLatest: async (): Promise<ReportArtifactV1> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/reports/latest');
    return toCamelCase<ReportArtifactV1>(response.data);
  },

  listArtifacts: async (limit = 20): Promise<ReportArtifactV1[]> => {
    const response = await apiClient.get<Array<Record<string, unknown>>>('/api/v1/reports/artifacts', {
      params: { limit },
    });
    return response.data.map((item) => toCamelCase<ReportArtifactV1>(item));
  },

  getArtifact: async (artifactId: string): Promise<ReportArtifactV1> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/reports/artifacts/${encodeURIComponent(artifactId)}`,
    );
    return toCamelCase<ReportArtifactV1>(response.data);
  },
};
