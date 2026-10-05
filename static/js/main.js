let currentParseData = null;

// 打开并解析分享链接，弹出选集窗口
async function parseAndSelectFiles(pwdId, showTitle) {
    const cookie = localStorage.getItem('quark_cookie') || '';
    if (!cookie) {
        alert('请先配置夸克 Cookie！');
        openConfigModal();
        return;
    }

    appendLog(`[系统] 🔍 正在解析夸克分享资源 (ID: ${pwdId})...`);

    try {
        const res = await fetch('/api/parse-share-detail', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pwd_id: pwdId, title: showTitle, cookie: cookie })
        });
        const data = await res.json();
        if (data.success) {
            currentParseData = data;
            renderParseFileList(data.files);
            document.getElementById('select-files-modal').style.display = 'flex';
        } else {
            alert('解析失败: ' + data.message);
        }
    } catch (err) {
        alert('解析网络异常: ' + err.message);
    }
}

function renderParseFileList(files) {
    const container = document.getElementById('parse-file-list');
    container.innerHTML = '';
    files.forEach((f, idx) => {
        const item = document.createElement('div');
        item.style.cssText = 'display:flex; align-items:center; justify-content:space-between; padding:6px; border-bottom:1px solid #1e293b; font-size:12px;';
        item.innerHTML = `
            <div style="display:flex; align-items:center; gap:8px; overflow:hidden;">
                <input type="checkbox" class="parse-file-check" value="${f.fid}" ${f.is_video ? 'checked' : ''} onchange="updateSelectedParseCount()">
                <div style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                    <div style="color:${f.is_video ? '#38bdf8' : '#94a3b8'}; font-weight:bold;">${f.cleaned_name || f.raw_name}</div>
                    <div style="font-size:10px; color:#64748b;">原名: ${f.raw_name}</div>
                </div>
            </div>
            <span style="color:#f59e0b; white-space:nowrap; margin-left:8px;">${f.size_str}</span>
        `;
        container.appendChild(item);
    });
    updateSelectedParseCount();
}

function updateSelectedParseCount() {
    const checked = document.querySelectorAll('.parse-file-check:checked');
    document.getElementById('selected-parse-count').textContent = `已选 ${checked.length} 个文件`;
}

function selectAllParseFiles(status) {
    document.querySelectorAll('.parse-file-check').forEach(c => c.checked = status);
    updateSelectedParseCount();
}

async function submitSaveSelectedFiles() {
    const checked = Array.from(document.querySelectorAll('.parse-file-check:checked')).map(c => c.value);
    if (checked.length === 0) {
        alert('请勾选要转存的文件！');
        return;
    }

    const cookie = localStorage.getItem('quark_cookie') || '';
    const targetFid = getTargetFolderId();

    try {
        const res = await fetch('/api/save-selected-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pwd_id: currentParseData.pwd_id,
                stoken: currentParseData.stoken,
                fids: checked,
                target_fid: targetFid,
                cookie: cookie
            })
        });
        const data = await res.json();
        if (data.success) {
            alert('✅ 选集文件已成功转存到夸克网盘！');
            closeSelectFilesModal();
        } else {
            alert('❌ 转存失败: ' + data.message);
        }
    } catch (err) {
        alert('请求网络异常: ' + err.message);
    }
}

function closeSelectFilesModal() { document.getElementById('select-files-modal').style.display = 'none'; }

/* 📺 追剧订阅逻辑 */
function openSubModal() {
    document.getElementById('sub-modal').style.display = 'flex';
    fetchSubscriptions();
}
function closeSubModal() { document.getElementById('sub-modal').style.display = 'none'; }

async function fetchSubscriptions() {
    const res = await fetch('/api/subscriptions');
    const data = await res.json();
    if (data.success) {
        const box = document.getElementById('sub-list-box');
        box.innerHTML = '';
        if (data.subscriptions.length === 0) {
            box.innerHTML = `<div style="text-align:center; color:#64748b; font-size:12px; padding:10px;">暂无自动追剧订阅</div>`;
            return;
        }
        data.subscriptions.forEach(sub => {
            const item = document.createElement('div');
            item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:8px; border-bottom:1px solid #1e293b; font-size:12px;';
            item.innerHTML = `
                <div>
                    <b style="color:#60a5fa;">${sub.title}</b> <span style="color:#64748b;">(已存集数: ${sub.saved_episodes.length}集)</span>
                    <div style="font-size:10px; color:#94a3b8;">上次检查: ${sub.last_check} | 间隔: ${sub.interval_hours}小时</div>
                </div>
                <div>
                    <button class="btn-sm" style="background:#0284c7; margin-right:4px;" onclick="runSubNow('${sub.id}')">🔄 立即检测</button>
                    <button class="btn-del" onclick="deleteSub('${sub.id}')">✕</button>
                </div>
            `;
            box.appendChild(item);
        });
    }
}

async function addSubscription() {
    const title = document.getElementById('sub-title-input').value.trim();
    const pwdId = document.getElementById('sub-pwd-input').value.trim();
    const targetFid = document.getElementById('sub-fid-input').value.trim() || '0';
    const intervalHours = document.getElementById('sub-interval-input').value;

    if (!title || !pwdId) {
        alert('请输入剧集名称和夸克链接 ID！');
        return;
    }

    const cookie = localStorage.getItem('quark_cookie') || '';
    await fetch('/api/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, pwd_id: pwdId, target_fid: targetFid, interval_hours: intervalHours, cookie })
    });

    document.getElementById('sub-title-input').value = '';
    document.getElementById('sub-pwd-input').value = '';
    fetchSubscriptions();
}

async function deleteSub(subId) {
    await fetch(`/api/subscriptions?id=${subId}`, { method: 'DELETE' });
    fetchSubscriptions();
}

async function runSubNow(subId) {
    const cookie = localStorage.getItem('quark_cookie') || '';
    const res = await fetch('/api/subscriptions/run-now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: subId, cookie })
    });
    const data = await res.json();
    alert(data.message);
    fetchSubscriptions();
}
