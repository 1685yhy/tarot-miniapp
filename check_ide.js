const a = require('miniprogram-automator');
(async () => {
    try {
        const mp = await a.connect({ projectPath: 'E:/tarot-miniapp/miniapp' });
        console.log('CONNECTED');
        const page = await mp.currentPage();
        console.log('PAGE:' + page.path);
        const logs = await mp.getLogs();
        console.log('LOGS:' + logs.length);
        logs.filter(l => l.level === 'error' || l.level === 'warn').forEach(l => {
            console.log('[' + l.level.toUpperCase() + '] ' + l.msg);
        });
        await mp.close();
    } catch(e) {
        console.log('ERROR:' + e.message);
    }
})();
