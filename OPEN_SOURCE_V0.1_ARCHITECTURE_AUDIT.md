# Evidence Writer｜Architecture / Contracts v0.1.2

**审计结论：CONDITIONAL PASS；不授权 runtime implementation。**  
**范围：最后一次 Contract 修订；不新增 Runner、Provider、Auditor、Writer、Final Review runtime 或 CI。**  
**日期：2026-09-14**

## 0. 结论与停线

Production 隔离、Claim 五分类、Derived hypothesis、Author Intent/Capability 无事实权限、Reference Library 的非 runtime 定位、版权/隐私边界、Public Regression 与 Private Holdout 分离均维持通过。

本版修正 v0.1.1 的 Contract 缺口：

1. WriterHandoff 和 WriterInput 都改为 self-contained；
2. operational stage status 与 Final Review 的 domain verdict 分离；
3. ReviewFinding 结构化；
4. 补齐可确定性验证的不变量和真实 SHA-256 digest 规则；
5. AuthorIntent 保留七字段并允许 `EMOTIONAL_STATE=UNSET`。

本文件、`contracts.schema.json`、`complete_chain.valid.yaml` 和最小 `.gitignore` 是唯一允许进入正式 GitHub Private 仓库的文件。**提交后立即停止，等待最终 Contract 审核。**

## 1. Production 隔离与正式仓库

正式仓库已核实为 Private `ciguo/evidence-writer`，当前为空，已授权账户具 admin/push 权限。Production 的 Google Drive、File/Folder ID、自动任务、运行路径、Manifest、每日生产链，以及 Topic Selection v1.1 audited、research-article-topic v1.1、audit-evidence-package v1.2.1-final、WRITER_INPUT 0.1、Capability Registry v0.1、chinese-article-drafter v1.4.0-rc1+input0.1、Final Review v1.0、IO Contract v0.1、Production Manifest v1.1 一律不读取、不写入、不依赖、不同步。

本环境不能解析 `github.com`，不能进行命令行 clone；因此本地 scratch 仅用作临时 Contract 验证区，正式提交通过已授权 GitHub 连接器直接写入 `ciguo/evidence-writer`。它不再是正式源仓库。Production 不复制、不挂载、不建立 symlink、不作为 remote。

最小 `.gitignore` 排除：`.env`、`.env.*`、`output/`、`private_holdout/`、`private_data/`、`tmp/`、`cache/`、`local_exports/`。

## 2. 公开资产边界

| 类别 | 处置 |
|---|---|
| 新写 Contract、通用政策、合成或明确授权 fixture | 可公开 |
| Production Prompt、真实文章、真实 Intent、Gold Corpus、编辑轨迹、私有评测 | Private / Exclude |
| 审计/Writer/Final Review 的通用机制 | Rewrite，不复制生产原文 |
| 密钥、ID、绝对路径、聊天记录、后台数据、揭盲材料、未确认版权正文 | Exclude |

Reference Library 继续不是 runtime 依赖。现代受版权保护作品默认 `link_only/no_quote`；`copyright_status=unknown` 也只链接。禁止 `write like X` 及同义功能。Private Holdout 永不入 Git，且不得默认使用 Gold Corpus、真实 Intent、私人文章、编辑轨迹或未经授权内容。

## 3. Contract 链与权限

```text
ResearchPackage
  → Auditor StageResult<WriterHandoff>
  → Adapter StageResult<WriterInput>
  → Writer StageResult<DraftArtifact>
  → Final Review StageResult<ReviewResult>
```

**唯一事实授权路径：**

```text
ResearchPackage（仅 Auditor 可读）
  → WriterHandoff.evidence_authority = WRITER_HANDOFF_ONLY
  → Writer
```

AuthorIntent 与 CapabilityPlan 都固定 `fact_authority=NONE`。Capability 只能影响组织、节奏、解释密度、情绪呈现、问题处理、结尾、知识呈现和作者位置；不能新增事实、数字、场景、动作、心理、动机、因果、机构意图或专业判断。

### 3.1 ResearchPackage

只供 Auditor 读取。它直接持有 `Source[]` 和统一 `Claim[]`；Claim 仅可为 `FACT | SIGNAL | HYPOTHESIS | LIMIT | FORBIDDEN`。每个 Claim 同时拥有 `source_ids` 与 `supporting_claim_ids`，所以 `DERIVED` hypothesis 可以由合法 Claims 推导而不必拥有直接 URL。

### 3.2 WriterHandoff：self-contained safe package

WriterHandoff 不再使用 `accepted_claim_ids` 作为正文授权的唯一内容。它必须直接携带：

- `sources[]`：仅限被 handoff Claims 引用的必要来源元数据；
- `authorized_claims[]`：允许 Writer 使用的 FACT、SIGNAL、HYPOTHESIS；
- `boundary_claims[]`：所有相关 LIMIT 与 FORBIDDEN；
- `evidence_authority=WRITER_HANDOFF_ONLY`；
- `canonical_json_sha256`。

Writer 不得读取 ResearchPackage；也不得通过 Capability、Intent 或外部常识补证。FORBIDDEN 不得出现在 `authorized_claims`。

### 3.3 AuthorIntent：七字段与自动模式

必须完整保留：

```text
WHY_NOW
CENTRAL_TENSION
CORE_POSITION
EMOTIONAL_STATE
DISTANCE_TO_OBJECT
DO_NOT_BECOME
ENDING_DESTINATION
```

`EMOTIONAL_STATE` 可明确为 `UNSET`，表示自动/低干预模式；不是缺失字段，也不提供任何事实权限。

### 3.4 CapabilityPlan

Plan 直接持有 0–3 条结构化选择：`CAPABILITY_ID`、`OBJECTIVE`、`EXECUTION_DIRECTIVE`、`SKIP_IF`、`SUCCESS_CHECK`。每个 Capability ID 必须存在于指定 Registry version；Registry 是独立的非事实控制资产，WriterInput 不加载整个 Reference Library。

### 3.5 WriterInput：self-contained

`WriterInput` 直接嵌入 `evidence_handoff: WriterHandoff`、`author_intent: AuthorIntent` 与 `capability_plan: CapabilityPlan`，禁止 `"writer_handoff"` 等裸字符串别名。不得引入数据库、RAG、resolver 或隐藏上下文。

## 4. StageResult / ArtifactEnvelope

每个 operational stage 用统一 `StageResult` 表达：

```yaml
stage: AUDITOR | ADAPTER | WRITER | FINAL_REVIEW
stage_status: PASS | FAIL | BLOCKED
artifact_envelope: # 仅 PASS 必需
  artifact_type:
  artifact_schema_version:
  canonical_json_sha256:
  artifact:
error_code: # FAIL / BLOCKED 必需
reason:     # FAIL / BLOCKED 必需
```

`PASS` 必须包含 artifact；`FAIL/BLOCKED` 必须包含 `error_code` 和 `reason`，**不得强制要求正文或其他 artifact**。Final Review 的内容结论不再滥用 stage_status，而是放在 `ReviewResult.review_verdict`：`PASS | LOCAL_REPAIR | RETURN_TO_WRITER`。

## 5. ReviewResult / ReviewFinding

ReviewFinding 不得是 arbitrary array item；每项至少为：

```yaml
finding_type: EXTERNAL_FACT | NUMBER_TIME_PLACE | ACTION | SCENE | QUOTE | GROUP_TRAIT | PSYCHOLOGY | MOTIVE | CAUSALITY | PROFESSIONAL_JUDGMENT
location: {start_line: 1, end_line: 1}
original_text:
evidence_claim_ids: []
action: FLAG | LOCAL_REPAIR | RETURN_TO_WRITER
repaired_text: null
reason:
```

`review_verdict=PASS` 或 `LOCAL_REPAIR` 必须有 `final_text`；`RETURN_TO_WRITER` 必须有非空 `return_reason`。LOCAL_REPAIR 只允许删除、缩小或降级未经授权内容，不能补新证据；若删除导致主线坍塌，则 RETURN_TO_WRITER。Final Review 不作为第二 Writer，不整篇润色。

## 6. Deterministic invariants

后续 implementation 必须 fail closed 检查：

1. Source ID 唯一，Claim ID 唯一；
2. 所有 source/claim 引用均存在；不得 dangling；
3. `supporting_claim_ids` 不得 self-reference，依赖图不得 cycle；
4. WriterHandoff 的 authorized 与 prohibited/boundary Claim ID 不相交；
5. FORBIDDEN 不得授权给 Writer；
6. `AUTHOR_HYPOTHESIS` 只能配 `HYPOTHESIS`，不得伪装 FACT/SIGNAL/LIMIT/FORBIDDEN；
7. Capability ID 必须存在于声明的 Registry version；
8. Capability 数量为 0–3，Intent/Plan 的 `fact_authority=NONE`；
9. 所有 digest 符合真实 SHA-256 格式，并对相应 Contract canonical JSON 复算一致；
10. StageResult 与 ReviewResult 的条件字段满足本版规则。

JSON Schema 负责结构和局部 enum/条件字段；引用完整性、图环、跨对象相交、Registry membership 与 digest 复算属于 deterministic policy layer，不得让 LLM 判断。

## 7. Digest 规范

所有 Contract digest 必须是：

```text
sha256:<64 个小写十六进制字符>
```

计算对象为对应 artifact 的 JSON 值，使用 RFC 8785 JSON Canonicalization Scheme（JCS）序列化为 UTF-8 字节，再计算 SHA-256。不得对 YAML 原文、含格式化空白的 JSON、或含 digest 字段自身的循环对象计算。若 artifact 包含 `canonical_json_sha256`，计算时将该字段排除；验证时以同一规则重算。

## 8. Regression / Holdout / License

Public regression 使用 synthetic、public-domain、licensed 或明确授权材料，不做全文一致性。最低覆盖：factual penetration、hypothesis laundering、unauthorized predicate、fabricated experience、unsupported psychology/causality、institutional motive speculation、input contract、zero-capability fallback。

首发前仍须分开审计代码、spec、文档、Reference Card、fixture 与第三方依赖。Apache-2.0 与 MIT 仅为候选；在权利清单完成前不宣布统一顶层 License。

## 9. 本轮验证与 Stop Condition

本轮以 Schema validation 和临时 invalid fixtures 验证以下失败闭合情形：dangling claim、cyclic claim、Capability >3、fact_authority 非 NONE、FORBIDDEN 被授权、fake SHA-256、RETURN_TO_WRITER 缺 return_reason。

完成正式仓库提交 `ARCHITECTURE_CONTRACTS_V0.1.2` 后，立即停止。未收到明确 `IMPLEMENTATION AUTHORIZED` 前，不得创建或运行 Runner、Provider、Auditor runtime、Writer runtime、Final Review runtime、CI 或测试实现。
