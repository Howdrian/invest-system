import json

from scripts.audit_semantic_quality import audit_semantic_quality


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_semantic_quality_audit_rejects_leaked_rejected_claim(tmp_path):
    docs = tmp_path / "docs"
    date = "2026-07-12"
    rejected = "没有证据的确定性结论"
    _write_json(docs / "reports" / f"{date}.artifact.json", {
        "researchReliability": {"audited": True, "headlineSafe": True, "label": "较高可信"},
        "readerV3": {
            "hero": {"oneLine": rejected},
            "adjudication": {
                "baseCase": "震荡",
                "strongestAlternative": "若宽度恶化则转弱",
                "judgment": "维持震荡",
            },
        },
    })
    _write_json(docs / "agent_memos" / date / "CIOAgent.json", {
        "schema": "agent_memo_v1",
        "agent": "CIOAgent",
        "agentRuntime": "LLM",
        "semantic_validation": {
            "claims": [{
                "claimId": "c1",
                "text": rejected,
                "safeText": "",
                "status": "rejected",
            }],
        },
    })

    result = audit_semantic_quality(docs, date)

    assert result["ok"] is False
    assert any(item.startswith("rejected_claim_leaked") for item in result["errors"])


def test_semantic_quality_audit_accepts_conditional_scenario(tmp_path):
    docs = tmp_path / "docs"
    date = "2026-07-12"
    _write_json(docs / "reports" / f"{date}.artifact.json", {
        "researchReliability": {"audited": True, "headlineSafe": True, "label": "可用，含待确认情景"},
        "readerV3": {
            "hero": {"oneLine": "当前维持震荡判断。"},
            "reliability": {
                "headlineSafe": True,
                "headlineEvidenceSupported": True,
            },
            "adjudication": {
                "baseCase": "震荡",
                "strongestAlternative": "若宽度恶化则转弱",
                "judgment": "维持震荡",
            },
        },
    })
    for index in range(11):
        _write_json(docs / "agent_memos" / date / f"Agent{index}.json", {
            "schema": "agent_memo_v1",
            "agent": f"Agent{index}",
            "agentRuntime": "LLM",
            "semantic_validation": {
                "claims": [{
                    "claimId": f"c{index}",
                    "text": "市场可能转弱",
                    "safeText": "待验证情景：市场可能转弱",
                    "status": "hypothesis",
                }],
            },
        })

    result = audit_semantic_quality(docs, date)

    assert result["ok"] is True
    assert result["conditionalClaims"] == 11
