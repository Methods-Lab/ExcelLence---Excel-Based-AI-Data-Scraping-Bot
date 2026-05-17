# ExcelAI

ExcelAI is a Phase 1 AI-assisted data extraction and Excel table creation app built with FastAPI and a custom dark-luxury frontend.

**Note:** Repository updated - now syncing with Methods Lab (main branch)

## Features

- JWT login and signup
- Text, image, PDF, and URL extraction flows
- Groq-powered structured table generation with fallback parsing
- Inline table editing and sorting.
- Excel and CSV export
- Vercel deployment config

## Local Run

### Backend

```bash
cd excelai
python -m uvicorn backend.main:app --reload
```

### Frontend

Serve the  `frontend` folder with any static file server, or open `frontend/index.html` through a local dev server

## Demo Accounts

- `demo@excelai.dev` / `ExcelAI123!`
- `admin@excelai.dev` / `AdminExcelAI123!`

## Environment

Copy `backend/.env.example` to `.env` and set:

- `GROQ_API_KEY` — Your Groq API key from console.groq.com
- `SECRET_KEY` — A secure random string for JWT signing (min 32 chars)
- `ALGORITHM` — JWT algorithm (default: `HS256`)
- `ACCESS_TOKEN_EXPIRE_MINUTES` — Session duration in minutes (default: `1440` = 1 day)
- `CORS_ORIGINS` — Allowed frontend origins (dev: `http://localhost:3000`, production: your domain)
- `GROQ_MODEL` — Model name (default: `llama-3.3-70b-versatile`)

### Local Development

The `.env` file is automatically loaded when running the backend locally.

### Vercel Deployment

1. **Connect your GitHub repository to Vercel:**
   - Go to https://vercel.com
   - Click "New Project" and import your GitHub repository
   - Vercel will auto-detect the Python framework

2. **Configure Environment Variables:**
   - In your Vercel project, go to **Settings → Environment Variables**
   - Add these variables:
     - `GROQ_API_KEY` = your Groq API key (keep as secret)
     - `SECRET_KEY` = your JWT secret key (keep as secret)
     - `ALGORITHM` = `HS256`
     - `ACCESS_TOKEN_EXPIRE_MINUTES` = `1440`
     - `CORS_ORIGINS` = `https://your-project.vercel.app` (replace with your actual Vercel domain)
     - `GROQ_MODEL` = `llama-3.3-70b-versatile`

3. **Deploy:**
   - Click "Deploy"
   - Wait for the build to complete
   - Your app will be live at `https://your-project.vercel.app`

4. **After First Deployment:**
   - Note your actual Vercel domain
   - Update `CORS_ORIGINS` environment variable to match your production domain
   - Redeploy to apply the change

**Troubleshooting:**
- If you see a 404 error, check that all environment variables are set correctly
- Make sure `CORS_ORIGINS` uses `https://` (not `http://`) for production
- Check deployment logs in Vercel dashboard for any Python errors

**Pro Tip:** Use `vercel env pull` locally to test with production environment variables:

## API Endpoints

- `POST /api/auth/login`
- `POST /api/auth/signup`
- `GET /api/auth/me`
- `POST /api/extract/text`
- `POST /api/extract/image`
- `POST /api/extract/url`
- `POST /api/export/excel`
- `POST /api/export/csv`
