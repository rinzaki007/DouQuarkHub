let channelList = [];

window.onload = () => {
    loadAdminConfig();
    refreshAdminStatus();
    fetchAdminSubscriptions();
    fetchAdminChannels();
};

function switchSection(sec) {
    document.querySelectorAll('.admin-section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.sidebar-menu li').forEach(l => l.classList.remove('active'));
    document.getElementById(`sec-${sec}`).classList.add('active');
    event.currentTarget.classList.add('active');
}

function loadAdminConfig() {
    document.getElementById('quark-cookie-input').value = localStorage.getItem('quark_cookie') || '';
    document.getElementById('folder-id-input').value = localStorage.getItem('target_folder_id') || '0';
    document.getElementById('openlist-url-input').value = localStorage.getItem('openlist_url') || '';
    document.getElementById('folder-movie-input').value = localStorage.getItem('folder_movie') || '';
    document.getElementById('folder-tv-input').value = localStorage.getItem('folder_tv') || '';
}

async function refreshAdminStatus() {
    const cookie = localStorage.getItem('quark_cookie') || '';
    const badge = document.getElementById('quark-status-badge');
    if (cookie) {
        try {
            const res = await fetch('/api/check-cookie', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({cookie})
            });
            const data = await res.json();
            badge.className = data.valid ? 'badge badge-success' : 'badge badge-danger';
            badge.textContent = data.valid ? '🟢 有效' : '🔴 失效';
        } catch (e) { badge.textContent = '检测出错'; }
    } else {
        badge.className = 'badge badge-danger';
        badge.textContent = '未配置';
    }

    const chBadge = document.getElementById('channel-status-badge');
    try {
        const chRes = await fetch('/api/check-channels');
        const chData = await chRes.json();
        if (chData.success) {
            chBadge.className = 'badge badge-success';
            chBadge.textContent = `🟢 ${chData.valid_count}/${chData.total} 联通`;
        }
    } catch (e) { chBadge.textContent = '检测超时'; }
}

function clearAdminLog() {
    document.getElementById('log-body').textContent = '日志已清空...';
}

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

async function saveAdminConfig() {
    localStorage.setItem('quark_cookie', document.getElementById('quark-cookie-input').value.trim());
    localStorage.setItem('target_folder_id', document.getElementById('folder-id-input').value.trim());
    localStorage.setItem('openlist_url', document.getElementById('openlist-url-input').value.trim());
    localStorage.setItem('folder_movie', document.getElementById('folder-movie-input').value.trim());
    localStorage.setItem('folder_tv', document.getElementById('folder-tv-input').value.trim());

    await fetch('/api/channels', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channels: channelList})
    });
    alert('全部设置保存成功！');
    refreshAdminStatus();
}

// 🎯 配置导出 JSON 功能
function exportConfig() {
    const configData = {
        quark_cookie: localStorage.getItem('quark_cookie') || '',
        target_folder_id: localStorage.getItem('target_folder_id') || '0',
        openlist_url: localStorage.getItem('openlist_url') || '',
        folder_movie: localStorage.getItem('folder_movie') || '',
        folder_tv: localStorage.getItem('folder_tv') || '',
        channels: channelList
    };

    const blob = new Blob([JSON.stringify(configData, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `moviesync_config_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
}

// 🎯 配置导入 JSON 功能
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
            refreshAdminStatus();
        } catch (err) {
            alert('导入失败，请检查 JSON 格式是否正确: ' + err.message);
        }
    };
    reader.readAsText(file);
}
