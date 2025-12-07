# Deployment Guide

This guide covers deploying the Polymarket Insights Chatbot to production.

## Architecture

- **Frontend**: React + Vite (deploy on Vercel)
- **Backend**: FastAPI (deploy on Railway, Render, or Fly.io)

## Option 1: Frontend on Vercel + Backend on Railway (Recommended)

### Deploy Frontend to Vercel

1. **Install Vercel CLI** (optional, can use web interface):
   ```bash
   npm i -g vercel
   ```

2. **Deploy from frontend directory**:
   ```bash
   cd frontend
   vercel
   ```

3. **Or use Vercel Dashboard**:
   - Go to [vercel.com](https://vercel.com)
   - Import your Git repository
   - Set root directory to `frontend`
   - Build command: `npm run build`
   - Output directory: `dist`

4. **Update API URL**:
   - After deploying backend, update `frontend/src/App.tsx`:
     ```typescript
     const API_BASE_URL = process.env.VITE_API_BASE_URL || 'https://your-backend-url.railway.app'
     ```
   - Or set environment variable `VITE_API_BASE_URL` in Vercel dashboard

### Deploy Backend to Railway

1. **Create Railway account** at [railway.app](https://railway.app)

2. **Create new project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo" (or use Railway CLI)

3. **Configure project**:
   - Root directory: `backend`
   - Build command: (leave empty, Railway auto-detects Python)
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

4. **Set environment variables** in Railway dashboard:
   ```
   ANTHROPIC_API_KEY=your_anthropic_api_key
   POLYMARKET_API_URL=https://gamma-api.polymarket.com
   PORT=8000
   ```

5. **Get your backend URL**:
   - Railway will provide a URL like `https://your-app.railway.app`
   - Update frontend to use this URL

### Alternative: Deploy Backend to Render

1. **Create Render account** at [render.com](https://render.com)

2. **Create new Web Service**:
   - Connect your GitHub repository
   - Root directory: `backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

3. **Set environment variables** in Render dashboard

4. **Get your backend URL** and update frontend

## Option 2: Deploy Both on Vercel (Serverless)

### Setup Vercel Serverless Functions

1. **Create `api/` directory in root**:
   ```
   api/
     handler.py
   ```

2. **Create `vercel.json` in root**:
   ```json
   {
     "builds": [
       {
         "src": "frontend/package.json",
         "use": "@vercel/static-build",
         "config": {
           "distDir": "dist"
         }
       },
       {
         "src": "api/handler.py",
         "use": "@vercel/python"
       }
     ],
     "routes": [
       {
         "src": "/api/(.*)",
         "dest": "api/handler.py"
       },
       {
         "src": "/(.*)",
         "dest": "frontend/$1"
       }
     ]
   }
   ```

3. **Note**: This approach requires refactoring FastAPI to work as serverless functions, which is more complex.

## Environment Variables

### Frontend (Vercel)
- `VITE_API_BASE_URL`: Your backend API URL

### Backend (Railway/Render)
- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `POLYMARKET_API_URL`: https://gamma-api.polymarket.com (default)
- `PORT`: Port number (usually auto-set by platform)

## CORS Configuration

Make sure your backend allows requests from your Vercel frontend domain:

```python
# In backend/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://your-frontend.vercel.app"  # Add your Vercel domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Post-Deployment Checklist

- [ ] Backend is accessible and returns health check
- [ ] Frontend can connect to backend API
- [ ] Environment variables are set correctly
- [ ] CORS is configured for production domain
- [ ] Test chat functionality
- [ ] Test trending markets loading
- [ ] Verify translations work

## Troubleshooting

### Frontend can't connect to backend
- Check CORS settings in backend
- Verify `VITE_API_BASE_URL` is set correctly
- Check backend logs for errors

### Backend deployment fails
- Verify all dependencies in `requirements.txt`
- Check Python version (Railway/Render usually auto-detect)
- Review build logs for specific errors

### API rate limits
- Check Anthropic API key is valid
- Verify Polymarket API is accessible
- Review backend logs for API errors

