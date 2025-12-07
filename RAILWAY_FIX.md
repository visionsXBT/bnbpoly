# Railway Deployment Fix

## The Problem
Railway is detecting Node.js instead of Python because it sees the root `package.json`.

## Solution: Configure Railway Settings

### For Backend Service:

1. **Go to your Backend service in Railway**
2. **Click on "Settings"**
3. **Under "Build & Deploy":**
   - **Root Directory**: Must be set to `backend` (this is critical!)
   - **Build Command**: Leave EMPTY or set to: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Under "Build":**
   - **Builder**: Select `Nixpacks` (NOT Railpack)
   - If you don't see this option, you may need to delete and recreate the service

### Alternative: Delete and Recreate Service

If the above doesn't work:

1. **Delete the current backend service**
2. **Create a new service** from the same GitHub repo
3. **IMMEDIATELY set Root Directory to `backend`** before Railway auto-detects
4. **Set Builder to `Nixpacks`** in settings
5. **Add environment variables:**
   - `ANTHROPIC_API_KEY`
   - `POLYMARKET_API_URL=https://gamma-api.polymarket.com`

### Verify Root Directory

The Root Directory MUST be `backend` (not `/backend` or `./backend`, just `backend`).

When Railway looks in the `backend` directory, it should see:
- `requirements.txt` → detects Python
- `main.py` → confirms Python project
- `nixpacks.toml` → tells Railway to use Nixpacks

### Check Build Logs

After redeploying, check the build logs. You should see:
- "Detected Python" (not "Detected Node")
- "Installing dependencies from requirements.txt"
- "Starting uvicorn"

If you still see "Detected Node", the Root Directory is not set correctly.

