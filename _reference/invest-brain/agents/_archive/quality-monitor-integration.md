# 质量监控集成指南
Quality Monitor Integration Guide

**版本**: v0.9
**角色**: 质量审查员（Quality Reviewer）
**协作模式**: Python核心检查 + Claude深度审查

---

## 混合质量监控架构

### 工作流程

```
┌──────────────────────────────────────────┐
│  Phase 1: Python自动化检查（30秒）        │
├──────────────────────────────────────────┤
│  quality_monitor_core.py                 │
│    ├─ 数据真实性检查: 0-28分             │
│    ├─ 完整性检查: 0-25分                 │
│    └─ 市场分离检查: 0-5分                │
│                                          │
│  输出: core_scores.json                  │
│  自动评分: 0-58分                         │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│  Phase 2: Claude深度审查（3-5分钟）       │
├──────────────────────────────────────────┤
│  基于 agents/quality-reviewer.md         │
│    ├─ 读取 core_scores.json             │
│    ├─ 逻辑一致性审查: 0-28分             │
│    └─ 可操作性审查: 0-14分               │
│                                          │
│  输出: quality_review_final.yaml         │
│  最终评分: 0-100分                        │
└──────────────────────────────────────────┘
```

---

## Claude审查任务

### 1. 读取Python自动评分结果

**文件**: `core_scores.json`

**关键字段**:
```json
{
  "auto_score": 56,          // Python自动评分总分
  "data_accuracy": 28,       // 数据真实性
  "completeness": 23,        // 完整性（可能<25）
  "market_separation": 5,    // 市场分离
  "issues_found": 3,         // 发现的问题数量
  "issues": [...],           // 具体问题列表
  "passed": true             // 是否通过自动检查
}
```

### 2. 审查提示词模板

```
我已经使用 quality_monitor_core.py 完成了自动化检查，结果如下：

📊 **Python自动评分**: {auto_score}/58
  - 数据真实性: {data_accuracy}/28
  - 完整性: {completeness}/25
  - 市场分离: {market_separation}/5

⚠️ **发现问题**: {issues_found}个
{issues列表}

现在请你基于 agents/quality-reviewer.md 标准，执行以下深度审查：

1. **逻辑一致性**（26-28分）：
   - 风险评估与配置建议是否一致？
   - 时间线处理是否合理？
   - 因果链条是否完整？

2. **可操作性**（13-14分）：
   - 建议是否具体量化？
   - 执行时间窗口是否明确？
   - 风险应对触发条件是否清晰？

请生成最终质量评审报告（quality_review_final.yaml）。
```

### 3. Claude需要审查的维度

#### 3.1 逻辑一致性（Logic Consistency）: 26-28/28分

**检查要点**:

1. **风险评估与配置建议一致性**
   ```yaml
   场景1:
     风险评估: "VIX升至25，市场恐慌"
     配置建议: "增持风险资产至70%"
     问题: ❌ 矛盾 - 高风险环境不应激进
     扣分: -2分

   场景2:
     风险评估: "VIX回落至15，市场平静"
     配置建议: "维持现金20%观望"
     判断: ⚠️ 可能过于保守，需要解释理由
     扣分: -1分

   场景3:
     风险评估: "恒指下跌，南向资金大幅流入"
     配置建议: "增持港股ADR 15-20%"
     判断: ✅ 逻辑自洽 - 资金流入验证配置
     扣分: 0分
   ```

2. **时间维度处理合理性**
   ```yaml
   正确示例:
     - "9/26观察: VIX 15.29"
     - "10/16验证: VIX 25.31"
     - "事后修正: 应降低美股至40-45%"
     判断: ✅ 时间线清晰，事后验证标注明确

   错误示例:
     - "上周VIX上升"
     - "过去4周北向资金流入"
     判断: ❌ 模糊时间表述（应被Python检测）
   ```

3. **因果推理链完整性**
   ```yaml
   完整链条:
     观察 → 数据 → 推理 → 结论 → 建议

   示例:
     ✅ "南向+158亿（观察）→ 3.3σ极端（数据）→
         内地资金看好港股（推理）→ 资金流向验证（结论）→
         增持港股15-20%（建议）"

     ❌ "建议增持港股"（缺少支持链条）
   ```

**扣分标准**:
- 严重矛盾（风险与建议完全相反）: -3分
- 中等不一致（需要额外解释但缺失）: -2分
- 轻微逻辑跳跃（推理链不够紧密）: -1分

---

#### 3.2 可操作性（Actionability）: 13-14/14分

**检查要点**:

1. **配置建议具体性**
   ```yaml
   优秀 (14分):
     "降低美股至40-45%，其中科技30%+金融10%+现金5%"

   良好 (13分):
     "降低美股至40-45%"

   及格 (11-12分):
     "适度降低美股仓位"

   不及格 (<11分):
     "谨慎操作" "关注市场变化"
   ```

2. **执行时间窗口明确性**
   ```yaml
   优秀:
     "VIX突破20立即减仓5%，VIX突破25再减10%"
     "南向持续3日>100亿后加仓"
     "等待软件板块连续3日净流入转正"

   良好:
     "VIX>25时防御"
     "南向大幅流入时关注"

   模糊:
     "择机调整" "待时机成熟"
   ```

3. **风险应对触发条件清晰度**
   ```yaml
   优秀示例 - VIX三级止损:
     - Tier 1 Yellow: VIX≥20 → 减仓7%, 现金至22%
     - Tier 2 Red:    VIX≥25 → 减仓15%, 现金至37%
     - Tier 3 Emergency: VIX≥30 → 现金70%

   模糊示例:
     "市场波动加剧时减仓"（什么是"加剧"？）
     "风险上升后防御"（如何定义"上升"？）
   ```

**扣分标准**:
- 建议完全模糊（"谨慎操作"）: -3分
- 缺少量化标准（"适度增持"）: -2分
- 缺少时间窗口（"等待企稳"未定义）: -1分

---

### 4. 输出格式要求

Claude必须生成符合以下YAML格式的最终报告：

**文件名**: `quality_review_final.yaml`

```yaml
review_result:
  status: "通过" | "需修改" | "拒绝"
  overall_score: 95  # 总分0-100

  dimension_scores:
    logic_consistency: 26/28      # Claude手动评分
    completeness: 23/25           # 来自Python
    accuracy: 28/28               # 来自Python
    actionability: 13/14          # Claude手动评分
    market_separation: 5/5        # 来自Python

  python_auto_score:
    total: 56/58
    data_accuracy: 28/28
    completeness: 23/25
    market_separation: 5/5

  claude_judgment_score:
    total: 39/42
    logic_consistency: 26/28
    actionability: 13/14

  issues:
    - type: "逻辑清晰度"
      severity: "轻微"
      location: "简明版第1页"
      description: "部分仓位演化数据来源标注不够清晰"
      suggestion: "明确标注'基于观察文件'vs'基于市场数据'"
      deduction: 0  # 优化建议，不扣分

    - type: "可操作性优化"
      severity: "轻微"
      location: "A股配置建议"
      description: "'企稳'标准未量化"
      suggestion: "改为'连续3日净流入转正'"
      deduction: -1

  corrections_required: []  # 如果status="通过"则为空

  approval:
    can_publish: true
    iteration_count: 1
    max_iterations: 3
    reason: "Python自动检查56/58，Claude深度审查39/42，总分95/100，达到A级标准。"

  summary:
    strengths:
      - "✅ 数据真实性完美（28/28）- Python验证零捏造"
      - "✅ 市场分离完美（5/5）- VIX/北向/南向归属100%正确"
      - "✅ 逻辑一致性优秀（26/28）- 因果链完整"
      - "✅ 可操作性优秀（13/14）- 配置建议具体量化"

    weaknesses:
      - "⚠️ 完整性扣2分: 11 SPDR数据缺失（已在报告中警告）"
      - "⚠️ 可操作性扣1分: 部分触发条件可更具体"

    overall_assessment: "A级报告（95/100），达到发布标准，建议直接发布。"

timestamp: "2025-10-17T12:00:00"
report_file: "history/week_2025_09_26/v1/brief_report.md"
data_file: "market_data.json"
python_scores_file: "core_scores.json"
```

---

### 5. 审查决策树

```
┌─ 读取 core_scores.json
│
├─ Python自动评分 ≥ 52/58?
│  ├─ No → 自动拒绝（"❌ 拒绝"）
│  └─ Yes → 继续Claude审查
│
├─ 数据真实性 = 28/28?
│  ├─ No → 检查严重程度
│  │  ├─ <25 → 拒绝
│  │  └─ 25-27 → 警告，继续
│  └─ Yes → 继续
│
├─ 市场分离 ≥ 3/5?
│  ├─ No → 拒绝（v0.9核心要求）
│  └─ Yes → 继续
│
├─ Claude逻辑一致性审查（26-28分）
│  ├─ 风险与建议一致性
│  ├─ 时间维度处理
│  └─ 因果推理链
│
├─ Claude可操作性审查（13-14分）
│  ├─ 建议具体性
│  ├─ 时间窗口明确性
│  └─ 触发条件清晰度
│
├─ 计算总分 = Python(56) + Claude(39) = 95
│
└─ 最终决策:
   ├─ ≥90 且无严重问题 → "✅ 通过"
   ├─ 80-89 或1-2中等问题 → "⚠️ 需修改"
   └─ <80 或有严重问题 → "❌ 拒绝"
```

---

### 6. 常见审查场景

#### 场景1: Python完美，Claude发现逻辑问题

```yaml
Python结果:
  auto_score: 58/58  # 完美
  issues_found: 0

Claude审查发现:
  - 问题: "Page 1评估'高风险'，但Page 2建议'增持美股至70%'"
  - 类型: 逻辑矛盾
  - 扣分: -3分（逻辑一致性）

最终结果:
  - 逻辑一致性: 25/28
  - 总分: 58 + 38 = 96/100
  - 状态: "需修改"（严重逻辑矛盾必须修正）
```

#### 场景2: Python发现数据问题，Claude确认

```yaml
Python结果:
  auto_score: 53/58
  issues:
    - "11 SPDR数据缺失 (-5分)"

Claude审查:
  - 确认: "报告已明确标注数据缺失并警告"
  - 判断: 扣分合理，但已充分披露
  - 逻辑一致性: 28/28
  - 可操作性: 14/14

最终结果:
  - 总分: 53 + 42 = 95/100
  - 状态: "✅ 通过"（数据缺失已披露）
```

#### 场景3: 边界情况 - 90分临界

```yaml
Python: 52/58
Claude: 38/42
总分: 90/100

决策:
  - 检查是否有严重问题
  - 无严重问题 → "✅ 通过"
  - 有1个严重问题 → "⚠️ 需修改"
```

---

### 7. Claude执行检查清单

使用此清单确保完整审查：

```
□ 1. 读取并理解 core_scores.json
□ 2. 确认Python自动评分 ≥ 52/58
□ 3. 确认数据真实性 = 28/28（零容忍捏造）
□ 4. 确认市场分离 ≥ 3/5（v0.9要求）
□ 5. 阅读完整报告
□ 6. 逻辑一致性审查:
   □ 6.1 风险评估与配置建议一致性
   □ 6.2 时间线处理合理性
   □ 6.3 因果推理链完整性
□ 7. 可操作性审查:
   □ 7.1 配置建议具体量化
   □ 7.2 执行时间窗口明确
   □ 7.3 触发条件清晰
□ 8. 计算最终得分（Python + Claude）
□ 9. 判断通过/需修改/拒绝
□ 10. 生成 quality_review_final.yaml
□ 11. 如果"需修改"，提供具体修改建议
```

---

### 8. 与quality-reviewer.md的关系

**quality-reviewer.md** (原标准):
- 定义5维度评分标准
- 定义通过条件（≥90分）
- 定义零容忍捏造政策

**quality-monitor-integration.md** (本文档):
- 定义混合工作流（Python + Claude）
- 定义Claude具体审查任务
- 定义集成格式和决策树

**使用顺序**:
1. Python执行 → core_scores.json
2. Claude读取 core_scores.json
3. Claude基于 quality-reviewer.md 标准执行深度审查
4. Claude按本文档格式输出 quality_review_final.yaml

---

### 9. 优势总结

#### Python自动检查优势:
- ✅ **速度快**: 30秒完成56/58分评估
- ✅ **零容忍捏造**: 100%准确的数据验证
- ✅ **一致性**: 每次执行标准完全相同
- ✅ **可追溯**: JSON输出便于审计

#### Claude深度审查优势:
- ✅ **语义理解**: 判断逻辑一致性需要上下文理解
- ✅ **实用判断**: 评估建议可操作性需要经验
- ✅ **灵活性**: 处理特殊情况和边界问题
- ✅ **建设性反馈**: 提供改进建议而非仅扣分

#### 混合模式优势:
- ✅ **效率**: 1-2分钟完成完整质量审查（vs 纯Claude 5-8分钟）
- ✅ **准确性**: 机械检查100%准确 + 判断分析高质量
- ✅ **可扩展**: Python可轻松增加新检查项
- ✅ **最佳平衡**: 速度、准确性、灵活性兼顾

---

## 快速开始

### 命令行执行

```bash
# 1. Python自动检查（30秒）
python3 scripts/quality_monitor_core.py \
  --report history/week_2025_09_26/v1/brief_report.md \
  --data market_data.json \
  --output core_scores.json

# 2. Claude深度审查（在Claude Code中）
# 读取 core_scores.json，基于 quality-reviewer.md 执行审查
# 输出 quality_review_final.yaml
```

### 完整工作流脚本

参见 `scripts/run_full_qa.sh` 完整集成示例。

---

**最后更新**: 2025-10-17
**维护者**: 投研系统开发团队
