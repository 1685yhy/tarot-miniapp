/**
 * Direct test - spawn CLI and try to connect
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const net = require('net');

const CLI_PATH = 'E:\\微信web开发者工具\\cli.bat';
const PROJECT_PATH = 'E:\\tarot-miniapp\\miniapp';
const AUTO_PORT = 9420;

// Test if cli.bat exists
console.log('CLI path exists:', fs.existsSync(CLI_PATH));
console.log('Project path exists:', fs.existsSync(PROJECT_PATH));

// Try to spawn the auto command
console.log('\nSpawning auto command...');
const proc = spawn('cmd.exe', ['/c', CLI_PATH, 'auto', '--project', PROJECT_PATH, '--auto-port', String(AUTO_PORT)], {
  stdio: ['ignore', 'pipe', 'pipe'],
  cwd: 'E:\\',
  windowsVerbatimArguments: true,
});

let out = '';
proc.stdout.on('data', d => {
  const s = d.toString();
  out += s;
  process.stdout.write(s);
});
proc.stderr.on('data', d => {
  const s = d.toString();
  out += s;
  process.stderr.write(s);
});

proc.on('error', e => console.error('SPAWN ERROR:', e.message));
proc.on('exit', (code) => {
  console.log('\nCLI exited with code:', code);
  console.log('Full output:', out);
});

// Check if port opens
let checkCount = 0;
const checkPort = setInterval(() => {
  if (++checkCount > 15) {
    clearInterval(checkPort);
    console.log('\nPort never opened. Checking all listening ports...');
    // List all listening ports
    const listProc = spawn('netstat', ['-ano', '|', 'findstr', '942'], { shell: true, stdio: 'inherit' });
    return;
  }
  const sock = new net.Socket();
  sock.setTimeout(1000);
  sock.on('connect', () => {
    console.log(`\nPort ${AUTO_PORT} is OPEN on check ${checkCount}!`);
    sock.destroy();
    clearInterval(checkPort);

    // Now try to connect with automator
    console.log('\nTrying automator connect...');
    const auto = require('E:\\tarot-miniapp\\node_modules\\miniprogram-automator');
    auto.connect({ wsEndpoint: 'ws://127.0.0.1:' + AUTO_PORT }).then(mp => {
      console.log('CONNECTED!');
      mp.currentPage().then(p => console.log('Page:', p ? p.path : 'null'));
    }).catch(e => console.error('AUTO CONNECT ERROR:', e.message));
  });
  sock.on('error', () => {
    if (checkCount % 3 === 0) console.log(`Check ${checkCount}: port ${AUTO_PORT} not yet open`);
  });
  sock.on('timeout', () => {
    sock.destroy();
  });
  sock.connect(AUTO_PORT, '127.0.0.1');
}, 2000);

// Kill after 35 seconds
setTimeout(() => {
  clearInterval(checkPort);
  proc.kill();
  process.exit(1);
}, 35000);
