# ADR 0004: Prefer Official WeCom Channel Over Automation

## Status

Accepted

## Date

2026-03-11

## Implementation Status

Complete

Last reviewed: 2026-03-12

Notes:

- The supported messaging path is built around official WeCom callback and API
  integration.
- Automation-based account control is not the shipped default transport.
- Any future production move toward automation should supersede this ADR
  explicitly rather than arrive as an incremental implementation drift.

## Context

The product needs a durable messaging channel for doctor-facing assistant usage.
One requested direction was direct conversation with a WeCom personal account
without relying on WeCom KF or a miniapp.

We reviewed three families of options:

- official WeCom self-built application integration
- Wechaty-style WeCom automation such as `WorkPro`
- personal-WeChat bot stacks such as `ChatGPT-on-WeChat`

This system handles medical workflow state, draft confirmation, patient binding,
and accuracy-sensitive record writes. The transport layer therefore needs stable
identity, predictable delivery, low operational risk, and a supportable failure
model.

Automation-based account control may be acceptable for short-lived internal
experiments, but it creates a weaker foundation for a formal medical product
channel.

## Decision

Adopt official WeCom application integration as the formal supported messaging
channel.

Specifically:

- the product should target official WeCom callback/API integration first
- Wechaty-style account automation is not an approved product transport
- personal-WeChat bot projects are not an approved product transport
- "personal WeChat directly chatting with a WeCom personal account" is not an
  MVP requirement for the formal supported path unless it is later supported by
  the official WeCom channel model

If an owner-only experiment is needed, an automation adapter may be built as an
isolated PoC. That PoC must not redefine the product transport decision or
become the default production path.

## Consequences

- channel integration work should be structured as a thin official WeCom
  adapter in front of the existing backend
- doctor workflow logic, patient state, and persistence rules should remain in
  this repo's core services, not in the transport adapter
- future plans should not assume arbitrary public personal-WeChat access as part
  of the supported MVP
- if a later review proposes Wechaty or similar automation for production use,
  it must explicitly justify why this ADR should be superseded
