#!/usr/bin/env -S uvx --quiet --from mcp --from jupyter-client --from ipykernel python
# /// script
# dependencies = [
#   "mcp",
#   "jupyter-client",
#   "ipykernel",
# ]
# ///
"""
Python Kernel MCP Server

A Model Context Protocol server that provides Python code execution
via an isolated IPython kernel process.
"""

import asyncio
import time
import uuid
import html
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ImageContent, EmbeddedResource
from jupyter_client import AsyncKernelManager

mcp = FastMCP("python-kernel")

class KernelState:
    """Manages the IPython kernel lifecycle"""
    def __init__(self):
        self.km: Optional[AsyncKernelManager] = None
        self.kc = None
        self.kernel_id = str(uuid.uuid4())
        self.start_time = time.time()
        self.session_api_url: Optional[str] = None
        self.session_id: Optional[str] = None
    
    def get_uptime(self) -> float:
        """Get kernel uptime in seconds"""
        return time.time() - self.start_time
    
    async def ensure_started(self):
        """Start kernel if not already running"""
        if self.km is None:
            self.km = AsyncKernelManager()
            await self.km.start_kernel()
            self.kc = self.km.client()
            self.kc.start_channels()
            await self.kc.wait_for_ready()
            self.kernel_id = str(uuid.uuid4())
            self.start_time = time.time()

state = KernelState()

@mcp.tool()
async def execute_python(code: str) -> list[TextContent | EmbeddedResource]:
    """
    Execute Python code in an isolated IPython kernel.
    
    The kernel maintains state between executions, so variables
    and imports persist across calls.
    
    Args:
        code: Python code to execute
        
    Returns:
        Execution output including stdout, results, and errors
    """
    await state.ensure_started()
    
    msg_id = state.kc.execute(code)
    
    outputs = []
    errors = []
    
    while True:
        try:
            msg = await asyncio.wait_for(
                state.kc.get_iopub_msg(),
                timeout=30.0
            )
            
            if msg['parent_header'].get('msg_id') != msg_id:
                continue
            
            content = msg['content']
            msg_type = msg['header']['msg_type']
            
            if msg_type == 'stream':
                outputs.append(content['text'])
            elif msg_type == 'execute_result':
                outputs.append(content['data'].get('text/plain', ''))
            elif msg_type == 'error':
                errors.extend(content['traceback'])
            elif msg_type == 'status' and content['execution_state'] == 'idle':
                break
                
        except asyncio.TimeoutError:
            errors.append("Execution timed out after 30 seconds")
            break
    
    # Build response parts for backwards compatibility
    result_parts = []
    
    # Add kernel metadata as text
    uptime = state.get_uptime()
    result_parts.append(TextContent(
        type="text",
        text=f"**Kernel Info:** ID: `{state.kernel_id[:8]}...` | Uptime: `{uptime:.1f}s`"
    ))
    
    # Show the executed code as text
    result_parts.append(TextContent(
        type="text",
        text=f"**Executed:**\n```python\n{code}\n```"
    ))
    
    # Add output if any
    if outputs:
        output_text = '\n'.join(outputs)
        result_parts.append(TextContent(
            type="text",
            text=f"**Output:**\n```\n{output_text}\n```"
        ))
    
    # Add errors if any
    if errors:
        error_text = '\n'.join(errors)
        result_parts.append(TextContent(
            type="text",
            text=f"**Errors:**\n```python\n{error_text}\n```"
        ))
    
    # If no output or errors
    if not outputs and not errors:
        result_parts.append(TextContent(
            type="text",
            text="✓ Code executed successfully (no output)"
        ))
    
    # Also add MCP-UI resource for rich rendering
    output_text = '\n'.join(outputs) if outputs else ''
    error_text = '\n'.join(errors) if errors else ''
    
    ui_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 8px; max-width: 100%;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #333;">
            <div style="font-weight: 600; color: #569cd6; font-size: 14px;">Python Kernel</div>
            <div style="font-size: 12px; color: #858585;">
                ID: {html.escape(state.kernel_id[:8])}... | Uptime: {uptime:.1f}s
            </div>
        </div>
        
        <div style="margin-bottom: 16px;">
            <div style="margin-bottom: 8px; font-weight: 600; color: #4ec9b0; font-size: 13px;">Code:</div>
            <pre style="background: #252526; padding: 12px; border-radius: 4px; overflow-x: auto; margin: 0; border-left: 3px solid #569cd6;"><code style="font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 13px; line-height: 1.5;">{html.escape(code)}</code></pre>
        </div>
        
        {f'''<div style="margin-bottom: 16px;">
            <div style="margin-bottom: 8px; font-weight: 600; color: #4ec9b0; font-size: 13px;">Output:</div>
            <pre style="background: #252526; padding: 12px; border-radius: 4px; overflow-x: auto; margin: 0; border-left: 3px solid #4ec9b0;"><code style="font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 13px; line-height: 1.5;">{html.escape(output_text)}</code></pre>
        </div>''' if output_text else ''}
        
        {f'''<div style="margin-bottom: 16px;">
            <div style="margin-bottom: 8px; font-weight: 600; color: #f48771; font-size: 13px;">Errors:</div>
            <pre style="background: #3b1f1f; padding: 12px; border-radius: 4px; overflow-x: auto; margin: 0; border-left: 3px solid #f48771;"><code style="font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 13px; line-height: 1.5; color: #f48771;">{html.escape(error_text)}</code></pre>
        </div>''' if error_text else ''}
        
        {'''<div style="color: #4ec9b0; font-size: 13px;">✓ Code executed successfully</div>''' if not output_text and not error_text else ''}
    </div>
    """
    
    result_parts.append(EmbeddedResource(
        type="resource",
        resource={
            "uri": f"ui://python-kernel/result-{uuid.uuid4()}",
            "mimeType": "text/html",
            "text": ui_html
        }
    ))
    
    return result_parts

@mcp.tool()
async def kernel_status() -> str:
    """
    Get current kernel status and metadata.
    
    Returns information about the running kernel including uptime,
    kernel ID, and whether it's currently running.
    """
    if state.km is None:
        return "No kernel running"
    
    uptime = state.get_uptime()
    return f"""Kernel Status:
  ID: {state.kernel_id}
  Uptime: {uptime:.1f} seconds
  Running: Yes
"""

@mcp.tool()
async def restart_kernel() -> str:
    """
    Restart the Python kernel, clearing all state.
    
    All variables, imports, and functions will be lost.
    A new kernel ID will be assigned.
    """
    if state.km is not None:
        await state.km.shutdown_kernel()
        state.km = None
        state.kc = None
    
    await state.ensure_started()
    return f"Kernel restarted. New ID: {state.kernel_id}"

if __name__ == "__main__":
    mcp.run()
