const { spawn } = require('child_process');
const auto = require('E:\\tarot-miniapp\\node_modules\\miniprogram-automator');

// Use the WeChat DevTools CLI to launch and connect
async function main() {
  const cliPath = 'E:\\微信web开发者工具\\cli.bat';
  const projectPath = 'E:\\tarot-miniapp\\miniapp';
  const autoPort = 9420;

  console.log('Spawning DevTools CLI...');
  const proc = spawn(cliPath, ['auto', '--project', projectPath, '--auto-port', String(autoPort)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: true,
    cwd: 'E:\\',
  });

  proc.stdout.on('data', (d) => process.stdout.write('[CLI] ' + d.toString()));
  proc.stderr.on('data', (d) => process.stderr.write('[CLI-ERR] ' + d.toString()));

  proc.on('error', (e) => {
    console.error('Spawn error:', e.message);
  });

  // Wait for the automation port to be ready
  console.log('Waiting for automation endpoint...');
  await new Promise(resolve => setTimeout(resolve, 10000));

  // Try to connect
  console.log('Connecting to ws://127.0.0.1:' + autoPort);
  try {
    const mp = await auto.connect({ wsEndpoint: 'ws://127.0.0.1:' + autoPort });
    console.log('=== CONNECTED TO MINIPROGRAM ===');

    // Check current page
    const page = await mp.currentPage();
    console.log('Current page:', page ? page.path : 'null');

    // Get logs
    const logs = await mp.getLogs();
    console.log('Total logs:', logs.length);

    const errors = logs.filter(l => l.level === 'error');
    const warns = logs.filter(l => l.level === 'warn');
    console.log('Errors:', errors.length);
    errors.forEach(l => console.log(' [ERR]', l.msg));
    console.log('Warnings:', warns.length);
    warns.slice(0, 10).forEach(l => console.log(' [WARN]', l.msg));

    await mp.close();
    console.log('=== DISCONNECTED ===');
  } catch(e) {
    console.error('Connection failed:', e.message);
  }

  proc.kill();
}

main().catch(console.error);
