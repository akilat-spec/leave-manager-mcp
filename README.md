# leave-manager-mcp

[![smithery badge](https://smithery.ai/badge/@akilat-spec/leave-manager-mcp)](https://smithery.ai/server/@akilat-spec/leave-manager-mcp)

An MCP server for viewing work day patterns and calculating working days in a given period.

### Protocol

This server implements the MCP protocol, a simple protocol intended for Large Language Models(LLMs) like Claude to retrieve up-to-date information from local files, APIs, services, databases, and other resources and tools.

### Getting Started

First, clone this repository using:
```
git clone https://github.com/akilat-spec/leave-manager-mcp
```

### Installing via Smithery

To install leave-manager-mcp automatically via [Smithery](https://smithery.ai/server/@akilat-spec/leave-manager-mcp):

```bash
npx -y @smithery/cli install @akilat-spec/leave-manager-mcp
```

### Running

Navigate to the repo folder and run:
```
node index.js
```
Though not necessary, you can create an access token for MCP requests using:
```
node create-access-token
```
And add it to your Claude Desktop MCP server credentials settings.

### Available Tools

- `getWeekPattern`: Get week day pattern(s) using:
	- `weekPattern`: A string of any combination of weekdays e.g: "MO,FR" that is repeated. Defaults to "MO,FR".
- `weekDaysReduce`: Reduce to week day from provided date range using:
	- `start`: Date string representing start of period.
	- `end`: Date string representing end of period.
	- `weekPattern`: A string of any combination of weekdays e.g: "MO,TH", defaults to "MO,FR".

### Data Persistence

This server can persist data by using a JSON file (data.json) under the project root. Ensure this file is present when the server is started.
