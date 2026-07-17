const auto = require('miniprogram-automator');
(async () => {
  try {
    console.log('Launching DevTools...');
    const mp = await auto.launch({
      projectPath: 'E:\\tarot-miniapp\\miniapp',
      cliPath: 'E:\\微信web开发者工具\\cli.bat',
      port: 9420,
    });
    console.log('LAUNCHED & CONNECTED');
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
    console.log('LAUNCH ERROR: ' + e.message);
  }
})();
