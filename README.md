# AI Social Media Agent (SocioAgentic AI)

An enterprise-grade, autonomous AI Social Media Management Platform featuring multi-model copy generation, automated quality review scoring, dual-channel Human-in-the-Loop (HITL) approvals via Web UI and Slack Block Kit, calendar scheduling, APScheduler-driven background publication, and robust OAuth 2.0 PKCE integrations for X (Twitter), LinkedIn, Meta Facebook Pages, and Meta Instagram Business.

Designed for reliable operation out-of-the-box with zero mandatory paid credentials: high-fidelity contextual mock publishing, intelligent mock LLM synthesis, and Slack simulation enable 100% of workflows without external developer dependencies.

---

## 1. System Architecture & Features

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 Client & Interface Layer                               │
│     Modern SaaS Web UI (Studio, Approvals, Calendar, Accounts, Analytics, Audit)       │
│                      Slack Workspace (Interactive Block Kit Cards)                     │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                FastAPI Gateway (/api/v1)                               │
│    /posts  •  /approvals  •  /schedules  •  /auth  •  /slack  •  /health  •  /static   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                Core Application Services                               │
│  • ContentService: LangGraph multi-model generation pipeline & rubric evaluation       │
│  • ApprovalService: Atomic CAS transitions, state machine & persistent audit history   │
│  • ScheduleService & APScheduler: Background job dispatch, due-worker & timezone logic │
│  • SlackService: HMAC-SHA256 signature verification (300s window), Block Kit builder   │
│  • OAuthService: RFC 7636 PKCE S256, 10m TTL state consumption, Fernet encryption     │
│  • PublishingService & Registry: Platform publishers with strict mock guardrails       │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              Relational Persistence Layer                              │
│       SQLite / PostgreSQL via SQLAlchemy ORM (Posts, Approvals, Schedules,             │
│                 Publish Logs, Activity Logs, Accounts, OAuth States)                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Key Capabilities
1. **Intelligent Multi-Platform Studio:** Generate tailored social posts for X (Twitter), LinkedIn, Facebook Pages, and Instagram Business with configurable tone, audience, and length constraints.
2. **Autonomous Review Scoring:** Automated evaluation assessing coherence, platform suitability, and policy compliance ($0-100$ score with self-correction threshold $\ge 70$).
3. **Dual-Channel HITL Approvals:**
   - **Web UI:** Review queue with inline editable variants, approval with instant scheduling, and rejection with mandatory reason recording.
   - **Slack Block Kit:** Interactive notifications dispatched to Slack with instant Approve/Reject action buttons, raw body HMAC-SHA256 verification, and in-place message replacement.
4. **Dynamic Calendar & Rescheduling:** Monthly grid view with timezone switching, peak engagement slot indicators, and cancel/reschedule workflows.
5. **Secure Multi-Platform OAuth:** RFC 7636 PKCE S256 with single-use atomic consumption, Fernet token encryption at rest, and origin-validated popup callbacks.
6. **Full Audit Trail:** Comprehensive activity logs capturing every prompt generation, approval decision, scheduling event, and publication attempt.

---

## 2. Quickstart & Installation

### Prerequisites
- Python 3.10+ (tested on Python 3.12)
- Virtual environment (`venv` or `conda` recommended)

### Step 1: Clone and Set Up Environment
```bash
# Clone the repository
git clone <repo-url>
cd ICT

# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy the provided `.env.example` to `.env`:
```bash
cp .env.example .env
```
By default, `.env.example` is pre-configured for **local mock development**:
```ini
ENVIRONMENT=development
APP_NAME="AI Social Media Agent"
DEBUG=true
PORT=8000
HOST=0.0.0.0

DATABASE_URL=sqlite:///./social_agent.db
SECRET_KEY=dev_secret_key_change_in_production_min_32_chars!
FERNET_KEY=k8zZ01Ua9qL_Wc4z7d_YxG8jB2nF6mP0rT3vA5eC7sI=

# Safe Sandbox Defaults (Zero External Dependencies Required)
MOCK_SOCIAL_PUBLISHING=true
SLACK_MOCK_MODE=true
LLM_PROVIDER=mock
```

### Step 3: Run the Application
```bash
python run.py
```
Open your browser to:
- **Web Dashboard:** `http://localhost:8000/`
- **Interactive Swagger Docs:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

#### Operator Authentication (Phase 9 Security Hardening)
The web interface is protected by signed HttpOnly operator sessions and CSRF tokens:
- **Development Username:** `operator`
- **Development Password:** `DevSecurePassword2026!`
*(In production, custom credentials must be configured via `OPERATOR_USERNAME` and `OPERATOR_PASSWORD` in `.env`)*

---

## 3. Running Automated Tests

All tests run in **strict isolation** against temporary SQLite databases with automated assertions ensuring the active `social_agent.db` database is never touched. External network calls are mocked.

Run the entire 105-test verification suite:
```powershell
python -m pytest tests/ -v
```

Run specific test modules:
```powershell
# Phase 9 Security Hardening & Session Auth
python -m pytest tests/test_phase9_security.py -v

# Phase 9 Database & Process Isolation
python -m pytest tests/test_phase9_isolation.py -v

# Phase 8 Analytics & Audit Logs
python -m pytest tests/test_analytics_and_activity.py -v

# OAuth PKCE & X (Twitter) infrastructure
python -m pytest tests/test_oauth_infrastructure.py -v

# LinkedIn OAuth & Posts API
python -m pytest tests/test_linkedin_integration.py -v

# Meta Facebook Pages
python -m pytest tests/test_facebook_integration.py -v

# Meta Instagram Business
python -m pytest tests/test_instagram_integration.py -v

# Slack Block Kit, HMAC-SHA256 & Replay Protection
python -m pytest tests/test_slack_integration.py -v

# Scheduling & Cancellation Lifecycle
python -m pytest tests/test_cancellation_and_rescheduling.py -v

# Human Review State Machine
python -m pytest tests/test_phase6_comprehensive.py -v

# Full Unbroken E2E Lifecycle Gate
python -m pytest tests/test_phase7_e2e_acceptance.py -v
```

---

## 4. End-to-End Mock Mode Demo Walkthrough

Follow this step-by-step procedure to demonstrate the full application lifecycle in local mock mode without configuring external APIs:

### Step 1: Content Generation (Studio)
1. Navigate to `http://localhost:8000/` and click **Create Content (Studio)** in the sidebar.
2. Select target platforms (e.g., **X (Twitter)** and **LinkedIn**).
3. Choose a prompt chip or enter a topic (e.g., `"Announcing our autonomous AI Social Media Agent with LangGraph"`).
4. Click **Generate Content Variants**.
5. The LangGraph engine synthesizes platform-adapted copy, runs AI review scoring, saves the draft, and queues it for human review (`AWAITING_HUMAN_APPROVAL`).
6. Because `SLACK_MOCK_MODE=true`, a mock Slack Block Kit card is automatically dispatched.

### Step 2: Review & Approval (Approvals Queue)
1. Click **Review & Approvals** in the sidebar.
2. Observe the pending card with the generated topic, platforms, AI quality score, and copy previews.
3. Test the Slack Card integration:
   - Click **💬 Dispatch Slack** to simulate re-dispatching the Slack interactive notification.
   - Alternatively, approve via the Web UI by clicking **✅ Approve Post**.
4. The post transitions atomically from `AWAITING_HUMAN_APPROVAL` to `APPROVED` with an audit log entry.

### Step 3: Scheduling (Content Calendar)
1. From the approved card, click **📅 Schedule Post**.
2. Select a scheduled date and time (or pick a suggested peak engagement slot).
3. Click **Confirm Schedule**.
4. Navigate to **Content Calendar** in the sidebar to view the scheduled post pill in the monthly grid.
5. Click the scheduled post pill to inspect details or test timezone conversions.

### Step 4: Cancellation & Rescheduling
1. In the Content Calendar or Approvals view, click **❌ Cancel Schedule**.
2. Confirm cancellation; the schedule transitions to `CANCELLED` and the post safely reverts to `APPROVED` state.
3. Click **📅 Schedule Post** again to reschedule to a new time window.

### Step 5: Mock Publishing & Delivery Audit
1. Click **⚡ Publish Now** on the scheduled post.
2. The `PublisherRegistry` strictly invokes `MockPublisher` because `MOCK_SOCIAL_PUBLISHING=true`.
3. Publication succeeds with a simulated external ID (`mock_post_...`).
4. Navigate to **Activity Log** in the sidebar to review the tamper-evident audit history capturing every step: `CONTENT_GENERATED`, `APPROVAL_REQUESTED`, `SLACK_NOTIFICATION_DISPATCHED`, `APPROVAL_APPROVED`, `POST_SCHEDULED`, `SCHEDULE_CANCELLED`, and `POST_PUBLISHED`.

---

## 5. Transitioning to Live Production

To connect real developer accounts and publish live content:

### 1. Generate Production Fernet Encryption Key
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Set the resulting string in `.env` as `FERNET_KEY`.

### 2. Configure Developer Credentials in `.env`

```ini
ENVIRONMENT=production
DEBUG=false
MOCK_SOCIAL_PUBLISHING=false
SLACK_MOCK_MODE=false
FRONTEND_ORIGIN=https://your-domain.com

# X (Twitter) Developer Portal (OAuth 2.0 PKCE)
X_CLIENT_ID=your_x_client_id
X_CLIENT_SECRET=your_x_client_secret

# LinkedIn Developer Portal (OIDC + w_member_social)
LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret

# Meta Developer Portal (Facebook Pages & Instagram Business)
META_APP_ID=your_meta_app_id
META_APP_SECRET=your_meta_app_secret

# Slack App Management (Interactivity & Bot Token)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your_slack_signing_secret
SLACK_DEFAULT_CHANNEL=#social-approvals
```

### 3. Developer Portal Setup Requirements
- **X (Twitter):** Set redirect URI to `https://<domain>/api/v1/auth/twitter/callback` with scopes `tweet.read`, `tweet.write`, `users.read`, `offline.access`.
- **LinkedIn:** Set redirect URI to `https://<domain>/api/v1/auth/linkedin/callback` with scopes `openid`, `profile`, `email`, `w_member_social`.
- **Meta (Facebook & Instagram):** Set redirect URI to `https://<domain>/api/v1/auth/facebook/callback`. Requires Meta App Review approval for `pages_manage_posts` and `instagram_content_publish`. Instagram requires a linked Business/Creator account and valid public HTTPS image/video URLs (text-only posts are rejected by Meta).
- **Slack:** In Slack App settings $\rightarrow$ Interactivity & Shortcuts, set Request URL to `https://<domain>/api/v1/slack/interactions`.

---

## 6. License
Internal Academic / Professional Project Submission. All rights reserved.
