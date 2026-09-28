import OpenAI from 'openai';
import { config } from '../config/env.js';
import type {
  ChatCompletionMessageParam,
  ChatCompletionTool,
  ChatCompletionChunk,
} from 'openai/resources/chat/completions.mjs';

/**
 * Verified NVIDIA open-source models available on Nebius Token Factory / AI Cloud
 */
export const SUPPORTED_NVIDIA_MODELS = [
  'nvidia/llama-3.1-nemotron-70b-instruct',
  'nvidia/Llama-3.1-Nemotron-70B-Instruct-HF',
  'meta-llama/Meta-Llama-3.1-70B-Instruct',
  'meta-llama/Meta-Llama-3.1-8B-Instruct',
  'Qwen/Qwen2.5-Coder-32B-Instruct',
  'mistralai/Mistral-Large-Instruct-2407',
] as const;

export type SupportedModel = (typeof SUPPORTED_NVIDIA_MODELS)[number] | string;

export interface NebiusClientOptions {
  apiKey?: string;
  baseUrl?: string;
  defaultModel?: string;
}

export class NebiusClient {
  private client: OpenAI;
  public readonly defaultModel: string;
  public readonly baseUrl: string;

  constructor(options?: NebiusClientOptions) {
    const apiKey = options?.apiKey || config.nebius.apiKey;
    this.baseUrl = options?.baseUrl || config.nebius.baseUrl;
    this.defaultModel = options?.defaultModel || config.nebius.defaultModel;

    this.client = new OpenAI({
      apiKey,
      baseURL: this.baseUrl,
    });
  }

  /**
   * Access to raw OpenAI client instance
   */
  public get raw(): OpenAI {
    return this.client;
  }

  /**
   * Execute chat completion with tool calling support
   */
  public async createChatCompletion(params: {
    messages: ChatCompletionMessageParam[];
    tools?: ChatCompletionTool[];
    model?: string;
    temperature?: number;
    maxTokens?: number;
  }) {
    const model = params.model || this.defaultModel;

    try {
      const response = await this.client.chat.completions.create({
        model,
        messages: params.messages,
        tools: params.tools && params.tools.length > 0 ? params.tools : undefined,
        tool_choice: params.tools && params.tools.length > 0 ? 'auto' : undefined,
        temperature: params.temperature ?? 0.2,
        max_tokens: params.maxTokens ?? 4096,
      });

      return response;
    } catch (error: any) {
      console.error(`[NebiusClient] Error during chat completion (${model}):`, error?.message || error);
      throw error;
    }
  }

  /**
   * Execute streaming chat completion yielding chunks in real time
   */
  public async *streamChatCompletion(params: {
    messages: ChatCompletionMessageParam[];
    tools?: ChatCompletionTool[];
    model?: string;
    temperature?: number;
    maxTokens?: number;
  }): AsyncGenerator<ChatCompletionChunk, void, unknown> {
    const model = params.model || this.defaultModel;

    const stream = await this.client.chat.completions.create({
      model,
      messages: params.messages,
      tools: params.tools && params.tools.length > 0 ? params.tools : undefined,
      tool_choice: params.tools && params.tools.length > 0 ? 'auto' : undefined,
      temperature: params.temperature ?? 0.2,
      max_tokens: params.maxTokens ?? 4096,
      stream: true,
    });

    for await (const chunk of stream) {
      yield chunk;
    }
  }

  /**
   * Verify connectivity to Nebius endpoint
   */
  public async checkHealth(): Promise<{ ok: boolean; message: string; availableModels?: string[] }> {
    try {
      const modelsList = await this.client.models.list();
      const modelIds = modelsList.data.map((m) => m.id);
      return {
        ok: true,
        message: 'Connected to Nebius Token Factory successfully',
        availableModels: modelIds,
      };
    } catch (error: any) {
      return {
        ok: false,
        message: `Failed to connect to Nebius API (${this.baseUrl}): ${error?.message || 'Unknown error'}`,
      };
    }
  }
}

// Global default singleton instance
export const defaultNebiusClient = new NebiusClient();
