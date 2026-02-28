# myob-mcp-server

MCP server for the MYOB AccountRight Live API.

## Prerequisites

- Python 3.12+
- A MYOB developer account with an API key (client ID and secret)

## Installation

```bash
git clone https://github.com/fixxdigital/myob-mcp-server.git
cd myob-mcp-server
pip install .
```

This installs the `myob-mcp-server` command.

## Configuration

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Edit `.env` with your MYOB API credentials. Then either use the config file (which supports `${ENV_VAR}` substitution):

```bash
cp config/config.example.json config/config.json
```

Or pass credentials directly via the MCP client config (see below).

The server searches for config in this order:
1. `$MYOB_MCP_CONFIG` (path to a specific config file)
2. `./config/config.json` (relative to working directory)
3. `~/.config/myob-mcp/config.json` or `%APPDATA%/myob-mcp/config.json` on Windows

## MCP Client Setup

Add to your Claude Desktop or Claude Code MCP config:

```json
{
  "mcpServers": {
    "myob": {
      "command": "myob-mcp-server",
      "env": {
        "MYOB_CLIENT_ID": "your-client-id",
        "MYOB_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

The `env` block can be omitted if you use a config file instead.

## First Run

Use the `oauth_authorize` tool to authenticate. This opens a browser window for MYOB login. Once authorized, tokens are saved automatically and refreshed as needed.

## Available Tools

- **OAuth** -- authorize, refresh, status
- **Company** -- list company files
- **Accounts** -- list and get accounts
- **Tax Codes** -- list tax codes
- **Contacts** -- list, get, create customers and suppliers
- **Employees** -- list employees
- **Invoices** -- list, get, create sales invoices
- **Payments** -- record customer payments
- **Bills** -- list, get, create purchase bills
- **Banking** -- list bank accounts and transactions, create spend money transactions
- **Attachments** -- upload, list, delete attachments on bills and spend money transactions
- **Jobs** -- list jobs
- **Sales Orders** -- list, get, create, edit sales orders and record deposits
