const a = require('miniprogram-automator');
(async () => {
    try {
        const mp = await a.connect({ projectPath: 'E:/tarot-miniapp/miniapp' });
        console.log('OK');
        const pg = await mp.currentPage();
        console.log('PAGE:' + pg.path);
        const logs = await mp.getLogs();
        logs.filter(l => l.level === 'error').forEach(l => console.log('ERR:' + l.msg));
        logs.filter(l => l.level === 'warn').forEach(l => console.log('WRN:' + l.msg));
        console.log('DONE:' + logs.length + ' logs');
        await mp.close();
    } catch(e) { console.log('FAIL:' + e.message); }
})();
