import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'https://bnbpoly-production.up.railway.app';

// Proxy all /api requests to the backend (including WebSocket upgrades)
const proxyMiddleware = createProxyMiddleware({
  target: BACKEND_URL,
  changeOrigin: true,
  secure: true,
  ws: true, // Enable WebSocket proxying
  pathRewrite: {
    '^/api': '/api', // Keep /api in the path
  },
  onError: (err, req, res) => {
    console.error('Proxy error:', err);
    if (!res.headersSent) {
      res.status(500).json({ error: 'Proxy error', message: err.message });
    }
  },
  onProxyReq: (proxyReq, req, res) => {
    console.log(`Proxying ${req.method} ${req.url} to ${BACKEND_URL}${req.url}`);
    // Add CORS headers to the proxy request
    proxyReq.setHeader('Origin', BACKEND_URL);
  },
  onProxyRes: (proxyRes, req, res) => {
    // Add CORS headers to the response
    proxyRes.headers['Access-Control-Allow-Origin'] = '*';
    proxyRes.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
    proxyRes.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization';
    console.log(`Proxy response: ${proxyRes.statusCode} for ${req.url}`);
  },
  logLevel: 'info',
});

// Proxy API requests first
app.use('/api', proxyMiddleware);

// Serve static files from the dist directory
app.use(express.static(path.join(__dirname, 'dist')));

// Catch-all handler: serve index.html for all non-API routes
// This must be last to catch all routes not handled above
app.use((req, res) => {
  res.sendFile(path.join(__dirname, 'dist', 'index.html'));
});

const server = app.listen(PORT, () => {
  console.log(`Frontend server running on port ${PORT}`);
  console.log(`Proxying /api requests to ${BACKEND_URL}`);
});

// Handle WebSocket upgrades
if (proxyMiddleware.upgrade) {
  server.on('upgrade', proxyMiddleware.upgrade);
}
