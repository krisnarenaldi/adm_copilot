"""
ADM Copilot — FastAPI Backend Entry Point

Provides endpoints for:
  - POST /auth/register — New user registration (company email only)
  - POST /auth/login   — JWT-based authentication
  - POST /audit        — ADM audit pipeline (JWT-protected)
  - POST /fare-rules   — Dynamic Fare Rules ingestion (JWT-protected)
  - GET  /airlines     — List of supported airlines
"""

import os
import tempfile

from dotenv import load_dotenv
load_dotenv()  # loads backend/.env before any other imports read env vars

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware

from models import (
    LoginRequest,
    LoginResponse,
    AuthError,
    LockoutError,
    RegisterRequest,
    RegisterResponse,
    RegistrationError,
    IngestionResponse,
    AuditResponse,
    ExtractionError,
    LLMError,
    Airline,
)
from auth import AuthService, _get_supabase_client
from ingestion import IngestionPipeline
from rate_limiter import RateLimiter
from pdf_extractor import PDFExtractor
from retriever import VectorRetriever
from llm_orchestrator import LLMOrchestrator

app = FastAPI(
    title="ADM Copilot API",
    description="AI-powered Agency Debit Memo audit assistant",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the Vercel frontend origin (configured via env var)
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
async def login(body: LoginRequest) -> LoginResponse:
    """
    Authenticate a user and return a JWT.

    - **200**: `{ access_token, token_type, expires_in }`
    - **401**: Invalid credentials (generic message, no field hint)
    - **429**: Account locked after ≥5 consecutive failures within 15 minutes
    """
    service = AuthService()

    try:
        token = service.login(body.email, body.password)
    except LockoutError as exc:
        locked_until_iso = exc.locked_until.strftime("%Y-%m-%dT%H:%M:%SZ")
        raise HTTPException(
            status_code=429,
            detail=f"Account locked. Try again after {locked_until_iso}.",
        ) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid credentials.") from exc

    return LoginResponse(access_token=token)


@app.post("/auth/register", response_model=RegisterResponse, status_code=201, tags=["auth"])
async def register(body: RegisterRequest) -> RegisterResponse:
    """
    Register a new user account.

    - **201**: Account created successfully.
    - **409**: Email already registered.
    - **422**: Validation error (free email domain, short password, invalid email format, etc.)
    """
    service = AuthService()

    try:
        service.register(body.agent_travel_name, body.email, body.password)
    except RegistrationError as exc:
        # Distinguish duplicate-email (409) from domain rejection (422)
        if "already exists" in exc.message:
            raise HTTPException(status_code=409, detail=exc.message) from exc
        raise HTTPException(status_code=422, detail=exc.message) from exc

    return RegisterResponse(email=body.email)


# ---------------------------------------------------------------------------
# Fare Rules ingestion endpoint
# ---------------------------------------------------------------------------

@app.post("/fare-rules", response_model=IngestionResponse, tags=["fare-rules"])
async def upload_fare_rules(
    file: UploadFile = File(...),
    airline_code: str = Form(...),
    authorization: str | None = Header(default=None),
) -> IngestionResponse:
    """
    Ingest a Fare Rules document (PDF or plain text) into ChromaDB.

    - **200**: Document parsed, chunked, and stored successfully.
    - **401**: Missing or invalid JWT.
    - **409**: Document already uploaded for this airline.
    - **422**: Extraction failure or missing/invalid parameters.
    """
    # 1. JWT authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")

    token = authorization.removeprefix("Bearer ").strip()

    auth_service = AuthService()
    claims = auth_service.verify_jwt(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired JWT.")

    # 2. Validate airline_code
    if not airline_code or not airline_code.strip():
        raise HTTPException(status_code=422, detail="airline_code must be a non-empty string.")

    # 3. Save uploaded file to a temp file, ingest, then clean up
    tmp_path: str | None = None
    try:
        suffix = ".pdf" if (file.content_type or "").lower() == "application/pdf" else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        pipeline = IngestionPipeline()
        success, message = pipeline.ingest_document(tmp_path, airline_code.strip())
        
        if not success:
            if "already uploaded" in message:
                raise HTTPException(status_code=409, detail=message)
            else:
                raise HTTPException(status_code=422, detail=message)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to ingest fare rules: {exc}",
        ) from exc
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return IngestionResponse(
        status="success",
        message=message,
    )


# ---------------------------------------------------------------------------
# Audit endpoint
# ---------------------------------------------------------------------------

@app.post("/audit", response_model=AuditResponse, tags=["audit"])
async def audit(
    file: UploadFile = File(...),
    airline_code: str = Form(...),
    authorization: str | None = Header(default=None),
) -> AuditResponse:
    """
    Run the full ADM audit pipeline.

    Pipeline:
      1. Verify JWT from ``Authorization: Bearer <token>`` header.
      2. Check rate limit for the authenticated user.
      3. Extract text from the uploaded ADM PDF.
      4. Retrieve relevant Fare Rules chunks from ChromaDB.
      5. Call the LLM to produce a verdict, analysis, and dispute draft.
      6. Record the upload (only on success).
      7. Return ``AuditResponse``.

    Error codes:
      - **401**: JWT missing or invalid.
      - **422**: PDF extraction failure, no Fare Rules found, or malformed LLM response.
      - **429**: Rate limit exceeded (includes ``reset_at`` timestamp).
      - **502**: LLM call failed or timed out.
    """
    # ------------------------------------------------------------------
    # Step 1: JWT verification
    # ------------------------------------------------------------------
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    auth_service = AuthService()
    claims = auth_service.verify_jwt(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired JWT.")

    user_email: str = claims.sub

    # ------------------------------------------------------------------
    # Step 2: Rate limit check
    # ------------------------------------------------------------------
    rate_limiter = RateLimiter()
    quota = rate_limiter.check_quota(user_email)
    if not quota.allowed:
        reset_at_iso = (
            quota.reset_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if quota.reset_at
            else "unknown"
        )
        raise HTTPException(
            status_code=429,
            detail=f"Upload quota exceeded. Quota resets at {reset_at_iso}.",
        )

    # ------------------------------------------------------------------
    # Step 3: PDF text extraction
    # ------------------------------------------------------------------
    pdf_bytes = await file.read()
    extractor = PDFExtractor()
    extraction_result = extractor.extract_text(pdf_bytes)
    if isinstance(extraction_result, ExtractionError):
        raise HTTPException(
            status_code=422,
            detail=f"PDF extraction failed: {extraction_result.message}",
        )
    adm_text: str = extraction_result

    # ------------------------------------------------------------------
    # Step 4: Vector retrieval
    # ------------------------------------------------------------------
    retriever = VectorRetriever()
    chunks = retriever.retrieve_chunks(airline_code=airline_code, query_text=adm_text)
    if not chunks:
        raise HTTPException(
            status_code=422,
            detail=f"No Fare Rules are available for airline '{airline_code}'.",
        )

    # ------------------------------------------------------------------
    # Step 5: LLM call
    # ------------------------------------------------------------------
    orchestrator = LLMOrchestrator()
    llm_result = orchestrator.run_audit(adm_text=adm_text, fare_rules_chunks=chunks)
    if isinstance(llm_result, LLMError):
        # Distinguish between a call/timeout failure and a parse failure.
        # LLMError is used for both; parse errors contain "Malformed" in the message.
        if "Malformed" in llm_result.message or "malformed" in llm_result.message:
            raise HTTPException(
                status_code=422,
                detail=f"Malformed AI response: {llm_result.message}",
            )
        raise HTTPException(
            status_code=502,
            detail=f"AI service error: {llm_result.message}",
        )

    # ------------------------------------------------------------------
    # Step 6: Record upload (only on success)
    # ------------------------------------------------------------------
    rate_limiter.record_upload(user_email)

    # ------------------------------------------------------------------
    # Step 7: Return AuditResponse
    # ------------------------------------------------------------------
    return AuditResponse(
        verdict=llm_result.verdict,
        analysis=llm_result.analysis,
        dispute_draft=llm_result.dispute_draft,
    )


# ---------------------------------------------------------------------------
# Airlines endpoint (public — no JWT required)
# ---------------------------------------------------------------------------

@app.get("/airlines", response_model=list[Airline], tags=["airlines"])
async def list_airlines() -> list[Airline]:
    """
    Return all supported airlines from the `airlines` table.

    This endpoint is public (no JWT required) so the frontend can populate
    the airline selector before the user logs in.

    - **200**: List of `{ code, name }` objects.
    - **502**: Supabase query failed.
    """
    try:
        db = _get_supabase_client()
        response = (
            db.table("airlines")
            .select("code, name")
            .order("name")
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve airlines from the database.",
        ) from exc

    rows = response.data or []
    return [Airline(code=row["code"], name=row["name"]) for row in rows]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Liveness probe used by Hugging Face Spaces."""
    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    url = os.environ.get("SUPABASE_URL", "NOT SET")
    key = os.environ.get("SUPABASE_KEY", "NOT SET")
    # Only print partial key for security
    print(f"SUPABASE_URL: {url}")
    print(f"SUPABASE_KEY: {'SET (' + key[:15] + '...)' if key != 'NOT SET' else 'NOT SET'}")