// Direct IDE interaction via its built-in HTTP server
// IDE is at http://127.0.0.1:34745 after CLI auto

const http = require('http');

function ideGet(path) {
  return new Promise((resolve, reject) => {
    http.get('http://127.0.0.1:34745' + path, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ code: res.statusCode, data: data.slice(0, 500) }));
    }).on('error', reject);
  });
}

(async () => {
  // Try known IDE API paths
  const paths = ['/', '/json', '/json/list', '/json/version', '/inspector/json', '/devtools/inspector'];
  for (const p of paths) {
    try {
      const r = await ideGet(p);
      console.log(p + ' -> ' + r.code + ' ' + r.data.slice(0, 100));
    } catch(e) {
      console.log(p + ' -> ERR: ' + e.message);
    }
  }
})();
