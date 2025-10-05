#!/usr/bin/env -S uvx --quiet --from mcp --from jupyter-client --from ipykernel python
# /// script
# dependencies = [
#   "mcp",
#   "jupyter-client",
#   "ipykernel",
#   "numpy",
#   "pandas",
#   "matplotlib",
# ]
# ///
"""
Python Kernel MCP Server

A Model Context Protocol server that provides Python code execution
via an isolated IPython kernel process.
"""

import asyncio
import time
import base64
import uuid
import html
from typing import Optional

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import TextContent, EmbeddedResource
from jupyter_client import AsyncKernelManager
import pathlib

STATIC_DIR = pathlib.Path(__file__).parent / "highlight_js"
HIGHLIGHT_JS = (STATIC_DIR / "highlight.min.js").read_text()
HIGHLIGHT_CSS = (STATIC_DIR / "github-dark.min.css").read_text()
HIGHLIGHT_PYTHON = (STATIC_DIR / "python.min.js").read_text()

IMPORTS = (
    "import numpy as np\n" "import pandas as pd\n" "import matplotlib.pyplot as plt\n"
)

mcp = FastMCP(
    "PyKernel",
    instructions=(
        "PyKernel allows an agent to run python code in a jupyter kernel without writing "
        "out a python file.\n Use this for quick analysis when the user has not explicitly "
        "asked to create a python file. Written by Simon de Wit. The kernel persists between "
        "calls, but could restart without warning. If that happens, reinitialize it as needed.\n\n"
        "The kernel comes preconfigured with:\n"
        f"{IMPORTS}\n"
        "DO NOT REPRINT THE CODE YOU SEND AFTER EXECUTION!"
    ),
)


class KernelState:
    def __init__(self):
        self.km: Optional[AsyncKernelManager] = None
        self.kc = None
        self.kernel_id = str(uuid.uuid4())
        self.start_time = time.time()
        self.session_api_url: Optional[str] = None
        self.session_id: Optional[str] = None

    def get_uptime(self) -> float:
        return time.time() - self.start_time

    async def ensure_started(self):
        if self.km is None:
            self.km = AsyncKernelManager()
            await self.km.start_kernel()
            self.kc = self.km.client()
            self.kc.start_channels()
            await self.kc.wait_for_ready()
            self.kc.execute(IMPORTS)
            self.kc.execute("%matplotlib inline")
            self.kernel_id = str(uuid.uuid4())
            self.start_time = time.time()


state = KernelState()


async def html_result(code, error_text, output_text, images):
    images_html = ""
    if images:
        images_html = '<div style="margin-bottom: 16px;">'
        images_html += '<div style="margin-bottom: 8px; font-weight: 600; color: #4ec9b0; font-size: 13px;">Images:</div>'
        for img_data in images:
            images_html += f'<img src="data:image/png;base64,{img_data}" style="max-width: 100%; border-radius: 4px; margin-bottom: 8px;">'
        images_html += "</div>"

    ui_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>{HIGHLIGHT_CSS}</style>
        <script>{HIGHLIGHT_JS}</script>
        <script>{HIGHLIGHT_PYTHON}</script>
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            .hljs {{
                background: #252526 !important;
                padding: 12px !important;
                border-radius: 4px !important;
                overflow-x: auto !important;
            }}
        </style>
    </head>
    <body>
    <div id="content" style="background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 8px;">
        <div style="margin-bottom: 16px;">
            <div style="margin-bottom: 8px; font-weight: 600; color: #4ec9b0; font-size: 13px;">Code:</div>
            <div style="border-left: 3px solid #569cd6;">
                <pre><code class="language-python">{html.escape(code)}</code></pre>
            </div>
        </div>
        
        {images_html}

        {f'''<div style="margin-bottom: 16px;">
            <div style="margin-bottom: 8px; font-weight: 600; color: #4ec9b0; font-size: 13px;">Output:</div>
            <div style="border-left: 3px solid #4ec9b0;">
                <pre style="background: #252526; padding: 12px; border-radius: 4px; overflow-x: auto; margin: 0;"><code style="font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 13px; line-height: 1.5;">{html.escape(output_text)}</code></pre>
            </div>
        </div>''' if output_text else ''}

        {f'''<div style="margin-bottom: 16px;">
            <div style="margin-bottom: 8px; font-weight: 600; color: #f48771; font-size: 13px;">Errors:</div>
            <div style="border-left: 3px solid #f48771;">
                <pre style="background: #3b1f1f; padding: 12px; border-radius: 4px; overflow-x: auto; margin: 0;"><code class="language-python" style="font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 13px; line-height: 1.5; color: #f48771;">{html.escape(error_text)}</code></pre>
            </div>
        </div>''' if error_text else ''}

        {'''<div style="color: #4ec9b0; font-size: 13px;">✓ Code executed successfully</div>''' if not output_text and not error_text else ''}
    </div>
    <script>
        // Apply syntax highlighting
        hljs.highlightAll();

        function notifySize() {{
            const content = document.getElementById('content');
            const height = content.scrollHeight + 40;
            window.parent.postMessage({{
                type: 'ui-size-change',
                payload: {{ height: height, width: window.innerWidth }}
            }}, '*');
        }}

        window.addEventListener('load', () => {{
            notifySize();
            // Re-notify after highlighting completes
            setTimeout(notifySize, 100);
        }});

        window.addEventListener('resize', notifySize);
        notifySize();
    </script>
    </body>
    </html>
    """
    return ui_html


@mcp.tool()
async def execute_python(code: str) -> list[TextContent | EmbeddedResource]:
    """Execute a bit of Python code in the kernel.

    The user will see both the code that is executed and the results, so no
    need to repeat either of those things unless it fits further explanations.
    """
    await state.ensure_started()

    msg_id = state.kc.execute(code)

    outputs = []
    errors = []
    images = []

    while True:
        try:
            msg = await asyncio.wait_for(state.kc.get_iopub_msg(), timeout=30.0)

            if msg["parent_header"].get("msg_id") != msg_id:
                continue

            content = msg["content"]
            msg_type = msg["header"]["msg_type"]

            if msg_type == "stream":
                outputs.append(content["text"])
            elif msg_type == "display_data":
                if "image/png" in content["data"]:
                    images.append(content["data"]["image/png"])
            elif msg_type == "execute_result":
                outputs.append(content["data"].get("text/plain", ""))
            elif msg_type == "error":
                errors.extend(content["traceback"])
            elif msg_type == "status" and content["execution_state"] == "idle":
                break

        except asyncio.TimeoutError:
            errors.append("Execution timed out after 30 seconds")
            break

    result_parts = []

    uptime = state.get_uptime()
    result_parts.append(
        TextContent(
            type="text",
            text=f"**Kernel Info:** ID: `{state.kernel_id[:8]}...` | Uptime: `{uptime:.1f}s`",
        )
    )

    result_parts.append(
        TextContent(type="text", text=f"**Executed:**\n```python\n{code}\n```")
    )

    for img_data in images:
        result_parts.append(
            EmbeddedResource(
                type="resource",
                resource={
                    "uri": f"image://pykernel/{uuid.uuid4()}.png",
                    "mimeType": "image/png",
                    "blob": img_data,
                },
            )
        )

    if outputs:
        output_text = "\n".join(outputs)
        result_parts.append(
            TextContent(type="text", text=f"**Output:**\n```\n{output_text}\n```")
        )

    if errors:
        error_text = "\n".join(errors)
        result_parts.append(
            TextContent(type="text", text=f"**Errors:**\n```python\n{error_text}\n```")
        )

    if not outputs and not errors and not images:
        result_parts.append(
            TextContent(type="text", text="✓ Code executed successfully")
        )

    output_text = "\n".join(outputs) if outputs else ""
    error_text = "\n".join(errors) if errors else ""

    ui_html = await html_result(code, error_text, output_text, images)

    result_parts.append(
        EmbeddedResource(
            type="resource",
            resource={
                "uri": f"ui://pykernel_mcp/result-{uuid.uuid4()}",
                "mimeType": "text/html",
                "text": ui_html,
            },
        )
    )

    return result_parts


@mcp.tool()
async def install_package(package: str) -> list[TextContent | EmbeddedResource]:
    """Install a Python package in the kernel using pip."""
    return await execute_python(f"%pip install {package}")


@mcp.tool()
async def restart_kernel() -> str:
    """Restart the Python kernel, clearing all state."""
    if state.km is not None:
        await state.km.shutdown_kernel()
        state.km = None
        state.kc = None

    await state.ensure_started()
    return f"Kernel restarted. New ID: {state.kernel_id}"


if __name__ == "__main__":
    mcp.run()
