# Deploying to Railway (Full Stack)

Railway can deploy both your frontend and backend from the same repository. You have two options:

## Option 1: Two Services (Recommended)

Deploy frontend and backend as separate Railway services from the same repo.

### Step 1: Deploy Backend Service

1. Go to [railway.app](https://railway.app) and sign up/login
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository
4. Railway will detect it's a Python project
5. **Configure the service:**
   - **Root Directory**: `backend`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Railway will auto-detect Python and install dependencies

6. **Add Environment Variables:**
   - `ANTHROPIC_API_KEY` = your Anthropic API key
   - `POLYMARKET_API_URL` = `https://gamma-api.polymarket.com`
   - `FRONTEND_URL` = (you'll set this after deploying frontend)

7. **Get your backend URL:**
   - Railway will provide a URL like `https://your-backend.railway.app`
   - Copy this URL

### Step 2: Deploy Frontend Service

1. In the same Railway project, click **"New Service"** → **"GitHub Repo"**
2. Select the same repository
3. **Configure the service:**
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Start Command**: `npx serve -s dist -l $PORT`
   - Railway will auto-detect Node.js

4. **Add Environment Variables:**
   - `VITE_API_BASE_URL` = `https://your-backend.railway.app` (use the backend URL from Step 1)
   - `PORT` = `3000` (or let Railway auto-assign)

5. **Get your frontend URL:**
   - Railway will provide a URL like `https://your-frontend.railway.app`

### Step 3: Update CORS

1. Go back to your **Backend Service** settings
2. Update the `FRONTEND_URL` environment variable with your frontend URL
3. Redeploy the backend service (Railway will auto-redeploy when env vars change)

### Step 4: Install serve for Frontend (if needed)

If Railway doesn't have `serve` available, you can:

1. Add to `frontend/package.json`:
   ```json
   {
     "scripts": {
       "start": "serve -s dist -l $PORT"
     },
     "dependencies": {
       "serve": "^14.2.0"
     }
   }
   ```

## Option 2: Single Service with Custom Build

Deploy everything as one service (more complex, not recommended).

### Setup

1. Create a `build.sh` script in the root:
   ```bash
   #!/bin/bash
   # Build frontend
   cd frontend
   npm install
   npm run build
   cd ..
   
   # Install backend dependencies
   cd backend
   pip install -r requirements.txt
   cd ..
   ```

2. Create a `start.sh` script:
   ```bash
   #!/bin/bash
   # Start backend
   cd backend
   uvicorn main:app --host 0.0.0.0 --port $PORT &
   
   # Serve frontend
   cd ../frontend
   npx serve -s dist -l 3000
   ```

3. In Railway:
   - **Build Command**: `chmod +x build.sh && ./build.sh`
   - **Start Command**: `chmod +x start.sh && ./start.sh`

## Recommended: Option 1 (Two Services)

Option 1 is cleaner because:
- ✅ Separate scaling for frontend and backend
- ✅ Independent deployments
- ✅ Better error isolation
- ✅ Easier to manage

## Environment Variables Summary

### Backend Service:
```
ANTHROPIC_API_KEY=your_key_here
POLYMARKET_API_URL=https://gamma-api.polymarket.com
FRONTEND_URL=https://your-frontend.railway.app
```

### Frontend Service:
```
VITE_API_BASE_URL=https://your-backend.railway.app
PORT=3000
```

## Post-Deployment Checklist

- [ ] Backend service is running and accessible
- [ ] Frontend service is running and accessible
- [ ] Frontend can make API calls to backend (check browser console)
- [ ] CORS is configured correctly
- [ ] Environment variables are set
- [ ] Test chat functionality
- [ ] Test trending markets loading

## Troubleshooting

### Frontend can't connect to backend
- Check `VITE_API_BASE_URL` is set correctly
- Verify backend URL is accessible
- Check CORS settings in backend
- Look at Railway logs for both services

### Build fails
- Check Railway logs for specific errors
- Verify all dependencies are in `package.json` and `requirements.txt`
- Ensure Node.js and Python versions are compatible

### Port issues
- Railway auto-assigns `$PORT` - don't hardcode ports
- Frontend should use `$PORT` or Railway's assigned port
- Backend uses `$PORT` from Railway

## Railway CLI (Optional)

You can also use Railway CLI:

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to project
railway link

# Deploy
railway up
```

