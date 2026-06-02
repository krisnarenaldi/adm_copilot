# ── Stage: runtime ────────────────────────────────────────────────────────────
FROM python:3.13-slim

# Hugging Face Spaces runs as a non-root user; create one to match
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install system dependencies required by PyMuPDF and ChromaDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer-cache friendly)
# We copy the backend requirements.txt
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (from backend directory)
COPY backend/ .

# Pre-built ChromaDB vector store (bundled at build time)
# The chroma_db/ directory should be present in the build context.
# If it doesn't exist yet, ChromaDB will create an empty store at startup.

# Switch to non-root user
USER appuser

# Expose the port Hugging Face Spaces expects
EXPOSE 7860

# Start the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
