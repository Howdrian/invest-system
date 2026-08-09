/**
 * Analysis-related type definitions.
 * Aligned with the API schema.
 */

// ============ Request Types ============

export type StockReportType = 'simple' | 'detailed' | 'full' | 'brief';
export type ReportType = StockReportType | 'market_review';
export type AnalysisPhase = 'auto' | 'premarket' | 'intraday' | 'postmarket';
export type MarketReviewRegion = 'cn' | 'hk' | 'us' | 'jp' | 'kr';

export interface AnalysisRequest {
  stockCode?: string;
  stockCodes?: string[];
  reportType?: StockReportType;
  forceRefresh?: boolean;
  asyncMode?: boolean;
  analysisPhase?: AnalysisPhase;
  stockName?: string;
  originalQuery?: string;
  selectionSource?: 'manual' | 'autocomplete' | 'import' | 'image';
  notify?: boolean;
  skills?: string[];
  reportLanguage?: ReportLanguage;
}

export interface MarketReviewRequest {
  sendNotification?: boolean;
  reportLanguage?: ReportLanguage;
  regions?: readonly MarketReviewRegion[];
}

export interface MarketReviewAccepted {
  status: 'accepted';
  message: string;
  sendNotification: boolean;
  region: string;
  traceId?: string;
  taskId?: string;
}

// ============ Report Types ============

export type ReportLanguage = 'zh' | 'en' | 'ko';

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
  readerVisible?: boolean;
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

export type ReportArtifactAnalysisMode =
  | 'FULL_REVIEW'
  | 'LIMITED_REVIEW'
  | 'SCREEN_ONLY'
  | 'OBSERVE_ONLY'
  | 'BLOCKED';

export interface ReportArtifactSourceHealthDomain {
  label?: string;
  status: string;
  coverage: number;
  freshness: string;
  confidence: string;
  blockers: string[];
  repairHints: string[];
}

export interface ReportArtifactProviderMatrixRow {
  provider: string;
  market?: string;
  domain?: string;
  operation?: string;
  status: string;
  authState?: string;
  recordCount?: number;
  latencyMs?: number;
  errorType?: string;
  fallbackTo?: string;
  sourceTier?: string;
  sourceScope?: 'subject_evidence' | 'source_smoke';
  factType?: string;
  observedAt?: string;
}

export interface ReportArtifactClaimPolicy {
  canScore: boolean;
  canActionableAdvice: boolean;
  canPositionSizing: boolean;
  mustShowCaveat: boolean;
}

export interface ReportArtifactClaimEvidenceRow {
  label?: string;
  status: 'supported' | 'partial' | 'missing' | string;
  requiredDomains: string[];
  evidenceIds: string[];
  evidenceCount: number;
  missingDomains: string[];
  blockers?: string[];
}

export interface ReportArtifactClaimEvidence {
  schema: 'claim_evidence_v1';
  supportFactTypes: string[];
  positionSizingMissingCriticalThreshold: number;
  claims: Record<string, ReportArtifactClaimEvidenceRow>;
}

export interface ReportArtifactEvidenceStats {
  schema: 'evidence_stats_v1';
  verifiedFacts: number;
  derivedFacts?: number;
  discoveryItems: number;
  missingFacts?: number;
  missingCriticalFacts: number;
}

export interface ReportArtifactEvidenceItem {
  id?: string;
  domain?: string;
  factType?: 'verified_fact' | 'derived_fact' | 'discovery' | 'missing';
  provider?: string;
  symbol?: string;
  value?: string;
  asOf?: string;
  eventTime?: string;
  publishedAt?: string;
  fetchedAt?: string;
  sourceUrl?: string;
  rawPath?: string;
  confidence?: string;
  evidenceScope?: 'subject_evidence' | 'source_smoke';
}

export interface ReportArtifactReaderBrief {
  schema?: string;
  runDate?: string;
  mode?: ReportArtifactAnalysisMode;
  oneLine?: string;
  analysis?: string;
  finalConclusion?: string;
  why?: string[];
  risks?: string[];
  watchlist?: string[];
  universe?: {
    mode?: string;
    subjectCount?: number;
    subjects?: string[];
  };
  dataConfidence?: string;
  nextSteps?: string[];
}

export interface ReportArtifactDailyUniverseGroup {
  name: string;
  source?: string;
  symbols?: string[];
  market?: string;
  series?: string[];
  whyIncluded?: string;
  evidenceRequirements?: string[];
}

export interface ReportArtifactDailyUniverse {
  schema?: 'daily_universe_v1' | string;
  runDate?: string;
  mode?: string;
  market?: string;
  subjectSymbols?: string[];
  groups?: ReportArtifactDailyUniverseGroup[];
  notes?: string[];
}

export interface ReportArtifactDepartmentReport {
  agent?: string;
  label?: string;
  subject?: string;
  origin?: string;
  readerVisible?: boolean;
  summaryForReader?: string;
  keyClaims?: string[];
  evidenceIds?: string[];
  counterpoints?: string[];
  dataGaps?: string[];
  confidence?: string;
  nextAction?: string;
}

export interface ReportArtifactOriginalAnalysis {
  runDate?: string;
  marketContextAvailable?: boolean;
  marketReviewAvailable?: boolean;
  stockContextCount?: number;
  stockAnalysisCount?: number;
  decisionSignalCount?: number;
  portfolioSnapshotAvailable?: boolean;
  refsPath?: string;
  refCount?: number;
  availableKinds?: string[];
  notes?: string[];
}

export interface ReportArtifactDepartmentInputRef {
  kind?: string;
  status?: string;
  summary?: string;
  sourceKind?: string;
  evidenceIds?: string[];
  symbols?: string[];
}

export interface ReportArtifactDepartmentInput {
  agent?: string;
  inputProfile?: string;
  sourceKinds?: string[];
  originalKinds?: string[];
  evidenceDomains?: string[];
  description?: string;
  evidenceIds?: string[];
  originalAnalysisRefs?: ReportArtifactDepartmentInputRef[];
}

export interface ReportArtifactReaderV2EvidenceSample {
  id?: string;
  label?: string;
  sourceName?: string;
  provider?: string;
  factType?: string;
  asOf?: string;
  sourceUrl?: string;
}

export interface ReportArtifactReaderV2Section {
  key: string;
  title: string;
  body?: string;
  bullets?: string[];
}

export interface ReportArtifactReaderV2DepartmentCard {
  agent?: string;
  label?: string;
  conclusion?: string;
  keyClaims?: string[];
  counterpoints?: string[];
  dataGaps?: string[];
  nextAction?: string;
  nextActions?: string[];
  confidence?: string;
  supportSignals?: string[];
  usedOriginalAnalysis?: string[];
  evidenceIds?: string[];
  evidenceSamples?: ReportArtifactReaderV2EvidenceSample[];
}

export interface ReportArtifactReaderV2SupportDrawer {
  agent?: string;
  title?: string;
  originalAnalysis?: string[];
  evidence?: ReportArtifactReaderV2EvidenceSample[];
}

export interface ReportArtifactReaderV2 {
  schema?: string;
  runDate?: string;
  sections?: ReportArtifactReaderV2Section[];
  departmentCards?: ReportArtifactReaderV2DepartmentCard[];
  supportDrawers?: ReportArtifactReaderV2SupportDrawer[];
}

export interface ReportArtifactReaderV3Hero {
  marketStance?: string;
  portfolioAction?: string;
  validity?: string;
  dataCoverage?: string;
  action?: string;
  status?: string;
  confidence?: string;
  oneLine?: string;
  maxLimitation?: string;
  coverage?: string;
}

export interface ReportArtifactReaderV3DepartmentCard {
  agent?: string;
  label?: string;
  conclusion?: string;
  keyClaims?: string[];
  counterpoints?: string[];
  dataGaps?: string[];
  nextAction?: string;
  nextActions?: string[];
  confidence?: string;
  supportSignals?: string[];
  challengedClaims?: Array<{
    claim?: string;
    status?: string;
    opposingScenario?: string;
    falsifier?: string;
  }>;
  evidenceSamples?: ReportArtifactReaderV2EvidenceSample[];
}

export interface ReportArtifactReaderV3Section {
  key?: string;
  title?: string;
  body?: string;
  bullets?: string[];
  counterpoints?: string[];
  nextActions?: string[];
  evidenceSamples?: ReportArtifactReaderV2EvidenceSample[];
}

export interface ReportArtifactReaderV3MarketRow {
  market?: string;
  scopeLabel?: string;
  scopeType?: 'market' | 'sample' | string;
  state?: string;
  headline?: string;
  scopeNote?: string;
  breadthAvailable?: boolean;
  asOf?: string;
  evidenceIds?: string[];
}

export interface ReportArtifactReaderV3StockRow {
  symbol?: string;
  name?: string;
  market?: 'CN' | 'HK' | 'US' | string;
  stance?: string;
  lastPrice?: number;
  currency?: string;
  return1dPct?: number;
  return20dPct?: number;
  trend?: string;
  fundamental?: string;
  valuation?: string;
  latestEvent?: string;
  eventDate?: string;
  eventUrl?: string;
  watchLevels?: string;
  asOf?: string;
  evidenceIds?: string[];
}

export interface ReportArtifactReaderV3 {
  schema?: string;
  runDate?: string;
  timing?: {
    reportDate?: string;
    generatedAt?: string;
    dataAsOf?: string;
  };
  hero?: ReportArtifactReaderV3Hero;
  assessment?: {
    dataCoverage?: string;
    conclusionConfidence?: string;
  };
  keyReasons?: string[];
  counterpoints?: string[];
  nextSteps?: string[];
  marketMatrix?: ReportArtifactReaderV3MarketRow[];
  stockMatrix?: ReportArtifactReaderV3StockRow[];
  marketGeo?: string[];
  adjudication?: {
    sharedFacts?: string[];
    baseCase?: string;
    strongestAlternative?: string;
    judgment?: string;
    why?: string;
    invalidationTriggers?: string[];
  };
  challengeVerdicts?: Array<{
    department?: string;
    claim?: string;
    status?: string;
    opposingScenario?: string;
    falsifier?: string;
  }>;
  reliability?: {
    label?: string;
    headlineSafe?: boolean;
    headlineDisplayable?: boolean;
    headlineEvidenceSupported?: boolean;
    headlineStatus?: string;
    warnings?: string[];
    supportedClaims?: number;
    hypothesisClaims?: number;
    rejectedClaims?: number;
  };
  reportSections?: ReportArtifactReaderV3Section[];
  dataConfidence?: string;
  evidenceSummary?: {
    verifiedFacts?: number;
    derivedFacts?: number;
    discoveryItems?: number;
    missingCriticalFacts?: number;
    departmentGapItems?: number;
  };
  departmentCards?: ReportArtifactReaderV3DepartmentCard[];
  diagnosticsPath?: string;
}

export interface ReportArtifactSourceHealthV2 {
  schema: 'source_health_v2';
  generatedAt?: string;
  overallMode: ReportArtifactAnalysisMode;
  overallScore: number;
  domains: Record<string, ReportArtifactSourceHealthDomain>;
  providerMatrix: ReportArtifactProviderMatrixRow[];
  claimPolicy: ReportArtifactClaimPolicy;
  claimEvidence?: ReportArtifactClaimEvidence;
  evidenceStats?: ReportArtifactEvidenceStats;
  blockingReasons?: string[];
}


export interface ReportArtifactRunMatrixRef {
  runId?: string;
  runDate?: string;
}

export interface ReportArtifactSnapshotRefs {
  providerLedgerPath?: string;
  evidenceLedgerPath?: string;
  sourceHealthPath?: string;
  runMatrixPath?: string;
  providerLedgerSha256?: string;
  evidenceLedgerSha256?: string;
  sourceHealthSha256?: string;
  runMatrixSha256?: string;
  agentRunId?: string;
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
  sourceHealthV2?: ReportArtifactSourceHealthV2;
  analysisMode?: ReportArtifactAnalysisMode;
  dataCoverage?: {
    mode?: ReportArtifactAnalysisMode;
    label?: string;
    score?: number;
    missingCriticalFacts?: number;
  };
  conclusionConfidence?: {
    label?: string;
    headlineSafe?: boolean;
    supportedClaims?: number;
    hypothesisClaims?: number;
    rejectedClaims?: number;
  };
  claimPolicy?: ReportArtifactClaimPolicy;
  claimEvidence?: ReportArtifactClaimEvidence;
  evidenceStats?: ReportArtifactEvidenceStats;
  evidenceItems?: ReportArtifactEvidenceItem[];
  readerBrief?: ReportArtifactReaderBrief;
  dailyUniverse?: ReportArtifactDailyUniverse;
  departmentReports?: ReportArtifactDepartmentReport[];
  originalAnalysis?: ReportArtifactOriginalAnalysis;
  departmentInputs?: ReportArtifactDepartmentInput[];
  readerV2?: ReportArtifactReaderV2;
  readerV3?: ReportArtifactReaderV3;
  researchReliability?: {
    schema?: string;
    label?: string;
    headlineSafe?: boolean;
    inputClaims?: number;
    readerClaims?: number;
    supportedClaims?: number;
    partialClaims?: number;
    hypothesisClaims?: number;
    disputedClaims?: number;
    rejectedClaims?: number;
    warnings?: string[];
  };
  runMatrix?: ReportArtifactRunMatrixRef;
  snapshotRefs?: ReportArtifactSnapshotRefs;
  decision?: ReportArtifactDecision;
  agentOrigins?: ReportArtifactAgentOrigins;
  provenance: ReportArtifactProvenance;
  publish: ReportArtifactPublish;
  quality: ReportArtifactQuality;
}


export type MarketPhaseValue =
  | 'premarket'
  | 'intraday'
  | 'lunch_break'
  | 'closing_auction'
  | 'postmarket'
  | 'non_trading'
  | 'unknown';

export interface MarketPhaseSummary {
  market?: string | null;
  phase: MarketPhaseValue;
  marketLocalTime?: string | null;
  sessionDate?: string | null;
  effectiveDailyBarDate?: string | null;
  isTradingDay?: boolean | null;
  isMarketOpenNow?: boolean | null;
  isPartialBar?: boolean | null;
  minutesToOpen?: number | null;
  minutesToClose?: number | null;
  triggerSource?: string | null;
  analysisIntent?: string | null;
  warnings: string[];
}

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
  modelUsed?: string;  // 历史元数据快照，仅用于展示，不用于运行时模型选择
  marketPhaseSummary?: MarketPhaseSummary | null;
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
  | 'Very Bullish'
  | '매우 비관'
  | '비관'
  | '중립'
  | '낙관'
  | '매우 낙관';

export type DecisionAction = 'buy' | 'add' | 'hold' | 'reduce' | 'sell' | 'watch' | 'avoid' | 'alert';

/** Report summary section */
export interface ReportSummary {
  analysisSummary: string;
  operationAdvice: string;
  action?: DecisionAction | null;
  actionLabel?: string | null;
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
  code?: string;
  changePct?: number;
  source?: string;
  updatedAt?: string;
}

export interface SectorRankings {
  top?: SectorRankingItem[];
  bottom?: SectorRankingItem[];
}

export type MarketStructureStatus = 'ok' | 'partial' | 'unknown' | 'not_supported';
export type MarketStructureThemeSource = 'industry' | 'concept' | 'mixed' | 'unknown';
export type MarketStructureThemePhase = 'warming' | 'accelerating' | 'cooling' | 'unknown';
export type MarketStructureStockRole = 'leader' | 'follower' | 'edge' | 'unknown';

export interface MarketStructureSource {
  provider: string;
  dataset: string;
  status: string;
  message?: string | null;
}

export interface MarketStructureDataQuality {
  status: MarketStructureStatus;
  missingFields?: string[];
  sources?: MarketStructureSource[];
  errors?: string[];
}

export interface RankedThemeItem {
  name: string;
  changePct?: number | null;
  rank?: number | null;
  source?: MarketStructureThemeSource;
  code?: string | null;
  updatedAt?: string | null;
}

export interface MarketThemeItem extends RankedThemeItem {
  phase?: MarketStructureThemePhase;
  strengthScore?: number | null;
  reason?: string | null;
}

export interface ThemeBreadth {
  activeCount?: number;
  leadingIndustryCount?: number;
  leadingConceptCount?: number;
  laggingCount?: number;
}

export interface MarketThemeContext {
  schemaVersion: 'market-theme-v1';
  status: MarketStructureStatus;
  market: string;
  tradeDate?: string | null;
  activeThemes?: MarketThemeItem[];
  leadingIndustries?: RankedThemeItem[];
  leadingConcepts?: RankedThemeItem[];
  laggingThemes?: RankedThemeItem[];
  themeBreadth?: ThemeBreadth;
  dataQuality?: MarketStructureDataQuality;
}

export interface StockBoardPosition {
  name: string;
  type?: string | null;
  code?: string | null;
  rank?: number | null;
  changePct?: number | null;
  source?: MarketStructureThemeSource;
}

export interface PrimaryTheme {
  name: string;
  source?: MarketStructureThemeSource;
  phase?: MarketStructureThemePhase;
  rank?: number | null;
  changePct?: number | null;
}

export interface MarketStructureRiskTag {
  code: string;
  message: string;
}

export interface StockMarketPosition {
  schemaVersion: 'stock-market-position-v1';
  status: MarketStructureStatus;
  stockCode: string;
  stockName?: string | null;
  market: string;
  primaryTheme?: PrimaryTheme | null;
  relatedBoards?: StockBoardPosition[];
  stockRole?: MarketStructureStockRole;
  themePhase?: MarketStructureThemePhase;
  riskTags?: MarketStructureRiskTag[];
  missingFields?: string[];
}

export interface MarketStructureContext {
  schemaVersion: 'market-structure-v1';
  status: MarketStructureStatus;
  market: string;
  tradeDate?: string | null;
  marketThemeContext: MarketThemeContext;
  stockMarketPosition: StockMarketPosition;
}

export interface MarketReviewPayloadSection {
  key?: string;
  title: string;
  markdown: string;
}

export interface MarketReviewIndex {
  code: string;
  name: string;
  current?: number;
  change?: number;
  changePct?: number;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
  amount?: number;
  amplitude?: number;
}

export interface MarketReviewBreadth {
  upCount?: number;
  downCount?: number;
  flatCount?: number;
  limitUpCount?: number;
  limitDownCount?: number;
  totalAmount?: number;
  turnoverUnit?: string;
}

export interface MarketReviewPayload {
  version?: number;
  kind?: 'market_review' | string;
  region?: string;
  language?: ReportLanguage | string;
  title?: string;
  rootTitle?: string;
  generatedAt?: string;
  date?: string;
  marketScope?: string;
  marketLight?: Record<string, unknown>;
  breadth?: MarketReviewBreadth;
  indices?: MarketReviewIndex[];
  sectors?: SectorRankings;
  concepts?: SectorRankings;
  news?: Array<Record<string, unknown>>;
  sections?: MarketReviewPayloadSection[];
  markets?: Record<string, MarketReviewPayload>;
  markdownReport?: string;
}

export type AnalysisContextPackBlockStatus =
  | 'available'
  | 'missing'
  | 'not_supported'
  | 'fallback'
  | 'stale'
  | 'estimated'
  | 'partial'
  | 'fetch_failed';

export interface AnalysisContextPackOverviewSubject {
  code: string;
  stockName?: string | null;
  market?: string | null;
}

export interface AnalysisContextPackOverviewBlock {
  key: string;
  label: string;
  status: AnalysisContextPackBlockStatus;
  source?: string | null;
  warnings: string[];
  missingReasons: string[];
}

export interface AnalysisContextPackOverviewCounts {
  available: number;
  missing: number;
  notSupported: number;
  fallback: number;
  stale: number;
  estimated: number;
  partial: number;
  fetchFailed: number;
}

export interface AnalysisContextPackOverviewMetadata {
  triggerSource?: string | null;
  newsResultCount?: number | null;
}

export type AnalysisContextPackDataQualityLevel = 'good' | 'usable' | 'limited' | 'poor';

export interface AnalysisContextPackOverviewDataQuality {
  overallScore?: number | null;
  level?: AnalysisContextPackDataQualityLevel | null;
  blockScores: Record<string, number>;
  limitations: string[];
}

export interface AnalysisContextPackOverview {
  packVersion: string;
  createdAt?: string | null;
  subject: AnalysisContextPackOverviewSubject;
  blocks: AnalysisContextPackOverviewBlock[];
  counts: AnalysisContextPackOverviewCounts;
  dataQuality?: AnalysisContextPackOverviewDataQuality | null;
  warnings: string[];
  metadata: AnalysisContextPackOverviewMetadata;
}

/** Details section */
export interface ReportDetails {
  newsContent?: string;
  rawResult?: Record<string, unknown>;
  contextSnapshot?: Record<string, unknown> & { marketReviewPayload?: MarketReviewPayload };
  analysisContextPackOverview?: AnalysisContextPackOverview | null;
  financialReport?: Record<string, unknown>;
  dividendMetrics?: Record<string, unknown>;
  belongBoards?: RelatedBoard[];
  sectorRankings?: SectorRankings;
  conceptRankings?: SectorRankings;
  marketStructure?: MarketStructureContext | null;
}

/** Full analysis report */
export interface AnalysisReport {
  meta: ReportMeta;
  summary: ReportSummary;
  strategy?: ReportStrategy;
  details?: ReportDetails;
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
  analysisPhase?: AnalysisPhase;
}

export interface BatchTaskAcceptedItem {
  taskId: string;
  traceId?: string;
  stockCode: string;
  status: 'pending' | 'processing';
  message?: string;
  analysisPhase?: AnalysisPhase;
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
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancel_requested' | 'cancelled';
  progress?: number;
  result?: AnalysisResult;
  marketReviewReport?: string;
  marketReviewPayload?: MarketReviewPayload;
  region?: string;
  error?: string;
  stockName?: string;
  originalQuery?: string;
  selectionSource?: string;
  analysisPhase?: AnalysisPhase | null;
  skills?: string[];
}

/** Task details used by task list and SSE events */
export interface TaskInfo {
  taskId: string;
  traceId?: string;
  stockCode: string;
  stockName?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancel_requested' | 'cancelled';
  progress: number;
  message?: string;
  reportType: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  error?: string;
  originalQuery?: string;
  selectionSource?: string;
  analysisPhase?: AnalysisPhase;
  skills?: string[];
  region?: string;
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
  region?: string;
  trendPrediction?: string;
  analysisSummary?: string;
  sentimentScore?: number;
  operationAdvice?: string;
  action?: DecisionAction | null;
  actionLabel?: string | null;
  currentPrice?: number;
  changePct?: number;
  volumeRatio?: number;
  turnoverRate?: number;
  modelUsed?: string;  // 历史元数据快照，仅用于列表展示，不影响运行时调用与路由
  marketPhaseSummary?: MarketPhaseSummary | null;
  createdAt: string;
}

export type StockHistoryRange = 'all' | '30d' | '90d';

export interface StockHistoryFilters {
  range: StockHistoryRange;
  model: string;
  sort: 'desc' | 'asc';
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
  reportType?: ReportType;
  startDate?: string;
  endDate?: string;
}

/** History pagination parameters */
export interface HistoryPagination {
  page: number;
  limit: number;
}

// ============ Stock Bar Types ============

export interface StockBarItem {
  id: number;
  stockCode: string;
  stockName?: string;
  reportType?: string;
  sentimentScore?: number;
  operationAdvice?: string;
  action?: DecisionAction | null;
  actionLabel?: string | null;
  analysisCount: number;
  lastAnalysisTime?: string;
  modelUsed?: string;
  marketPhaseSummary?: MarketPhaseSummary | null;
}

export interface StockBarResponse {
  total: number;
  items: StockBarItem[];
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
  if (language === 'ko') {
    if (score <= 20) return '매우 비관';
    if (score <= 40) return '비관';
    if (score <= 60) return '중립';
    if (score <= 80) return '낙관';
    return '매우 낙관';
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
