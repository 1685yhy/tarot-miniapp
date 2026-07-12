// Start weapp-dev-mcp and expose it as an HTTP server
const { spawn } = require('child_process');
const path = require('path');

const mcp = spawn('npx', ['-y', '@yfme/weapp-dev-mcp'], {
  cwd: 'E:/tarot-miniapp',
  stdio: ['pipe', 'pipe', 'pipe'],
  env: { ...process.env, WEAPP_WS_ENDPOINT: 'ws://127.0.0.1:19109' }
});

mcp.stdout.on('data', (d) => process.stdout.write('OUT:' + d));
mcp.stderr.on('data', (d) => process.stderr.write('ERR:' + d));
mcp.on('close', (c) => console.log('MCP exited with code ' + c));

setTimeout(() => process.exit(0), 8000);
