# PyKernel MCP

MCP server to make it possible for an agent to execute python in a Jupyter kernel.

## Features

PyKernel provides a persistent IPython kernel environment for executing Python code through the Model Context Protocol.
After setting this server up, your agent will be able to:

- **Maintains state between executions** - variables, imports, and functions persist across tool calls
- **Pre-loaded scientific stack** - comes with numpy, pandas, and matplotlib already imported
- **Rich output support** - captures text output, errors, and matplotlib plots
- **Visualizations** - inline matplotlib plots rendered as images
- **Package installation** - install additional packages on-the-fly with the `install_package` tool
- **Kernel management** - restart the kernel to clear state when needed

### Use Cases

- Quick data analysis and exploration without writing files
- Iterative computation where you build on previous results
- Mathematical calculations and statistical analysis
- Data visualization with matplotlib
- Testing Python code snippets
- Prototyping algorithms with maintained state

The kernel automatically handles execution timeouts, captures both stdout and stderr, and provides detailed error tracebacks when code fails.


## Test
Just execute:
```shell
npx @modelcontextprotocol/inspector uv run src/pykernel_mcp/server.py
```


## Installation

### Click the button to install:

[![Install in Goose](https://block.github.io/goose/img/extension-install-dark.svg)](https://block.github.io/goose/extension?cmd=uvx&arg=pykernel-mcp&id=pykernel-mcp&name=PyKernel&description=MCP%20server%20providing%20persistent%20IPython%20kernel%20for%20executing%20Python%20code%20with%20numpy%2C%20pandas%2C%20and%20matplotlib)

### Or install manually:

Go to `Advanced settings` -> `Extensions` -> `Add custom extension`. Name to your liking, use type `STDIO`, and set the `command` to `uvx pykernel-mcp`. Click "Add Extension".
