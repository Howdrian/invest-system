import { Link } from 'react-router-dom';
import type { ReportReaderFocusList } from '../../types/analysis';

/** Presentation only: priority, scope and copy come from the shared Reader. */
export function ResearchHighlights({ value }: { value?: ReportReaderFocusList }) {
  if (!value?.highlights?.length) return null;
  return <div className="research-highlights" aria-label="三地投资要点">
    {value.highlights.map((row) => <a key={row.market} href="#report-focus">
      <span>{row.market}</span><p>{row.summary}</p>
    </a>)}
  </div>;
}

export function ResearchFocusList({ value, sourceUrl }: {
  value?: ReportReaderFocusList; sourceUrl: (value?: string) => string | null;
}) {
  if (!value) return null;
  const number = (v?: number | null, unit = '%') => v == null || !Number.isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}${unit}`;
  return <section id="report-focus" aria-labelledby="report-focus-title" className="research-focus scroll-mt-20 border-b border-border/70 pb-9">
    <p className="text-xs font-medium tracking-widest text-info">投资观点 · 先看取舍，再读依据</p>
    <h2 id="report-focus-title" className="mt-1 text-2xl font-semibold text-foreground">本期关注清单</h2>
    <p className="mt-2 text-sm leading-6 text-secondary-text">研究评级与入场节奏分别阅读；以下是研究建议，不是你的自选或持仓清单。</p>
    <details className="research-reading-note">
      <summary>研究范围与时间</summary>
      <p>{value.note}</p>
      {value.researchWindow?.displayLines?.map((line) => <p key={line}>{line}</p>)}
      {!value.researchWindow?.displayLines?.length && value.researchWindow?.label && <p>{value.researchWindow.label} · {value.researchWindow.lookbackStart} 至 {value.researchWindow.outlookEnd}</p>}
      <p>{value.sectorCoverage}</p>
    </details>
    <h3 className="mt-7 text-lg font-semibold text-foreground">行业选择</h3>
    <div className="research-sector-decisions">
      {value.sectors.map((row) => <details key={`${row.market}-${row.priority}-${row.targets.join('-')}`}>
        <summary><span className="research-market-label">{row.market}</span>
          <span className="research-decision-title">{row.targets.join('、')}</span>
          <span className="research-rating">{row.priority}</span>
          <span className="research-teaser">{row.lead || row.basis}</span>
          <span className="research-expand">展开理由与条件 ＋</span>
        </summary>
        <div className="research-expanded"><p>{row.basis}</p>
          {row.watchFor && <p><b>参与节奏与改判条件：</b>{row.watchFor}</p>}
        </div>
      </details>)}
    </div>
    <details className="research-reading-note mt-5">
      <summary>行业相对表现 · 图表与来源</summary>
      {value.sectorPerformance?.map((market) => {
        const comparable = market.rows.filter((r) => r.relative20dPp != null && Number.isFinite(r.relative20dPp));
        const scale = Math.max(1, ...comparable.map((r) => Math.abs(r.relative20dPp!)));
        return <article key={market.market} className="mt-5 border-b border-border/50 pb-5">
          <h4 className="text-lg font-semibold text-foreground">{market.market} · 行业动态</h4>
          <p className="mt-1 text-xs text-secondary-text">行情截至 {market.asOf} · 比较基准 {market.benchmark}</p>
          <p className="mt-2 text-sm leading-6 text-secondary-text">{market.scope}</p>
          <p className="mt-3 text-sm text-secondary-text">近20日相对居前：{comparable.slice(0, 3).map((r) => `${r.name}（${number(r.relative20dPp, '个百分点')}）`).join('、') || '暂无同日期基准比较'}</p>
          <div className="research-bars" aria-label={`${market.market}20日相对收益`}>
            {comparable.map((row) => <div className="research-bar-row" key={row.code}>
              <span>{row.name}</span><span className="research-bar-track" aria-hidden="true">
                <i className={row.relative20dPp! >= 0 ? 'positive' : 'negative'} style={{ width: `${Math.abs(row.relative20dPp!) / scale * 50}%`, left: row.relative20dPp! >= 0 ? '50%' : `${50 - Math.abs(row.relative20dPp!) / scale * 50}%` }} />
              </span><span>{number(row.relative20dPp, 'pp')}</span>
            </div>)}
          </div>
          <details className="mt-3"><summary className="cursor-pointer text-sm text-info">展开 {market.rows.length} 个行业/主题的阶段表现与来源</summary>
            <div className="mt-3 overflow-x-auto"><table className="report-sector-table w-full text-right text-sm tabular-nums">
              <thead className="text-secondary-text"><tr>{['行业/主题', '1日', '5日', '20日', '60日', '120日', '较基准20日'].map((title, i) => <th key={title} className={`p-2 font-medium ${i === 0 ? 'text-left' : ''}`}>{title}</th>)}</tr></thead>
              <tbody>{market.rows.map((row) => <tr key={row.code} className="border-t border-border/40">
                <td className="p-2 text-left"><a href={sourceUrl(row.sourceUrl) || undefined} target="_blank" rel="noreferrer" className="text-info hover:underline">{row.name}</a><div className="text-xs text-secondary-text">{row.code} · {row.asOf}</div></td>
                {[row.return1dPct, row.return5dPct, row.return20dPct, row.return60dPct, row.return120dPct].map((v, i) => <td key={i} className="p-2">{number(v)}</td>)}
                <td className="p-2">{number(row.relative20dPp, 'pp')}</td>
              </tr>)}</tbody>
            </table></div>
          </details>
          <p className="mt-2 text-xs text-secondary-text">均为交易日窗口。pp为百分点差；相对居前不等于绝对上涨。行情比较不是投资评级。</p>
        </article>;
      })}
    </details>
    <h3 className="mt-8 text-lg font-semibold text-foreground">公司研究与参与节奏</h3>
    <div className="research-stock-grid">
      {value.stocks.map((row) => <article key={row.symbol} id={`research-stock-${row.symbol}`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h4 className="text-xl font-semibold text-foreground">{row.name} <span className="text-xs font-normal text-secondary-text">{row.symbol} · {row.market}</span></h4>
          <span className="research-rating">{row.priority}</span>
        </div>
        <p className="mt-3 leading-7 text-foreground">{row.lead || row.reason}</p>
        <p className="mt-2 flex flex-wrap gap-3 text-xs text-secondary-text"><span>{row.listOrigin}</span>{row.horizon && <span>研究周期：{row.horizon}</span>}</p>
        <details className="research-company-detail mt-4">
          <summary>综合研究 · 理由、反证与入场条件</summary>
          <div className="research-expanded">
            {!row.research?.some((claim) => claim.text === row.reason) && <p><b>当前综合判断：</b>{row.reason}</p>}
            {row.watchFor && <p><b>参与节奏与改判条件：</b>{row.watchFor}</p>}
            {row.research?.map((claim, i) => <section className="mt-5 border-t border-border/50 pt-4" key={`${claim.department}-${i}`}>
              <h5 className="font-semibold text-foreground">{claim.department} <span className="font-normal text-xs text-secondary-text">{claim.label}</span></h5>
              <p className="mt-2">{claim.text}</p>
              {claim.evidenceSamples.length > 0 && <ul className="mt-2 space-y-1 text-xs text-secondary-text">{claim.evidenceSamples.map((sample, j) => <li key={sample.id || j}>
                {sourceUrl(sample.sourceUrl) ? <a href={sourceUrl(sample.sourceUrl)!} target="_blank" rel="noreferrer" className="text-info">{sample.sourceName || '来源'}</a> : <span>{sample.sourceName || '同轮研究证据'}</span>}
                {sample.asOf && ` · ${sample.asOf}`}
                {sample.label && <p className="leading-6">{sample.label}</p>}
              </li>)}</ul>}
            </section>)}
            {!row.research?.length && <a className="text-info" href="#report-departments">查看完整部门依据 →</a>}
          </div>
        </details>
        {row.historyRecordId && <div className="mt-4 text-xs leading-5 text-secondary-text">
          <Link className="text-info hover:underline" to={`/reports/history:${row.historyRecordId}`}>原 DSA 短线分析 →</Link>
          <p>独立时点与策略，保留原文；不同于上方的 CIO 综合评级。</p>
        </div>}
      </article>)}
    </div>
    <a className="mt-5 inline-block text-sm text-info" href="#report-departments">查看完整部门研究 →</a>
  </section>;
}
