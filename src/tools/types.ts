/**
 * Tool Interfaces and Types for CoreMind Agent
 */

export interface ReadFileArgs {
  path: string;
  start_line?: number;
  end_line?: number;
}

export interface WriteFileArgs {
  path: string;
  content: string;
}

export interface ApplyDiffArgs {
  path: string;
  patch: string;
}

export interface RunSandboxPythonArgs {
  code?: string;
  script_path?: string;
  args?: string[];
  timeout?: number;
}

export interface RunSandboxTestsArgs {
  test_command?: string;
  test_path?: string;
  timeout?: number;
}

export interface SandboxExecutionResult {
  success: boolean;
  stdout: string;
  stderr: string;
  exitCode: number;
  traceback?: string;
  durationMs: number;
  command: string;
}

export interface ToolResult<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export type SupportedToolName =
  | 'read_file'
  | 'write_file'
  | 'apply_diff'
  | 'run_sandbox_python'
  | 'run_sandbox_tests';

export interface ToolExecutionContext {
  workspaceRoot: string;
  sessionId: string;
}
