const a = require('miniprogram-automator');
(async () => {
  try {
    const mp = await a.connect({
      projectPath: 'E:/tarot-miniapp/miniapp',
    });
    console.log('CONNECTED');
    const page = await mp.currentPage();
    console.log('PAGE:' + page.path);
    const logs = await mp.getLogs();
    logs.filter(function(l) { return l.level === 'error'; }).forEach(function(l) {
      console.log('ERR:' + l.msg);
    });
    await mp.close();
  } catch(e) {
    console.log('FAIL:' + e.message);
  }
})();
