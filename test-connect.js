const auto = require('E:\\tarot-miniapp\\node_modules\\miniprogram-automator');
(async () => {
  try {
    console.log('Connecting to ws://127.0.0.1:9420...');
    const mp = await auto.connect({ wsEndpoint: 'ws://127.0.0.1:9420' });
    console.log('CONNECTED');
    const page = await mp.currentPage();
    console.log('PAGE:' + (page ? page.path : 'null'));
    const logs = await mp.getLogs();
    console.log('LOGS:' + logs.length);
    const errors = logs.filter(l => l.level === 'error');
    const warns = logs.filter(l => l.level === 'warn');
    console.log('ERRORS:' + errors.length);
    errors.forEach(l => console.log('ERR:', l.msg));
    console.log('WARNS:' + warns.length);
    warns.slice(0,5).forEach(l => console.log('WRN:', l.msg));
    await mp.close();
    console.log('DISCONNECTED');
  } catch(e) {
    console.log('CONNECT ERROR: ' + e.message);
    console.log(e.stack);
  }
})();
