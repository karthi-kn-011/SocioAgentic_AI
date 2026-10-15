# AI Social Media Agent — Implementation Roadmap

**Document Version:** 2.1  
**Project:** ICT Project 3 — AI Social Media Agent  
**Date:** October 2026  
**Status:** Approved for Intelligent AI Content Generation

---

## Roadmap Overview

This roadmap defines the step-by-step engineering plan to build the **AI Social Media Agent** from scratch. Development is broken into 10 manageable, modular phases. UI/UX was prioritized in Phase 3 to establish visual clarity. Phase 4 establishes the intelligent, theme-aware, platform-adaptive AI generation and self-correcting review engine.

```mermaid
gantt
    title 10-Phase Phased Engineering Roadmap
    dateFormat  X
    axisFormat  Phase %s
    section Foundations & UI
    Phase 1 : Architecture & Specification        :done,    p1, 0, 1
    Phase 2 : Foundation, Database & Design System :done,    p2, 1, 2
    Phase 3 : Frontend Shell & Core UI/UX          :done,    p3, 2, 3
    section Core Intelligence & Services
    Phase 4 : Intelligent AI Agents & LangGraph   :active,  p4, 3, 4
    Phase 5 : Core Services, HITL & Scheduler      :         p5, 4, 5
    Phase 6 : REST API & Frontend Integration      :         p6, 5, 6
    section Integrations & Audit
    Phase 7 : OAuth & Social Platform Integrations :         p7, 6, 7
    Phase 8 : Analytics & Activity                 :         p8, 7, 8
    section Verification & Release
    Phase 9 : Testing, Security & Docker           :         p9, 8, 9
    Phase 10: Documentation & Final Demo           :         p10, 9, 10
```

---

## Phase 1: Architecture & Specification *(Complete)*
- Reference project inspection and gap analysis.
- Initial system architecture specification.

---

## Phase 2: Project Foundation, Database & Design System *(Complete)*
- Backend directory structure, Pydantic settings (`config.py`), and `.env`.
- SQLAlchemy 2.0 declarative database models (`Post`, `ApprovalRequest`, `SocialAccount`, `ScheduledPost`, `PublishLog`, `AnalyticsMetrics`, `ActivityLog`, `OAuthState`).
- Alembic database migration `001_initial_schema.py` executed.
- Fernet symmetric token encryption utility (`security.py`).
- CSS design tokens (`tokens.css`, `reset.css`, `layout.css`, `components.css`).
- Health endpoint (`/api/v1/health`) and 10/10 automated tests passing.

---

## Phase 3: Frontend Shell & Core UI/UX *(Complete)*
- Responsive SaaS web interface shell (`index.html`).
- Feature styling (`views.css`) for all 8 views.
- Modular component managers: toast notifications (`toast.js`), accessible modal dialogs (`modal.js`), badges (`badge.js`), and loaders (`loader.js`).
- Interactive views wired up: Dashboard, Studio with prompt quick-picks, Approvals queue with editable textareas and Slack simulator, Content Calendar grid, Social Accounts, Authentic Analytics, Activity Log, and Settings with Dark/Light theme switcher.
- Verified all 19 static and API routes return `HTTP 200 OK`.

---

## Phase 4: Intelligent AI Agents & Multi-Provider Architecture *(Complete)*

### Objectives Achieved
- Implemented multi-provider abstraction (`LLMProvider`, `GroqProvider`, `GeminiProvider`, `MockProvider`) with server-side API keys and live model switching.
- **Dynamic Content Generation**: Topic interpretation, expansion, and context-guided formatting.
- **Theme-Aware Generation Engine**: Distinct writing strategies across 10 themes.
- **Platform-Aware Adaptation**: Network-specific rules for LinkedIn, X (Twitter), Instagram, Facebook.
- **7-Dimension AI Content Quality Review**: Grammar, relevance, theme, platform, naturalness, originality, CTA.
- Verified with 9/9 live behavioral verification tests and 21 unit/integration tests.

---

## Phase 5: Human-in-the-Loop (HITL) Orchestration & LangGraph Workflow *(Complete)*

### Objectives Achieved
- **LangGraph Workflow**: StateGraph with `generate_node`, `review_node`, `self_correction_node`, and `should_self_correct` routing logic.
- **Durable Persistence**: State backed exclusively by SQLite with SQLAlchemy 2.0 (zero Redis dependency). Survived application restart.
- **Post & Approval Lifecycle**: Clear states (`draft`, `ai_review`, `awaiting_human_approval`, `approved`, `rejected`, `regenerating`, `failed`).
- **Approval API**: `GET /api/v1/approvals/pending`, `GET /api/v1/approvals/{id}`, `GET /api/v1/approvals/history`, `POST /api/v1/approvals/{id}/approve`, `POST /api/v1/approvals/{id}/reject`, `POST /api/v1/approvals/{id}/regenerate`.
- **Validation & Concurrency**: Atomic state transitions with HTTP 409 conflict protection; mandatory rejection reason validation; maximum regeneration ceiling (`MAX_REGENERATIONS = 5`).
- **Audit Logging**: Comprehensive activity tracking (`GENERATE_POST_VARIANTS`, `CONTENT_GENERATED`, `APPROVAL_REQUESTED`, `APPROVAL_APPROVED`, `APPROVAL_REJECTED`, `CONTENT_REGENERATED`, `REGENERATION_LIMIT_REACHED`).
- **Frontend Review UI**: Real-time connected approvals queue with live actions, rejection modal, and regeneration state updates.
- **Test Suite**: 24/24 Phase 5 tests passed; 44/44 total regression tests passed.

---

## Phase 6: Social Platform Integrations, Scheduler & Notifications *(Next Target)*

### Objectives
- Connect FastAPI routers (`/api/v1/posts`, `/api/v1/approvals`, `/api/v1/calendar`, `/api/v1/settings`, `/api/v1/webhooks`) to the live agent pipeline.
- Implement UI generation controls in Studio: Theme, Audience, Content Type, Length, Regenerate with Variation, Improve Hook, Make Shorter, Make Longer.
- Wire live API fetch calls from `studio.js`, `approvals.js`, and `calendar.js`.

### Deliverables
- `backend/app/routers/posts.py`, `approvals.py`, `calendar.py`, `settings.py`, `webhooks.py`
- `frontend/js/api.js`, `frontend/js/store.js`
- Updated `studio.js`, `approvals.js`, `calendar.js`

---

## Phase 7: OAuth & Social Platform Integrations

### Objectives
- Implement **`OAuthManager`** with PKCE code challenge (S256) and database-backed state cache in `oauth_states` (10-minute TTL, no Redis).
- Implement platform connectors: `MockSocialPublisher`, `XPublisher`, `LinkedInPublisher`, and `MetaPublisher`.
- Wire frontend Social Accounts connection matrix.

---

## Phase 8: Analytics & Activity

### Objectives
- Implement **`AnalyticsService`** computing authentic metrics (success rates, publication logs) with zero fabricated numbers.
- Implement **`AuditService`** recording chronological audit trail in `activity_logs`.
- Complete frontend Analytics and Activity views.

---

## Phase 9: Testing, Security & Docker

### Objectives
- Comprehensive unit, integration, and E2E test suites with 100% pass rate.
- Security hardening (rejection of dev keys in production).
- Dockerfile and `docker-compose.yml` (FastAPI + PostgreSQL 16).

---

## Phase 10: Documentation & Final Demo

### Objectives
- `README.md` and `docs/API_REFERENCE.md`.
- End-to-end user walkthrough verification.
