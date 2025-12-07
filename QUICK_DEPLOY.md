# Quick Deployment Guide - Railway

## Step-by-Step Deployment

### Prerequisites
- GitHub account
- Railway account (free at [railway.app](https://railway.app))
- Anthropic API key

### Step 1: Push to GitHub

1. Initialize git (if not already done):
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

2. Create a GitHub repository and push:
   ```bash
   git remote add origin https://github.com/yourusername/your-repo-name.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Deploy Backend

1. Go to [railway.app](https://railway.app) and sign up/login
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. Railway will create a service - this will be your **backend**
6. Click on the service → **Settings**
7. Set **Root Directory** to: `backend`
8. Go to **Variables** tab and add:
   ```
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   POLYMARKET_API_URL=https://gamma-api.polymarket.com
   ```
9. Go to **Settings** → **Generate Domain** to get your backend URL
10. Copy the URL (e.g., `https://your-backend.railway.app`)

### Step 3: Deploy Frontend

1. In the same Railway project, click **"+ New"** → **"GitHub Repo"**
2. Select the same repository
3. Click on the new service → **Settings**
4. Set **Root Directory** to: `frontend`
5. Go to **Variables** tab and add:
   ```
   VITE_API_BASE_URL=https://your-backend.railway.app
   ```
   (Use the backend URL from Step 2)
6. Go to **Settings** → **Generate Domain** to get your frontend URL
7. Copy the URL (e.g., `https://your-frontend.railway.app`)

### Step 4: Update CORS

1. Go back to your **Backend** service
2. Go to **Variables** tab
3. Add/Update:
   ```
   FRONTEND_URL=https://your-frontend.railway.app
   ```
   (Use the frontend URL from Step 3)
4. Railway will automatically redeploy

### Step 5: Test

1. Visit your frontend URL
2. Open browser console (F12)
3. Try sending a message in the chat
4. Check that it connects to the backend

## Troubleshooting

### Backend won't start
- Check Railway logs: Click service → **Deployments** → Click latest deployment → **View Logs**
- Verify `ANTHROPIC_API_KEY` is set correctly
- Check that Root Directory is set to `backend`

### Frontend can't connect to backend
- Verify `VITE_API_BASE_URL` matches your backend URL exactly
- Check backend logs for CORS errors
- Make sure `FRONTEND_URL` is set in backend variables
- Check browser console for errors

### Build fails
- Check Railway logs for specific errors
- Verify all files are committed to GitHub
- Make sure Root Directory paths are correct

## Railway CLI (Alternative)

You can also use Railway CLI:

```bash
# Install
npm i -g @railway/cli

# Login
railway login

# Initialize
railway init

# Link to project
railway link

# Set variables
railway variables set ANTHROPIC_API_KEY=your_key

# Deploy
railway up
```

## Cost

Railway's free tier includes:
- $5 credit per month
- Enough for small to medium traffic
- Auto-sleeps after inactivity (wakes on request)

## Next Steps

- Set up custom domains (optional)
- Configure monitoring
- Set up automatic deployments from GitHub

