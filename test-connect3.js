const http = require('http');
const net = require('net');

async function httpGet(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve({ status: res.statusCode, data }));
    }).on('error', reject);
  });
}

async function main() {
  // Check IDE HTTP API endpoints
  const endpoints = ['/', '/json', '/json/list', '/json/version'];
  for (const ep of endpoints) {
    try {
      const r = await httpGet('http://127.0.0.1:57316' + ep);
      console.log(ep + ' -> ' + r.status + ' ' + JSON.stringify(r.data).slice(0, 200));
    } catch(e) {
      console.log(ep + ' -> ERR: ' + e.message);
    }
  }

  // Try to find the automation port
  // DevTools automation typically listens on a port like 9420 or auto-assigned
  // Try connecting to common automation ports
  const ports = [9420, 9421, 9422, 9423, 9424, 9425];
  for (const port of ports) {
    try {
      const sock = new net.Socket();
      const open = await new Promise((resolve) => {
        sock.setTimeout(500);
        sock.on('connect', () => { sock.destroy(); resolve(true); });
        sock.on('error', () => resolve(false));
        sock.on('timeout', () => { sock.destroy(); resolve(false); });
        sock.connect(port, '127.0.0.1');
      });
      if (open) console.log('Port ' + port + ': OPEN');
    } catch(e) {}
  }
}

main();
