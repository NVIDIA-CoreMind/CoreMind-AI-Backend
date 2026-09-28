import { exec, spawn } from 'child_process';
import fs from 'fs/promises';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { config } from '../config/env.js';
import type { SandboxExecutionResult } from '../tools/types.js';

export interface PythonRunnerOptions {
  pythonPath?: string;
  defaultTimeoutMs?: number;
  workDir?: string;
}

export class PythonRunner {
  private pythonPath: string;
  private defaultTimeoutMs: number;
  private workDir: string;

  constructor(options?: PythonRunnerOptions) {
    this.pythonPath = options?.pythonPath || config.sandbox.pythonPath;
    this.defaultTimeoutMs = options?.defaultTimeoutMs || config.sandbox.timeoutMs;
    this.workDir = options?.workDir || config.sandbox.workDir;
  }

  /**
   * Ensure workspace sandbox directory exists
   */
  public async ensureWorkDir(dirPath: string = this.workDir): Promise<void> {
    try {
      await fs.mkdir(dirPath, { recursive: true });
    } catch (err: any) {
      console.error(`[PythonRunner] Failed to create sandbox dir: ${dirPath}`, err);
    }
  }

  /**
   * Extract Python traceback from stderr or stdout
   */
  public extractTraceback(output: string): string | undefined {
    const tracebackRegex = /Traceback \(most recent call last\):[\s\S]+?(?=(\r?\n\r?\n|$))/;
    const match = output.match(tracebackRegex);
    if (match) {
      return match[0].trim();
    }

    // Secondary match for assertion errors, syntax errors, or unhandled exceptions
    const exceptionRegex = /(?:(\w+Error|\w+Exception|AssertionError):[^\r\n]+)/;
    const excMatch = output.match(exceptionRegex);
    if (excMatch) {
      return excMatch[0].trim();
    }

    return undefined;
  }

  /**
   * Execute Python code passed as string or script file in isolated workspace
   */
  public async runCode(params: {
    code?: string;
    scriptPath?: string;
    args?: string[];
    cwd?: string;
    timeoutMs?: number;
  }): Promise<SandboxExecutionResult> {
    const targetCwd = params.cwd || this.workDir;
    await this.ensureWorkDir(targetCwd);

    const timeout = params.timeoutMs ?? this.defaultTimeoutMs;
    let tempScriptCreated = false;
    let finalScriptPath: string;

    if (params.code) {
      const tempFileName = `_temp_run_${Date.now()}_${uuidv4().substring(0, 8)}.py`;
      finalScriptPath = path.join(targetCwd, tempFileName);
      await fs.writeFile(finalScriptPath, params.code, 'utf-8');
      tempScriptCreated = true;
    } else if (params.scriptPath) {
      finalScriptPath = path.isAbsolute(params.scriptPath)
        ? params.scriptPath
        : path.join(targetCwd, params.scriptPath);
    } else {
      return {
        success: false,
        stdout: '',
        stderr: 'No code or scriptPath provided for execution.',
        exitCode: 1,
        durationMs: 0,
        command: '',
      };
    }

    const commandArgs = [finalScriptPath, ...(params.args || [])];
    const startTime = Date.now();

    try {
      const result = await this.spawnProcess(this.pythonPath, commandArgs, targetCwd, timeout);
      const durationMs = Date.now() - startTime;
      const combinedOutput = `${result.stdout}\n${result.stderr}`;
      const traceback = this.extractTraceback(combinedOutput);

      return {
        success: result.exitCode === 0,
        stdout: result.stdout,
        stderr: result.stderr,
        exitCode: result.exitCode,
        traceback,
        durationMs,
        command: `${this.pythonPath} ${commandArgs.join(' ')}`,
      };
    } finally {
      if (tempScriptCreated) {
        try {
          await fs.unlink(finalScriptPath);
        } catch {
          // Ignore temp file cleanup errors
        }
      }
    }
  }

  /**
   * Run pytest or testing command within target directory
   */
  public async runTests(params: {
    testCommand?: string;
    testPath?: string;
    cwd?: string;
    timeoutMs?: number;
  }): Promise<SandboxExecutionResult> {
    const targetCwd = params.cwd || this.workDir;
    await this.ensureWorkDir(targetCwd);

    const timeout = params.timeoutMs ?? this.defaultTimeoutMs;
    let cmd = params.testCommand;

    if (!cmd) {
      const testTarget = params.testPath ? `"${params.testPath}"` : '';
      cmd = `python -m pytest -v ${testTarget}`.trim();
    }

    const startTime = Date.now();

    return new Promise<SandboxExecutionResult>((resolve) => {
      exec(
        cmd,
        {
          cwd: targetCwd,
          timeout,
          env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            PYTHONPATH: targetCwd,
          },
        },
        (error, stdout, stderr) => {
          const durationMs = Date.now() - startTime;
          const exitCode = error ? (error.code ?? 1) : 0;
          const combinedOutput = `${stdout}\n${stderr}`;
          const traceback = this.extractTraceback(combinedOutput);

          // Pytest returns code 0 for all tests passed, 1 for some failed, 5 for no tests collected
          resolve({
            success: exitCode === 0,
            stdout: stdout.toString(),
            stderr: stderr.toString(),
            exitCode: typeof exitCode === 'number' ? exitCode : 1,
            traceback,
            durationMs,
            command: cmd,
          });
        }
      );
    });
  }

  /**
   * Internal process spawner with timeout and output capture
   */
  private spawnProcess(
    command: string,
    args: string[],
    cwd: string,
    timeoutMs: number
  ): Promise<{ stdout: string; stderr: string; exitCode: number }> {
    return new Promise((resolve) => {
      const child = spawn(command, args, {
        cwd,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: '1',
          PYTHONPATH: cwd,
        },
        shell: false,
      });

      let stdout = '';
      let stderr = '';
      let timedOut = false;

      const timer = setTimeout(() => {
        timedOut = true;
        child.kill('SIGTERM');
        setTimeout(() => {
          if (!child.killed) {
            child.kill('SIGKILL');
          }
        }, 1000);
      }, timeoutMs);

      child.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      child.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      child.on('error', (err) => {
        clearTimeout(timer);
        resolve({
          stdout,
          stderr: `${stderr}\nExecution Error: ${err.message}`,
          exitCode: 1,
        });
      });

      child.on('close', (code) => {
        clearTimeout(timer);
        if (timedOut) {
          stderr += `\n[Sandbox Timeout] Process killed after ${timeoutMs}ms limit exceeded.`;
        }
        resolve({
          stdout,
          stderr,
          exitCode: timedOut ? 124 : (code ?? 0),
        });
      });
    });
  }
}

export const defaultPythonRunner = new PythonRunner();
