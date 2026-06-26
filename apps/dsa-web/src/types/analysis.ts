/**
 * Analysis-related type definitions.
 * Aligned with the API schema.
 */

// ============ Request Types ============

export type StockReportType = 'simple' | 'detailed' | 'full' | 'brief';
export type ReportType = StockReportType | 'market_review';

export interface AnalysisRequest {
  stockCode?: string;
  stockCodes?: string[];
  reportType?: StockReportType;
  forceRefresh?: boolean;
  asyncMode?: boolean;
  stockName?: string;
  originalQuery?: string;
  selectionSource?: 'manual' | 'autocomplete' | 'import' | 'image';
  notify?: boolean;
  skills?: string[];
}

export interface MarketReviewRequest {
  sendNotification?: boolean;
}

export interface MarketReviewAccepted {
  status: 'accepted';
  message: string;
  sendNotification: boolean;
  traceId?: string;
  taskId?: string;
}

// ============ Report Types ============

export type ReportArtifactType =
  | 'daily'
  | 'market_summary'
  | 'macro_review'
  | 'source_health'
  | 'screening_funnel'
  | 'deep_review_queue'
  | 'preliminary_review'
  | 'market_strategy'
  | 'stock_governed'
  | 'agent_memo'
  | 'run_status';

export type ReportArtifactAudience = 'reader' | 'audit' | 'machine' | 'run_status';
export type ReportArtifactSectionKind =
  | 'source'
  | 'facts'
  | 'analysis'
  | 'final_conclusion'
  | 'next_steps'
  | 'risk'
  | 'evidence'
  | 'raw';

export interface ReportArtifactSummary {
  oneLine: string;
  keyFacts: string[];
  analysis: string;
  finalConclusion: string;
  nextSteps: string[];
}

export interface ReportArtifactSection {
  key: string;
  title: string;
  kind: ReportArtifactSectionKind;
  contentMarkdown?: string;
  data?: unknown;
  sourceRefs?: string[];
  confidence?: 'high' | 'medium' | 'low';
  blocking?: boolean;
}

export interface ReportArtifactSourceHealth {
  status?: string;
  verdict?: string;
  canScore?: boolean;
  canTradeReview?: boolean;
  coverageScore?: number;
  freshnessStatus?: string;
  fallbackUsed?: string;
  failureReason?: string;
  decisionImpact?: string;
  [key: string]: unknown;
}

export interface ReportArtifactDecision {
  action: 'buy' | 'sell' | 'hold' | 'watch' | 'no_action';
  gateStatus: 'passed' | 'blocked' | 'watch';
  score?: number;
  targetPct?: number;
  blockedReasons?: string[];
}

export interface ReportArtifactAgentOrigins {
  raw: number;
  derived: number;
  missing: number;
}

export interface ReportArtifactProvenance {
  origin: string;
  sourceFiles: string[];
  generatedBy: string;
  runId?: string;
  taskId?: string;
  recordId?: string;
  queryId?: string;
}

export interface ReportArtifactPublish {
  webPath?: string;
  docsPath?: string;
  markdownPath?: string;
  jsonPath?: string;
  htmlPath?: string;
}

export interface ReportArtifactQuality {
  completeness: 'complete' | 'partial' | 'failed';
  missingFields: string[];
  validationErrors: string[];
  staleAsOf?: string;
}

export interface ReportArtifactV1 {
  schemaVersion: 'report_artifact_v1';
  artifactId: string;
  runDate: string;
  generatedAt: string;
  artifactType: ReportArtifactType;
  audience: ReportArtifactAudience;
  title: string;
  summary: ReportArtifactSummary;
  sections: ReportArtifactSection[];
  sourceHealth?: ReportArtifactSourceHealth;
  decision?: ReportArtifactDecision;
  agentOrigins?: ReportArtifactAgentOrigins;
  provenance: ReportArtifactProvenance;
  publish: ReportArtifactPublish;
  quality: ReportArtifactQuality;
}


export type ReportLanguage = 'zh' | 'en';

/** Report metadata */
export interface ReportMeta {
  id?: number;  // Analysis history record ID, present for persisted reports
  queryId: string;
  stockCode: string;
  stockName: string;
  reportType: ReportType;
  reportLanguage?: ReportLanguage;
  createdAt: string;
  currentPrice?: number;
  changePct?: number;
  modelUsed?: string;  // LLM model used for analysis
}

/** Sentiment label */
export type SentimentLabel =
  | '极度悲观'
  | '悲观'
  | '中性'
  | '乐观'
  | '极度乐观'
  | 'Very Bearish'
  | 'Bearish'
  | 'Neutral'
  | 'Bullish'
  | 'Very Bullish';

/** Report summary section */
export interface ReportSummary {
  analysisSummary: string;
  operationAdvice: string;
  trendPrediction: string;
  sentimentScore: number;
  sentimentLabel?: SentimentLabel;
}

/** Strategy section */
export interface ReportStrategy {
  idealBuy?: string;
  secondaryBuy?: string;
  stopLoss?: string;
  takeProfit?: string;
}

export interface RelatedBoard {
  name: string;
  code?: string;
  type?: string;
}

export interface SectorRankingItem {
  name: string;
  changePct?: number;
}

export interface SectorRankings {
  top?: SectorRankingItem[];
  bottom?: SectorRankingItem[];
}

/** Details section */
export interface ReportDetails {
  newsContent?: string;
  rawResult?: Record<string, unknown>;
  contextSnapshot?: Record<string, unknown>;
  financialReport?: Record<string, unknown>;
  dividendMetrics?: Record<string, unknown>;
  belongBoards?: RelatedBoard[];
  sectorRankings?: SectorRankings;
}

/** Full analysis report */
export interface AnalysisReport {
  meta: ReportMeta;
  summary: ReportSummary;
  strategy?: ReportStrategy;
  details?: ReportDetails;
  artifact?: ReportArtifactV1;
}

// ============ Analysis Result Types ============

export type RunDiagnosticStatus = 'normal' | 'degraded' | 'failed' | 'unknown';

export type RunDiagnosticComponentStatus =
  | 'ok'
  | 'degraded'
  | 'failed'
  | 'unknown'
  | 'not_configured'
  | 'skipped';

export interface RunDiagnosticComponent {
  key: string;
  label: string;
  status: RunDiagnosticComponentStatus;
  message: string;
  details?: Record<string, unknown>;
}

export interface RunDiagnosticSummary {
  traceId?: string;
  taskId?: string;
  queryId?: string;
  stockCode?: string;
  triggerSource?: string;
  status: RunDiagnosticStatus;
  statusLabel: string;
  reason: string;
  components: Record<string, RunDiagnosticComponent>;
  copyText: string;
}

/** Sync analysis response */
export interface AnalysisResult {
  queryId: string;
  traceId?: string;
  stockCode: string;
  stockName: string;
  report: AnalysisReport;
  diagnosticSummary?: RunDiagnosticSummary;
  createdAt: string;
}

/** Async task accepted response */
export interface TaskAccepted {
  taskId: string;
  traceId?: string;
  status: 'pending' | 'processing';
  message?: string;
}

export interface BatchTaskAcceptedItem {
  taskId: string;
  traceId?: string;
  stockCode: string;
  status: 'pending' | 'processing';
  message?: string;
}

export interface BatchDuplicateTaskItem {
  stockCode: string;
  existingTaskId: string;
  message: string;
}

export interface BatchTaskAcceptedResponse {
  accepted: BatchTaskAcceptedItem[];
  duplicates: BatchDuplicateTaskItem[];
  message: string;
}

export type AnalyzeAsyncResponse = TaskAccepted | BatchTaskAcceptedResponse;

export type AnalyzeResponse = AnalysisResult | AnalyzeAsyncResponse;

/** Task status */
export interface TaskStatus {
  taskId: string;
  traceId?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress?: number;
  result?: AnalysisResult;
  marketReviewReport?: string;
  error?: string;
  stockName?: string;
  originalQuery?: string;
  selectionSource?: string;
  skills?: string[];
}

/** Task details used by task list and SSE events */
export interface TaskInfo {
  taskId: string;
  traceId?: string;
  stockCode: string;
  stockName?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string;
  reportType: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  error?: string;
  originalQuery?: string;
  selectionSource?: string;
}

/** Task list response */
export interface TaskListResponse {
  total: number;
  pending: number;
  processing: number;
  tasks: TaskInfo[];
}

/** Duplicate task error response */
export interface DuplicateTaskError {
  error: 'duplicate_task';
  message: string;
  stockCode: string;
  existingTaskId: string;
}

// ============ History Types ============

/** History item summary */
export interface HistoryItem {
  id: number;  // Record primary key ID, always present for persisted history items
  queryId: string;  // Linked analysis query ID
  stockCode: string;
  stockName?: string;
  reportType?: ReportType;
  sentimentScore?: number;
  operationAdvice?: string;
  createdAt: string;
}

/** History list response */
export interface HistoryListResponse {
  total: number;
  page: number;
  limit: number;
  items: HistoryItem[];
}

/** News item */
export interface NewsIntelItem {
  title: string;
  snippet: string;
  url: string;
}

/** News response */
export interface NewsIntelResponse {
  total: number;
  items: NewsIntelItem[];
}

/** History filter parameters */
export interface HistoryFilters {
  stockCode?: string;
  startDate?: string;
  endDate?: string;
}

/** History pagination parameters */
export interface HistoryPagination {
  page: number;
  limit: number;
}

// ============ Error Types ============

export interface ApiError {
  error: string;
  message: string;
  detail?: Record<string, unknown>;
}

// ============ Helper Functions ============

/** Get sentiment label by score */
export const getSentimentLabel = (score: number, language: ReportLanguage = 'zh'): SentimentLabel => {
  if (language === 'en') {
    if (score <= 20) return 'Very Bearish';
    if (score <= 40) return 'Bearish';
    if (score <= 60) return 'Neutral';
    if (score <= 80) return 'Bullish';
    return 'Very Bullish';
  }
  if (score <= 20) return '极度悲观';
  if (score <= 40) return '悲观';
  if (score <= 60) return '中性';
  if (score <= 80) return '乐观';
  return '极度乐观';
};

/** Get sentiment color by score */
export const getSentimentColor = (score: number): string => {
  if (score <= 20) return '#ef4444'; // red-500
  if (score <= 40) return '#f97316'; // orange-500
  if (score <= 60) return '#eab308'; // yellow-500
  if (score <= 80) return '#22c55e'; // green-500
  return '#10b981'; // emerald-500
};
