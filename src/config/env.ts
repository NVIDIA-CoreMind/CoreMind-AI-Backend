import dotenv from 'dotenv';
import path from 'path';
import { z } from 'zod';

// Load .env file
dotenv.config();

const envSchema = z.object({
  PORT: z.coerce.number().default(4000),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  NEBIUS_API_KEY: z.string().default('dummy-key-for-dev'),
  NEBIUS_BASE_URL: z.string().default('https://api.tokenfactory.nebius.com/v1'),
  NEBIUS_MODEL: z.string().default('nvidia/llama-3.1-nemotron-70b-instruct'),
  PYTHON_PATH: z.string().default('python'),
  SANDBOX_TIMEOUT_MS: z.coerce.number().default(30000),
  SANDBOX_WORK_DIR: z.string().default(path.resolve(process.cwd(), 'workspace_sandbox')),
  AGENT_MAX_ITERATIONS: z.coerce.number().default(25),
  AGENT_MAX_DEBUG_RETRIES: z.coerce.number().default(5),
});

const parsedEnv = envSchema.safeParse(process.cwd() ? process.env : {});

if (!parsedEnv.success) {
  console.error('Invalid environment variables:', parsedEnv.error.format());
  throw new Error('Environment configuration validation failed');
}

export const config = {
  port: parsedEnv.data.PORT,
  nodeEnv: parsedEnv.data.NODE_ENV,
  nebius: {
    apiKey: parsedEnv.data.NEBIUS_API_KEY,
    baseUrl: parsedEnv.data.NEBIUS_BASE_URL,
    defaultModel: parsedEnv.data.NEBIUS_MODEL,
  },
  sandbox: {
    pythonPath: parsedEnv.data.PYTHON_PATH,
    timeoutMs: parsedEnv.data.SANDBOX_TIMEOUT_MS,
    workDir: path.resolve(process.cwd(), parsedEnv.data.SANDBOX_WORK_DIR),
  },
  agent: {
    maxIterations: parsedEnv.data.AGENT_MAX_ITERATIONS,
    maxDebugRetries: parsedEnv.data.AGENT_MAX_DEBUG_RETRIES,
  },
};

export type AppConfig = typeof config;
