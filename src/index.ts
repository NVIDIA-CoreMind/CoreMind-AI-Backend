import express from 'express';
import cors from 'cors';
import { config } from './config/env.js';
import { apiRouter } from './server/routes.js';
import { defaultPythonRunner } from './sandbox/pythonRunner.js';

export const app = express();

// Middlewares
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Request logger
app.use((req, _res, next) => {
  if (config.nodeEnv !== 'test') {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  }
  next();
});

// Mount Routes
app.use('/', apiRouter);

// Global Error Handler
app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error('[ServerError]', err);
  res.status(500).json({
    error: 'Internal Server Error',
    message: err?.message || 'Unknown error occurred',
  });
});

/**
 * Start Server
 */
export async function startServer() {
  // Ensure sandbox directory is ready
  await defaultPythonRunner.ensureWorkDir();

  const server = app.listen(config.port, () => {
    console.log(`
==============================================================
   CoreMind AI Backend - Autonomous Engineering Agent
==============================================================
  Port:              ${config.port}
  Environment:       ${config.nodeEnv}
  Nebius Base URL:   ${config.nebius.baseUrl}
  Active NVIDIA LLM: ${config.nebius.defaultModel}
  Sandbox Directory: ${config.sandbox.workDir}
  Python Path:       ${config.sandbox.pythonPath}
==============================================================
  Endpoints:
    - GET  /health            : Service & Nebius API connectivity
    - GET  /api/models        : List supported NVIDIA models
    - POST /api/agent/run     : Start agent loop (SSE Stream)
    - POST /api/sandbox/execute : Run isolated Python script
    - POST /api/sandbox/test    : Run test suite in sandbox
==============================================================
    `);
  });

  const shutdown = () => {
    console.log('\n[Server] Gracefully shutting down CoreMind AI backend...');
    server.close(() => {
      console.log('[Server] HTTP server closed.');
      process.exit(0);
    });
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  return server;
}

// Start immediately when executed directly
if (process.env.NODE_ENV !== 'test') {
  startServer().catch((err) => {
    console.error('[Fatal] Failed to start server:', err);
    process.exit(1);
  });
}
