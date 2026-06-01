# Implementation Plan: ADM Copilot

## Overview

Implement the ADM Copilot system in two parallel tracks: a **FastAPI backend** (Python) hosted on Hugging Face Spaces and a **Next.js frontend** (TypeScript) hosted on Vercel. The backend handles JWT authentication, rate limiting, PDF extraction, vector retrieval, and LLM orchestration. The frontend provides the audit dashboard, file upload, processing feedback, and results display. Both tracks are wired together in the final integration phase.

---

## Tasks

- [x] 1. Project scaffolding and shared configuration
  - [x] 1.1 Scaffold FastAPI backend project structure
    - Create `backend/` directory with `main.py`, `requirements.txt`, `Dockerfile`, and `.env.example`
    - Add dependencies: `fastapi`, `uvicorn`, `pydantic`, `python-jose[cryptography]`, `passlib[bcrypt]`, `pymupdf`, `chromadb`, `langchain`, `langchain-google-genai`, `supabase`, `hypothesis`, `pytest`, `pytest-asyncio`, `httpx`
    - Configure `pyproject.toml` or `setup.cfg` for pytest with `asyncio_mode = auto`
    - _Requirements: 5.1, 5.3_

  - [x] 1.2 Scaffold Next.js frontend project structure
    - Create `frontend/` with `npx create-next-app@latest` using TypeScript, Tailwind CSS, and App Router
    - Add dependencies: `@tanstack/react-query`, `react-hook-form`, `zod`, `react-dropzone`, `react-markdown`, `fast-check`, `@testing-library/react`, `@testing-library/jest-dom`, `jest`, `jest-environment-jsdom`
    - Configure `jest.config.ts` and `jest.setup.ts`
    - _Requirements: 4.1, 6.1, 8.1_

  - [x] 1.3 Define shared Pydantic data models
    - Implement `UserClaims`, `QuotaStatus`, `Chunk`, `LLMResponse`, and `AuditResponse` models in `backend/models.py`
    - _Requirements: 5.7_

- [x] 2. Database schema and Supabase setup
  - [x] 2.1 Create Supabase SQL migration scripts
    - Write `migrations/001_create_users.sql` for the `users` table including the `agent_travel_name` column
    - Write `migrations/002_create_user_uploads.sql` for the `user_uploads` table
    - Write `migrations/003_create_login_attempts.sql` for the `login_attempts` table
    - Write `migrations/004_create_airlines.sql` for the `airlines` table (code TEXT PRIMARY KEY, name TEXT NOT NULL)
    - _Requirements: 1.1, 1.6, 2.4_


- [x] 3. Authentication — backend
  - [x] 3.1 Implement `AuthService` class
    - Implement `login(email, password) → JWT | AuthError`: query `users` table, verify bcrypt hash, issue JWT with `exp = iat + 86400`
    - Implement `verify_jwt(token) → UserClaims | None`: decode and validate JWT signature and expiry
    - Implement `check_lockout(email) → LockoutStatus`: count failed attempts in last 15 minutes
    - Implement `record_failed_attempt(email) → None`: insert row into `login_attempts`
    - Return HTTP 401 with generic message on invalid credentials; HTTP 429 after ≥5 consecutive failures
    - _Requirements: 1.1, 1.2, 1.3, 1.6_

  - [ ]* 3.2 Write property test for credential format validation (Property 1)
    - **Property 1: Input Validation Rejects Invalid Credentials Format**
    - **Validates: Requirements 1.1**
    - Use `@given(email=st.text(), password=st.text())` to assert that only RFC 5322 emails and passwords ≥8 chars are accepted

  - [ ]* 3.3 Write property test for JWT expiry (Property 2)
    - **Property 2: JWT Expiry Is Always 24 Hours**
    - **Validates: Requirements 1.2**
    - Use `@given(user=valid_user_strategy())` to assert `exp == iat + 86400` for every issued token

  - [ ]* 3.4 Write property test for generic 401 message (Property 3)
    - **Property 3: Invalid Credentials Always Return Generic 401**
    - **Validates: Requirements 1.3**
    - Use `@given(email=st.emails(), password=st.text())` to assert response body never contains "email" or "password"

  - [ ]* 3.5 Write property test for account lockout (Property 4)
    - **Property 4: Account Lockout After 5 Consecutive Failures**
    - **Validates: Requirements 1.6**
    - Use `@given(email=st.emails())` to assert HTTP 429 is returned after ≥5 consecutive failures

  - [x] 3.6 Implement `POST /auth/login` endpoint
    - Wire `AuthService` into a FastAPI route; return `{ access_token, token_type, expires_in }` on success
    - _Requirements: 1.1, 1.2, 1.3, 1.6_

- [x] 4. Rate limiting — backend
  - [x] 4.1 Implement `RateLimiter` class
    - Implement `check_quota(user_email) → QuotaStatus`: count `user_uploads` rows in rolling 24h window; read `MAX_UPLOADS_PER_DAY` from env (default 5, valid 1–100)
    - Implement `record_upload(user_email) → None`: insert row into `user_uploads`
    - Return `QuotaStatus` with `reset_at = earliest_upload_in_window + 24h`
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

  - [ ]* 4.2 Write property test for rate limit config parsing (Property 5)
    - **Property 5: Rate Limit Configuration Parsing**
    - **Validates: Requirements 2.1**
    - Use `@given(value=st.one_of(st.integers(1, 100), st.text(), st.none()))` to assert correct default and range behavior

  - [ ]* 4.3 Write property test for quota enforcement (Property 6)
    - **Property 6: Quota Enforcement and Tracking Accuracy**
    - **Validates: Requirements 2.2, 2.4, 2.5**
    - Use `@given(email=st.emails(), limit=st.integers(1, 10))` to assert (N+1)th upload is rejected, counter increments correctly, and `reset_at` is accurate

- [x] 5. Fare Rules ingestion pipeline
  - [x] 5.1 Implement `IngestionPipeline` class
    - Implement `ingest_document(file_path, airline_code) → None`: parse PDF/text with PyMuPDF, chunk at 1000 chars with 100-char overlap, store in ChromaDB with `{"airline_code": airline_code}` metadata
    - Reject documents without a valid `airline_code` and log the error
    - Log and skip corrupt/unparseable documents without halting the run
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 5.2 Write property test for chunking algorithm (Property 7)
    - **Property 7: Chunking Algorithm Correctness**
    - **Validates: Requirements 3.2**
    - Use `@given(text=st.text(min_size=1001))` to assert non-final chunks are exactly 1000 chars, consecutive chunks share a 100-char overlap, and the original text is reconstructable

  - [ ]* 5.3 Write property test for airline code metadata integrity (Property 8)
    - **Property 8: Airline Code Metadata Integrity**
    - **Validates: Requirements 3.3, 3.4**
    - Use `@given(airline_code=st.text(min_size=2, max_size=3), doc=valid_document_strategy())` to assert every stored chunk carries the correct `airline_code` and queries return only matching chunks (≤20)

  - [x] 5.4 Implement `VectorRetriever` class
    - Implement `retrieve_chunks(airline_code, query_text, top_k=20) → list[Chunk]`: query ChromaDB with `airline_code` metadata filter, return up to 20 ranked chunks
    - Return empty list when no chunks match (triggers 422 upstream)
    - _Requirements: 3.4, 5.5_

  - [x] 5.5 Implement dynamic upload endpoint `POST /fare-rules`
    - Create FastAPI route protected by JWT authentication
    - Accept `multipart/form-data` with `file` (PDF/text) and `airline_code`
    - Call `IngestionPipeline` to parse and chunk the file, dynamically appending the records to persistent ChromaDB
    - Return 200 on success, 401 on missing/invalid JWT, 422 on extraction or parameter failure
    - _Requirements: 3.6, 3.7, 3.8_


- [x] 6. Checkpoint — backend data layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. PDF extraction and LLM orchestration — backend
  - [x] 7.1 Implement `PDFExtractor` class
    - Implement `extract_text(pdf_bytes) → str | ExtractionError` using PyMuPDF (`fitz`)
    - Must complete in under 500ms from bytes-in-memory to text-returned
    - _Requirements: 5.3, 5.4, 5.8_

  - [ ]* 7.2 Write property test for extraction performance (Property 13)
    - **Property 13: ADM Text Extraction Performance**
    - **Validates: Requirements 5.4**
    - Use `@given(pdf=valid_pdf_strategy())` to assert elapsed time < 500ms for any valid PDF

  - [x] 7.3 Implement `LLMOrchestrator` class
    - Implement `run_audit(adm_text, fare_rules_chunks) → LLMResponse | LLMError`: build structured prompt containing complete ADM text and all chunk texts, call Gemma via LangChain/Google Python SDK, parse response into `{ verdict, analysis, dispute_draft }`
    - Return `LLMError` on timeout or call failure; raise parse error if response is malformed
    - _Requirements: 5.6, 5.7, 5.10, 5.11_

  - [ ]* 7.4 Write property test for prompt completeness (Property 14)
    - **Property 14: Prompt Contains All Required Context**
    - **Validates: Requirements 5.6**
    - Use `@given(adm_text=st.text(min_size=1), chunks=st.lists(chunk_strategy(), min_size=1))` to assert the compiled prompt contains the complete ADM text and every chunk text without truncation

  - [ ]* 7.5 Write property test for LLM response parsing (Property 15)
    - **Property 15: LLM Response Parsing Round-Trip**
    - **Validates: Requirements 5.7**
    - Use `@given(response=well_formed_llm_response_strategy())` to assert all three components are extracted as non-empty strings and `verdict` is one of the two valid values

  - [ ]* 7.6 Write property test for audit pipeline error handling (Property 16)
    - **Property 16: Audit Pipeline Error Handling**
    - **Validates: Requirements 5.8, 5.9, 5.10, 5.11**
    - Use `@given(pdf=corrupt_pdf_strategy())` to assert each error condition maps to the correct HTTP status code and the `user_uploads` counter is not incremented

- [x] 8. Audit endpoint — backend
  - [x] 8.1 Implement `POST /audit` endpoint
    - Accept `multipart/form-data` (`file` + `airline_code`), require `Authorization: Bearer <JWT>` header
    - Orchestrate: JWT verify → rate limit check → PDF extract → vector retrieve → LLM call → parse → record upload → return `AuditResponse`
    - Return correct HTTP error codes (401, 422, 429, 502) for each failure mode; do not increment `user_uploads` on error
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11_

  - [ ]* 8.2 Write property test for invalid JWT returning 401 (Property 12)
    - **Property 12: Invalid JWT Always Returns 401**
    - **Validates: Requirements 5.2**
    - Use `@given(token=st.one_of(st.none(), st.text(), expired_jwt_strategy()))` to assert HTTP 401 is returned and no pipeline step executes

  - [x] 8.3 Write integration tests for the full audit pipeline
    - Test valid request → 200 with all three response components (mocked LLM)
    - Test rate limit enforcement: N+1 request → 429 with correct `reset_at`
    - Test JWT middleware: invalid token → 401, no pipeline execution
    - Test ChromaDB airline_code filter: cross-airline contamination check
    - _Requirements: 5.1–5.11_

  - [x] 8.4 Implement `GET /airlines` endpoint
    - Query the `airlines` table and return a list of objects containing `code` and `name`
    - Make it accessible publically or protected as appropriate


- [x] 9. Checkpoint — backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Authentication — frontend
  - [x] 10.1 Implement `AuthGuard` component and JWT storage utility
    - Read JWT from memory/secure storage on mount; check `exp` claim client-side
    - Redirect to `/login` if token is absent or expired; clear token on expiry detection
    - Wrap all protected routes with `AuthGuard`
    - _Requirements: 1.4, 1.5_

  - [x] 10.2 Implement `LoginPage` component
    - Email + password form; call `POST /auth/login`
    - On success: store JWT, redirect to `/dashboard`
    - On 401: display generic error (no field-level hint)
    - On 429: display lockout message with remaining duration
    - On network error: display "service temporarily unavailable" without redirecting
    - _Requirements: 1.3, 1.6, 1.7_

  - [ ]* 10.3 Write unit tests for `LoginPage`
    - Test valid submit flow, 401 display, 429 lockout display, network error display
    - _Requirements: 1.3, 1.6, 1.7_

- [x] 11. Airline selector and file drop zone — frontend
  - [x] 11.1 Implement `AirlineSelector` component
    - Combobox with type-ahead filtering; accept airline code or full name as search input
    - Show inline validation error below the control when submitted without selection
    - Fetch and load airline list dynamically from backend `GET /airlines` on mount
    - _Requirements: 4.1, 4.3, 4.9_


  - [ ]* 11.2 Write property test for combobox filtering (Property 9)
    - **Property 9: Combobox Filtering Completeness**
    - **Validates: Requirements 4.1**
    - Use `fc.assert(fc.property(fc.string(), (query) => { ... }))` to assert every displayed option contains the query string (case-insensitive) in code or name

  - [x] 11.3 Implement `FileDropZone` component
    - Accept exactly one `.pdf` file (MIME `application/pdf`), max 10 MB; replace on re-drop
    - Reject non-PDF files and multiple simultaneous drops (keep first)
    - Show inline validation errors below the control
    - _Requirements: 4.2, 4.4, 4.5, 4.6_

  - [ ]* 11.4 Write property test for file drop zone validation (Property 10)
    - **Property 10: File Drop Zone Validation**
    - **Validates: Requirements 4.2, 4.5**
    - Use `fc.assert(fc.property(fc.array(fileArbitrary()), (files) => { ... }))` to assert only the first valid PDF ≤10 MB is accepted

- [x] 12. Processing tracker and input panel — frontend
  - [x] 12.1 Implement `ProcessingTracker` component
    - Display exactly three fixed stages: "Extracting text..." → "Matching rules..." → "Querying AI..."
    - Each stage has one of three mutually exclusive states: `pending | active | completed`; exactly one stage is `active` at any time
    - Driven by frontend request state (not SSE); hidden on completion or error dismissal
    - _Requirements: 7.1, 7.2, 7.5, 7.6_

  - [ ]* 12.2 Write property test for processing tracker state invariant (Property 20)
    - **Property 20: Processing Tracker State Invariant**
    - **Validates: Requirements 7.1, 7.2**
    - Use `fc.assert(fc.property(processingStateArbitrary(), (state) => { ... }))` to assert exactly one stage is active, no stage is in two states simultaneously, and transitions only go forward

  - [x] 12.3 Implement `InputPanel` component
    - Compose `AirlineSelector`, `FileDropZone`, and submit button
    - Disable all controls during processing; immediately re-enable controls (airline selector, file drop zone, and submit button) if an error occurs to support rapid correction
    - Trigger `POST /audit` with PDF, `airline_code`, and `Authorization: Bearer <JWT>` header on submit
    - _Requirements: 4.3, 4.4, 4.7, 4.8, 7.3, 7.4, 7.6_


  - [ ]* 12.4 Write property test for controls disabled during processing (Property 21)
    - **Property 21: Input Controls Disabled During Processing**
    - **Validates: Requirements 7.3**
    - Use `fc.assert(fc.property(inFlightStateArbitrary(), (state) => { ... }))` to assert all three controls are disabled while a request is in-flight

  - [ ]* 12.5 Write property test for request includes JWT (Property 11)
    - **Property 11: Request Always Includes JWT in Authorization Header**
    - **Validates: Requirements 4.8**
    - Use `fc.assert(fc.property(validFormStateArbitrary(), (formState) => { ... }))` to assert every outgoing request includes `Authorization: Bearer <JWT>`, the PDF bytes, and the `airline_code`

- [x] 13. Results display — frontend
  - [x] 13.1 Implement `VerdictBadge` component
    - Render exactly one badge at a time (replace previous before inserting new)
    - `VALID DISPUTE FOUND`: green background, white text; `VALID ADM / NO DISPUTE`: red background, white text
    - Hide badge entirely if CSS styling cannot be applied
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 13.2 Write property test for exactly one verdict badge (Property 17)
    - **Property 17: Exactly One Verdict Badge at All Times**
    - **Validates: Requirements 6.1**
    - Use `fc.assert(fc.property(fc.array(auditResultArbitrary(), { minLength: 1 }), (results) => { ... }))` to assert the DOM always contains exactly one badge after rendering each result

  - [x] 13.3 Implement `AnalysisBlock` component
    - Render LLM analysis as markdown using `react-markdown`
    - Preserve all policy clause, date, booking class, and penalty amount references without truncation
    - _Requirements: 6.4_

  - [ ]* 13.4 Write property test for analysis content preservation (Property 18)
    - **Property 18: Analysis Content Preservation**
    - **Validates: Requirements 6.4**
    - Use `fc.assert(fc.property(analysisWithReferencesArbitrary(), (analysis) => { ... }))` to assert rendered markdown preserves all policy references

  - [x] 13.5 Implement `DisputeDraftBox` component
    - Read-only `<textarea>` pre-populated with the LLM-generated dispute email
    - "Copy to Clipboard" button positioned adjacent, visible without scrolling
    - On copy: show "Copied!" or checkmark for ≥2 seconds, then revert to default state
    - _Requirements: 6.5, 6.6, 6.7_

  - [ ]* 13.6 Write property test for clipboard copy completeness (Property 19)
    - **Property 19: Clipboard Copy Completeness**
    - **Validates: Requirements 6.7**
    - Use `fc.assert(fc.property(fc.string(), (disputeDraft) => { ... }))` to assert clipboard content character count equals the original dispute draft string

  - [x] 13.7 Implement `ResultsPanel` component
    - Compose `VerdictBadge`, `AnalysisBlock`, and `DisputeDraftBox`
    - Only visible after a successful audit response
    - _Requirements: 6.1–6.7_

- [x] 14. Audit dashboard layout — frontend
  - [x] 14.1 Implement `AuditDashboard` page
    - Render `InputPanel` and `ResultsPanel` side-by-side on ≥1280px viewports; stacked on narrower viewports
    - Manage shared state: `processingState`, `auditResult`, `error`
    - Display inline rate-limit message (HTTP 429) on current page without navigating away
    - _Requirements: 2.6, 8.1, 8.2, 8.3, 8.4_

  - [ ]* 14.2 Write responsive layout tests
    - Viewport 1280px+: assert two-column layout, all three panels visible without vertical scroll
    - Viewport <1280px: assert single-column layout, no horizontal overflow
    - Viewport 375px: assert all controls are reachable and usable
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 15. Checkpoint — frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Integration and wiring
  - [x] 16.1 Configure CORS and environment variables
    - Add `CORS` middleware to FastAPI allowing the Vercel frontend origin
    - Document all required env vars in `backend/.env.example` and `frontend/.env.example`: `SUPABASE_URL`, `SUPABASE_KEY`, `JWT_SECRET`, `GOOGLE_API_KEY`, `MAX_UPLOADS_PER_DAY`, `NEXT_PUBLIC_API_URL`
    - _Requirements: 5.1, 2.1_

  - [x] 16.2 Wire frontend API client to backend endpoints
    - Implement `apiClient.ts` with typed wrappers for `POST /auth/login` and `POST /audit`
    - Attach JWT from storage to every `POST /audit` request in the `Authorization: Bearer` header
    - Handle all error status codes (401, 422, 429, 502) and surface them to the relevant UI components
    - _Requirements: 4.8, 5.1, 5.2, 2.6_

  - [ ] 16.3 Write end-to-end integration tests
    - Test full login → audit → results flow with mocked backend responses
    - Test error recovery flow: error displayed → input controls immediately re-enabled for correction
    - _Requirements: 1.4, 1.5, 7.4, 7.6_


- [ ] 17. Final checkpoint — all tests pass
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints at tasks 6, 9, 15, and 17 ensure incremental validation
- Property tests use Hypothesis (backend) and fast-check (frontend) as specified in the design
- Unit tests and property tests are complementary — both should be run together
- The `IngestionPipeline` (task 5) is an offline build-time process; the pre-built `chroma_db` directory must be bundled into the Docker image before deploying the backend

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1", "4.1", "5.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5", "4.2", "5.2", "5.3"] },
    { "id": 4, "tasks": ["3.6", "4.3", "5.4"] },
    { "id": 5, "tasks": ["7.1", "7.3"] },
    { "id": 6, "tasks": ["7.2", "7.4", "7.5", "7.6"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3"] },
    { "id": 9, "tasks": ["10.1", "10.2", "11.1", "11.3", "12.1"] },
    { "id": 10, "tasks": ["10.3", "11.2", "11.4", "12.2", "12.3"] },
    { "id": 11, "tasks": ["12.4", "12.5", "13.1", "13.3", "13.5"] },
    { "id": 12, "tasks": ["13.2", "13.4", "13.6", "13.7"] },
    { "id": 13, "tasks": ["14.1"] },
    { "id": 14, "tasks": ["14.2"] },
    { "id": 15, "tasks": ["16.1"] },
    { "id": 16, "tasks": ["16.2"] },
    { "id": 17, "tasks": ["16.3"] }
  ]
}
```
