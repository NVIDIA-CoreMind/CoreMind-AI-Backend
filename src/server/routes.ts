import { Router, Request, Response } from 'express';
import path from 'path';
import { defaultExecutionEngine } from '../agent/executionEngine.js';
import { defaultPythonRunner } from '../sandbox/pythonRunner.js';
import { defaultNebiusClient, SUPPORTED_NVIDIA_MODELS } from '../providers/nebiusClient.js';
import { SSEStream } from './sseHandler.js';
import { config } from '../config/env.js';

export const apiRouter = Router();

/**
 * Health check endpoint
 */
apiRouter.get('/health', async (_req: Request, res: Response) => {
  const nebiusHealth = await defaultNebiusClient.checkHealth();
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    nebius: nebiusHealth,
    environment: config.nodeEnv,
    activeModel: config.nebius.defaultModel,
  });
});

/**
 * Models list endpoint
 */
apiRouter.get('/api/models', (_req: Request, res: Response) => {
  res.json({
    defaultModel: config.nebius.defaultModel,
    supportedModels: SUPPORTED_NVIDIA_MODELS,
    baseUrl: defaultNebiusClient.baseUrl,
  });
});

/**
 * Main Agent Run Endpoint with Server-Sent Events (SSE) streaming
 * POST /api/agent/run
 * Body: { task: string, workspacePath?: string, model?: string, extraContext?: string }
 */
apiRouter.post('/api/agent/run', async (req: Request, res: Response): Promise<void> => {
  const { task, workspacePath, model, extraContext, maxIterations, maxDebugRetries } = req.body;

  if (!task || typeof task !== 'string') {
    res.status(400).json({ error: 'Field "task" is required and must be a string.' });
    return;
  }

  // Resolve target workspace
  const resolvedWorkspace = workspacePath
    ? path.resolve(workspacePath)
    : config.sandbox.workDir;

  // Initialize SSE stream
  const sse = new SSEStream(res);

  sse.send('phase_change', {
    from: 'INITIALIZING',
    to: 'TASK',
    reason: 'Received user task and initialized SSE stream',
  });

  try {
    const result = await defaultExecutionEngine.runAgentLoop({
      task,
      workspacePath: resolvedWorkspace,
      model,
      extraContext,
      maxIterations,
      maxDebugRetries,
      stream: sse,
    });

    sse.close({
      success: result.success,
      finalPhase: result.finalPhase,
      iterations: result.iterations,
      summary: result.summary,
      stateSummary: result.stateSummary,
    });
  } catch (error: any) {
    sse.send('error', { message: error.message || 'Execution failed' });
    sse.close({ success: false, error: error.message });
  }
});

/**
 * Direct Sandbox Python Execution Endpoint
 * POST /api/sandbox/execute
 * Body: { code?: string, scriptPath?: string, cwd?: string, timeout?: number }
 */
apiRouter.post('/api/sandbox/execute', async (req: Request, res: Response): Promise<void> => {
  const { code, scriptPath, cwd, timeout } = req.body;

  if (!code && !scriptPath) {
    res.status(400).json({ error: 'Either "code" or "scriptPath" must be provided.' });
    return;
  }

  try {
    const targetCwd = cwd ? path.resolve(cwd) : config.sandbox.workDir;
    const result = await defaultPythonRunner.runCode({
      code,
      scriptPath,
      cwd: targetCwd,
      timeoutMs: timeout,
    });

    res.json(result);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * Direct Sandbox Test Execution Endpoint
 * POST /api/sandbox/test
 * Body: { testCommand?: string, testPath?: string, cwd?: string, timeout?: number }
 */
apiRouter.post('/api/sandbox/test', async (req: Request, res: Response): Promise<void> => {
  const { testCommand, testPath, cwd, timeout } = req.body;

  try {
    const targetCwd = cwd ? path.resolve(cwd) : config.sandbox.workDir;
    const result = await defaultPythonRunner.runTests({
      testCommand,
      testPath,
      cwd: targetCwd,
      timeoutMs: timeout,
    });

    res.json(result);
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});
