# Sehat Saathi — Backend (English-only Edition)

Voice-first discharge-instruction assistant with patient-controlled caregiver access and swappable AI providers.
Built in Python 3.12 with **FastAPI**, **SQLite**, and **Docker**.

Conforms strictly to:
- **Software Requirements Specification (SRS v1.1 - English-only Edition)**
- **System Architecture & UML Design Document v1.0**

---

## 🌟 Key Capabilities & Requirements Addressed

1. **Provider Abstraction Layer (`PR-01` to `PR-15`)**:
   - Clean interfaces for `STTProvider`, `LLMProvider`, and `TTSProvider`.
   - Adapters for **AMD Developer Cloud** (OpenAI-compatible vLLM & AMD speech), **Hugging Face Inference API** (with cold-start retry), and an offline deterministic **Mock Provider**.
   - Provider switching exclusively in backend `.env` (`AI_PROVIDER`, `LLM_PROVIDER`, `STT_PROVIDER`, `TTS_PROVIDER`).
   - Resilient automatic fallback (`AUTO_FALLBACK=true`, `PR-09`).
   - Protected operator diagnostics endpoint (`GET /internal/health`, `PR-12`).
   - Zero vendor or provider exposure to client endpoints (`PR-07`).

2. **Deterministic Safety Pipeline (`FR-12`, `FR-13`, `UX-27`)**:
   - Pre-LLM deterministic red-flag filter covering **Chest Pain**, **Shortness of Breath**, **Fainting / Collapse**, **Severe Bleeding**, and **Stroke / Sudden Weakness**.
   - Filter overrides the LLM and cannot be bypassed.
   - Immediate emergency view, 911 prompt, and alert fan-out to all linked caregivers.

3. **Discharge Summary Grounding & Honest Handoff (`FR-02`, `FR-03`, `FR-05`, `FR-14`, `UX-16`, `UX-28`)**:
   - Sentences of the discharge summary are indexed with stable line IDs (`L1`, `L2`, ...).
   - Validates that citations exist. Invalid or absent citations automatically trigger an **Honest Handoff** ("*This information is not in your discharge summary. I have made a note so your doctor or family can be informed.*") and log into the clinician review queue.
   - Displays citation source line and confidence badge (`Certain`, `Possibly`, `Unknown`).
   - Never gives diagnoses, adjusts doses, or recommends new medicines.

4. **Confirm-Before-Act Actions (`FR-06` to `FR-11`, `FR-16`, `UX-14`, `UX-15`)**:
   - **Reminders**: Preserves dose text exactly as written. Speaks echo-back before saving.
   - **Appointments**: Offers available slots from mock calendar (max 3 at a time). Requires confirmation before booking.
   - Polite rejection handling: Saying "no" returns the patient to the question without error.

5. **Caregiver Pairing & Scoping (`FR-18` to `FR-26`, `UX-39` to `UX-44`)**:
   - **Patient Device Token**: Generated upon registration; stored hashed in DB.
   - **8-Hex Pairing Key**: 10-minute validity (`XXXX-XXXX` format), single-use; new key invalidates prior unused key.
   - **Rate Limiting**: Max 5 failed redemption attempts per IP per 10 minutes.
   - **Two-Step Consent**: Caregiver submits key & name; patient approves on their phone before any session token (>= 128-bit) is issued.
   - **Strict Data Scoping**: Caregiver dashboard is strictly scoped to the patient ID bound to the session token.
   - **Immediate Revocation**: Patient can revoke a linked caregiver at any time; subsequent requests with that token are rejected immediately (HTTP 403: "*Your connection has been removed*").

---

## 📁 Repository Structure

```
d:\AMD Hackathon ACT III\
├── .venv/                      # Python virtual environment
├── .env.example                # Sample environment configuration (SRS Section 6.3)
├── .env                        # Active configuration
├── Dockerfile                  # Containerized deployment
├── docker-compose.yml          # Docker Compose service definition
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Pytest configuration
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application and lifespan hooks
│   ├── config.py               # Pydantic Settings and PR-11 validation
│   ├── database.py             # SQLite tables, seed data, and aiosqlite helpers
│   ├── utils.py                # Timezone-aware UTC helpers
│   ├── models/
│   │   └── schemas.py          # Pydantic models for all API requests and responses
│   ├── services/
│   │   ├── safety_service.py   # Deterministic red-flag pattern matcher
│   │   ├── grounding_service.py# Citation validator and honest handoff generator
│   │   ├── turn_orchestrator.py# Main dialogue pipeline coordinator
│   │   ├── pairing_service.py  # Key generation, consent, tokens, and rate limits
│   │   ├── reminder_service.py # Exact dose preservation and reminder confirmation
│   │   ├── appointment_service.py # Mock slots and booking confirmation
│   │   ├── alert_service.py    # Alert fan-out and handled tracking
│   │   └── dashboard_service.py# Scoped caregiver dashboard and review queue
│   ├── providers/
│   │   ├── base.py             # STTProvider, LLMProvider, TTSProvider contracts
│   │   ├── amd_provider.py     # AMD Developer Cloud vLLM (OpenAI-compatible) & speech
│   │   ├── huggingface_provider.py # Hugging Face Inference API with 503 retry
│   │   ├── mock_provider.py    # Offline deterministic mock provider
│   │   └── factory.py          # Dynamic provider resolver with auto-fallback
│   ├── data/
│   │   ├── synthetic_summary.json # Synthetic discharge summary with numbered lines
│   │   ├── red_flags.json      # English red-flag pattern dictionary
│   │   └── conformance_dataset.json # PR-14 40-utterance test dataset
│   └── static/
│       └── audio/              # Generated WAV audio replies and emergency sirens
└── tests/
    ├── test_api_endpoints.py           # Integration tests for all endpoints
    ├── test_grounding_and_handoff.py   # Citation verification and handoff tests
    ├── test_pairing_and_access.py      # Pairing, consent, scoping, revocation tests
    ├── test_reminders_and_booking.py   # Confirm-before-act tests
    ├── test_safety_and_redflags.py     # Deterministic red-flag tests
    └── test_provider_conformance.py    # PR-14 40-utterance benchmark test
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.11 or higher (Python 3.12 recommended)
- Virtual environment created

### 2. Activate Virtual Environment
On Windows (PowerShell):
```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Run the FastAPI Server
```powershell
.\.venv\Scripts\uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Once started:
- API Root: `http://localhost:8000/`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/healthz`

---

## 🧪 Running Automated Tests

Run the full test suite with verbose output:
```powershell
.\.venv\Scripts\pytest -v
```

### PR-14 Conformance Benchmark
To view the benchmark metrics for the 40-utterance dataset:
```powershell
.\.venv\Scripts\pytest tests/test_provider_conformance.py -v -s
```
**Results achieved:**
- **Red-Flag Recall**: 100.0% (Target: 100%)
- **Valid Citations on Grounded Answers**: 100.0% (Target: 100%)
- **Intent Accuracy**: 95.0% (Target: >= 85%)
- **Out-of-Scope Handoff Rate**: 100.0% (Target: >= 90%)

---

## 🔌 API Reference Guide

### Patient Endpoints
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/patient/register` | None | Registers patient device and returns `device_token` (`FR-19`) |
| `POST` | `/api/turn` | Patient Token | Submits voice/text; returns transcript, grounded answer, citations (`FR-01`) |
| `POST` | `/api/confirm` | Patient Token | Confirms or rejects pending reminder/booking (`FR-16`, `UX-14`) |
| `GET` | `/api/reminders` | Patient Token | Lists active patient reminders |
| `POST` | `/api/reminders/{id}/action` | Patient Token | Records medicine taken, snoozed, or missed (`FR-09`) |
| `GET` | `/api/slots` | Patient Token | Lists mock clinic appointment slots (max 3) (`FR-10`) |
| `POST` | `/api/emergency/notify` | Patient Token | One-tap "Notify family" emergency broadcast (`UX-17`) |

### Caregiver Pairing Endpoints
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/pair/create` | Patient Token | Generates 8-hex pairing key with 10-minute expiry (`FR-20`) |
| `POST` | `/api/pair/redeem` | None (Rate-limited) | Submits key & caregiver name to initiate consent (`FR-21`) |
| `GET` | `/api/pair/pending` | Patient Token | Polls for pending caregiver link requests (`UX-42`) |
| `POST` | `/api/pair/decide` | Patient Token | Patient approves or declines link request (`FR-22`) |
| `GET` | `/api/pair/status` | Query `pending_id` | Caregiver polls for approval and receives session token once (`FR-22`) |
| `GET` | `/api/pair/links` | Patient Token | Lists active linked caregivers (`FR-24`) |
| `DELETE` | `/api/pair/links/{id}` | Patient Token | Immediately revokes a caregiver link (`FR-24`) |

### Caregiver Dashboard Endpoints
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/dashboard` | Caregiver Token | Scoped dashboard: Today's Status summary, alerts, review queue, adherence (`UX-35`) |
| `POST` | `/api/alerts/{id}/handled` | Caregiver Token | Marks an alert as handled (`UX-36`) |
| `POST` | `/api/review/{id}/note` | Caregiver Token | Clinician adds note to a review queue item (`UX-37`) |

### Operator Diagnostics Endpoint
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/internal/health` | Operator Token | Reports active provider, models, last call, latency (`PR-12`) |

---

## 🔄 Provider Switching

To switch providers, update `.env` and restart the backend:

- **For AMD Developer Cloud (vLLM & Speech)**:
  ```ini
  AI_PROVIDER=amd
  AMD_LLM_BASE_URL=https://<your-amd-vllm-endpoint>/v1
  AMD_LLM_API_KEY=<your-amd-api-key>
  AMD_LLM_MODEL=meta-llama/Llama-3-8B-Instruct
  ```

- **For Free Hugging Face Inference API**:
  ```ini
  AI_PROVIDER=huggingface
  HF_TOKEN=hf_xxxxxxxxxxxxxx
  HF_LLM_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
  ```

- **For Offline / CI Testing**:
  ```ini
  AI_PROVIDER=mock
  ```

---

## 🐳 Docker Deployment

Build and run using Docker Compose:
```bash
docker-compose up --build -d
```
The application will be accessible on port `8000`.
