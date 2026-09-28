import type { ChatCompletionTool } from 'openai/resources/chat/completions.mjs';
import { executeReadFile, executeWriteFile, executeApplyDiff } from './fileTools.js';
import { executeRunSandboxPython, executeRunSandboxTests } from './sandboxTools.js';
import { PythonRunner, defaultPythonRunner } from '../sandbox/pythonRunner.js';
import type {
  ToolResult,
  ReadFileArgs,
  WriteFileArgs,
  ApplyDiffArgs,
  RunSandboxPythonArgs,
  RunSandboxTestsArgs,
  SupportedToolName,
} from './types.js';

/**
 * Standard OpenAI Tools Schema exposed to Nebius/NVIDIA Models
 */
export const CORE_MIND_TOOLS: ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: 'read_file',
      description: 'Read the contents of a file within the workspace. Supports viewing specific line spans.',
      parameters: {
        type: 'object',
        properties: {
          path: {
            type: 'string',
            description: 'Relative path to the file within the active workspace.',
          },
          start_line: {
            type: 'number',
            description: 'Optional 1-indexed starting line number.',
          },
          end_line: {
            type: 'number',
            description: 'Optional 1-indexed ending line number.',
          },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'write_file',
      description: 'Create a new file or completely overwrite an existing file with provided content.',
      parameters: {
        type: 'object',
        properties: {
          path: {
            type: 'string',
            description: 'Relative path where the file will be saved.',
          },
          content: {
            type: 'string',
            description: 'The raw UTF-8 string content to write.',
          },
        },
        required: ['path', 'content'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'apply_diff',
      description: 'Apply surgical diff modifications to an existing file using unified diff or search/replace blocks.',
      parameters: {
        type: 'object',
        properties: {
          path: {
            type: 'string',
            description: 'Relative path of the target file to patch.',
          },
          patch: {
            type: 'string',
            description: 'Unified diff patch or <<<<<<< SEARCH / ======= / >>>>>>> block patch.',
          },
        },
        required: ['path', 'patch'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_sandbox_python',
      description: 'Execute Python code or a Python script inside the isolated execution sandbox.',
      parameters: {
        type: 'object',
        properties: {
          code: {
            type: 'string',
            description: 'Python code snippet to execute directly.',
          },
          script_path: {
            type: 'string',
            description: 'Relative path to an existing Python file in workspace to execute.',
          },
          args: {
            type: 'array',
            items: { type: 'string' },
            description: 'Optional CLI command line arguments to pass to the Python process.',
          },
          timeout: {
            type: 'number',
            description: 'Optional timeout in milliseconds (default: 30000).',
          },
        },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_sandbox_tests',
      description: 'Execute pytest or unittest test suites inside the isolated sandbox and capture complete test outcomes.',
      parameters: {
        type: 'object',
        properties: {
          test_command: {
            type: 'string',
            description: 'Optional custom test command (e.g., "pytest tests/test_core.py -v"). Defaults to "python -m pytest -v".',
          },
          test_path: {
            type: 'string',
            description: 'Optional relative path to a specific test file or directory.',
          },
          timeout: {
            type: 'number',
            description: 'Optional timeout in milliseconds.',
          },
        },
      },
    },
  },
];

export class ToolRegistry {
  private runner: PythonRunner;

  constructor(runner: PythonRunner = defaultPythonRunner) {
    this.runner = runner;
  }

  public getTools(): ChatCompletionTool[] {
    return CORE_MIND_TOOLS;
  }

  /**
   * Dispatch and execute a tool call by name with validated arguments
   */
  public async executeTool(
    toolName: string,
    rawArgs: string | Record<string, any>,
    workspaceRoot: string
  ): Promise<ToolResult> {
    let parsedArgs: Record<string, any>;

    if (typeof rawArgs === 'string') {
      try {
        parsedArgs = JSON.parse(rawArgs);
      } catch (err: any) {
        return {
          success: false,
          error: `Malformed JSON arguments for tool "${toolName}": ${err.message}`,
        };
      }
    } else {
      parsedArgs = rawArgs;
    }

    try {
      switch (toolName as SupportedToolName) {
        case 'read_file':
          return await executeReadFile(
            workspaceRoot,
            parsedArgs.path,
            parsedArgs.start_line,
            parsedArgs.end_line
          );

        case 'write_file':
          return await executeWriteFile(workspaceRoot, parsedArgs.path, parsedArgs.content);

        case 'apply_diff':
          return await executeApplyDiff(workspaceRoot, parsedArgs.path, parsedArgs.patch);

        case 'run_sandbox_python':
          return await executeRunSandboxPython(
            this.runner,
            parsedArgs as RunSandboxPythonArgs,
            workspaceRoot
          );

        case 'run_sandbox_tests':
          return await executeRunSandboxTests(
            this.runner,
            parsedArgs as RunSandboxTestsArgs,
            workspaceRoot
          );

        default:
          return {
            success: false,
            error: `Unsupported tool: "${toolName}". Available tools: read_file, write_file, apply_diff, run_sandbox_python, run_sandbox_tests.`,
          };
      }
    } catch (err: any) {
      return {
        success: false,
        error: `Unexpected error executing tool "${toolName}": ${err.message}`,
      };
    }
  }
}

export const defaultToolRegistry = new ToolRegistry();
