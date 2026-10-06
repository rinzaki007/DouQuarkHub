let channelList = [];
let rawLogList = [];

window.onload = () => {
    loadAdminConfig();
    fetchAdminSubscriptions();
    fetchAdminChannels();
    initDemoLogs();
};

function switchSection(sec) {
    document.querySelectorAll('.admin-section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.sidebar-menu li').forEach(l => l.classList.remove('active'));
    document.getElementById(`sec-${sec}`).classList.add('active');
    event.currentTarget.classList.add('active');
}

// 🎯 读取四大分类目录配置
function loadAdminConfig() {
    document.getElementById('quark-cookie-input').value = localStorage.getItem('quark_cookie') || '';
    document.getElementById('folder-id-input').value = localStorage.getItem('target_folder_id') || '0';
    document.getElementById('openlist-url-input').value = localStorage.getItem('openlist_url') || '';
    
    document.getElementById('folder-movie-input').value = localStorage.getItem('folder_movie') || '';
    document.getElementById('folder-tv-input').value = localStorage.getItem('folder_tv') || '';
    document.getElementById('folder-show-input').value = localStorage.getItem('folder_show') || '';
    document.getElementById('folder-anime-input').value = localStorage.getItem('folder_anime') || '';
}

// 🎯 保存四大分类目录配置
async function saveAdminConfig() {
    localStorage.setItem('quark_cookie', document.getElementById('quark-cookie-input').value.trim());
    localStorage.setItem('target_folder_id', document.getElementById('folder-id-input').value.trim());
    localStorage.setItem('openlist_url', document.getElementById('openlist-url-input').value.trim());
    
    localStorage.setItem('folder_movie', document.getElementById('folder-movie-input').value.trim());
    localStorage.setItem('folder_tv', document.getElementById('folder-tv-input').value.trim());
    localStorage.setItem('folder_show', document.getElementById('folder-show-input').value.trim());
    localStorage.setItem('folder_anime', document.getElementById('folder-anime-input').value.trim());

    await fetch('/api/channels', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channels: channelList})
    });
    alert('全部参数与分类目录保存成功！');
}

// 🎯 导入与导出 JSON 同步覆盖四大目录
function exportConfig() {
    const configData = {
        quark_cookie: localStorage.getItem('quark_cookie') || '',
        target_folder_id: localStorage.getItem('target_folder_id') || '0',
        openlist_url: localStorage.getItem('openlist_url') || '',
        folder_movie: localStorage.getItem('folder_movie') || '',
        folder_tv: localStorage.getItem('folder_tv') || '',
        folder_show: localStorage.getItem('folder_show') || '',
        folder_anime: localStorage.getItem('folder_anime') || '',
        channels: channelList
    };

    const blob = new Blob([JSON.stringify(configData, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `moviesync_config_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
}

function triggerImportConfig() {
    document.getElementById('import-file-input').click();
}

function handleImportConfig(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async function(e) {
        try {
            const config = JSON.parse(e.target.result);
            if (config.quark_cookie !== undefined) localStorage.setItem('quark_cookie', config.quark_cookie);
            if (config.target_folder_id !== undefined) localStorage.setItem('target_folder_id', config.target_folder_id);
            if (config.openlist_url !== undefined) localStorage.setItem('openlist_url', config.openlist_url);
            
            if (config.folder_movie !== undefined) localStorage.setItem('folder_movie', config.folder_movie);
            if (config.folder_tv !== undefined) localStorage.setItem('folder_tv', config.folder_tv);
            if (config.folder_show !== undefined) localStorage.setItem('folder_show', config.folder_show);
            if (config.folder_anime !== undefined) localStorage.setItem('folder_anime', config.folder_anime);

            if (Array.isArray(config.channels)) {
                channelList = config.channels;
                await fetch('/api/channels', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({channels: channelList})
                });
            }

            loadAdminConfig();
            renderAdminChannels();
            alert('配置已成功导入！');
        } catch (err) {
            alert('导入失败，请检查 JSON 格式: ' + err.message);
        }
    };
    reader.readAsText(file);
}

// 🎯 彩色多级日志管理控制台
function initDemoLogs() {
    appendAdminLog('INFO', 'MovieSync 后台控制系统就绪...');
    appendAdminLog('SUCCESS', '自动化定时巡检引擎任务运行正常。');
}

function appendAdminLog(level, msg) {
    const time = new Date().toLocaleTimeString();
    rawLogList.push({ level, time, msg });
    renderLogConsole();
}

function renderLogConsole(filterLevel = 'ALL') {
    const logBox = document.getElementById('admin-log-body');
    if (!logBox) return;
    logBox.innerHTML = '';

    const classMap = {
        'INFO': 'log-tag-info',
        'SUCCESS': 'log-tag-success',
        'WARN': 'log-tag-warn',
        'ERROR': 'log-tag-error'
    };

    rawLogList.forEach(item => {
        if (filterLevel !== 'ALL' && item.level !== filterLevel) return;
        const line = document.createElement('div');
        line.className = 'log-line';
        line.innerHTML = `<span style="color:#64748b;">[${item.time}]</span> <span class="${classMap[item.level] || 'log-tag-info'}">[${item.level}]</span> ${item.msg}`;
        logBox.appendChild(line);
    });
    logBox.scrollTop = logBox.scrollHeight;
}

function filterLogs(level) {
    renderLogConsole(level);
}

function clearAdminLog() {
    rawLogList = [];
    renderLogConsole();
}

// 频道管理与追剧任务原样保留
async function fetchAdminSubscriptions() {
    const res = await fetch('/api/subscriptions');
    const data = await res.json();
    if (data.success) {
        const box = document.getElementById('sub-list-box');
        box.innerHTML = '';
        data.subscriptions.forEach(sub => {
            const item = document.createElement('div');
            item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:8px; border-bottom:1px solid #1e293b; font-size:12px;';
            item.innerHTML = `
                <div>
                    <b style="color:#60a5fa;">${sub.title}</b> 
                    <span style="color:#38bdf8;">[ID: ${sub.pwd_id}]</span>
                    <span style="color:#f59e0b;">(跳过前 ${sub.start_ep || 0} 集)</span>
                </div>
                <div>
                    <button class="btn-sm" onclick="runSubNow('${sub.id}')">🔄 检测</button>
                    <button class="btn-del" onclick="deleteSub('${sub.id}')">✕</button>
                </div>
            `;
            box.appendChild(item);
        });
    }
}

async function deleteSub(id) {
    await fetch(`/api/subscriptions?id=${id}`, {method: 'DELETE'});
    fetchAdminSubscriptions();
}

async function runSubNow(id) {
    const cookie = localStorage.getItem('quark_cookie') || '';
    const res = await fetch('/api/subscriptions/run-now', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id, cookie})
    });
    const data = await res.json();
    alert(data.message);
    fetchAdminSubscriptions();
}

async function fetchAdminChannels() {
    const res = await fetch('/api/channels');
    const data = await res.json();
    if (data.success) {
        channelList = data.channels;
        renderAdminChannels();
    }
}

function renderAdminChannels() {
    const box = document.getElementById('channel-list-box');
    box.innerHTML = '';
    channelList.forEach((ch, idx) => {
        const item = document.createElement('div');
        item.className = 'channel-item';
        item.innerHTML = `<div><b>${ch.name}</b> <span class="ch-id">(${ch.id})</span></div><button class="btn-del" onclick="removeChannel(${idx})">✕</button>`;
        box.appendChild(item);
    });
}

function addChannel() {
    const name = document.getElementById('new-ch-name').value.trim();
    const id = document.getElementById('new-ch-id').value.trim();
    if (name && id) {
        channelList.push({name, id});
        renderAdminChannels();
        document.getElementById('new-ch-name').value = '';
        document.getElementById('new-ch-id').value = '';
    }
}

function removeChannel(idx) {
    channelList.splice(idx, 1);
    renderAdminChannels();
}
