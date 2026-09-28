import type {
  ChatCompletionMessageParam,
  ChatCompletionToolMessageParam,
  ChatCompletionAssistantMessageParam,
} from 'openai/resources/chat/completions.mjs';
import { NebiusClient, defaultNebiusClient } from '../providers/nebiusClient.js';
import { ToolRegistry, defaultToolRegistry } from '../tools/registry.js';
import { AgentStateMachine, AgentPhase } from './stateMachine.js';
import { buildSystemPrompt } from './systemPrompt.js';
import { config } from '../config/env.js';
import type { SSEStream } from '../server/sseHandler.js';

export interface AgentLoopOptions {
  task: string;
  workspacePath: string;
  model?: string;
  maxIterations?: number;
  maxDebugRetries?: number;
  extraContext?: string;
  stream?: SSEStream;
  onEvent?: (type: string, data: any) => void;
}

export interface AgentLoopResult {
  success: boolean;
  finalPhase: AgentPhase;
  iterations: number;
  messages: ChatCompletionMessageParam[];
  summary: string;
  stateSummary: ReturnType<AgentStateMachine['getSummary']>;
  error?: string;
}

export class ExecutionEngine {
  private nebiusClient: NebiusClient;
  private toolRegistry: ToolRegistry;

  constructor(
    nebiusClient: NebiusClient = defaultNebiusClient,
    toolRegistry: ToolRegistry = defaultToolRegistry
  ) {
    this.nebiusClient = nebiusClient;
    this.toolRegistry = toolRegistry;
  }

  /**
   * Run the autonomous 7-step engineering agent loop
   */
  public async runAgentLoop(options: AgentLoopOptions): Promise<AgentLoopResult> {
    const {
      task,
      workspacePath,
      model = config.nebius.defaultModel,
      maxIterations = config.agent.maxIterations,
      maxDebugRetries = config.agent.maxDebugRetries,
      extraContext,
      stream,
      onEvent,
    } = options;

    const emit = (type: string, payload: any) => {
      if (onEvent) onEvent(type, payload);
      if (stream && !stream.isClosed()) {
        stream.send(type as any, payload);
      }
    };

    // Initialize State Machine
    const stateMachine = new AgentStateMachine({
      maxDebugRetries,
      onPhaseChange: (from, to, reason) => {
        emit('phase_change', { from, to, reason });
      },
    });

    // Start in TASK phase and emit initial event
    emit('phase_change', {
      from: 'INITIALIZING',
      to: AgentPhase.TASK,
      reason: 'Starting task evaluation',
    });

    // Build initial prompt and messages
    const systemPrompt = buildSystemPrompt(workspacePath, extraContext);
    const messages: ChatCompletionMessageParam[] = [
      { role: 'system', content: systemPrompt },
      {
        role: 'user',
        content: `Target Task:\n${task}\n\nPlease proceed following the 7-step loop: TASK -> PLAN -> CODE -> RUN -> TEST -> DEBUG / FIX -> VERIFY.`,
      },
    ];

    let iteration = 0;
    let finalSummary = '';

    try {
      while (iteration < maxIterations) {
        iteration++;

        if (stateMachine.isTerminal()) {
          break;
        }

        // Request LLM completion with tools
        const response = await this.nebiusClient.createChatCompletion({
          messages,
          tools: this.toolRegistry.getTools(),
          model,
        });

        const choice = response.choices[0];
        if (!choice || !choice.message) {
          throw new Error('Received empty response from Nebius API');
        }

        const assistantMsg = choice.message;
        const content = assistantMsg.content || '';

        // Detect explicit phase markers in text (e.g., [PHASE: PLAN])
        if (content) {
          stateMachine.detectAndTransitionFromText(content);
          emit('thought', {
            content,
            phase: stateMachine.getCurrentPhase(),
            iteration,
          });
        }

        // Push assistant message into history
        const assistantRecord: ChatCompletionAssistantMessageParam = {
          role: 'assistant',
          content: assistantMsg.content || null,
        };

        if (assistantMsg.tool_calls && assistantMsg.tool_calls.length > 0) {
          assistantRecord.tool_calls = assistantMsg.tool_calls;
        }

        messages.push(assistantRecord);

        // If no tool calls and agent claims completion or phase is VERIFY
        if (!assistantMsg.tool_calls || assistantMsg.tool_calls.length === 0) {
          finalSummary = content;

          if (
            stateMachine.getCurrentPhase() === AgentPhase.VERIFY ||
            content.toLowerCase().includes('task completed') ||
            content.toLowerCase().includes('verified successfully')
          ) {
            stateMachine.complete('Agent concluded task with verification');
          }
          break;
        }

        // Execute all tool calls
        for (const toolCall of assistantMsg.tool_calls) {
          const toolName = toolCall.function.name;
          const toolArgs = toolCall.function.arguments;

          emit('tool_call', {
            id: toolCall.id,
            name: toolName,
            args: toolArgs,
            phase: stateMachine.getCurrentPhase(),
          });

          // Dispatch tool
          const result = await this.toolRegistry.executeTool(
            toolName,
            toolArgs,
            workspacePath
          );

          emit('tool_result', {
            id: toolCall.id,
            name: toolName,
            success: result.success,
            data: result.data,
            error: result.error,
          });

          // Phase transition logic based on tool execution
          if (toolName === 'write_file' || toolName === 'apply_diff') {
            if (stateMachine.getCurrentPhase() === AgentPhase.PLAN) {
              stateMachine.transitionTo(AgentPhase.CODE, `Modifying workspace: ${toolName}`);
            }
            if (toolName === 'apply_diff') {
              emit('diff_applied', {
                path: (result.data as any)?.path,
                success: result.success,
              });
            }
          }

          if (toolName === 'run_sandbox_python') {
            const sbResult = result.data;
            if (sbResult) {
              emit('sandbox_output', sbResult);
              if (!sbResult.success || sbResult.traceback) {
                stateMachine.transitionTo(AgentPhase.DEBUG, 'Python execution error detected');
              } else if (stateMachine.getCurrentPhase() === AgentPhase.CODE) {
                stateMachine.transitionTo(AgentPhase.RUN, 'Script executed cleanly in sandbox');
              }
            }
          }

          if (toolName === 'run_sandbox_tests') {
            const testResult = result.data;
            if (testResult) {
              emit('sandbox_output', testResult);
              if (!testResult.success || testResult.traceback || testResult.exitCode !== 0) {
                stateMachine.transitionTo(AgentPhase.DEBUG, 'Test suite failures or tracebacks detected');
              } else {
                stateMachine.transitionTo(AgentPhase.VERIFY, 'All tests passed cleanly with code 0');
              }
            }
          }

          // Format tool response for message history
          const toolResponseMsg: ChatCompletionToolMessageParam = {
            role: 'tool',
            tool_call_id: toolCall.id,
            content: JSON.stringify(result),
          };

          messages.push(toolResponseMsg);
        }
      }

      if (iteration >= maxIterations && !stateMachine.isTerminal()) {
        stateMachine.fail(`Reached maximum execution limit of ${maxIterations} turns`);
      }

      const finalPhase = stateMachine.getCurrentPhase();
      const isSuccess = finalPhase === AgentPhase.COMPLETED || finalPhase === AgentPhase.VERIFY;

      const agentResult: AgentLoopResult = {
        success: isSuccess,
        finalPhase,
        iterations: iteration,
        messages,
        summary: finalSummary || `Agent finished in phase: ${finalPhase}`,
        stateSummary: stateMachine.getSummary(),
      };

      emit('verification', {
        success: isSuccess,
        finalPhase,
        summary: agentResult.summary,
      });

      return agentResult;
    } catch (error: any) {
      stateMachine.fail(error.message || 'Fatal error during agent loop execution');
      emit('error', { message: error.message, stack: error.stack });

      return {
        success: false,
        finalPhase: stateMachine.getCurrentPhase(),
        iterations: iteration,
        messages,
        summary: 'Agent loop aborted due to an unhandled exception',
        stateSummary: stateMachine.getSummary(),
        error: error.message,
      };
    }
  }
}

export const defaultExecutionEngine = new ExecutionEngine();
