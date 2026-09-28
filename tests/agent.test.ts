import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import path from 'path';
import fs from 'fs/promises';
import { AgentStateMachine, AgentPhase } from '../src/agent/stateMachine.js';
import { PythonRunner } from '../src/sandbox/pythonRunner.js';
import { executeReadFile, executeWriteFile, executeApplyDiff, resolveSafePath } from '../src/tools/fileTools.js';
import { ToolRegistry, CORE_MIND_TOOLS } from '../src/tools/registry.js';
import { ExecutionEngine } from '../src/agent/executionEngine.js';
import { NebiusClient } from '../src/providers/nebiusClient.js';

const TEST_WORKSPACE = path.resolve(process.cwd(), 'workspace_test_sandbox');

describe('CoreMind Agent - State Machine', () => {
  it('should initialize in TASK phase', () => {
    const sm = new AgentStateMachine();
    expect(sm.getCurrentPhase()).toBe(AgentPhase.TASK);
    expect(sm.isTerminal()).toBe(false);
  });

  it('should transition through the 7-step engineering phases', () => {
    const transitions: AgentPhase[] = [];
    const sm = new AgentStateMachine({
      onPhaseChange: (_from, to) => transitions.push(to),
    });

    sm.transitionTo(AgentPhase.PLAN, 'Planning task');
    sm.transitionTo(AgentPhase.CODE, 'Generating code');
    sm.transitionTo(AgentPhase.RUN, 'Running in sandbox');
    sm.transitionTo(AgentPhase.TEST, 'Testing code');
    sm.transitionTo(AgentPhase.DEBUG, 'Debugging failed test');
    sm.transitionTo(AgentPhase.VERIFY, 'Verifying fixed code');
    sm.complete('All tests passed');

    expect(sm.getCurrentPhase()).toBe(AgentPhase.COMPLETED);
    expect(sm.isTerminal()).toBe(true);
    expect(transitions).toEqual([
      AgentPhase.PLAN,
      AgentPhase.CODE,
      AgentPhase.RUN,
      AgentPhase.TEST,
      AgentPhase.DEBUG,
      AgentPhase.VERIFY,
      AgentPhase.COMPLETED,
    ]);
  });

  it('should detect phase transitions from model text output', () => {
    const sm = new AgentStateMachine();

    const phase1 = sm.detectAndTransitionFromText('[PHASE: PLAN]\nI will now analyze the dependencies.');
    expect(phase1).toBe(AgentPhase.PLAN);
    expect(sm.getCurrentPhase()).toBe(AgentPhase.PLAN);

    const phase2 = sm.detectAndTransitionFromText('Let us start coding [PHASE: CODE] now.');
    expect(phase2).toBe(AgentPhase.CODE);
    expect(sm.getCurrentPhase()).toBe(AgentPhase.CODE);
  });

  it('should enforce max debug retries and fail task', () => {
    const sm = new AgentStateMachine({ maxDebugRetries: 2 });

    sm.transitionTo(AgentPhase.DEBUG, 'Error 1');
    expect(sm.getDebugRetryCount()).toBe(1);

    sm.transitionTo(AgentPhase.CODE, 'Fix 1');
    sm.transitionTo(AgentPhase.DEBUG, 'Error 2');
    expect(sm.getDebugRetryCount()).toBe(2);

    sm.transitionTo(AgentPhase.CODE, 'Fix 2');
    sm.transitionTo(AgentPhase.DEBUG, 'Error 3 - exceeds limit');

    expect(sm.getCurrentPhase()).toBe(AgentPhase.FAILED);
    expect(sm.isTerminal()).toBe(true);
  });

  it('should not allow transitions once in terminal state', () => {
    const sm = new AgentStateMachine();
    sm.complete('Done');
    const result = sm.transitionTo(AgentPhase.PLAN, 'Cannot transition');
    expect(result).toBe(false);
    expect(sm.getCurrentPhase()).toBe(AgentPhase.COMPLETED);
  });
});

describe('CoreMind Agent - Python Sandbox Runner', () => {
  let runner: PythonRunner;

  beforeEach(async () => {
    runner = new PythonRunner({ workDir: TEST_WORKSPACE, defaultTimeoutMs: 5000 });
    await runner.ensureWorkDir();
  });

  afterEach(async () => {
    try {
      await fs.rm(TEST_WORKSPACE, { recursive: true, force: true });
    } catch {
      // Ignore cleanup error
    }
  });

  it('should execute valid Python code and capture stdout', async () => {
    const result = await runner.runCode({
      code: 'print("CoreMind Sandbox Execution Active")\nprint(40 + 2)',
    });

    expect(result.success).toBe(true);
    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain('CoreMind Sandbox Execution Active');
    expect(result.stdout).toContain('42');
    expect(result.traceback).toBeUndefined();
  });

  it('should capture tracebacks and errors upon execution failure', async () => {
    const result = await runner.runCode({
      code: 'def divide(a, b):\n    return a / b\n\ndivide(10, 0)',
    });

    expect(result.success).toBe(false);
    expect(result.exitCode).not.toBe(0);
    expect(result.traceback).toBeDefined();
    expect(result.traceback).toContain('ZeroDivisionError');
  });

  it('should handle timeout when execution takes too long', async () => {
    const result = await runner.runCode({
      code: 'import time\ntime.sleep(5)',
      timeoutMs: 800,
    });

    expect(result.success).toBe(false);
    expect(result.exitCode).toBe(124);
    expect(result.stderr).toContain('[Sandbox Timeout]');
  });
});

describe('CoreMind Agent - File Workspace Tools', () => {
  beforeEach(async () => {
    await fs.mkdir(TEST_WORKSPACE, { recursive: true });
  });

  afterEach(async () => {
    try {
      await fs.rm(TEST_WORKSPACE, { recursive: true, force: true });
    } catch {
      // Ignore
    }
  });

  it('should reject path traversal outside workspace', () => {
    expect(() => {
      resolveSafePath(TEST_WORKSPACE, '../../secret.txt');
    }).toThrow(/Access denied/);
  });

  it('should write and read files with line range support', async () => {
    const content = ['line 1', 'line 2', 'line 3', 'line 4', 'line 5'].join('\n');
    const writeRes = await executeWriteFile(TEST_WORKSPACE, 'sub/test.txt', content);

    expect(writeRes.success).toBe(true);
    expect(writeRes.data?.bytesWritten).toBeGreaterThan(0);

    // Read full
    const fullRead = await executeReadFile(TEST_WORKSPACE, 'sub/test.txt');
    expect(fullRead.success).toBe(true);
    expect(fullRead.data?.content).toBe(content);
    expect(fullRead.data?.totalLines).toBe(5);

    // Read lines 2-4
    const partialRead = await executeReadFile(TEST_WORKSPACE, 'sub/test.txt', 2, 4);
    expect(partialRead.success).toBe(true);
    expect(partialRead.data?.content).toContain('2: line 2');
    expect(partialRead.data?.content).toContain('4: line 4');
    expect(partialRead.data?.content).not.toContain('1: line 1');
  });

  it('should apply search/replace block patches surgically', async () => {
    const initialCode = `def calculate(a, b):\n    return a - b\n`;
    await executeWriteFile(TEST_WORKSPACE, 'math_utils.py', initialCode);

    const patch = `<<<<<<< SEARCH
def calculate(a, b):
    return a - b
=======
def calculate(a, b):
    return a + b
>>>>>>>`;

    const diffRes = await executeApplyDiff(TEST_WORKSPACE, 'math_utils.py', patch);
    expect(diffRes.success).toBe(true);

    const updated = await executeReadFile(TEST_WORKSPACE, 'math_utils.py');
    expect(updated.data?.content).toContain('return a + b');
  });
});

describe('CoreMind Agent - Tool Registry', () => {
  it('should expose OpenAI standard tool schemas', () => {
    const registry = new ToolRegistry();
    const tools = registry.getTools();

    expect(tools.length).toBe(5);
    const names = tools.map((t) => (t as any).function.name);
    expect(names).toContain('read_file');
    expect(names).toContain('write_file');
    expect(names).toContain('apply_diff');
    expect(names).toContain('run_sandbox_python');
    expect(names).toContain('run_sandbox_tests');
  });

  it('should return error on unknown tool call', async () => {
    const registry = new ToolRegistry();
    const res = await registry.executeTool('unknown_tool', {}, TEST_WORKSPACE);
    expect(res.success).toBe(false);
    expect(res.error).toContain('Unsupported tool');
  });
});

describe('CoreMind Agent - Execution Engine (Mocked LLM Loop)', () => {
  it('should run a multi-turn autonomous loop through verification', async () => {
    // Mock NebiusClient to simulate LLM turns:
    // Turn 1: [PHASE: PLAN] + writes python file
    // Turn 2: [PHASE: RUN] + runs sandbox python
    // Turn 3: [PHASE: VERIFY] + claims completion
    let callCount = 0;
    const mockNebiusClient = {
      baseUrl: 'https://api.tokenfactory.nebius.com/v1',
      defaultModel: 'nvidia/llama-3.1-nemotron-70b-instruct',
      createChatCompletion: async () => {
        callCount++;
        if (callCount === 1) {
          return {
            choices: [
              {
                message: {
                  role: 'assistant',
                  content: '[PHASE: PLAN]\nI will write a python script to compute fibonacci numbers.',
                  tool_calls: [
                    {
                      id: 'call_1',
                      type: 'function',
                      function: {
                        name: 'write_file',
                        arguments: JSON.stringify({
                          path: 'fib.py',
                          content: 'def fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)\nprint("FIB_RESULT:", fib(7))\n',
                        }),
                      },
                    },
                  ],
                },
              },
            ],
          };
        }

        if (callCount === 2) {
          return {
            choices: [
              {
                message: {
                  role: 'assistant',
                  content: '[PHASE: RUN]\nNow running fib.py in sandbox.',
                  tool_calls: [
                    {
                      id: 'call_2',
                      type: 'function',
                      function: {
                        name: 'run_sandbox_python',
                        arguments: JSON.stringify({
                          script_path: 'fib.py',
                        }),
                      },
                    },
                  ],
                },
              },
            ],
          };
        }

        return {
          choices: [
            {
              message: {
                role: 'assistant',
                content: '[PHASE: VERIFY]\nFibonacci computation verified successfully. FIB_RESULT: 13.',
              },
            },
          ],
        };
      },
    } as unknown as NebiusClient;

    const runner = new PythonRunner({ workDir: TEST_WORKSPACE });
    const registry = new ToolRegistry(runner);
    const engine = new ExecutionEngine(mockNebiusClient, registry);

    const phasesSeen: string[] = [];
    const result = await engine.runAgentLoop({
      task: 'Compute fibonacci of 7 in Python',
      workspacePath: TEST_WORKSPACE,
      onEvent: (type, payload) => {
        if (type === 'phase_change') {
          phasesSeen.push(payload.to);
        }
      },
    });

    expect(result.success).toBe(true);
    expect(result.finalPhase).toBe(AgentPhase.COMPLETED);
    expect(result.iterations).toBe(3);
    expect(phasesSeen).toContain(AgentPhase.TASK);
    expect(phasesSeen).toContain(AgentPhase.PLAN);
    expect(phasesSeen).toContain(AgentPhase.CODE);
    expect(phasesSeen).toContain(AgentPhase.RUN);
    expect(phasesSeen).toContain(AgentPhase.VERIFY);
    expect(phasesSeen).toContain(AgentPhase.COMPLETED);

    // Verify fib.py was written and executed
    const fileExists = await fs.stat(path.join(TEST_WORKSPACE, 'fib.py'));
    expect(fileExists.isFile()).toBe(true);
  });
});
