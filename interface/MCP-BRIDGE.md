# Clawdbot MCP Bridge

**Purpose:** Allow Claude Code to communicate with KageBot (Clawdbot) via MCP tools.

**Implementation:** `/Users/kagebot/clawd/projects/clawdbot-mcp-bridge/`

## Architecture

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   Claude Code   │  MCP    │   MCP Bridge    │  HTTP   │    Clawdbot     │
│   (Laptop)      │◄───────►│   (Laptop)      │◄───────►│    Gateway      │
│                 │         │   Port 3100     │         │  192.168.6.100  │
└─────────────────┘         └─────────────────┘         └─────────────────┘
                                    │
                                    ▼
                            ┌─────────────────┐
                            │  Session Store  │
                            │  (responses)    │
                            └─────────────────┘
```

## MCP Tools Exposed

### `kage_send`
Send a message to KageBot and wait for response.

```json
{
  "name": "kage_send",
  "description": "Send a message to KageBot (Clawdbot) and receive a response",
  "inputSchema": {
    "type": "object",
    "properties": {
      "message": {
        "type": "string",
        "description": "Message to send to KageBot"
      },
      "timeout_seconds": {
        "type": "number",
        "description": "Max seconds to wait for response (default: 120)"
      }
    },
    "required": ["message"]
  }
}
```

**Returns:**
```json
{
  "response": "KageBot's reply text",
  "session_key": "agent:main:claude-code",
  "duration_ms": 3420
}
```

### `kage_status`
Check if KageBot is reachable.

```json
{
  "name": "kage_status",
  "description": "Check Clawdbot Gateway status",
  "inputSchema": {
    "type": "object",
    "properties": {}
  }
}
```

**Returns:**
```json
{
  "online": true,
  "gateway_version": "1.2.3",
  "session_key": "agent:main:claude-code"
}
```

## Implementation

### Bridge Server (Node.js)

```javascript
// mcp-bridge.js
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const GATEWAY_URL = process.env.CLAWDBOT_URL || "http://192.168.6.100:18789";
const SESSION_KEY = "agent:main:claude-code";

const server = new Server({
  name: "clawdbot-bridge",
  version: "1.0.0"
}, {
  capabilities: { tools: {} }
});

server.setRequestHandler("tools/list", async () => ({
  tools: [
    {
      name: "kage_send",
      description: "Send a message to KageBot and receive a response",
      inputSchema: {
        type: "object",
        properties: {
          message: { type: "string", description: "Message to send" },
          timeout_seconds: { type: "number", description: "Timeout (default 120)" }
        },
        required: ["message"]
      }
    },
    {
      name: "kage_status", 
      description: "Check if KageBot is reachable",
      inputSchema: { type: "object", properties: {} }
    }
  ]
}));

server.setRequestHandler("tools/call", async (request) => {
  const { name, arguments: args } = request.params;
  
  if (name === "kage_status") {
    try {
      const res = await fetch(`${GATEWAY_URL}/health`);
      return { content: [{ type: "text", text: JSON.stringify({ online: res.ok }) }] };
    } catch (e) {
      return { content: [{ type: "text", text: JSON.stringify({ online: false, error: e.message }) }] };
    }
  }
  
  if (name === "kage_send") {
    const timeout = (args.timeout_seconds || 120) * 1000;
    const start = Date.now();
    
    // Send message via sessions API
    const res = await fetch(`${GATEWAY_URL}/api/sessions/send`, {
      method: "POST",
      headers: { 
        "Content-Type": "application/json",
        "X-Clawdbot-Session-Key": SESSION_KEY
      },
      body: JSON.stringify({
        sessionKey: SESSION_KEY,
        message: args.message,
        timeoutSeconds: args.timeout_seconds || 120
      })
    });
    
    const data = await res.json();
    
    return {
      content: [{
        type: "text",
        text: JSON.stringify({
          response: data.reply || data.message,
          session_key: SESSION_KEY,
          duration_ms: Date.now() - start
        })
      }]
    };
  }
  
  throw new Error(`Unknown tool: ${name}`);
});

const transport = new StdioServerTransport();
await server.connect(transport);
```

### Package Setup

```json
{
  "name": "clawdbot-mcp-bridge",
  "version": "1.0.0",
  "type": "module",
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0"
  }
}
```

### Claude Code Configuration

Add to `~/.claude/settings.json` on the laptop:

```json
{
  "mcpServers": {
    "kagebot": {
      "command": "node",
      "args": ["/path/to/mcp-bridge.js"],
      "env": {
        "CLAWDBOT_URL": "http://192.168.6.100:18789"
      }
    }
  }
}
```

## Session Routing

The bridge uses a dedicated session key: `agent:main:claude-code`

This means:
- Claude Code gets its own conversation context with me
- Messages don't pollute the main Telegram session
- Session history is preserved between calls

## Usage Example (from Claude Code)

Once configured, Claude Code can simply call the tool:

```
User: Ask Kage to review this transcript schema

Claude Code: I'll check with KageBot about this.
[calls kage_send with message: "Hey, Claude Code here. Can you review this transcript schema? ..."]

KageBot responds: "The schema looks reasonable, but I'd suggest..."

Claude Code: KageBot suggests we should...
```

## Security Notes

- Bridge runs locally on the laptop (localhost MCP)
- Gateway is on the local network (192.168.6.100)
- No auth required for local network access (adjust if needed)
- Session key prevents cross-session pollution

## Future Enhancements

- [ ] Streaming responses (if Gateway supports SSE)
- [ ] File sharing (send files between agents)
- [ ] Shared task list (like Agent Teams)
- [ ] Notifications (Kage can ping Claude Code proactively)

---

*"Finally, a civilized way to collaborate. The commit-based communication was getting tedious."*
