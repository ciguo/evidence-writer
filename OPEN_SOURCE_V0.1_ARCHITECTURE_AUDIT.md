# Evidence Writer｜Contract Final Hardening v0.1.3

**状态：Contracts 条件冻结；不授权 runtime implementation。**  
**范围：仅 Contract hardening 与 Contract fixtures；不重做 Architecture。**  
**日期：2026-09-14**

## 0. 结论与停止条件

v0.1.2 已通过的 Production 隔离、WriterHandoff/WriterInput self-contained、五类 Claim、AuthorIntent 七字段与 UNSET、Capability fact_authority=NONE、Reference Library 非 runtime、现代版权 link_only/no_quote、Public Regression / Private Holdout 隔离、Provider abstraction、Topic Selection 不进入 v0.1 core，全部保持不变。

v0.1.3 只修复 Contract 漏洞：顶层 stage 身份、Claim Authorization Matrix、boundary 空集、完整 artifact provenance、ReviewResult 条件语义、failure output 关闭。本轮完成并提交后立即停止，等待 IMPLEMENTATION AUTHORIZED。

## 1. 正式仓库与隔离

正式源仓库为 Private [ciguo/evidence-writer](https://github.com/ciguo/evidence-writer)。Production 的 Google Drive、File/Folder ID、自动任务、运行路径、Manifest、每日生产链及其既有基线均不读取、不写入、不依赖、不同步。

本环境不能解析 github.com，故无法用命令行 clone；scratch 只作为临时验证区。正式文件通过已授权 GitHub 连接器直接写入 Private repo，不将 scratch 当作正式源仓库。Production 不复制、不挂载、不建立 symlink、不作为 remote。

## 2. 顶层 Stage 绑定

顶层字段不再仅引用泛型 StageResult：

| 顶层字段 | 唯一允许 stage | PASS artifact |
|---|---|---|
| auditor_result | AUDITOR | WriterHandoff |
| adapter_result | ADAPTER | WriterInput |
| writer_result | WRITER | DraftArtifact |
| final_review_result | FINAL_REVIEW | ReviewResult |

StageResult.stage_status 仅表达运行状态：PASS / FAIL / BLOCKED。PASS 必有 ArtifactEnvelope；FAIL/BLOCKED 必有 error_code 和 reason，并禁止携带 artifact_envelope。可选 diagnostic 仅为调试，不进入 artifact provenance chain，也不得被任何后续 stage 消费。

## 3. Claim Authorization Matrix

Claim 仍为统一模型：FACT / SIGNAL / HYPOTHESIS / LIMIT / FORBIDDEN。下列规则是 Schema + deterministic policy 的共同硬门：

| 条件 | 允许 / 必须 |
|---|---|
| SOURCE_BACKED | source_ids 至少 1 个 |
| DERIVED | supporting_claim_ids 至少 1 个 |
| AUTHOR_HYPOTHESIS | 只能是 HYPOTHESIS，allowed_use 只能为 [qualify] |
| FACT 且含 state | verification_status=VERIFIED |
| FACT 且 PARTIAL | allowed_use 只能为 [qualify] |
| HYPOTHESIS | allowed_use 只能为 [qualify] |
| LIMIT | allowed_use 只能为 [limit] |
| FORBIDDEN | allowed_use 只能为 [forbid]，且状态必须 FORBIDDEN |

WriterHandoff 的 authorized_claims 仅可承载通过此矩阵的 FACT、SIGNAL、HYPOTHESIS；UNVERIFIED/PARTIAL FACT 不得取得无条件 state，HYPOTHESIS 不得 state，FORBIDDEN 永远不得授权。

## 4. WriterHandoff / WriterInput

WriterHandoff 继续是 self-contained safe package，不读取 ResearchPackage，直接含：

- 必要 sources；
- authorized_claims（FACT/SIGNAL/HYPOTHESIS）；
- boundary_claims（LIMIT/FORBIDDEN，允许空数组）；
- evidence_authority=WRITER_HANDOFF_ONLY；
- input_artifact_digest，指向 ResearchPackage envelope digest。

没有 FORBIDDEN 不是错误；存在 FORBIDDEN 时必须满足 Authorization Matrix，且不得进入 authorized_claims。

WriterInput 继续直接嵌入 evidence_handoff、author_intent 和 capability_plan，不用裸字符串别名、数据库、RAG、resolver 或隐藏上下文。它的 input_artifact_digest 指向 WriterHandoff envelope digest。

## 5. 唯一 Digest 位置与 provenance chain

Artifact 的自身 digest 唯一存放在 ArtifactEnvelope.canonical_json_sha256。内部 artifact 不出现 canonical_json_sha256。ArtifactEnvelope.artifact_schema_version 作为外层声明保留，但必须与内部 artifact.schema_version 精确一致；内部版本是领域对象的版本真源，外层字段只用于拒绝错配 envelope。

Digest 固定为：

    RFC 8785 JCS canonical JSON → UTF-8 bytes → SHA-256

格式为 sha256: 后接 64 个小写十六进制字符。任何 policy validator 必须复算；不得对 YAML 原文、格式化 JSON 或包含 envelope digest 的循环对象计算。

权威 provenance 字段如下：

    WriterHandoff.input_artifact_digest  ← ResearchPackage envelope digest
    WriterInput.input_artifact_digest    ← WriterHandoff envelope digest
    DraftArtifact.input_artifact_digest  ← WriterInput envelope digest
    ReviewResult.reviewed_draft_digest   ← DraftArtifact envelope digest

每个链接都由 deterministic policy 精确比对，不接受同一内容但不同 digest 的替代。

## 6. Final Review Contract

ReviewResult.review_verdict 与 operational status 分离：

| verdict | 约束 |
|---|---|
| PASS | 必有 final_text，不得有 RETURN_TO_WRITER finding |
| LOCAL_REPAIR | 必有 final_text，至少一个 LOCAL_REPAIR finding；每个该 action 都必须有非空 repaired_text |
| RETURN_TO_WRITER | 必有 return_reason，至少一个 RETURN_TO_WRITER finding |

每个 ReviewFinding 必须有 finding_type、location、original_text、evidence_claim_ids、action、repaired_text、reason。evidence_claim_ids 只接受唯一 Claim ID 格式；end_line >= start_line 由 deterministic policy 检查。Final Review 仍只允许标记、局部删除/缩小/降级，不得补证据或整篇重写。

## 7. Deterministic policy invariants

后续实现必须 fail closed 检查：唯一 Source/Claim ID、无 dangling source/claim、无 self-reference、无 claim dependency cycle、授权/边界 Claim ID 不相交、FORBIDDEN 不授权、AUTHOR_HYPOTHESIS 类型与权限、Capability Registry membership、0–3 Capability、Intent/Plan 无事实权限、所有 digest 重算与 provenance 链、envelope/internal schema 对应、ReviewFinding Claim ID 与行号、Stage failure artifact 禁止。

JSON Schema 负责字段结构、enum、部分 conditional 约束；跨对象引用、图、digest 与 Registry membership 只由确定性代码检查，不能交给 LLM。

## 8. Fixtures、版权与 Holdout

contract_fixtures/negative_cases.yaml 记录 17 个 Contract 负例：保留 v0.1.2 的 7 例，并新增顶层 stage 错位、未验证 FACT state、HYPOTHESIS state、SOURCE_BACKED 无来源、DERIVED 无依据、schema version 不一致、PASS + RETURN finding、LOCAL_REPAIR 无 repaired text、错误 Draft digest 等。

Fixture 只用合成材料。Reference Library 不进入 runtime；现代受版权保护作品默认 link_only/no_quote；Private Holdout 永不入 Git，且不默认使用 Gold Corpus、真实 Intent、私人文章、编辑轨迹或未经授权内容。Package/spec 版本继续分离；License 只做兼容性审计，未宣布最终顶层 License。

## 9. Stop Condition

完成提交 CONTRACT_FINAL_HARDENING_V0.1.3 后停止。未收到明确 IMPLEMENTATION AUTHORIZED 前，不得开始 Runner、Provider、Auditor runtime、Writer runtime、Final Review runtime、CI 或任何生产实现。
