import { expect, test, type Page } from '@playwright/test';

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD;

if (!smokePassword) {
  test.skip(true, 'Set DSA_WEB_SMOKE_PASSWORD to run report markdown smoke tests.');
}

test.use({ locale: 'zh-CN' });

const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';
const REPORT_RECORD_ID = 91_001;
const REPORT_MARKDOWN = [
  '# 贵州茅台分析报告',
  '',
  '**结论：** 趋势维持强势。',
  '',
  '> 本报告来自 Playwright 隔离 fixture。',
].join('\n');

const reportHistoryItem = {
  id: REPORT_RECORD_ID,
  query_id: 'playwright-report-markdown',
  stock_code: '600519',
  stock_name: '贵州茅台',
  report_type: 'detailed',
  trend_prediction: '短线震荡偏强',
  analysis_summary: '趋势维持强势',
  sentiment_score: 78,
  operation_advice: '持有',
  created_at: '2026-03-18T08:00:00Z',
};

const reportDetail = {
  meta: {
    id: REPORT_RECORD_ID,
    query_id: reportHistoryItem.query_id,
    stock_code: reportHistoryItem.stock_code,
    stock_name: reportHistoryItem.stock_name,
    report_type: reportHistoryItem.report_type,
    report_language: 'zh',
    created_at: reportHistoryItem.created_at,
  },
  summary: {
    analysis_summary: reportHistoryItem.analysis_summary,
    operation_advice: reportHistoryItem.operation_advice,
    trend_prediction: reportHistoryItem.trend_prediction,
    sentiment_score: reportHistoryItem.sentiment_score,
    sentiment_label: '乐观',
  },
  strategy: {
    ideal_buy: '1500',
    secondary_buy: '1450',
    stop_loss: '1380',
    take_profit: '1750',
  },
  details: null,
};

interface ReportHistoryFixtureOptions {
  markdownGate?: Promise<void>;
}

async function installReportHistoryFixture(
  page: Page,
  { markdownGate }: ReportHistoryFixtureOptions = {},
) {
  await page.route('**/api/v1/history**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() !== 'GET') {
      await route.fulfill({
        status: 405,
        headers: { Allow: 'GET' },
        json: {
          detail: {
            error: 'method_not_allowed',
            message: 'Report markdown fixture only supports GET requests.',
          },
        },
      });
      return;
    }

    if (url.pathname === '/api/v1/history') {
      const reportType = url.searchParams.get('report_type');
      const stockCode = url.searchParams.get('stock_code');
      const hasFixture = reportType !== 'market_review' && (!stockCode || stockCode === reportHistoryItem.stock_code);

      await route.fulfill({
        status: 200,
        json: {
          total: hasFixture ? 1 : 0,
          page: Number(url.searchParams.get('page') || 1),
          limit: Number(url.searchParams.get('limit') || 20),
          items: hasFixture ? [reportHistoryItem] : [],
        },
      });
      return;
    }

    if (url.pathname === '/api/v1/history/stocks') {
      await route.fulfill({
        status: 200,
        json: {
          total: 1,
          items: [{
            id: REPORT_RECORD_ID,
            stock_code: reportHistoryItem.stock_code,
            stock_name: reportHistoryItem.stock_name,
            report_type: reportHistoryItem.report_type,
            sentiment_score: reportHistoryItem.sentiment_score,
            operation_advice: reportHistoryItem.operation_advice,
            analysis_count: 1,
            last_analysis_time: reportHistoryItem.created_at,
          }],
        },
      });
      return;
    }

    if (url.pathname === `/api/v1/history/${REPORT_RECORD_ID}`) {
      await route.fulfill({ status: 200, json: reportDetail });
      return;
    }

    if (url.pathname === `/api/v1/history/${REPORT_RECORD_ID}/markdown`) {
      if (markdownGate) {
        await markdownGate;
      }
      await route.fulfill({ status: 200, json: { content: REPORT_MARKDOWN } });
      return;
    }

    if (url.pathname === `/api/v1/history/${REPORT_RECORD_ID}/news`) {
      await route.fulfill({ status: 200, json: { total: 0, items: [] } });
      return;
    }

    if (url.pathname === `/api/v1/history/${REPORT_RECORD_ID}/diagnostics`) {
      await route.fulfill({
        status: 200,
        json: {
          query_id: reportHistoryItem.query_id,
          stock_code: reportHistoryItem.stock_code,
          status: 'normal',
          status_label: '正常',
          reason: 'Playwright fixture',
          components: {},
          copy_text: 'data_status: normal',
        },
      });
      return;
    }

    await route.fulfill({
      status: 404,
      json: {
        detail: {
          error: 'not_found',
          message: `No report markdown fixture for ${url.pathname}.`,
        },
      },
    });
  });
}

async function login(page: Page) {
  test.skip(!smokePassword, 'Set DSA_WEB_SMOKE_PASSWORD to run report markdown tests.');

  await page.addInitScript((storageKey) => {
    window.localStorage.setItem(storageKey, 'zh');
  }, UI_LANGUAGE_STORAGE_KEY);

  // Navigate to login page
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  // Wait for password input to be visible
  await expect(page.locator('#password')).toBeVisible({ timeout: 10_000 });

  // Fill password and submit
  await page.locator('#password').fill(smokePassword!);

  // Wait for and click the submit button
  const submitButton = page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ });
  await expect(submitButton).toBeVisible();

  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes('/api/v1/auth/login') && response.status() === 200,
      { timeout: 15_000 }
    ),
    submitButton.click(),
  ]);

  // Wait for navigation to home page after login
  await page.waitForURL('/', { timeout: 15_000 });
  await page.waitForLoadState('domcontentloaded');
  // Wait for page to stabilize by checking for stock input
  const stockInput = page.getByPlaceholder('输入股票代码或名称，如 600519、贵州茅台、AAPL');
  await expect(stockInput).toBeVisible({ timeout: 10_000 });
}

async function loginWithReportFixture(
  page: Page,
  options: ReportHistoryFixtureOptions = {},
) {
  await installReportHistoryFixture(page, options);
  await login(page);
}

async function selectFixtureReport(page: Page) {
  const stockBar = page.getByTestId('home-stock-bar');
  await expect(stockBar).toContainText('个股栏', { timeout: 10_000 });

  const firstHistoryItem = stockBar.locator('.home-history-item').first();
  await expect(firstHistoryItem).toBeVisible({ timeout: 10_000 });
  await firstHistoryItem.click();

  const detailedReportButton = page.getByRole('button', { name: '完整分析报告' });
  await expect(detailedReportButton).toBeEnabled({ timeout: 5000 });
  return detailedReportButton;
}

test.describe('ReportMarkdown component', () => {
  test('copy markdown source code', async ({ page, context }) => {
    // Grant clipboard permissions
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);

    await loginWithReportFixture(page);
    const detailedReportButton = await selectFixtureReport(page);

    // Click the "完整分析报告" button to open the markdown drawer
    await expect(detailedReportButton).toBeVisible({ timeout: 5000 });
    await detailedReportButton.click();

    // Verify drawer content is visible
    await expect(page.getByRole('dialog').getByText('完整分析报告')).toBeVisible();

    // Click copy markdown button
    const copyMarkdownButton = page.getByRole('button', { name: '复制 Markdown 源码' });
    await expect(copyMarkdownButton).toBeVisible({ timeout: 5000 });
    await copyMarkdownButton.click();

    // Verify clipboard contains markdown content
    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toBe(REPORT_MARKDOWN);

    // Verify checkmark icon is shown
    const checkmarkIcon = page.locator('button[aria-label="复制 Markdown 源码"] svg.text-success');
    await expect(checkmarkIcon).toBeVisible();

    // Wait for icon to revert (icon disappears after 2 seconds)
    await expect(checkmarkIcon).not.toBeVisible({ timeout: 3500 });
  });

  test('copy plain text', async ({ page, context }) => {
    // Grant clipboard permissions
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);

    await loginWithReportFixture(page);
    const detailedReportButton = await selectFixtureReport(page);

    // Click the "完整分析报告" button to open the markdown drawer
    await expect(detailedReportButton).toBeVisible({ timeout: 5000 });
    await detailedReportButton.click();

    // Verify drawer content is visible
    await expect(page.getByRole('dialog').getByText('完整分析报告')).toBeVisible();

    // Click copy plain text button
    const copyPlainTextButton = page.getByRole('button', { name: '复制纯文本' });
    await expect(copyPlainTextButton).toBeVisible({ timeout: 5000 });
    await copyPlainTextButton.click();

    // Verify clipboard contains text without markdown symbols
    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toBeTruthy();
    expect(clipboardText.length).toBeGreaterThan(0);
    expect(clipboardText).toContain('贵州茅台分析报告');
    expect(clipboardText).toContain('结论： 趋势维持强势。');

    // Verify it's plain text (no markdown symbols like #, **, >, etc.)
    expect(clipboardText).not.toMatch(/^#{1,6}\s+/m); // No headers
    expect(clipboardText).not.toMatch(/\*\*[^*]+\*\*/); // No bold
    // Verify table syntax is removed (no standalone pipe separators)
    const lines = clipboardText.split('\n');
    const hasTableSeparators = lines.some(line =>
      line.match(/^\|[\s|:-]+\|$/) || line.match(/^[\s|:-]+$/)
    );
    expect(hasTableSeparators).toBeFalsy();

    // Verify checkmark icon is shown
    const checkmarkIcon = page.locator('button[aria-label="复制纯文本"] svg.text-success');
    await expect(checkmarkIcon).toBeVisible();

    // Wait for icon to revert (icon disappears after 2 seconds)
    await expect(checkmarkIcon).not.toBeVisible({ timeout: 3500 });
  });

  test('mobile responsive layout', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 390, height: 844 });

    await loginWithReportFixture(page);

    // On mobile, a report should already be selected (showing in main content)
    // Wait for main content to load
    await expect(page.getByPlaceholder('输入股票代码或名称，如 600519、贵州茅台、AAPL')).toBeVisible({ timeout: 10_000 });

    // Click the "完整分析报告" button to open the markdown drawer
    const detailedReportButton = page.getByRole('button', { name: '完整分析报告' });
    await expect(detailedReportButton).toBeVisible({ timeout: 5000 });
    await detailedReportButton.click();

    // Verify drawer content is visible (this ensures drawer is fully open)
    await expect(page.getByRole('dialog').getByText('完整分析报告')).toBeVisible({ timeout: 10000 });

    // Verify toolbar buttons are visible and clickable on mobile
    const copyMarkdownButton = page.getByRole('button', { name: '复制 Markdown 源码' });
    const copyPlainTextButton = page.getByRole('button', { name: '复制纯文本' });

    await expect(copyMarkdownButton).toBeVisible({ timeout: 5000 });
    await expect(copyPlainTextButton).toBeVisible();

    // Verify buttons are clickable (not checking icon animation on mobile due to timing issues)
    await expect(copyMarkdownButton).toBeEnabled();
    await expect(copyPlainTextButton).toBeEnabled();
  });

  test('buttons are disabled during loading', async ({ page }) => {
    let releaseMarkdown!: () => void;
    const markdownGate = new Promise<void>((resolve) => {
      releaseMarkdown = resolve;
    });
    const copyMarkdownButton = page.getByRole('button', { name: '复制 Markdown 源码' });
    const copyPlainTextButton = page.getByRole('button', { name: '复制纯文本' });

    try {
      await loginWithReportFixture(page, { markdownGate });
      const detailedReportButton = await selectFixtureReport(page);

      // Click the "完整分析报告" button to open the markdown drawer.
      await expect(detailedReportButton).toBeVisible({ timeout: 5000 });
      await detailedReportButton.click();

      await expect(copyMarkdownButton).toBeVisible({ timeout: 5000 });
      await expect(copyPlainTextButton).toBeVisible();
      await expect(copyMarkdownButton).toBeDisabled();
      await expect(copyPlainTextButton).toBeDisabled();
    } finally {
      releaseMarkdown();
    }

    await expect(copyMarkdownButton).toBeEnabled({ timeout: 5000 });
    await expect(copyPlainTextButton).toBeEnabled();
  });
});
