from src.research_core import build_challenge_verdicts, build_research_reliability, build_scenario_adjudication


def _report(agent, claims, *, summary="结论", key_claims=None, counterpoints=None):
    return {
        "agent": agent,
        "summaryForReader": summary,
        "keyClaims": key_claims or [],
        "counterpoints": counterpoints or [],
        "claimEvidence": [
            {"claimId": row[0], "claim": row[2], "evidence_ids": ["ev:1"]}
            for row in claims
        ],
        "semanticValidation": {
            "inputClaimCount": len(claims),
            "readerClaimCount": sum(row[1] != "rejected" for row in claims),
            "claims": [
                {"claimId": row[0], "status": row[1]}
                for row in claims
            ],
            "summary": {"status": "supported"},
        },
    }


def test_reliability_separates_supported_hypothesis_and_rejected_claims():
    rows = [
        _report("MarketAgent", [("m1", "supported", "主要指数涨跌分化。")]),
        _report(
            "RedTeamAgent",
            [("r1", "hypothesis", "若市场宽度继续收窄，权重股稳定可能掩盖风险。")],
            counterpoints=["若市场宽度继续收窄，权重股稳定可能掩盖风险。"],
        ),
        _report(
            "CIOAgent",
            [("c1", "supported", "基准情景是震荡分化。"), ("c2", "rejected", "资金必然外逃。")],
            summary="基准情景是震荡分化。",
        ),
    ]

    reliability = build_research_reliability(rows)

    assert reliability["supportedClaims"] == 2
    assert reliability["hypothesisClaims"] == 1
    assert reliability["rejectedClaims"] == 1
    assert reliability["headlineSafe"] is True
    assert reliability["label"] == "结论有据，含推演"
    assert any("移除" in item for item in reliability["warnings"])


def test_empty_summary_audit_uses_exact_validated_claim_not_claim_count():
    cio = _report("CIOAgent", [("c1", "supported", "三地市场表现分化。")],
                  summary="三地市场表现分化。")
    cio["semanticValidation"]["summary"] = {}
    assert build_research_reliability([cio])["headlineSafe"] is True
    cio["summaryForReader"] = "资金必然外逃。"
    assert build_research_reliability([cio])["headlineSafe"] is False


def test_explicit_rejected_summary_does_not_reuse_accepted_claim():
    cio = _report("CIOAgent", [("c1", "supported", "三地市场表现分化。")],
                  summary="三地市场表现分化。")
    cio["semanticValidation"]["summary"] = {"status": "rejected"}
    assert build_research_reliability([cio])["headlineSafe"] is False


def test_future_conditions_do_not_reduce_current_conclusion_assessment():
    cio = _report("CIOAgent", [("c1", "supported", "市场表现分化。")], summary="市场表现分化。")
    before = build_research_reliability([cio])
    cio["semanticValidation"]["counterpoints"] = [{"status": "hypothesis"}]
    cio["semanticValidation"]["nextActions"] = [{"status": "hypothesis"}]
    after = build_research_reliability([cio])
    assert after["label"] == before["label"]
    assert after["hypothesisClaims"] == 0
    assert after["scenarioItems"] == 2


def test_claim_assessment_distinguishes_basis_from_prediction_without_restoring_rejections():
    from src.research_core import build_claim_assessment
    cio = _report("CIOAgent", [("c1", "supported", "已公布财务增长。"),
                               ("c2", "hypothesis", "增长或能延续。"),
                               ("c3", "rejected", "无来源保证盈利。")])
    assessment = build_claim_assessment(cio)
    assert [c["label"] for c in assessment["claims"]] == ["有据支持", "研究判断"]
    assert [c["text"] for c in assessment["claims"]] == ["已公布财务增长。", "增长或能延续。"]
    assert assessment["summary"] == "1条有据支持 · 1条研究判断"


def test_scenario_adjudication_keeps_base_case_and_opposing_case_separate():
    rows = [
        _report("MarketAgent", [("m1", "supported", "主要指数涨跌分化。")], summary="基准情景为震荡分化。"),
        _report(
            "RedTeamAgent",
            [("r1", "hypothesis", "若市场宽度继续恶化，震荡可能转为普跌。")],
            counterpoints=["若市场宽度继续恶化，震荡可能转为普跌。"],
        ),
        _report(
            "CIOAgent",
            [("c1", "supported", "目前维持震荡分化判断。")],
            summary="目前维持震荡分化判断。",
            key_claims=["指数证据暂未显示普跌。"],
        ),
    ]

    result = build_scenario_adjudication(rows)

    assert result["sharedFacts"] == ["主要指数涨跌分化。"]
    assert result["baseCase"] == "目前维持震荡分化判断。"
    assert "市场宽度" in result["strongestAlternative"]
    assert result["judgment"] == "目前维持震荡分化判断。"


def test_scenario_adjudication_never_promotes_all_rejected_claims_to_shared_facts():
    rows = [
        _report(
            "MarketAgent",
            [("m1", "rejected", "MSFT上涨可由AAPL证据证明。")],
            summary="证据不足。",
        ),
        _report(
            "CIOAgent",
            [("c1", "hypothesis", "本轮暂不形成方向判断。")],
            summary="本轮暂不形成方向判断。",
        ),
    ]

    result = build_scenario_adjudication(rows)

    assert result["sharedFacts"] == []


def test_scenario_adjudication_uses_only_semantically_validated_model_block():
    cio = _report(
        "CIOAgent",
        [("c1", "supported", "目前维持震荡分化判断。")],
        summary="目前维持震荡分化判断。",
    )
    cio["adjudication"] = {
        "sharedFacts": ["指数与宽度背离。"],
        "baseCase": "基准情景为结构分化。",
        "strongestAlternative": "若宽度转弱，可能演变为普跌。",
        "judgment": "当前采纳结构分化。",
        "why": "宽度尚未崩溃。",
        "invalidationTriggers": ["若上涨家数低于1000家。"],
    }
    cio["semanticValidation"]["adjudication"] = {"validated": True}

    result = build_scenario_adjudication([cio])

    assert result["baseCase"] == "基准情景为结构分化。"
    assert result["judgment"] == "当前采纳结构分化。"
    assert result["invalidationTriggers"] == ["若上涨家数低于1000家。"]


def test_scenario_adjudication_never_restores_rejected_auxiliary_fields():
    market = _report(
        "MarketAgent",
        [("m1", "supported", "主要指数涨跌分化。")],
        summary="主要指数涨跌分化。",
    )
    cio = _report(
        "CIOAgent",
        [("c1", "supported", "当前维持震荡分化判断。")],
        summary="当前维持震荡分化判断。",
    )
    cio["adjudication"] = {
        "sharedFacts": ["伪造事实：MSFT 已暴涨 99%。"],
        "baseCase": "基准情景为震荡分化。",
        "strongestAlternative": "若宽度转弱，压力可能扩散。",
        "judgment": "当前维持震荡分化判断。",
        "why": "主要指数涨跌分化。",
        "invalidationTriggers": ["伪造触发器：MSFT 跌破不存在的价位。"],
    }
    cio["semanticValidation"]["adjudication"] = {
        "validated": True,
        "fields": {
            "sharedFacts": [{
                "status": "rejected",
                "text": "伪造事实：MSFT 已暴涨 99%。",
                "reasons": ["market_stat_not_supported_by_cited_evidence"],
            }],
            "baseCase": [{"status": "supported", "safeText": "基准情景为震荡分化。"}],
            "strongestAlternative": [{
                "status": "supported",
                "safeText": "若宽度转弱，压力可能扩散。",
            }],
            "judgment": [{"status": "supported", "safeText": "当前维持震荡分化判断。"}],
            "why": [{"status": "supported", "safeText": "主要指数涨跌分化。"}],
            "invalidationTriggers": [{
                "status": "rejected",
                "text": "伪造触发器：MSFT 跌破不存在的价位。",
                "reasons": ["market_stat_not_supported_by_cited_evidence"],
            }],
        },
    }

    result = build_scenario_adjudication([market, cio])

    assert result["sharedFacts"] == ["主要指数涨跌分化。"]
    assert result["invalidationTriggers"] == []
    assert all("伪造" not in item for item in result["sharedFacts"])


def test_scenario_adjudication_does_not_publish_dirty_model_causal_why():
    cio = _report(
        "CIOAgent",
        [("c1", "supported", "主要指数下跌，信用利差未同步走阔。")],
        summary="主要指数下跌，信用利差未同步走阔。",
        key_claims=["主要指数下跌，信用利差未同步走阔。"],
    )
    cio["adjudication"] = {
        "sharedFacts": ["主要指数下跌。"],
        "baseCase": "低估值与分红护盘，市场处于结构性去杠杆。",
        "strongestAlternative": "若信用利差走阔，压力可能扩散。",
        "judgment": "当前先按局部风险释放处理。",
        "why": "回购与分红足以托底股价。",
        "invalidationTriggers": ["若信用利差走阔。"],
    }
    cio["semanticValidation"]["adjudication"] = {
        "validated": True,
        "fields": {
            "baseCase": [{
                "status": "hypothesis",
                "reasons": ["deleveraging_requires_flow_or_leverage_evidence"],
            }],
            "why": [{
                "status": "hypothesis",
                "reasons": ["corporate_action_does_not_prove_price_support"],
            }],
        },
    }

    result = build_scenario_adjudication([cio])

    assert result["baseCase"] == "当前先按局部风险释放处理。"
    assert result["why"] == "主要指数下跌，信用利差未同步走阔。"


def test_scenario_adjudication_marks_hypothesis_alternative_as_conditional():
    cio = _report(
        "CIOAgent",
        [("c1", "supported", "主要指数下跌。")],
        summary="主要指数下跌。",
    )
    cio["adjudication"] = {
        "sharedFacts": ["主要指数下跌。"],
        "baseCase": "压力暂时集中在本地市场。",
        "strongestAlternative": "美港市场宽度已经恶化，跨市场补跌将发生。",
        "judgment": "暂按本地市场调整处理。",
        "why": "主要指数下跌。",
        "invalidationTriggers": ["美港市场宽度明显转弱。"],
    }
    cio["semanticValidation"]["adjudication"] = {
        "validated": True,
        "fields": {
            "strongestAlternative": [{
                "status": "hypothesis",
                "safeText": "美港市场宽度同步转弱，跨市场压力可能扩散。",
                "reasons": ["market_breadth_language_requires_breadth_evidence"],
            }],
        },
    }

    result = build_scenario_adjudication([cio])

    assert result["strongestAlternative"] == (
        "若后续证据支持这一情景：美港市场宽度同步转弱，跨市场压力可能扩散。"
    )


def test_red_team_challenge_is_matched_to_exact_department_claim():
    fundamental = _report(
        "FundamentalAgent",
        [("FundamentalAgent:1", "hypothesis", "比亚迪基本面显示明显下滑。")],
        key_claims=["比亚迪基本面显示明显下滑。"],
    )
    red = _report("RedTeamAgent", [("RedTeamAgent:1", "hypothesis", "需排除口径影响。")])
    red["challenges"] = [{
        "targetClaimId": "FundamentalAgent:1",
        "issueType": "overreach",
        "opposingScenario": "若下滑来自会计口径，主营业务可能未恶化。",
        "falsifier": "官方定期报告证实销量与毛利率同步下降。",
        "evidence_ids": ["ev:1"],
        "validationStatus": "hypothesis",
    }]
    red["semanticValidation"]["challenges"] = {
        "challenges": [{"targetClaimId": "FundamentalAgent:1", "status": "hypothesis"}],
    }

    verdicts = build_challenge_verdicts([fundamental, red])

    assert verdicts == [{
        "targetClaimId": "FundamentalAgent:1",
        "department": "FundamentalAgent",
        "claim": "比亚迪基本面显示明显下滑。",
        "originalStatus": "hypothesis",
        "verdict": "challenged",
        "issueType": "overreach",
        "opposingScenario": "若下滑来自会计口径，主营业务可能未恶化。",
        "falsifier": "官方定期报告证实销量与毛利率同步下降。",
        "evidenceIds": ["ev:1"],
        "validationStatus": "hypothesis",
    }]
