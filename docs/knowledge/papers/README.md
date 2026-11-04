# Papers and surveys

One line each; the "ADF" column says what the paper changes or justifies here. ⚠ = verify id/venue before citing; "verified" entries were checked against arXiv/publisher pages on the date given.

| Id | Reference | ADF relevance | Concepts |
| --- | --- | --- | --- |
| PAP-01 | Greshake et al. 2023, *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*, arXiv:2302.12173 | Defines the attacker of ADR 0026: content the agent reads. Justifies `cannot_authorize`. | taint, THR-02 |
| PAP-02 | Willison 2025, *The lethal trifecta for AI agents* (blog, 2025-06) | The prioritisation axis; vocabulary of `coverage.md`. | THR-01..03 |
| PAP-03 | Beurer-Kellner et al. 2025, *Design Patterns for Securing LLM Agents against Prompt Injections*, arXiv:2506.08837 | Catalogue of structural patterns. ADF = action-selector + context-minimisation applied to effects, outside the model. | PDP, effect class |
| PAP-04 | Debenedetti et al. 2025, *Defeating Prompt Injections by Design* (CaMeL), arXiv:2503.18813 | Deterministic capability/taint tracking; closest relative of `taint`. Shows what ADF does **not** do (flow inside the model). | taint, ADR 0029 |
| PAP-05 | Debenedetti et al. 2024, *AgentDojo*, arXiv:2406.13352 | The standard benchmark. ADF does not compete; it measures deny/evidence, not attack success rate. | anti-goal: own benchmark |
| PAP-06 | Shi et al. 2025, *Progent: Programmable Privilege Control for LLM Agents*, arXiv:2504.11703 | Declarative per-call policy, default deny, inside the agent runtime. ADF adds the PEP at the effect and offline evidence. | PDP, bindings |
| PAP-07 | Costa, Köpf, Kolluri, Paverd, Russinovich, Salem, Tople, Wutschitz, Zanella-Béguelin (Microsoft) 2025, *Securing AI Agents with Information-Flow Control* (FIDES), arXiv:2505.23643 (v1 2025-05-29, v2 2025-09-03) — verified 2026-11-04 | IFC labels as the theory behind `taint` and `delivery_mode`. | ADR 0029 |
| PAP-08 | Zhan et al. 2024, *InjecAgent*, arXiv:2403.02691 | Attack taxonomy via tool output (direct harm vs data stealing) maps to effect classes. | THR-02, THR-03 |
| PAP-09 | Guo et al. 2024, *RedCode: Risky Code Execution and Generation Benchmark for Code Agents*, arXiv:2411.07781 | Source of risky-execution cases for `agent_config_policy_v1` and the write effect. | ADR 0028, 0032 |
| PAP-10 | Hou et al. 2025, *Model Context Protocol (MCP): Landscape, Security Threats, and Future Research Directions*, arXiv:2503.23278 | MCP lifecycle threats (install, update, rug-pull) → registry pin. | ADR 0031, THR-06 |
| PAP-11 | Radosevich & Halloran 2025, *MCP Safety Audit*, arXiv:2504.03767 | Concrete MCP exploits (RCE, credential theft) as eval seeds. | ADR 0031 |
| PAP-12 | OWASP GenAI Security Project, *Top 10 for Agentic Applications 2026* (published 2025-12-09) — verified 2026-11-04 | Mandatory mapping table in ADR 0026. | ASI01–10 |
| PAP-13 | Meta 2025, *Agents Rule of Two*; Google 2025, *An Introduction to Google's Approach for Secure AI Agents* | Industry phrasings of the trifecta; language for AppSec conversations. | positioning |
| PAP-14 | Kim, Choi, Lee 2025, *Prompt Flow Integrity to Prevent Privilege Escalation in LLM Agents*, arXiv:2503.15547 (2025-03-17) — verified 2026-11-04 | Privilege separation by flow; reference for subagent principals. | ADR 0033 |
