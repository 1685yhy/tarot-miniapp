const a = require('miniprogram-automator');
(async () => {
  try {
    const mp = await a.launch({
      projectPath: 'E:/tarot-miniapp/miniapp',
      cliPath: 'E:/微信web开发者工具/cli.bat',
    });
    console.log('CONNECTED');
    const page = await mp.currentPage();
    console.log('PAGE:' + page.path);
    const logs = await mp.getLogs();
    console.log('LOGS:' + logs.length);
    logs.filter(function(l) { return l.level === 'error'; }).forEach(function(l) {
      console.log('ERR:' + l.msg);
    });
    logs.filter(function(l) { return l.level === 'warn'; }).forEach(function(l) {
      console.log('WRN:' + l.msg);
    });
    await mp.close();
  } catch(e) {
    console.log('FAIL:' + e.message);
  }
})();
