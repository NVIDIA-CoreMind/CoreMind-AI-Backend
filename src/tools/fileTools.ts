import fs from 'fs/promises';
import path from 'path';
import { applyPatch } from 'diff';
import type { ToolResult } from './types.js';

/**
 * Resolves and verifies that a relative or absolute path is strictly within the workspace
 */
export function resolveSafePath(workspaceRoot: string, targetPath: string): string {
  const normalizedRoot = path.resolve(workspaceRoot);
  const resolvedTarget = path.isAbsolute(targetPath)
    ? path.resolve(targetPath)
    : path.resolve(normalizedRoot, targetPath);

  // Path traversal check
  if (!resolvedTarget.startsWith(normalizedRoot)) {
    throw new Error(
      `Access denied: Path "${targetPath}" resolves outside of workspace root "${normalizedRoot}"`
    );
  }

  return resolvedTarget;
}

/**
 * Tool: read_file
 */
export async function executeReadFile(
  workspaceRoot: string,
  filePath: string,
  startLine?: number,
  endLine?: number
): Promise<ToolResult<{ content: string; totalLines: number; range?: [number, number] }>> {
  try {
    const safePath = resolveSafePath(workspaceRoot, filePath);
    const rawContent = await fs.readFile(safePath, 'utf-8');
    const lines = rawContent.split(/\r?\n/);
    const totalLines = lines.length;

    if (startLine !== undefined || endLine !== undefined) {
      const start = Math.max(1, startLine ?? 1);
      const end = Math.min(totalLines, endLine ?? totalLines);
      const sliced = lines.slice(start - 1, end);
      const numberedContent = sliced
        .map((line, idx) => `${start + idx}: ${line}`)
        .join('\n');

      return {
        success: true,
        data: {
          content: numberedContent,
          totalLines,
          range: [start, end],
        },
      };
    }

    return {
      success: true,
      data: {
        content: rawContent,
        totalLines,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      error: `Failed to read file "${filePath}": ${error.message}`,
    };
  }
}

/**
 * Tool: write_file
 */
export async function executeWriteFile(
  workspaceRoot: string,
  filePath: string,
  content: string
): Promise<ToolResult<{ path: string; bytesWritten: number }>> {
  try {
    const safePath = resolveSafePath(workspaceRoot, filePath);
    const dir = path.dirname(safePath);
    await fs.mkdir(dir, { recursive: true });

    await fs.writeFile(safePath, content, 'utf-8');
    const bytesWritten = Buffer.byteLength(content, 'utf-8');

    return {
      success: true,
      data: {
        path: filePath,
        bytesWritten,
      },
      message: `Successfully wrote ${bytesWritten} bytes to ${filePath}`,
    };
  } catch (error: any) {
    return {
      success: false,
      error: `Failed to write file "${filePath}": ${error.message}`,
    };
  }
}

/**
 * Tool: apply_diff
 * Supports standard unified diff patch as well as search/replace block patch:
 * <<<<<<< SEARCH
 * [original lines]
 * =======
 * [new lines]
 * >>>>>>>
 */
export async function executeApplyDiff(
  workspaceRoot: string,
  filePath: string,
  patch: string
): Promise<ToolResult<{ path: string; applied: boolean }>> {
  try {
    const safePath = resolveSafePath(workspaceRoot, filePath);
    let originalContent = '';

    try {
      originalContent = await fs.readFile(safePath, 'utf-8');
    } catch (err: any) {
      return {
        success: false,
        error: `Cannot apply diff: Target file "${filePath}" does not exist.`,
      };
    }

    let patchedContent: string | false = false;

    // Check if patch is formatted as Search/Replace blocks
    if (patch.includes('<<<<<<< SEARCH') && patch.includes('=======')) {
      patchedContent = applySearchReplacePatch(originalContent, patch);
    } else {
      // Standard unified diff format
      patchedContent = applyPatch(originalContent, patch);
      if (patchedContent === false) {
        // Fallback: try search/replace parser if unified diff failed
        patchedContent = applySearchReplacePatch(originalContent, patch);
      }
    }

    if (patchedContent === false) {
      return {
        success: false,
        error: `Failed to cleanly apply patch to "${filePath}". Ensure search blocks or line numbers match the file content.`,
      };
    }

    await fs.writeFile(safePath, patchedContent, 'utf-8');

    return {
      success: true,
      data: {
        path: filePath,
        applied: true,
      },
      message: `Successfully applied diff to ${filePath}`,
    };
  } catch (error: any) {
    return {
      success: false,
      error: `Error applying diff to "${filePath}": ${error.message}`,
    };
  }
}

/**
 * Helper to apply Search/Replace block patches
 */
function applySearchReplacePatch(source: string, patch: string): string | false {
  const blockRegex = /<<<<<<< SEARCH\r?\n([\s\S]*?)\r?\n=======\r?\n([\s\S]*?)\r?\n>>>>>>>/g;
  let result = source;
  let matchesFound = 0;
  let match: RegExpExecArray | null;

  while ((match = blockRegex.exec(patch)) !== null) {
    matchesFound++;
    const searchTarget = match[1];
    const replacement = match[2];

    if (!result.includes(searchTarget)) {
      // Normalize line endings and retry
      const normalizedResult = result.replace(/\r\n/g, '\n');
      const normalizedTarget = searchTarget.replace(/\r\n/g, '\n');
      if (normalizedResult.includes(normalizedTarget)) {
        result = normalizedResult.replace(normalizedTarget, replacement.replace(/\r\n/g, '\n'));
        continue;
      }
      return false; // Target block not found in source
    }

    result = result.replace(searchTarget, replacement);
  }

  return matchesFound > 0 ? result : false;
}
