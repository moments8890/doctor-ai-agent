# WeCom Channel Choice Comparison

## Date

2026-03-11

## Goal

Choose the right doctor-facing messaging transport for a formal WeCom
integration, with specific attention to whether the system should rely on
official WeCom integration or automation-based account control.

## Options Reviewed

### 1. Official WeCom Self-Built Application

What it is:

- official callback/API-based integration
- stable fit for a thin transport adapter in front of the current backend

Strengths:

- strongest long-term supportability
- clearer identity and session mapping
- cleaner operational and compliance posture
- better fit for medical workflow, audit, and write-path controls

Weaknesses:

- may not deliver the exact "personal WeChat directly to WeCom personal
  account" UX that motivated the exploration
- product scope may need to stay within officially supported WeCom entrypoints

### 2. Wechaty + WorkPro

What it is:

- WeCom account automation through the Wechaty ecosystem
- closest technical path to direct account-style conversational behavior without
  using official WeCom KF

Strengths:

- fast path to an owner-only proof of concept
- can validate whether direct chat behavior is actually valuable before deeper
  product investment

Weaknesses:

- automation dependency instead of first-party application integration
- weaker operational predictability and supportability
- higher product risk if used as a real medical channel
- introduces a second system boundary that does not improve core assistant
  accuracy

### 3. Personal WeChat Bot Projects

What it is:

- personal WeChat automation examples such as `ChatGPT-on-WeChat`

Strengths:

- easy to understand as a simple bot demo
- useful only as a reference for transport prototyping

Weaknesses:

- not a WeCom product integration strategy
- poor fit for doctor identity, controlled rollout, and medical workflow state
- too demo-oriented to serve as system infrastructure

## Comparison Summary

For this product, the channel decision should be driven by:

- reliability of message delivery and identity
- compatibility with explicit draft confirmation and patient-binding rules
- maintainability of the transport layer
- ability to keep all medical logic in the backend rather than in the channel

Against those criteria, official WeCom self-built application integration is the
best fit.

Wechaty `WorkPro` remains useful only as a narrow internal experiment if the
team later wants to test direct account-style chat behavior. It should not be
the default integration path.

Personal WeChat bot repositories should be treated as demo references only.

## Decision

Use official WeCom integration as the formal supported channel.

This means:

- no product dependency on Wechaty-style automation
- no product dependency on personal-WeChat bot stacks
- no assumption that arbitrary personal-WeChat access is part of the supported
  MVP

The formal supported architecture should be:

1. receive official WeCom callback/webhook traffic
2. map sender/application metadata into the current doctor/session model
3. call the existing backend workflow and AI pipeline
4. return the assistant response through the official WeCom send path

## MVP Boundary

For MVP, the channel layer should stay intentionally narrow:

- one official WeCom transport
- text-first interaction
- no transport-owned medical workflow logic
- no divergence from the existing pending draft / confirmation contract

If direct personal-account chat remains strategically important, capture that as
a separate exploratory PoC rather than weakening the formal channel decision.
