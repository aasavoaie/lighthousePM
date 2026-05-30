# AGENTS

Guidelines for AI agents (Codex) working in this repository.

---

## 🎯 Goal

Build a backend service that:
- Ingests Jira data
- Computes deterministic metrics
- Produces release risk signals
- Exposes structured APIs

---

## 🧠 Core Principles

### 1. Deterministic first
- All outputs must be computed explicitly
- No inference or guess-based logic
- No hidden behavior

### 2. Simplicity over architecture
- Single service
- No microservices
- No unnecessary abstractions

### 3. Clarity over cleverness
- Code must be easy to read and debug
- Prefer explicit logic

### 4. Trust is critical
- Every signal must be explainable
- Every metric must be reproducible

---

## 🏗️ Architecture Rules

- FastAPI for API
- PostgreSQL for storage
- Service-based structure:

| Service | Responsibility |
|--------|---------------|
| jira_service | Jira API access |
| sync_service | Data ingestion |
| analytics_service | Metric computation |
| signal_service | Risk rules |

- No business logic in API routes

---

## 📊 Metrics Rules

- Metrics must be:
  - deterministic
  - testable
  - documented

- Avoid:
  - implicit assumptions
  - undocumented thresholds

---

## 🚦 Signal Rules

- Signals must:
  - be rule-based
  - include explicit reasons
  - be stored in DB

Example:

```json
{
  "signal": "RED",
  "reasons": [
    "2 open blockers",
    "Reopen rate above threshold"
  ]
}

--- 

## 🔌 API Rules
RESTful endpoints
Structured JSON responses
Consistent naming
Thin controllers (no business logic)

---

## 🧱 Coding Style
Use type hints
Prefer small functions
Avoid deep inheritance
Keep modules focused

---

## 📁 File Responsibilities
jira_service.py
External API calls
Response normalization
sync_service.py
Orchestrates ingestion
Upserts DB records
analytics_service.py
Computes metrics
signal_service.py
Applies rules
Produces release signals

---

## ❌ Do NOT
Add unnecessary abstraction layers
Introduce complex frameworks
Optimize prematurely
Mix business logic into API routes

---

## 🧪 Testing

Focus on:

Metric correctness
Signal logic

Include:

edge cases
empty datasets
threshold boundaries
🧭 Priorities
Jira ingestion
Database schema
Metrics engine
Signal engine
API endpoints
Tests

---

## ✅ Definition of Done

A task is complete when:

logic is deterministic
results are testable
API is stable
output is structured and clear
