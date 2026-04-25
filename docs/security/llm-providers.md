# LLM Provider Data-Handling Register

Tracks what each LLM provider does with the prompts and completions that pass
through their inference API: training-on-inputs default, retention period,
opt-out controls, contractual status with us.

This is the source of truth for **Area #3 / Finding C** of the security audit.
Update this file whenever a provider's terms change or a new DPA is signed.

## How this register is used

- The **PHI egress gate** (`src/infra/llm/egress.py`) classifies each provider
  as LOCAL / IN_CHINA / CROSS_BORDER and gates outbound traffic accordingly.
  See egress.py header comment for the policy.
- **This file** captures the contractual / policy layer that the gate can't
  enforce: whether the provider trains on inputs, how long they retain
  prompts, whether you have a Data Processing Agreement.
- A `Verified` row reads "yes" only when (a) you have a signed enterprise DPA
  with the provider AND (b) the technical control (e.g. an API header, an
  account toggle) is wired and tested.

## Provider register

> Notation: `?` = unknown / not yet confirmed. Treat as worst-case until verified.

### Currently active on prod

| Provider | Tier | Trains on inputs by default? | Retention (default) | API opt-out | Account opt-out | DPA signed? | Verified |
|---|---|---|---|---|---|---|---|
| **SiliconFlow** | IN_CHINA | ? (public docs silent; marketing claims "no data stored") | ? | none documented | enterprise BYOC available | TODO | no |
| **Ollama (local)** | LOCAL | no — runs on the Tencent CVM, no egress | n/a | n/a | n/a | n/a | yes (by topology) |

### Configured but not selected (would need PHI flags to enable)

| Provider | Tier | Trains on inputs by default? | Retention (default) | API opt-out | Account opt-out | DPA signed? | Verified |
|---|---|---|---|---|---|---|---|
| **Tencent LKEAP** | IN_CHINA | ? (public docs silent) | ? | none documented | ? | TODO | no |
| **DeepSeek (direct)** | IN_CHINA | **yes** (per public privacy policy) | ~30d inputs / ~180d backups | none documented | UI toggle "Improve the model for everyone" — does NOT cover API per current reading | TODO | no |
| **DashScope (Alibaba Bailian)** | IN_CHINA | ? (public docs silent on training) | ? | none documented | ? | TODO | no |
| **Groq** | CROSS_BORDER | per US policy; review for clinical use | ? | none documented | ? | n/a unless cross-border permitted | no |
| **Gemini (Google)** | CROSS_BORDER | depends on tier (free vs paid API; paid claims no training) | varies | none for chat/completions | account-level | n/a unless cross-border permitted | no |
| **OpenAI** | CROSS_BORDER | no for API by default since 2023 | 30d zero-retention available on request | none for default; ZDR contract | account-level | n/a unless cross-border permitted | no |
| **Cerebras / SambaNova / OpenRouter / xAI** | CROSS_BORDER | varies | varies | none | varies | n/a unless cross-border permitted | no |

## Required actions for medical data

Before sending PHI to any IN_CHINA provider routinely:

1. **Sign a DPA** (data processing agreement) that explicitly states:
   - No training on inputs.
   - Retention ≤ 30 days, or zero retention available.
   - Right to audit / certify deletion.
   - PIPL Article 21 obligations (the provider as processor binds to your
     instructions).
2. **Confirm the technical control matches the contract.** A clause that
   says "we don't train" but no API-level switch means you trust the
   provider's word; add monitoring (sample prompts and check whether they
   resurface in model outputs over time, where feasible).
3. **Update the table above** with `Verified: yes` once both are done.

Before sending PHI to any CROSS_BORDER provider, ALL of the above PLUS:

4. **Patient consent** for cross-border transfer (PIPL Art. 39). Generic
   "we may share with third parties" language is insufficient — Art. 39
   requires the foreign recipient be named and the categories of data spelled
   out.
5. **PIPL Art. 38 mechanism**: pick one of (a) CAC-led security assessment,
   (b) standard contractual clauses filed with CAC, or (c) certified
   protection certification. Currently most providers in the CROSS_BORDER
   list have no path here — assume "no" until shown otherwise.
6. **Set both env flags**: `PHI_CLOUD_EGRESS_ALLOWED=true` AND
   `PHI_CROSS_BORDER_ALLOWED=true` on the host. Default is unset → blocked.

## Defence in depth (independent of provider promises)

Two cheap controls reduce blast radius regardless of the contract terms:

- **Redaction before egress.** Replace `Patient.name` with "患者X" and
  `Patient.phone` with `[redacted]` in the prompt assembly. No quality loss
  for clinical reasoning, and a leaked prompt is meaningfully less useful
  to an attacker. See `docs/security/llm-providers.md#future-redaction`
  (TODO) — not yet implemented.
- **Prompt-injection containment.** Already shipped in
  `src/agent/prompt_safety.py`: untrusted content is HTML-escaped inside
  XML trust boundaries so a malicious patient message can't break out and
  exfiltrate the system prompt or knowledge base.

## Sign-off / freshness

| Field | Value |
|---|---|
| Last reviewed | 2026-04-26 |
| Active prod provider for routing/structuring/conversation | SiliconFlow (per `config/runtime.json`) |
| Active prod provider for vision | Ollama on the Tencent CVM (no egress) |
| Open follow-ups | Sign DPAs with SiliconFlow + Tencent LKEAP. Confirm SiliconFlow's "no data stored" claim contractually. Re-check DeepSeek API training opt-out semantics if their tier is bumped to enterprise. |
