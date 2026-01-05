const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'https://bnbpoly-production.up.railway.app';

// Serve static files from the dist directory
app.use(express.static(path.join(__dirname, 'dist')));

// Proxy all /api requests to the backend
app.use('/api', createProxyMiddleware({
  target: BACKEND_URL,
  changeOrigin: true,
  pathRewrite: {
    '^/api': '/api', // Keep /api in the path
  },
  onProxyReq: (proxyReq, req, res) => {
    // Add CORS headers to the proxy request
    proxyReq.setHeader('Origin', BACKEND_URL);
  },
  onProxyRes: (proxyRes, req, res) => {
    // Add CORS headers to the response
    proxyRes.headers['Access-Control-Allow-Origin'] = '*';
    proxyRes.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
    proxyRes.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization';
  },
  logLevel: 'debug',
}));

// Handle all other routes - serve the React app
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'dist', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Frontend server running on port ${PORT}`);
  console.log(`Proxying /api requests to ${BACKEND_URL}`);
});

