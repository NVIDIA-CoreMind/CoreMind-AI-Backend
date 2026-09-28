import type { Response } from 'express';

export type SSEEventType =
  | 'phase_change'
  | 'thought'
  | 'tool_call'
  | 'tool_result'
  | 'sandbox_output'
  | 'diff_applied'
  | 'verification'
  | 'error'
  | 'heartbeat'
  | 'done';

export interface SSEMessage<T = any> {
  type: SSEEventType;
  payload: T;
  timestamp?: number;
}

export class SSEStream {
  private res: Response;
  private heartbeatInterval?: NodeJS.Timeout;
  private closed = false;

  constructor(res: Response) {
    this.res = res;
    this.initializeHeaders();
    this.startHeartbeat();

    res.on('close', () => {
      this.close();
    });
  }

  private initializeHeaders(): void {
    this.res.setHeader('Content-Type', 'text/event-stream');
    this.res.setHeader('Cache-Control', 'no-cache, no-transform');
    this.res.setHeader('Connection', 'keep-alive');
    this.res.setHeader('X-Accel-Buffering', 'no'); // Disable buffering on Nginx proxies
    this.res.flushHeaders?.();
  }

  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      if (!this.closed) {
        this.send('heartbeat', { ping: Date.now() });
      }
    }, 15000);
  }

  /**
   * Send a typed SSE event to the connected client
   */
  public send<T>(type: SSEEventType, payload: T): void {
    if (this.closed) return;

    try {
      const message: SSEMessage<T> = {
        type,
        payload,
        timestamp: Date.now(),
      };

      const data = `event: ${type}\ndata: ${JSON.stringify(message)}\n\n`;
      this.res.write(data);
    } catch (err: any) {
      console.error('[SSEStream] Error writing data to stream:', err);
      this.close();
    }
  }

  /**
   * Gracefully close the SSE stream
   */
  public close(finalPayload?: any): void {
    if (this.closed) return;
    this.closed = true;

    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = undefined;
    }

    if (finalPayload !== undefined) {
      this.send('done', finalPayload);
    }

    try {
      this.res.end();
    } catch {
      // Ignore errors when ending stream
    }
  }

  public isClosed(): boolean {
    return this.closed;
  }
}
