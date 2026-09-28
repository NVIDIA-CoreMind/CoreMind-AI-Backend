import { PythonRunner, defaultPythonRunner } from '../sandbox/pythonRunner.js';
import type {
  RunSandboxPythonArgs,
  RunSandboxTestsArgs,
  SandboxExecutionResult,
  ToolResult,
} from './types.js';

export async function executeRunSandboxPython(
  runner: PythonRunner = defaultPythonRunner,
  args: RunSandboxPythonArgs,
  workspaceRoot: string
): Promise<ToolResult<SandboxExecutionResult>> {
  try {
    const result = await runner.runCode({
      code: args.code,
      scriptPath: args.script_path,
      args: args.args,
      cwd: workspaceRoot,
      timeoutMs: args.timeout,
    });

    const isSuccess = result.exitCode === 0;

    return {
      success: isSuccess,
      data: result,
      message: isSuccess
        ? `Python execution completed successfully in ${result.durationMs}ms.`
        : `Python execution failed with exit code ${result.exitCode}. Stderr: ${result.stderr}`,
    };
  } catch (error: any) {
    return {
      success: false,
      error: `Sandbox execution error: ${error.message}`,
    };
  }
}

export async function executeRunSandboxTests(
  runner: PythonRunner = defaultPythonRunner,
  args: RunSandboxTestsArgs,
  workspaceRoot: string
): Promise<ToolResult<SandboxExecutionResult>> {
  try {
    const result = await runner.runTests({
      testCommand: args.test_command,
      testPath: args.test_path,
      cwd: workspaceRoot,
      timeoutMs: args.timeout,
    });

    const isSuccess = result.exitCode === 0;

    return {
      success: isSuccess,
      data: result,
      message: isSuccess
        ? `All tests passed cleanly in ${result.durationMs}ms.`
        : `Tests failed with exit code ${result.exitCode}.\nTraceback/Error: ${result.traceback || result.stderr || 'No explicit traceback'}`,
    };
  } catch (error: any) {
    return {
      success: false,
      error: `Sandbox test execution error: ${error.message}`,
    };
  }
}
