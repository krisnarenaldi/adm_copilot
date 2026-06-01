# ADM Copilot Deployment Guide

## Overview
- Frontend: Deployed to **Vercel** (free tier)
- Backend (FastAPI + ChromaDB): Deployed to **Hugging Face Spaces** (free tier)
- Auth + Rate Limiting: **Supabase** (free tier)
- LLM: **Google AI (Gemini)** (free tier)

---

## Step 1: Set up Supabase

1. Sign up at [supabase.com](https://supabase.com/) and create a new project
2. Wait for your database to provision (~2 minutes)
3. Go to **Project Settings → API**:
   - Copy your `SUPABASE_URL` and `SUPABASE_KEY` (Secret key, not public)
4. Now create the required tables using the SQL Editor (go to **SQL Editor**):

   ### Create users table
   ```sql
   CREATE TABLE users (
       id SERIAL PRIMARY KEY,
       agent_travel_name TEXT NOT NULL,
       email TEXT UNIQUE NOT NULL,
       password_hash TEXT NOT NULL
   );
   ```

   ### Create login_attempts table (for rate limiting failed logins)
   ```sql
   CREATE TABLE login_attempts (
       id SERIAL PRIMARY KEY,
       email TEXT NOT NULL,
       success BOOLEAN NOT NULL,
       attempted_at TIMESTAMPTZ DEFAULT NOW()
   );
   ```

   ### Create user_uploads table
   ```sql
   CREATE TABLE user_uploads (
       id SERIAL PRIMARY KEY,
       user_email TEXT NOT NULL,
       upload_count INTEGER DEFAULT 0,
       last_upload_date TIMESTAMPTZ DEFAULT NOW(),
       UNIQUE(user_email)
   );
   ```

   ### Create airlines table
   ```sql
   CREATE TABLE airlines (
       code TEXT PRIMARY KEY,
       name TEXT NOT NULL
   );
   ```

5. Now insert the test airlines:
   ```sql
   INSERT INTO airlines (code, name) VALUES
   ('GA', 'Garuda Indonesia'),
   ('SQ', 'Singapore Airlines'),
   ('MH', 'Malaysia Airlines'),
   ('EK', 'Emirates'),
   ('QF', 'Qantas');
   ```

---

## Step 2: Get Google AI API Key
1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API Key** and create one for your project
3. Copy the generated key

---

## Step 3: Deploy Backend to Hugging Face Space

Okay! Since you're keeping the whole ADM_Copilot folder as a single GitHub repo (monorepo) for Vercel, we have two options for Hugging Face! Let's go with the simplest option:

### Option A (Easiest & Recommended): Push your entire monorepo to Hugging Face!
We've already added a root `Dockerfile` that knows to build the backend, so you can just push the whole repo! Steps:
1. Go to [huggingface.co/spaces](https://huggingface.co/spaces) and click **Create new Space**
2. Fill out the form:
   - **Owner**: Your account
   - **Space name**: adm-copilot-backend (or whatever you want)
   - **License**: (your choice)
   - **Select the Space SDK**: Docker
   - **Docker template**: Blank (no template)
   - **Hardware**: (CPU Basic - free tier is fine)
   - **Repositiory visibility**: (your choice - public or private)
3. Click **Create Space**
4. Now you'll be on your Space page. Let's push the code!

First, initialize git in your project folder if you haven't already:
```bash
cd /Users/krisnarenaldi/Documents/Projects/ADM_Copilot
git init
git add .
git commit -m "Initial commit"
```

Then, add GitHub remote (for Vercel's frontend):
```bash
# Add GitHub remote (replace with your repo URL!)
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git branch -M main
git push -u origin main
```

Now add your Hugging Face Space as a second remote and push to both!
```bash
# Replace <your-username> and <your-space-name>!
git remote add space https://huggingface.co/spaces/<your-username>/<your-space-name>
git push space main
```

Okay, that's it! Now both GitHub (for Vercel) and Hugging Face (for backend) have the code!

5. After pushing, go to your Hugging Face Space's Settings → **Variables and secrets**:
   - Click **New secret** and add all variables from `backend/.env.example`:
     - `SUPABASE_URL` (your Supabase URL)
     - `SUPABASE_KEY` (your Supabase secret key)
     - `JWT_SECRET` (use `openssl rand -hex 32` to generate one locally!)
     - `JWT_ALGORITHM` = HS256
     - `GOOGLE_API_KEY` (your Google AI API key)
     - `MAX_UPLOADS_PER_DAY` = 5
     - `ALLOWED_ORIGINS` = `http://localhost:3000,https://<your-vercel-app>.vercel.app` (we'll update this after deploying frontend!)
     - `CHROMA_DB_PATH` = ./chroma_db

---

## Step 4: Deploy Frontend to Vercel

1. Create a GitHub repo (or GitLab, etc.) and push your project to it (make sure to push all frontend files!)
2. Go to [vercel.com/new](https://vercel.com/new), sign in, and import your repo
3. Under "Configure Project":
   - **Root Directory**: `frontend`
   - **Framework Preset**: Next.js
4. Click **Environment Variables** and add:
   - `NEXT_PUBLIC_API_URL`: This is your Hugging Face Space URL! It should look like `https://<your-username>-<your-space-name>.hf.space`
5. Click **Deploy**!
6. After your frontend is deployed, go back to your Hugging Face Space's **Variables and secrets** and update `ALLOWED_ORIGINS` to include your new Vercel URL! It should look like:
   `ALLOWED_ORIGINS=http://localhost:3000,https://<your-vercel-app>.vercel.app`

---

## How to use after deployment

1. Register an account at your Vercel frontend
2. Select an airline
3. (Optional) Upload your first set of fare rules
4. Upload your ADM PDF and get your audit result!
