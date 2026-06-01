# ADM Copilot ✈️
An AI-powered travel audit assistant that automates the investigation of Agency Debit Memos (ADMs) using Retrieval-Augmented Generation (RAG)!

## What is it?
- Auditors can upload an ADM PDF, select an airline, and get an AI-generated audit verdict and a ready-to-send dispute letter!
- Uses a RAG architecture to cross-reference ADMs against stored airline fare rules!

## Tech Stack
### Frontend
- Next.js 14 (React framework)
- Tailwind CSS (Styling)
- Vercel (Hosting)

### Backend
- FastAPI (Web framework)
- ChromaDB (Vector database)
- Sentence-Transformers (Embeddings)
- Google Gemini (LLM for analysis and letter generation)
- Hugging Face Spaces (Hosting)

### Other Services
- Supabase PostgreSQL (User auth, rate limiting, and airlines data)
- Docker (Containerization)

## Getting Started Locally
### Prerequisites
- Python 3.11+
- Node.js 18+
- Supabase account + project
- Google AI API key (from [aistudio.google.com](https://aistudio.google.com/app/apikey))

### 1. Clone or navigate to the repo
```bash
cd /Users/krisnarenaldi/Documents/Projects/ADM_Copilot
```

### 2. Set up Backend
```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and fill in your Supabase and Google AI API keys!
cp .env.example .env
```

### 3. Set up Frontend
```bash
cd ../frontend

# Install dependencies
npm install

# Copy .env.example to .env.local and update NEXT_PUBLIC_API_URL!
cp .env.example .env.local
```

### 4. Run the Services!
```bash
# Run backend in one terminal (from backend directory)
cd backend
python -m uvicorn main:app --reload

# Run frontend in another terminal (from frontend directory)
cd frontend
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000)!

## How to Use
1. Register a new account or login
2. Select an airline
3. (Optional) Upload fare rules document for that airline
4. Upload your ADM PDF and click "Run Audit"
5. View verdict, analysis, and copy dispute letter!

## Deployment
For full deployment instructions, see [DEPLOYMENT.md](./DEPLOYMENT.md)!

## License
MIT
