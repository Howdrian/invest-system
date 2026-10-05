from src.research_core import AtomicClaim, ClaimStatus, ClaimType, evidence_pool_from_dicts, validate_claim, validate_claim_dicts


def test_cn_region_alias_accepts_existing_market_scope_and_not_foreign_company():
    rows = [{"id": "cn", "domain": "price", "subject": "market", "fact_type": "derived_fact",
             "as_of": "2026-09-07", "value": "up_count=2831", "measurements": {"up_count": 2831}},
            {"id": "foreign", "domain": "price", "subject": "AAPL", "fact_type": "derived_fact",
             "as_of": "2026-09-07", "value": "price=100"}]
    result = validate_claim_dicts([{"claim": "A股上涨2831家，选择性参与。", "subject": "market_cn",
                                   "domain": "price", "claimType": "recommendation", "evidence_ids": ["cn", "foreign"]}],
                                 rows, reference_date="2026-09-07")[0]
    assert result.status != ClaimStatus.REJECTED
    assert result.accepted_evidence_ids == ("cn",)


def test_regional_macro_opinion_can_use_shared_fred_facts():
    rows = [{"id": "oil", "domain": "macro", "subject": "DCOILWTICO", "metric": "DCOILWTICO",
             "fact_type": "verified_fact", "source_url": "https://fred.example/oil",
             "as_of": "2026-09-01", "value": "WTI=91.48"}]
    for subject in ("market_cn", "market_hk", "market_us", "market"):
        result = validate_claim_dicts([{"claim": "油价上涨，主观看好上游油气。", "subject": subject,
                                       "domain": "macro", "claimType": "recommendation", "evidence_ids": ["oil"]}],
                                     rows, reference_date="2026-09-07")[0]
        assert result.status != ClaimStatus.REJECTED


def test_monthly_and_quarterly_fred_period_start_dates_allow_release_lag():
    for metric, observed in (("CPIAUCSL", "2026-07-01"), ("GDP", "2026-04-01")):
        result = validate_claim_dicts([{"claim": "所给最近一期数据作为研究背景。", "subject": "macro",
                                       "domain": "macro", "evidence_ids": [metric]}],
            [{"id": metric, "metric": metric, "subject": metric, "domain": "macro",
              "as_of": observed, "source_url": "https://fred.example/series", "fact_type": "verified_fact"}],
            reference_date="2026-09-07")[0]
        assert result.status != ClaimStatus.REJECTED
    stale = validate_claim_dicts([{"claim": "当前通胀背景", "evidence_ids": ["old"]}],
        [{"id": "old", "domain": "macro", "metric": "CPIAUCSL", "as_of": "2025-01-01", "fact_type": "derived_fact"}],
        reference_date="2026-09-07")[0]
    assert stale.status == ClaimStatus.REJECTED


def test_denying_a_portfolio_benefit_is_not_claiming_actual_position_outcomes():
    result = _validate("样本上涨不能证明替换后能够降低真实组合风险。", [{
        "id": "sample", "fact_type": "derived_fact", "domain": "price", "subject": "market",
        "value": "sample return=10%",
    }])
    assert result.status != ClaimStatus.REJECTED


def test_no_positions_statement_is_not_a_portfolio_outcome():
    result = _validate("本轮未覆盖真实组合，不计算行业权重、集中度、实际盈亏或对冲效果。", [{
        "id": "scope", "fact_type": "derived_fact", "domain": "portfolio", "subject": "portfolio",
        "value": "No positions connected",
    }])
    assert result.status != ClaimStatus.REJECTED


def test_research_inference_can_cross_domains_but_factual_metrics_cannot():
    facts = [{"id": "oil", "domain": "macro", "subject": "DCOILWTICO", "metric": "DCOILWTICO",
              "fact_type": "verified_fact", "source_url": "https://fred.example/oil", "value": "WTI=91.48"}]
    inference = {"claim": "油价上涨有利于上游销售收入，主观看好上游油气。", "domain": "fundamentals",
                 "subject": "market_cn", "claimType": "recommendation", "evidence_ids": ["oil"]}
    result = validate_claim_dicts([inference], facts)[0]
    assert result.status == ClaimStatus.HYPOTHESIS
    assert result.accepted_evidence_ids == ("oil",)
    factual = {**inference, "claim": "上游净利润增长30%。", "claimType": "fact"}
    assert validate_claim_dicts([factual], facts)[0].status == ClaimStatus.REJECTED


def test_official_commodity_series_is_price_evidence_despite_macro_routing():
    result = validate_claim_dicts([{"claim": "WTI为91.48美元/桶。", "subject": "market", "domain": "price",
                                   "claimType": "fact", "evidence_ids": ["oil"]}],
        [{"id": "oil", "provider": "FRED", "domain": "macro", "subject": "DCOILWTICO", "metric": "DCOILWTICO",
          "value": "DCOILWTICO=91.48", "source_url": "https://fred.example/oil", "fact_type": "verified_fact"}])[0]
    assert result.status != ClaimStatus.REJECTED


def test_volume_caveat_and_future_trigger_are_not_assertions_of_expansion():
    rows = [{"id": "price", "domain": "price", "subject": "600519", "fact_type": "derived_fact",
             "metric": "daily_data", "value": "volume_vs_avg20=0.12", "measurements": {"volume_vs_avg20": 0.12}}]
    for text in ("修复交易值得参与，但当前成交量不能证明修复得到放量支持。",
                 "趋势最强，但当前未完成日线不能证明全天封板、成交可得性或放量质量。",
                 "当前价格修复。后续若放量突破，再提高评级。",
                 "成交量为20日均量0.12倍，尚非放量下跌。",
                 "最强反证是未出现放量下跌。"):
        result = _validate(text, rows)
        assert result.status != ClaimStatus.REJECTED
        assert "volume_expansion_contradicted_by_evidence" not in result.reasons


def test_combination_of_price_and_business_is_not_a_real_portfolio():
    result = _validate("当前价格与经营改善的组合不足以支持买入。", [{
        "id": "financial", "domain": "fundamentals", "fact_type": "derived_fact", "value": "PE=20.1",
    }])
    assert result.status != ClaimStatus.REJECTED
    assert 'portfolio_outcome_requires_actual_positions' not in result.reasons


def test_parallel_index_changes_bind_numbers_to_the_correct_index():
    rows = [{"id": "indices", "subject": "market", "domain": "price", "fact_type": "derived_fact",
             "measurements": {"index_sz399006_change_pct": -1.146, "index_sh000688_change_pct": -1.519}}]
    correct = _validate("创业板和科创50分别下跌1.146%和1.519%。", rows)
    assert correct.status != ClaimStatus.REJECTED
    wrong = _validate("创业板和科创50分别下跌9.146%和1.519%。", rows)
    assert wrong.status == ClaimStatus.REJECTED


def test_company_thesis_can_cite_its_financials_and_price_without_cross_subject_leak():
    rows = [{"id": "price", "subject": "600519", "domain": "price", "fact_type": "derived_fact", "value": "price=100"},
            {"id": "foreign", "subject": "AAPL", "domain": "price", "fact_type": "derived_fact", "value": "price=200"}]
    result = validate_claim_dicts([{"claim": "结合该公司价格与盈利作估值判断。", "subject": "600519",
                                   "domain": "fundamentals", "claimType": "interpretation", "evidence_ids": ["price", "foreign"]}], rows)[0]
    assert result.status != ClaimStatus.REJECTED
    assert result.accepted_evidence_ids == ('price',)


def test_shanghai_composite_alias_does_not_capture_sse50():
    from src.research_core.semantic_gate import _numeric_assertions
    assert _numeric_assertions("上证50下跌0.10%。") == [("index_sh000016_change_pct", -0.1, "exact")]
    assert _numeric_assertions("上证上涨0.20%。") == [("index_sh000001_change_pct", 0.2, "exact")]
    assert _numeric_assertions("上证和上证50分别下跌0.20%和0.10%。") == [
        ("index_sh000001_change_pct", -0.2, "exact"), ("index_sh000016_change_pct", -0.1, "exact"),
    ]


def test_financial_abbreviations_are_not_hallucinated_stock_tickers():
    from src.research_core.semantic_gate import _extract_security_symbols
    assert _extract_security_symbols("AAPL的OCF、FCF、EPS、ROIC和PE(TTM)须按GAAP及报告期区分。") == {"AAPL"}
    # Explicit security identity remains strict even when a ticker also has
    # a common accounting meaning.
    result = validate_claim_dicts([{"claim": "FCF价格上涨。", "subject": "FCF", "domain": "price", "evidence_ids": ["a"]}],
        [{"id": "a", "subject": "AAPL", "domain": "price", "fact_type": "derived_fact", "value": "price=100"}])[0]
    assert result.status == ClaimStatus.REJECTED


def test_quarterly_profit_is_compared_to_quarterly_not_half_year_growth():
    rows = [{"id": "financial", "subject": "600519", "domain": "fundamentals", "fact_type": "derived_fact",
             "measurements": {"net_profit_yoy_pct": 50}, "history": [
                 {"report_date": "2026-06-30", "net_profit_parent": 30},
                 {"report_date": "2026-03-31", "net_profit_parent": 10},
                 {"report_date": "2025-06-30", "net_profit_parent": 20},
                 {"report_date": "2025-03-31", "net_profit_parent": 5},
             ]}]
    assert _validate("拆算第二季度归母净利润同比增长33.33%。", rows).status != ClaimStatus.REJECTED
    assert _validate("拆算第二季度收入同比增长10%；归母净利润同比增长33.33%。", rows).status != ClaimStatus.REJECTED
    assert _validate("拆算第二季度归母净利润同比增长99%。", rows).status == ClaimStatus.REJECTED


def test_parallel_revenue_profit_percentages_are_not_mapped_to_one_metric():
    from src.research_core.semantic_gate import _numeric_assertions
    assert _numeric_assertions("第二季度收入、归母净利润同比增长56.91%、36.46%。") == []


def _validate(text, rows, *, claim_type=ClaimType.INTERPRETATION):
    pool = evidence_pool_from_dicts(rows)
    return validate_claim(AtomicClaim(
        id="claim:1",
        text=text,
        claim_type=claim_type,
        evidence_ids=tuple(row["id"] for row in rows),
    ), pool.facts)


def test_sahm_rule_needs_history_not_one_unemployment_point():
    result = _validate("5月失业率4.3%，萨姆规则已经触发。", [{
        "id": "fred:UNRATE:2026-05-01", "fact_type": "verified_fact", "provider": "FRED",
        "source_url": "https://fred.example/UNRATE", "value": "UNRATE=4.3",
    }], claim_type=ClaimType.FACT)
    assert result.status == ClaimStatus.REJECTED
    assert "sahm_rule_requires_official_or_historical_calculation" in result.reasons


def test_yield_curve_needs_comparable_treasury_maturities():
    result = _validate("10Y-2Y收益率曲线已经倒挂。", [{
        "id": "fred:DGS10:2026-06-29", "fact_type": "verified_fact", "provider": "FRED",
        "source_url": "https://fred.example/DGS10", "value": "DGS10=4.38",
    }], claim_type=ClaimType.FACT)
    assert result.status == ClaimStatus.REJECTED


def test_positive_official_spread_rejects_active_inversion_claim():
    result = validate_claim_dicts(
        [{
            "claim": "美国收益率曲线维持倒挂状态。",
            "claimType": "fact",
            "domain": "macro",
            "evidence_ids": ["fred:T10Y2Y"],
        }],
        [{
            "id": "fred:T10Y2Y",
            "fact_type": "verified_fact",
            "domain": "macro",
            "subject": "T10Y2Y",
            "metric": "T10Y2Y",
            "value": "T10Y2Y=0.36",
            "source_url": "https://fred.example/T10Y2Y",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "yield_curve_inversion_contradicted_by_spread" in result.reasons


def test_yield_curve_state_interpretation_without_comparable_maturity_is_rejected():
    result = validate_claim_dicts(
        [{
            "claim": "美国收益率曲线维持倒挂状态，仍需结合最新2年期利率确认。",
            "claimType": "interpretation",
            "domain": "macro",
            "evidence_ids": ["fred:DGS10"],
        }],
        [{
            "id": "fred:DGS10",
            "fact_type": "verified_fact",
            "domain": "macro",
            "subject": "DGS10",
            "metric": "DGS10",
            "value": "DGS10=4.56",
            "source_url": "https://fred.example/DGS10",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "yield_curve_requires_comparable_treasury_maturities" in result.reasons


def test_discovery_lawsuit_stays_hypothesis():
    result = _validate("苹果起诉OpenAI可能使双方合作破裂。", [{
        "id": "tavily:reuters:apple-openai", "fact_type": "discovery", "provider": "Tavily",
        "source_url": "https://reuters.example/story", "value": "Apple sues OpenAI",
    }])
    assert result.status == ClaimStatus.HYPOTHESIS
    assert result.safe_text.startswith("苹果起诉OpenAI可能")


def test_unrelated_form4_does_not_verify_lawsuit():
    result = _validate("苹果起诉OpenAI并申请临时禁令。", [{
        "id": "sec:AAPL:form4", "fact_type": "verified_fact", "provider": "SEC_EDGAR",
        "source_url": "https://sec.example/form4.xml", "form": "4", "subject": "AAPL",
        "value": "4 2026-06-17 form4.xml",
    }], claim_type=ClaimType.FACT)
    assert result.status == ClaimStatus.REJECTED
    assert "lawsuit_requires_court_ir_or_relevant_filing" in result.reasons


def test_fund_redemption_is_conditional_without_flow_evidence():
    result = _validate("权重股下跌将通过公募赎回触发流动性负反馈。", [{
        "id": "subject:market:main_indices", "fact_type": "derived_fact", "provider": "market",
        "raw_path": "run/indices.json", "value": "创业板指=-4.37%",
    }])
    assert result.status == ClaimStatus.HYPOTHESIS
    assert result.safe_text == "权重股下跌将通过公募赎回触发流动性负反馈。"


def test_sec_companyfact_needs_period_metadata_for_quarter_claim():
    result = _validate("苹果本季度收入为2549.4亿美元。", [{
        "id": "sec_companyfacts:AAPL:Revenue:2026-03-28", "fact_type": "verified_fact", "provider": "SEC_EDGAR",
        "source_url": "https://sec.example/companyfacts.json", "subject": "AAPL", "value": "Revenue=254940000000",
    }], claim_type=ClaimType.FACT)
    assert result.status == ClaimStatus.REJECTED
    assert "quarter_claim_requires_period_metadata" in result.reasons


def test_provider_run_is_not_substantive_evidence():
    result = _validate("市场已经进入系统性风险收缩。", [{
        "id": "provider_run:market_stats", "fact_type": "derived_fact", "provider": "DataFetcherManager",
        "raw_path": "provider_runs.jsonl", "value": "returned 6 records",
    }])
    assert result.status == ClaimStatus.HYPOTHESIS


def test_systemic_deleveraging_needs_breadth_and_independent_stress_evidence():
    result = _validate("A股已经进入系统性去杠杆初期传导。", [{
        "id": "subject:market:main_indices",
        "fact_type": "derived_fact",
        "provider": "DataFetcherManager",
        "domain": "price",
        "subject": "market",
        "metric": "main_indices",
        "raw_path": "subject_evidence.jsonl",
        "value": "上证指数=-1.85% 深证成指=-1.97%",
    }])

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "systemic_market_stress_requires_breadth_and_liquidity_evidence" in result.reasons
    assert result.safe_text == "A股已经进入系统性去杠杆初期传导。"


def test_claim_for_different_us_symbol_is_rejected_instead_of_rewritten_to_sample():
    result = _validate("MSFT价格上涨并进入多头趋势。", [{
        "id": "subject:AAPL:daily_data",
        "fact_type": "derived_fact",
        "provider": "YFinanceFetcher",
        "domain": "price",
        "subject": "AAPL",
        "metric": "daily_data",
        "raw_path": "subject_evidence.jsonl",
        "value": "AAPL latest_close=333.26 SMA5=321.65 SMA20=303.63",
    }])

    assert result.status == ClaimStatus.REJECTED
    assert "claim_subject_not_supported_by_cited_evidence" in result.reasons
    assert result.safe_text == ""


def test_security_symbols_normalize_exchange_suffixes_before_comparison():
    result = validate_claim_dicts(
        [{
            "claim": "600519.SH价格上涨。",
            "claimType": "fact",
            "subject": "600519.SH",
            "domain": "price",
            "evidence_ids": ["subject:600519:quote"],
        }],
        [{
            "id": "subject:600519:quote",
            "fact_type": "derived_fact",
            "provider": "TencentFetcher",
            "domain": "price",
            "subject": "600519",
            "metric": "realtime_quote",
            "raw_path": "subject_evidence.jsonl",
            "value": "price=1258.99 change_pct=0.63",
        }],
    )[0]

    assert result.status != ClaimStatus.REJECTED


def test_macro_and_market_acronyms_are_not_inferred_as_security_symbols():
    from src.research_core.semantic_gate import _extract_security_symbols

    assert _extract_security_symbols("HK/US CPI、PMI 与 ECB 政策均需复核。") == set()


def test_systemic_deep_decline_is_not_inferred_from_indices_alone():
    result = _validate("A股主要指数呈现系统性深调。", [{
        "id": "subject:market:main_indices",
        "fact_type": "derived_fact",
        "provider": "DataFetcherManager",
        "domain": "price",
        "subject": "market",
        "metric": "main_indices",
        "raw_path": "subject_evidence.jsonl",
        "value": "上证指数=-1.85% 科创50=-4.02%",
    }])

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "systemic_market_stress_requires_breadth_and_liquidity_evidence" in result.reasons
    assert result.safe_text == "A股主要指数呈现系统性深调。"


def test_systemic_weakness_is_not_inferred_from_indices_alone():
    result = _validate("A股市场已经系统性走弱。", [{
        "id": "subject:market:main_indices",
        "fact_type": "derived_fact",
        "provider": "DataFetcherManager",
        "domain": "price",
        "subject": "market",
        "metric": "main_indices",
        "raw_path": "subject_evidence.jsonl",
        "value": "上证指数=-1.85% 科创50=-4.02%",
    }])

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "systemic_market_stress_requires_breadth_and_liquidity_evidence" in result.reasons
    assert result.safe_text == "A股市场已经系统性走弱。"


def test_range_position_is_rendered_as_location_not_crash_probability():
    result = _validate(
        "AAPL在100%分位数极易触发获利回吐。",
        [{
            "id": "subject:AAPL:price_history_comparison",
            "fact_type": "derived_fact",
            "provider": "AlphaVantageFetcher",
            "domain": "price",
            "subject": "AAPL",
            "metric": "price_history_comparison",
            "raw_path": "subject_evidence.jsonl",
            "value": "return_20d_pct=11.37 range_position_pct=100",
        }],
        claim_type=ClaimType.SCENARIO,
    )

    assert "range_position_is_not_probability_or_valuation_percentile" in result.reasons
    assert result.safe_text == ""


def test_systemic_base_case_is_not_exempted_by_later_conditional_clause():
    result = _validate(
        "系统性去杠杆已经开始，一旦恐慌蔓延，权重股将无差别补跌。",
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "provider": "DataFetcherManager",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "raw_path": "subject_evidence.jsonl",
            "value": "上证指数=-1.85% 深证成指=-1.97%",
        }],
        claim_type=ClaimType.INTERPRETATION,
    )

    assert "systemic_market_stress_requires_breadth_and_liquidity_evidence" in result.reasons
    assert result.safe_text == "系统性去杠杆已经开始，一旦恐慌蔓延，权重股将无差别补跌。"


def test_explicit_uncertainty_about_systemic_stress_is_not_rewritten_as_a_systemic_claim():
    result = _validate(
        "市场宽度缺失，无法推导全市场未发生系统性流动性收缩。",
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "provider": "DataFetcherManager",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "raw_path": "subject_evidence.jsonl",
            "value": "上证指数=-1.85% 深证成指=-1.97%",
        }],
        claim_type=ClaimType.INTERPRETATION,
    )

    assert "systemic_market_stress_requires_breadth_and_liquidity_evidence" not in result.reasons
    assert result.safe_text != (
        "A股风险偏好明显收缩；现有指数证据支持市场转弱，"
        "但尚不足以确认系统性去杠杆，需结合市场宽度、资金流或信用压力复核。"
    )


def test_supported_price_fact_passes():
    result = _validate("创业板指下跌4.37%。", [{
        "id": "subject:market:main_indices", "fact_type": "derived_fact", "provider": "DataFetcherManager",
        "raw_path": "subject_provider_runs.jsonl", "value": "创业板指=-4.37%",
    }], claim_type=ClaimType.FACT)
    assert result.status == ClaimStatus.SUPPORTED


def test_macro_claim_cannot_be_supported_by_price_evidence():
    result = validate_claim_dicts(
        [{
            "claim": "通胀和利率环境已经明显转松。",
            "claimType": "interpretation",
            "evidence_ids": ["ev:price"],
        }],
        [{
            "id": "ev:price",
            "fact_type": "derived_fact",
            "domain": "price",
            "value": "AAPL price=220",
            "raw_path": "raw.json",
        }],
    )[0]
    assert result.status == ClaimStatus.HYPOTHESIS
    assert "claim_domain_not_supported_by_cited_evidence" in result.reasons


def test_explicit_scenario_keeps_original_wording_and_structured_status():
    result = validate_claim_dicts(
        [{
            "claim": "市场宽度继续恶化会转为普跌。",
            "claimType": "scenario",
            "evidence_ids": ["ev:breadth"],
        }],
        [{
            "id": "ev:breadth",
            "fact_type": "derived_fact",
            "domain": "price",
            "value": "market breadth down_count=3000",
            "raw_path": "raw.json",
        }],
    )[0]
    assert result.status == ClaimStatus.HYPOTHESIS
    assert result.safe_text == "市场宽度继续恶化会转为普跌。"


def test_macro_aggregate_subject_accepts_concrete_fred_series():
    result = validate_claim_dicts(
        [{
            "claim": "美国十年期国债收益率为4.38%。",
            "claimType": "fact",
            "subject": "macro",
            "domain": "macro",
            "metric": "DGS10",
            "evidence_ids": ["fred:DGS10:2026-06-29"],
        }],
        [{
            "id": "fred:DGS10:2026-06-29",
            "fact_type": "verified_fact",
            "domain": "macro",
            "subject": "DGS10",
            "metric": "DGS10",
            "value": "DGS10=4.38",
            "source_url": "https://fred.example/DGS10",
        }],
    )[0]
    assert result.status == ClaimStatus.SUPPORTED


def test_concrete_stock_subject_remains_strict():
    result = validate_claim_dicts(
        [{
            "claim": "AAPL价格上涨。",
            "claimType": "fact",
            "subject": "AAPL",
            "domain": "price",
            "evidence_ids": ["ev:600519"],
        }],
        [{
            "id": "ev:600519",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "600519",
            "value": "600519 price=1400",
            "raw_path": "raw.json",
        }],
    )[0]
    assert result.status == ClaimStatus.REJECTED


def test_geopolitical_causality_is_hypothesis_with_macro_price_only():
    result = validate_claim_dicts(
        [{
            "claim": "地缘冲突推动WTI原油升至78.94美元，并压制A股流动性。",
            "claimType": "interpretation",
            "subject": "macro",
            "domain": "macro",
            "metric": "DCOILWTICO",
            "evidence_ids": ["fred:DCOILWTICO:2026-06-22"],
        }],
        [{
            "id": "fred:DCOILWTICO:2026-06-22",
            "fact_type": "verified_fact",
            "domain": "macro",
            "subject": "DCOILWTICO",
            "metric": "DCOILWTICO",
            "value": "DCOILWTICO=78.94",
            "source_url": "https://fred.example/DCOILWTICO",
        }],
    )[0]
    assert result.status == ClaimStatus.HYPOTHESIS
    assert "geopolitical_event_not_officially_verified" in result.reasons
    assert result.safe_text == "地缘冲突推动WTI原油升至78.94美元，并压制A股流动性。"


def test_market_stat_fact_is_rejected_when_agent_mutates_breadth_and_turnover():
    result = validate_claim_dicts(
        [{
            "claim": "A股上涨3014家，两市成交额7344亿元。",
            "claimType": "fact",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["subject:market:market_stats"],
        }],
        [{
            "id": "subject:market:market_stats",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "metric": "market_stats",
            "measurements": {"up_count": 4211, "total_amount_100m_cny": 27040},
            "value": "up_count=4211 total_amount_100m_cny=27040",
            "raw_path": "subject_provider_runs.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "market_stat_contradicted_by_evidence" in result.reasons


def test_market_breadth_support_accepts_matching_non_cn_market_scope():
    result = validate_claim_dicts(
        [{
            "claim": "港股上涨家数多于下跌家数，市场宽度偏强。",
            "claimType": "interpretation",
            "subject": "market_hk",
            "domain": "price",
            "evidence_ids": ["subject:market_hk:market_stats"],
        }],
        [{
            "id": "subject:market_hk:market_stats",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market_hk",
            "metric": "market_stats",
            "value": "up_count=900 down_count=700",
            "measurements": {"up_count": 900, "down_count": 700},
            "raw_path": "raw.json",
        }],
    )[0]

    assert "market_breadth_language_requires_breadth_evidence" not in result.reasons


def test_market_stat_is_rejected_when_number_precedes_label_and_citation_has_no_measurement():
    result = validate_claim_dicts(
        [{
            "claim": "两市2.58万亿的成交额及超3300只个股上涨表明交易活跃。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["subject:market:main_indices"],
        }],
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "measurements": {"index_sh000001_change_pct": -0.29},
            "value": "index_sh000001_change_pct=-0.29",
            "raw_path": "subject_evidence.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "market_stat_not_supported_by_cited_evidence" in result.reasons


def test_fundamental_fact_is_rejected_when_growth_number_differs_from_evidence():
    result = validate_claim_dicts(
        [{
            "claim": "平安银行营业收入同比增长0.49%，归母净利润同比增长203.89%。",
            "claimType": "fact",
            "subject": "000001",
            "domain": "fundamentals",
            "evidence_ids": ["subject:000001:fundamental:growth"],
        }],
        [{
            "id": "subject:000001:fundamental:growth",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "subject": "000001",
            "metric": "fundamental_growth",
            "measurements": {"revenue_yoy_pct": 4.6516, "net_profit_yoy_pct": 3.0292},
            "value": "revenue_yoy=4.6516 net_profit_yoy=3.0292",
            "raw_path": "subject_evidence.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "fundamental_metric_contradicted_by_evidence" in result.reasons


def test_index_fact_is_rejected_when_change_differs_from_measurement():
    result = validate_claim_dicts(
        [{
            "claim": "科创50指数上涨2.00%。",
            "claimType": "fact",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["subject:market:main_indices"],
        }],
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "measurements": {"index_sh000688_change_pct": -4.25},
            "value": "index_sh000688_change_pct=-4.25",
            "raw_path": "subject_evidence.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "index_change_contradicted_by_evidence" in result.reasons


def test_strong_causal_wording_is_calibrated_without_direct_mechanism_evidence():
    result = validate_claim_dicts(
        [{
            "claim": "科创50下跌本质上是资金主动撤离科技板块。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["subject:market:main_indices"],
        }],
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "value": "科创50=-4.25%",
            "raw_path": "subject_evidence.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "strong_causal_language_requires_direct_mechanism_evidence" in result.reasons
    assert result.safe_text == "科创50下跌本质上是资金主动撤离科技板块。"


def test_multi_symbol_claim_requires_evidence_for_every_symbol():
    result = validate_claim_dicts(
        [{
            "claim": "AAPL与HK00700均维持多头结构。",
            "claimType": "interpretation",
            "domain": "price",
            "evidence_ids": ["ev:AAPL"],
        }],
        [{
            "id": "ev:AAPL",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "AAPL",
            "value": "AAPL close above sma20",
            "raw_path": "raw.json",
        }],
    )[0]
    assert result.status == ClaimStatus.REJECTED
    assert "claim_subject_not_supported_by_cited_evidence" in result.reasons


def test_multi_metric_macro_claim_accepts_each_cited_series():
    result = validate_claim_dicts(
        [{
            "claim": "10Y-2Y与10Y-3M利差分别为0.35%和0.71%。",
            "claimType": "fact",
            "subject": "macro",
            "domain": "macro",
            "metric": "T10Y2Y,T10Y3M",
            "evidence_ids": ["fred:T10Y2Y", "fred:T10Y3M"],
        }],
        [
            {"id": "fred:T10Y2Y", "fact_type": "verified_fact", "domain": "macro", "subject": "T10Y2Y", "metric": "T10Y2Y", "value": "T10Y2Y=0.35", "source_url": "https://fred.example/1"},
            {"id": "fred:T10Y3M", "fact_type": "verified_fact", "domain": "macro", "subject": "T10Y3M", "metric": "T10Y3M", "value": "T10Y3M=0.71", "source_url": "https://fred.example/2"},
        ],
    )[0]
    assert result.status == ClaimStatus.SUPPORTED


def test_sector_performance_does_not_prove_capital_flow():
    result = validate_claim_dicts(
        [{
            "claim": "资金流向医药板块抱团避险。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["ev:sector_rank"],
        }],
        [{
            "id": "ev:sector_rank",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "value": "医药制造业 change_pct=2.98",
            "raw_path": "raw.json",
        }],
    )[0]
    assert result.status == ClaimStatus.HYPOTHESIS
    assert "capital_flow_language_requires_flow_evidence" in result.reasons


def test_relative_defensive_performance_does_not_prove_fund_rotation():
    result = validate_claim_dicts(
        [{
            "claim": "资金向银行等低估值防御板块抱团的特征明显。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["ev:bank_price"],
        }],
        [{
            "id": "ev:bank_price",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "value": "银行板块相对大盘抗跌",
            "raw_path": "raw.json",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "capital_flow_language_requires_flow_evidence" in result.reasons
    assert result.safe_text == "资金向银行等低估值防御板块抱团的特征明显。"


def test_price_rotation_does_not_masquerade_as_active_fund_migration():
    result = validate_claim_dicts(
        [{
            "claim": "资金呈现明显的“弃科技、向防御”去杠杆特征。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["ev:relative_price"],
        }],
        [{
            "id": "ev:relative_price",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "value": "科技相对承压 防御样本相对抗跌",
            "raw_path": "raw.json",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert result.safe_text == "资金呈现明显的“弃科技、向防御”去杠杆特征。"


def test_single_tech_samples_do_not_prove_global_tech_pressure():
    result = validate_claim_dicts(
        [{
            "claim": "当前全球科技股高位共振派发压力加剧。",
            "claimType": "interpretation",
            "domain": "price",
            "evidence_ids": ["quote:AAPL", "daily:HK00700"],
        }],
        [
            {"id": "quote:AAPL", "fact_type": "derived_fact", "domain": "price", "subject": "AAPL", "value": "change_pct=0.82"},
            {"id": "daily:HK00700", "fact_type": "derived_fact", "domain": "price", "subject": "HK00700", "value": "return_1d_pct=3.90"},
        ],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "cross_market_scope_requires_market_benchmarks" in result.reasons
    assert result.safe_text == "当前全球科技股高位共振派发压力加剧。"


def test_global_tech_scope_rewrite_keeps_compound_sentence_readable():
    result = validate_claim_dicts(
        [{
            "claim": "美港股科技龙头短期维持强势，但由于估值与位置高企，极易受到全球科技股共振派发压力的回踩扰动。",
            "claimType": "interpretation",
            "domain": "price",
            "evidence_ids": ["quote:AAPL", "daily:HK00700"],
        }],
        [
            {"id": "quote:AAPL", "fact_type": "derived_fact", "domain": "price", "subject": "AAPL", "value": "change_pct=0.82"},
            {"id": "daily:HK00700", "fact_type": "derived_fact", "domain": "price", "subject": "HK00700", "value": "return_1d_pct=3.90"},
        ],
    )[0]

    assert result.safe_text == "美港股科技龙头短期维持强势，但由于估值与位置高企，极易受到全球科技股共振派发压力的回踩扰动。"


def test_qualitative_level_needs_benchmark():
    result = validate_claim_dicts(
        [{
            "claim": "VIX为15.84，市场处于温和区间。",
            "claimType": "fact",
            "subject": "macro",
            "domain": "macro",
            "metric": "VIXCLS",
            "evidence_ids": ["fred:VIXCLS"],
        }],
        [{
            "id": "fred:VIXCLS",
            "fact_type": "verified_fact",
            "domain": "macro",
            "subject": "VIXCLS",
            "metric": "VIXCLS",
            "value": "VIXCLS=15.84",
            "source_url": "https://fred.example/vix",
        }],
    )[0]
    assert result.status == ClaimStatus.HYPOTHESIS
    assert "qualitative_level_requires_benchmark" in result.reasons


def test_unsupported_intensity_is_calibrated_without_turning_judgment_into_maybe():
    result = validate_claim_dicts(
        [{
            "claim": "市场呈现极端分化与良性风格轮动，流动性依然充裕。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["subject:market:main_indices"],
        }],
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "value": "上证50=-0.29% 科创50=-4.25%",
            "raw_path": "subject_evidence.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert result.safe_text == "市场呈现极端分化与良性风格轮动，流动性依然充裕。"


def test_cross_market_stock_sample_is_not_promoted_to_market_level_claim():
    result = validate_claim_dicts(
        [{
            "claim": "跨市场对比显示美股表现强于A股和港股，跨市场间未出现系统性共振下跌。",
            "claimType": "interpretation",
            "domain": "price",
            "evidence_ids": ["quote:AAPL", "quote:HK00700"],
        }],
        [
            {"id": "quote:AAPL", "fact_type": "derived_fact", "domain": "price", "subject": "AAPL", "value": "change_pct=2.91"},
            {"id": "quote:HK00700", "fact_type": "derived_fact", "domain": "price", "subject": "HK00700", "value": "change_pct=-0.31"},
        ],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "cross_market_scope_requires_market_benchmarks" in result.reasons
    assert result.safe_text == "跨市场对比显示美股表现强于A股和港股，跨市场间未出现系统性共振下跌。"


def test_volume_expansion_claim_is_rejected_when_ratio_is_below_one():
    result = validate_claim_dicts(
        [{
            "claim": "比亚迪今日放量反弹，量价结构明显改善。",
            "claimType": "fact",
            "subject": "002594",
            "domain": "price",
            "evidence_ids": ["subject:002594:daily_data"],
        }],
        [{
            "id": "subject:002594:daily_data",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "002594",
            "value": "close=89.23 change_pct=2.59 volume_vs_avg20=0.42",
            "raw_path": "subject_provider_runs.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "volume_expansion_contradicted_by_evidence" in result.reasons


def test_volume_contraction_claim_is_supported_by_low_ratio():
    result = validate_claim_dicts(
        [{
            "claim": "比亚迪今日缩量反弹。",
            "claimType": "fact",
            "subject": "002594",
            "domain": "price",
            "evidence_ids": ["subject:002594:daily_data"],
        }],
        [{
            "id": "subject:002594:daily_data",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "002594",
            "value": "close=89.23 change_pct=2.59 volume_vs_avg20=0.42",
            "raw_path": "subject_provider_runs.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.SUPPORTED


def test_future_volume_breakout_trigger_is_not_rejected_by_current_low_volume():
    result = validate_claim_dicts(
        [{
            "claim": "若AAPL放量突破333.26美元且20日成交量比回升至1.2以上，则上行情景得到确认。",
            "claimType": "scenario",
            "subject": "AAPL",
            "domain": "price",
            "evidence_ids": ["subject:AAPL:daily_data"],
        }],
        [{
            "id": "subject:AAPL:daily_data",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "AAPL",
            "value": "close=333.26 volume_vs_avg20=0.94",
            "raw_path": "subject_provider_runs.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "volume_expansion_contradicted_by_evidence" not in result.reasons


def test_market_breadth_pair_requires_cited_market_stats():
    result = _validate(
        "上涨与下跌家数比为2498对2861，市场宽度明显恶化。",
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "provider": "DataFetcherManager",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "raw_path": "subject_evidence.jsonl",
            "value": "上证指数=-1.85% 科创50=-4.02%",
        }],
        claim_type=ClaimType.FACT,
    )

    assert result.status == ClaimStatus.REJECTED
    assert "market_stat_not_supported_by_cited_evidence" in result.reasons


def test_market_breadth_language_needs_market_stats_evidence():
    result = _validate(
        "主要指数下跌且市场宽度明显恶化。",
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "provider": "DataFetcherManager",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "raw_path": "subject_evidence.jsonl",
            "value": "上证指数=-1.85% 科创50=-4.02%",
        }],
        claim_type=ClaimType.INTERPRETATION,
    )

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "market_breadth_language_requires_breadth_evidence" in result.reasons
    assert result.safe_text == "主要指数下跌且市场宽度明显恶化。"


def test_aggregate_market_volume_scenario_ignores_unrelated_stock_ratio():
    result = validate_claim_dicts(
        [{
            "claim": "若两市成交额重新放量至8000亿元以上，市场风险偏好可能修复。",
            "claimType": "scenario",
            "domain": "price",
            "evidence_ids": ["subject:HK00700:daily_data", "subject:market:stats"],
        }],
        [
            {
                "id": "subject:HK00700:daily_data",
                "fact_type": "derived_fact",
                "domain": "price",
                "subject": "HK00700",
                "value": "close=500 volume_vs_avg20=0.71",
                "raw_path": "subject_provider_runs.jsonl",
            },
            {
                "id": "subject:market:stats",
                "fact_type": "derived_fact",
                "domain": "price",
                "subject": "market",
                "value": "A-share total_amount=7600亿元",
                "raw_path": "subject_provider_runs.jsonl",
            },
        ],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "volume_expansion_contradicted_by_evidence" not in result.reasons


def test_strong_fundamental_language_requires_official_filing_support():
    result = validate_claim_dicts(
        [{
            "claim": "比亚迪基本面严重恶化，存在业绩暴雷风险。",
            "claimType": "interpretation",
            "subject": "002594",
            "domain": "fundamentals",
            "evidence_ids": ["subject:002594:fundamental:growth"],
        }],
        [{
            "id": "subject:002594:fundamental:growth",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "subject": "002594",
            "provider": "YfinanceFundamentalAdapter",
            "confidence": "medium",
            "value": "revenue_yoy=-45.34 net_profit_yoy=-72.80",
            "raw_path": "subject_provider_runs.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "strong_fundamental_language_requires_official_filing" in result.reasons
    assert "不具备可持续性" not in result.safe_text


def test_fundamental_profit_driver_requires_filing_line_item_support():
    result = validate_claim_dicts(
        [{
            "claim": "平安银行利润增长主要来自拨备释放和低基数。",
            "claimType": "interpretation",
            "subject": "000001",
            "domain": "fundamentals",
            "evidence_ids": ["subject:000001:fundamental:growth"],
        }],
        [{
            "id": "subject:000001:fundamental:growth",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "subject": "000001",
            "provider": "YfinanceFundamentalAdapter",
            "value": "revenue_yoy=0.49 net_profit_yoy=203.89",
            "raw_path": "subject_provider_runs.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "fundamental_driver_requires_filing_detail" in result.reasons


def test_reporting_period_claim_requires_matching_official_filing():
    result = validate_claim_dicts(
        [{
            "claim": "贵州茅台最新披露的2026年中报显示增长。",
            "claimType": "interpretation",
            "subject": "600519",
            "domain": "fundamentals",
            "evidence_ids": ["subject:600519:fundamental:growth", "cninfo:600519:dividend"],
        }],
        [
            {
                "id": "subject:600519:fundamental:growth",
                "fact_type": "derived_fact",
                "domain": "fundamentals",
                "subject": "600519",
                "value": "revenue_yoy=6.33 net_profit_yoy=1.47",
                "raw_path": "fundamental.json",
            },
            {
                "id": "cninfo:600519:dividend",
                "fact_type": "verified_fact",
                "domain": "filings_events",
                "subject": "600519",
                "value": "贵州茅台2025年年度权益分派实施公告",
                "source_url": "https://www.cninfo.com.cn/example.pdf",
            },
        ],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "reporting_period_requires_matching_official_filing" in result.reasons
    assert result.safe_text == ""


def test_form4_presence_alone_does_not_prove_insider_sale():
    result = validate_claim_dicts(
        [{
            "claim": "AAPL 高管近期持续减持。",
            "claimType": "fact",
            "subject": "AAPL",
            "domain": "filings_events",
            "evidence_ids": ["sec:AAPL:form4"],
        }],
        [{
            "id": "sec:AAPL:form4",
            "fact_type": "verified_fact",
            "domain": "filings_events",
            "subject": "AAPL",
            "provider": "SEC_EDGAR",
            "form": "4",
            "value": "Form 4 filed 2026-07-10",
            "source_url": "https://sec.example/form4.xml",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "form4_sale_requires_transaction_detail" in result.reasons


def test_form4_sale_cannot_be_laundered_as_interpretation():
    result = validate_claim_dicts(
        [{
            "claim": "AAPL 高管近期存在 Form 4 减持申报。",
            "claimType": "interpretation",
            "subject": "AAPL",
            "domain": "filings_events",
            "evidence_ids": ["sec:AAPL:form4"],
        }],
        [{
            "id": "sec:AAPL:form4",
            "fact_type": "verified_fact",
            "domain": "filings_events",
            "subject": "AAPL",
            "provider": "SEC_EDGAR",
            "form": "4",
            "value": "Form 4 filed 2026-07-10",
            "source_url": "https://sec.example/form4.xml",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert result.safe_text == ""


def test_trend_structure_claim_needs_series_or_indicator_evidence():
    result = validate_claim_dicts(
        [{
            "claim": "比亚迪属于短期多头趋势的延续，可持续性较高。",
            "claimType": "interpretation",
            "subject": "002594",
            "domain": "price",
            "evidence_ids": ["subject:002594:quote"],
        }],
        [{
            "id": "subject:002594:quote",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "002594",
            "value": "price=89.23 change_pct=2.59",
            "raw_path": "subject_provider_runs.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "technical_structure_requires_series_evidence" in result.reasons


def test_market_extreme_wording_needs_market_history_not_stock_history():
    result = validate_claim_dicts(
        [{
            "claim": "A股呈现指数极端分化，两市成交额处于极高水平。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["subject:market:main_indices", "subject:AAPL:history"],
        }],
        [
            {
                "id": "subject:market:main_indices",
                "fact_type": "derived_fact",
                "domain": "price",
                "subject": "market",
                "metric": "main_indices",
                "value": "index_sh000016_change_pct=0.39 index_sh000688_change_pct=-4.25",
                "raw_path": "subject_evidence.jsonl",
            },
            {
                "id": "subject:AAPL:history",
                "fact_type": "derived_fact",
                "domain": "price",
                "subject": "AAPL",
                "metric": "daily_history",
                "value": "close history",
                "raw_path": "subject_evidence.jsonl",
            },
        ],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "market_intensity_requires_market_benchmark" in result.reasons
    assert result.safe_text == "A股呈现指数极端分化，两市成交额处于极高水平。"


def test_roe_alone_does_not_justify_valuation_premium():
    result = validate_claim_dicts(
        [{
            "claim": "AAPL 的 ROE 为141.471%，该 ROE 数值支持其高估值溢价。",
            "claimType": "interpretation",
            "subject": "AAPL",
            "domain": "fundamentals",
            "evidence_ids": ["subject:AAPL:fundamental:growth"],
        }],
        [{
            "id": "subject:AAPL:fundamental:growth",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "subject": "AAPL",
            "metric": "fundamental_growth",
            "value": "roe=141.471",
            "raw_path": "subject_evidence.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "roe_alone_cannot_justify_valuation" in result.reasons
    assert result.safe_text == "AAPL 的 ROE 为141.471%，该 ROE 数值支持其高估值溢价。"


def test_gdp_level_is_not_treated_as_growth_rate():
    result = validate_claim_dicts(
        [{
            "claim": "结合一季度GDP达31.87万亿美元的基数，美国宏观基本面属于温和增长。",
            "claimType": "interpretation",
            "subject": "macro",
            "domain": "macro",
            "evidence_ids": ["fred:GDP"],
        }],
        [{
            "id": "fred:GDP",
            "fact_type": "verified_fact",
            "domain": "macro",
            "subject": "GDP",
            "metric": "GDP",
            "value": "GDP=31870",
            "source_url": "https://fred.example/GDP",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "gdp_level_cannot_prove_growth_rate" in result.reasons
    assert result.safe_text == "结合一季度GDP达31.87万亿美元的基数，美国宏观基本面属于温和增长。"


def test_postprocessor_does_not_invent_currency_or_change_trigger_logic():
    result = validate_claim_dicts(
        [{
            "claim": (
                "AAPL盘中涨至324.69美元，前收314.86美元；平安银行（000001）支撑位10.60元；"
                "全市场流动性并未收缩；"
                "若科创50无量跌破1900点，则确立多头踩踏升级。"
            ),
            "claimType": "recommendation",
            "domain": "price",
            "evidence_ids": ["subject:AAPL:quote", "subject:000001:quote", "subject:market:market_stats"],
        }],
        [
            {
                "id": "subject:AAPL:quote",
                "fact_type": "derived_fact",
                "domain": "price",
                "subject": "AAPL",
                "metric": "quote",
                "value": "price=324.69",
                "raw_path": "subject_evidence.jsonl",
            },
            {
                "id": "subject:000001:quote",
                "fact_type": "derived_fact",
                "domain": "price",
                "subject": "000001",
                "metric": "quote",
                "value": "price=10.60",
                "raw_path": "subject_evidence.jsonl",
            },
            {
                "id": "subject:market:market_stats",
                "fact_type": "derived_fact",
                "domain": "price",
                "subject": "market",
                "metric": "market_stats",
                "value": "up_count=3350 down_count=2098 total_amount_100m_cny=25800",
                "raw_path": "subject_evidence.jsonl",
            },
        ],
    )[0]

    assert result.safe_text == ("AAPL盘中涨至324.69美元，前收314.86美元；平安银行（000001）支撑位10.60元；"
                "全市场流动性并未收缩；"
                "若科创50无量跌破1900点，则确立多头踩踏升级。")


def test_single_stock_samples_are_not_described_as_entire_markets():
    result = validate_claim_dicts(
        [{
            "claim": "美股盘中科技股走强，港股震荡偏弱，跨市场联动性较弱。",
            "claimType": "interpretation",
            "domain": "price",
            "evidence_ids": ["quote:AAPL", "quote:HK00700"],
        }],
        [
            {"id": "quote:AAPL", "fact_type": "derived_fact", "domain": "price", "subject": "AAPL", "value": "change_pct=2.91"},
            {"id": "quote:HK00700", "fact_type": "derived_fact", "domain": "price", "subject": "HK00700", "value": "change_pct=-0.31"},
        ],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert result.safe_text == "美股盘中科技股走强，港股震荡偏弱，跨市场联动性较弱。"


def test_rejecting_one_cause_does_not_prove_alternative_or_buy_action():
    result = validate_claim_dicts(
        [{
            "claim": "若未找到氦气官方公告，则可判定为纯交易超跌并低吸。",
            "claimType": "recommendation",
            "subject": "market",
            "domain": "news_sentiment",
            "evidence_ids": ["tavily:helium-rumor"],
        }],
        [{
            "id": "tavily:helium-rumor",
            "fact_type": "discovery",
            "domain": "news_sentiment",
            "subject": "market",
            "value": "search did not find an official helium notice",
            "source_url": "https://example.invalid/search",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "absence_of_one_cause_does_not_prove_alternative_or_action" in result.reasons
    assert result.safe_text == "若未找到氦气官方公告，则可判定为纯交易超跌并低吸。"


def test_watchlist_is_not_evidence_of_real_portfolio_hedging():
    result = validate_claim_dicts(
        [{
            "claim": "当前观察池已经对冲了组合中的科技调整。",
            "claimType": "interpretation",
            "subject": "portfolio",
            "domain": "portfolio",
            "evidence_ids": ["daily:watchlist"],
        }],
        [{
            "id": "daily:watchlist",
            "fact_type": "derived_fact",
            "domain": "portfolio",
            "subject": "portfolio",
            "value": "portfolio/watchlist symbols: 600519, 000001, AAPL, HK00700",
            "raw_path": "daily_universe.json",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "portfolio_outcome_requires_actual_positions" in result.reasons
    assert result.safe_text == ""


def test_one_day_sector_ranking_does_not_prove_persistence():
    result = validate_claim_dicts(
        [{
            "claim": "医药行业具备更强防御持续性。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "news_sentiment",
            "evidence_ids": ["subject:market:sector_rankings"],
        }],
        [{
            "id": "subject:market:sector_rankings",
            "fact_type": "derived_fact",
            "domain": "news_sentiment",
            "subject": "market",
            "value": "sector_rankings: 医药 +3.2%",
            "raw_path": "subject_evidence.jsonl",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "sector_persistence_requires_multi_period_or_driver_evidence" in result.reasons
    assert result.safe_text == "医药行业具备更强防御持续性。"


def test_missing_market_breadth_cannot_be_described_as_bearish_breadth():
    result = validate_claim_dicts(
        [{
            "claim": "主要指数偏弱，市场宽度略微偏向空头。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["subject:market:main_indices"],
        }],
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "metric": "main_indices",
            "value": "上证指数=-1.85% 创业板指=-2.95%",
            "raw_path": "main_indices.json",
        }],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "market_breadth_language_requires_breadth_evidence" in result.reasons
    assert result.safe_text == "主要指数偏弱，市场宽度略微偏向空头。"


def test_twenty_day_high_does_not_become_all_time_high():
    result = validate_claim_dicts(
        [{
            "claim": "AAPL 创历史新高，趋势保持强势。",
            "claimType": "interpretation",
            "subject": "AAPL",
            "domain": "price",
            "evidence_ids": ["subject:AAPL:price_history_comparison"],
        }],
        [{
            "id": "subject:AAPL:price_history_comparison",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "AAPL",
            "metric": "price_history_comparison",
            "value": "high20=333.26 range_position_pct=100",
            "raw_path": "price_history.json",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "all_time_high_requires_full_history_evidence" in result.reasons
    assert result.safe_text == ""


def test_coincident_buyback_does_not_prove_price_causality():
    result = validate_claim_dicts(
        [{
            "claim": "腾讯股价上涨主要受持续股份回购支撑。",
            "claimType": "interpretation",
            "subject": "HK00700",
            "domain": "price",
            "evidence_ids": ["subject:HK00700:daily", "official:HK00700:buyback"],
        }],
        [
            {
                "id": "subject:HK00700:daily",
                "fact_type": "derived_fact",
                "domain": "price",
                "subject": "HK00700",
                "value": "return_1d_pct=2.11",
                "raw_path": "daily.json",
            },
            {
                "id": "official:HK00700:buyback",
                "fact_type": "verified_fact",
                "domain": "filings_events",
                "subject": "HK00700",
                "value": "股份回购公告",
                "source_url": "https://www.hkexnews.hk/",
            },
        ],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "causal_attribution_requires_mechanism_evidence" in result.reasons
    assert result.safe_text == "腾讯股价上涨主要受持续股份回购支撑。"


def test_market_counts_in_shares_need_market_breadth_evidence():
    result = validate_claim_dicts(
        [{
            "claim": "上涨家数达2498只，下跌2861只，市场宽度未发生系统性崩溃。",
            "claimType": "interpretation",
            "subject": "market",
            "domain": "price",
            "evidence_ids": ["subject:market:main_indices"],
        }],
        [{
            "id": "subject:market:main_indices",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "market",
            "value": "上证指数=-1.85% 科创50=-4.02%",
            "raw_path": "main_indices.json",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "market_stat_not_supported_by_cited_evidence" in result.reasons


def test_nominal_gdp_level_does_not_prove_strong_growth():
    result = validate_claim_dicts(
        [{
            "claim": "美国 GDP 达到31865.721并创历史新高，显示宏观经济总量维持强劲增长。",
            "claimType": "interpretation",
            "subject": "macro",
            "domain": "macro",
            "evidence_ids": ["fred:GDP"],
        }],
        [{
            "id": "fred:GDP",
            "fact_type": "verified_fact",
            "domain": "macro",
            "subject": "macro",
            "value": "GDP=31865.721",
            "source_url": "https://fred.stlouisfed.org/series/GDP",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "gdp_level_cannot_prove_growth_rate" in result.reasons
    assert result.safe_text == ""


def test_positive_curve_snapshot_does_not_prove_inversion_has_ended():
    result = validate_claim_dicts(
        [{
            "claim": "10年期收益率高于2年期，收益率曲线已经结束倒挂。",
            "claimType": "interpretation",
            "subject": "macro",
            "domain": "macro",
            "evidence_ids": ["fred:DGS10", "fred:DGS2"],
        }],
        [
            {"id": "fred:DGS10", "fact_type": "verified_fact", "domain": "macro", "subject": "macro", "value": "DGS10=4.55", "source_url": "https://fred.example/DGS10"},
            {"id": "fred:DGS2", "fact_type": "verified_fact", "domain": "macro", "subject": "macro", "value": "DGS2=4.13", "source_url": "https://fred.example/DGS2"},
        ],
    )[0]

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "yield_curve_transition_requires_history" in result.reasons
    assert result.safe_text == "10年期收益率高于2年期，收益率曲线已经结束倒挂。"


def test_wrong_return_period_is_rejected_even_when_value_matches_another_period():
    result = validate_claim_dicts(
        [{
            "claim": "腾讯控股1200日收益率为-21.28%。",
            "claimType": "fact",
            "subject": "HK00700",
            "domain": "price",
            "evidence_ids": ["subject:HK00700:history"],
        }],
        [{
            "id": "subject:HK00700:history",
            "fact_type": "derived_fact",
            "domain": "price",
            "subject": "HK00700",
            "measurements": {"return_120d_pct": -21.28},
            "value": "return_120d_pct=-21.28",
            "raw_path": "history.json",
        }],
    )[0]

    assert result.status == ClaimStatus.REJECTED
    assert "return_period_not_supported_by_evidence" in result.reasons


def test_market_count_ratio_with_slash_is_rejected_without_breadth_evidence():
    result = _validate("上涨/下跌家数比达2498/2861，市场仍属结构分化。", [{
        "id": "subject:market:main_indices",
        "fact_type": "derived_fact",
        "domain": "price",
        "subject": "market",
        "metric": "main_indices",
        "value": "上证指数=-1.85% 科创50=-4.02%",
        "raw_path": "main_indices.json",
    }])

    assert result.status == ClaimStatus.REJECTED
    assert "market_stat_not_supported_by_cited_evidence" in result.reasons


def _dated_price_claim(evidence: dict, *, reference_date: str = "2026-08-21"):
    return validate_claim_dicts(
        [{
            "claim": "AAPL 当前价格保持在可观察区间。",
            "claimType": "fact",
            "subject": "AAPL",
            "domain": "price",
            "evidence_ids": [evidence["id"]],
        }],
        [evidence],
        reference_date=reference_date,
    )[0]


def test_semantic_gate_rejects_source_smoke_as_claim_support():
    result = _dated_price_claim({
        "id": "smoke:AAPL:quote",
        "fact_type": "derived_fact",
        "domain": "price",
        "subject": "AAPL",
        "value": "price=100",
        "raw_path": "smoke.json",
        "as_of": "2026-08-21",
        "evidence_scope": "source_smoke",
    })

    assert result.status == ClaimStatus.REJECTED
    assert "non_subject_evidence_scope" in result.reasons


def test_semantic_gate_rejects_missing_fact_as_claim_support():
    result = _dated_price_claim({
        "id": "missing:AAPL:quote",
        "fact_type": "missing",
        "domain": "price",
        "subject": "AAPL",
        "value": "quote unavailable",
        "as_of": "2026-08-21",
    })

    assert result.status == ClaimStatus.REJECTED
    assert "missing_evidence_cannot_support_claim" in result.reasons


def test_semantic_gate_rejects_stale_and_lookahead_price_evidence():
    stale = _dated_price_claim({
        "id": "subject:AAPL:quote:stale",
        "fact_type": "derived_fact",
        "domain": "price",
        "subject": "AAPL",
        "value": "price=100",
        "raw_path": "quote.json",
        "as_of": "2026-08-01",
    })
    future = _dated_price_claim({
        "id": "subject:AAPL:quote:future",
        "fact_type": "derived_fact",
        "domain": "price",
        "subject": "AAPL",
        "value": "price=100",
        "raw_path": "quote.json",
        "as_of": "2026-08-22",
    })

    assert stale.status == ClaimStatus.REJECTED
    assert "stale_evidence" in stale.reasons
    assert future.status == ClaimStatus.REJECTED
    assert "evidence_after_claim_time" in future.reasons


def test_semantic_gate_accepts_current_subject_evidence():
    result = _dated_price_claim({
        "id": "subject:AAPL:quote:current",
        "fact_type": "derived_fact",
        "domain": "price",
        "subject": "AAPL",
        "value": "price=100",
        "raw_path": "quote.json",
        "as_of": "2026-08-21",
    })

    assert result.status == ClaimStatus.SUPPORTED
    assert result.accepted_evidence_ids == ("subject:AAPL:quote:current",)


def test_single_period_growth_does_not_prove_slowdown():
    result = _validate("贵州茅台净利润增速放缓至1.47%，扩张动能明显承压。", [{
        "id": "subject:600519:fundamental:growth",
        "fact_type": "derived_fact",
        "domain": "fundamentals",
        "subject": "600519",
        "metric": "fundamental_growth",
        "value": "net_profit_yoy=1.47",
        "measurements": {"net_profit_yoy_pct": 1.47},
        "raw_path": "fundamental.json",
    }])

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "growth_trend_requires_multi_period_evidence" in result.reasons
    assert result.safe_text == "贵州茅台净利润增速放缓至1.47%，扩张动能明显承压。"


def test_low_valuation_label_requires_valuation_metrics():
    result = _validate("平安银行处于低估值安全区间。", [{
        "id": "subject:000001:fundamental:growth",
        "fact_type": "derived_fact",
        "domain": "fundamentals",
        "subject": "000001",
        "metric": "fundamental_growth",
        "value": "revenue_yoy=4.65 roe=2.83",
        "raw_path": "fundamental.json",
    }])

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "valuation_label_requires_valuation_evidence" in result.reasons
    assert result.safe_text == "平安银行处于低估值安全区间。"


def test_current_valuation_plus_unrelated_history_does_not_prove_historical_low():
    result = _validate("苹果估值处于历史低位。", [
        {
            "id": "subject:AAPL:fundamental:valuation:2099-01-02",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "subject": "AAPL",
            "metric": "fundamental_valuation",
            "value": "trailing_pe=22 price_to_book=5.5",
            "measurements": {"trailing_pe": 22.0, "price_to_book": 5.5},
            "raw_path": "fundamental.json",
        },
        {
            "id": "subject:AAPL:fundamental:history_comparison:2099-01-02",
            "fact_type": "derived_fact",
            "domain": "fundamentals",
            "subject": "AAPL",
            "metric": "fundamental_history_comparison",
            "value": "revenue_yoy_pct=10",
            "raw_path": "fundamental.json",
        },
    ])

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "valuation_label_requires_valuation_evidence" in result.reasons


def test_eligible_local_valuation_percentile_supports_bounded_valuation_label():
    result = _validate("苹果估值在近 30 个本地日度样本中偏低。", [{
        "id": "subject:AAPL:fundamental:valuation_history:2099-01-02",
        "fact_type": "derived_fact",
        "domain": "fundamentals",
        "subject": "AAPL",
        "metric": "valuation_history_comparison",
        "value": "observations=30 pe_local_run_percentile=20",
        "measurements": {"valuation_percentile_eligible": 1.0, "pe_local_run_percentile": 20.0},
        "raw_path": "fundamental.json",
    }])

    assert "valuation_label_requires_valuation_evidence" not in result.reasons


def test_eligible_generic_online_valuation_history_supports_bounded_label():
    result = _validate("平安银行估值在近三年公开样本中偏低。", [{
        "id": "subject:000001:fundamental:valuation:2099-01-02",
        "fact_type": "derived_fact",
        "domain": "fundamentals",
        "subject": "000001",
        "metric": "fundamental_valuation",
        "value": "trailing_pe=5.5 pe_history_percentile=18",
        "measurements": {
            "trailing_pe": 5.5,
            "pe_history_percentile": 18.0,
            "valuation_percentile_eligible": 1.0,
        },
        "raw_path": "fundamental.json",
    }])

    assert "valuation_label_requires_valuation_evidence" not in result.reasons


def test_buyback_fact_does_not_prove_downside_defense():
    result = _validate("腾讯控股持续回购提供下行防御。", [{
        "id": "hkex:00700:buyback",
        "fact_type": "verified_fact",
        "domain": "filings_events",
        "subject": "HK00700",
        "value": "股份回购披露",
        "source_url": "https://www.hkexnews.hk/",
    }])

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "corporate_action_does_not_prove_price_support" in result.reasons
    assert result.safe_text == "腾讯控股持续回购提供下行防御。"


def test_index_decline_alone_does_not_prove_structural_deleveraging():
    result = _validate("A股进入结构性去杠杆与获利回吐阶段。", [{
        "id": "subject:market:main_indices",
        "fact_type": "derived_fact",
        "domain": "price",
        "subject": "market",
        "metric": "main_indices",
        "value": "上证指数=-1.85% 科创50=-4.02%",
        "raw_path": "main_indices.json",
    }])

    assert result.status == ClaimStatus.HYPOTHESIS
    assert "deleveraging_requires_flow_or_leverage_evidence" in result.reasons
    assert result.safe_text == "A股进入结构性去杠杆与获利回吐阶段。"


def test_collection_session_does_not_become_premarket_price_move():
    result = _validate("A股观察标的盘前走势偏弱，平安银行盘前下跌0.65%。", [{
        "id": "subject:000001:quote",
        "fact_type": "derived_fact",
        "domain": "price",
        "subject": "000001",
        "metric": "realtime_quote",
        "value": "quote session=premarket price=10.77 change_pct=-0.65",
        "measurements": {"change_pct": -0.65},
        "raw_path": "quote.json",
    }])

    assert result.status == ClaimStatus.REJECTED
    assert "collection_session_does_not_prove_session_price_move" in result.reasons
    assert result.safe_text == ""


def test_regional_sector_price_evidence_is_not_rejected_as_news():
    row = {'id': 'sectors:us', 'fact_type': 'derived_fact', 'subject': 'market_us',
           'domain': 'news_sentiment', 'metric': 'sector_performance', 'raw_path': 'sectors.json',
           'value': '能源(XLE) return_20d_pct=4 relative_20d_pp=2', 'benchmark': 'SPY',
           'records': [{'code': 'XLE', 'return_20d_pct': 4}]}
    result = validate_claim_dicts([{'claim': '美股能源行业20日强于SPY。', 'subject': 'market',
                                  'domain': 'price', 'evidence_ids': ['sectors:us']}], [row])[0]
    assert result.status == ClaimStatus.SUPPORTED
    # Aggregate supports its listed proxies, not an unrelated security or financial assertion.
    for subject, domain in [('AAPL', 'price'), ('XLE', 'fundamentals')]:
        result = validate_claim_dicts([{'claim': '估值合理。' if domain == 'fundamentals' else '价格走强。',
                                       'subject': subject, 'domain': domain, 'evidence_ids': ['sectors:us']}], [row])[0]
        assert result.status == ClaimStatus.REJECTED
    row['fact_type'] = 'discovery'
    result = validate_claim_dicts([{'claim': '能源价格走强。', 'domain': 'price',
                                   'evidence_ids': ['sectors:us']}], [row])[0]
    assert result.status == ClaimStatus.REJECTED


def test_cn_industry_rankings_are_price_evidence_not_fund_flow():
    row = {'id': 'sector:cn', 'fact_type': 'derived_fact', 'subject': 'market',
           'domain': 'news_sentiment', 'metric': 'sector_rankings', 'raw_path': 'sectors.json',
           'value': '农业 change_pct=4.17'}
    good, bad = validate_claim_dicts([
        {'claim': '农业行业当日涨幅居前。', 'subject': 'market', 'domain': 'price', 'evidence_ids': ['sector:cn']},
        {'claim': '资金流入农业行业。', 'subject': 'market', 'domain': 'price', 'evidence_ids': ['sector:cn']},
    ], [row])
    assert good.status == ClaimStatus.SUPPORTED
    assert 'capital_flow_language_requires_flow_evidence' in bad.reasons


def test_regional_claim_scopes_match_only_their_own_market():
    rows=[{'id': 'hk-sector','subject':'market_hk','domain':'news_sentiment','metric':'sector_performance',
           'fact_type':'derived_fact','raw_path':'hk.json','value':'内地银行 return_20d_pct=4'},
          {'id': 'us-sector','subject':'market_us','domain':'news_sentiment','metric':'sector_performance',
           'fact_type':'derived_fact','raw_path':'us.json','value':'能源 return_20d_pct=3'}]
    good,bad=validate_claim_dicts([
        {'claim':'港股内地银行价格偏强。','subject':'HK','domain':'price','evidence_ids':['hk-sector']},
        {'claim':'港股内地银行价格偏强。','subject':'HK','domain':'price','evidence_ids':['us-sector']},
    ],rows)
    assert good.status==ClaimStatus.SUPPORTED
    assert bad.status==ClaimStatus.REJECTED


def test_explicit_multi_subject_claim_requires_evidence_for_each_named_stock():
    rows=[{'id':'a','subject':'AAPL','domain':'price','metric':'daily_data','value':'价格=100',
           'fact_type':'derived_fact','raw_path':'a.json'},
          {'id':'h','subject':'HK00700','domain':'price','metric':'daily_data','value':'价格=400',
           'fact_type':'derived_fact','raw_path':'h.json'}]
    claim={'claim':'两只观察标的价格有据可查。','subject':'AAPL, HK00700','domain':'price','evidence_ids':['a','h']}
    assert validate_claim_dicts([claim],rows)[0].status==ClaimStatus.SUPPORTED
    claim['evidence_ids']=['a']
    result=validate_claim_dicts([claim],rows)[0]
    assert 'claim_subject_not_supported_by_cited_evidence' in result.reasons
    assert result.status==ClaimStatus.REJECTED


def test_known_universe_comparison_covers_only_listed_numeric_rows():
    row={'id':'u','subject':'market','domain':'price','metric':'universe_price_comparison',
         'fact_type':'derived_fact','raw_path':'u.json','value':'universe=2; leaders=AAPL +2.21%, HK00700 -7.52%'}
    claim={'claim':'两只标的阶段表现分化。','subject':'AAPL, HK00700','domain':'price','evidence_ids':['u']}
    assert validate_claim_dicts([claim],[row])[0].status==ClaimStatus.SUPPORTED
    claim['subject']='AAPL, MSFT'
    assert validate_claim_dicts([claim],[row])[0].status==ClaimStatus.REJECTED
