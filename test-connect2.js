const http = require('http');
const net = require('net');

// First check what ports are available
function checkPort(port) {
  return new Promise((resolve) => {
    const sock = new net.Socket();
    sock.setTimeout(1000);
    sock.on('connect', () => { sock.destroy(); resolve(true); });
    sock.on('error', () => resolve(false));
    sock.on('timeout', () => { sock.destroy(); resolve(false); });
    sock.connect(port, '127.0.0.1');
  });
}

async function main() {
  const ports = [9420, 9421, 9422, 9423, 9424, 9425, 19109, 57316];
  for (const port of ports) {
    const open = await checkPort(port);
    console.log(`Port ${port}: ${open ? 'OPEN' : 'CLOSED'}`);
  }
  
  // Try to find any websocket endpoint on the IDE HTTP server
  try {
    const data = await new Promise((resolve, reject) => {
      http.get('http://127.0.0.1:57316/json', (res) => {
        let d = '';
        res.on('data', c => d += c);
        res.on('end', () => resolve(d));
      }).on('error', reject);
    });
    console.log('IDE /json:', data.slice(0, 300));
  } catch(e) {
    console.log('IDE /json error:', e.message);
  }
}

main();
