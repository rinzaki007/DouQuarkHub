let currentChaseSelectedCandidate = null;

function openChaseModal() { 
    document.getElementById('chase-modal').classList.remove('hidden');
    switchChaseTab('add');
    loadModalSubscriptions();
    loadCategoryOptions();
}

function closeChaseModal() { 
    document.getElementById('chase-modal').classList.add('hidden'); 
}

function switchChaseTab(tabName) {
    const tabAdd = document.getElementById('chase-tab-add');
    const tabList = document.getElementById('chase-tab-list');
    const panelAdd = document.getElementById('chase-panel-add');
    const panelList = document.getElementById('chase-panel-list');
    const submitBtn = document.getElementById('btn-submit-chase');

    if (tabName === 'add') {
        tabAdd.className = "px-3.5 py-1.5 rounded bg-purple-600 text-white font-medium transition shadow";
        tabList.className = "px-3.5 py-1.5 rounded text-slate-400 hover:text-white transition";
        panelAdd.classList.remove('hidden');
        panelList.classList.add('hidden');
        if(currentChaseSelectedCandidate) submitBtn.classList.remove('hidden');
    } else {
        tabList.className = "px-3.5 py-1.5 rounded bg-purple-600 text-white font-medium transition shadow";
        tabAdd.className = "px-3.5 py-1.5 rounded text-slate-400 hover:text-white transition";
        panelList.classList.remove('hidden');
        panelAdd.classList.add('hidden');
        submitBtn.classList.add('hidden');
        loadModalSubscriptions();
    }
}

async function loadModalSubscriptions() {
    const tbody = document.getElementById('modal-sub-table-body');
    tbody.innerHTML = '<tr><td colspan="5" class="px-3.5 py-6 text-center text-slate-500"><i class="fa-solid fa-spinner fa-spin"></i> 正在加载...</td></tr>';
    try {
        const resp = await fetch('/api/subscriptions');
        const res = await resp.json();
        if (res.success && res.subscriptions) {
            document.getElementById('sub-count-badge').innerText = res.subscriptions.length;
            if (res.subscriptions.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="px-3.5 py-8 text-center text-slate-500">暂无自动化追剧任务，请先去【添加新追剧】创建。</td></tr>';
                return;
            }
            tbody.innerHTML = '';
            res.subscriptions.forEach(sub => {
                const tr = document.createElement('tr');
                tr.className = "hover:bg-slate-900/60";
                tr.innerHTML = `
                    <td class="px-3.5 py-3 font-medium text-slate-200">${sub.title}</td>
                    <td class="px-3.5 py-3 text-emerald-400">${sub.channel || '默认频道'}</td>
                    <td class="px-3.5 py-3 text-slate-400">${sub.interval_hours} 小时</td>
                    <td class="px-3.5 py-3 text-slate-400">${sub.last_check || '等待触发'}</td>
                    <td class="px-3.5 py-3 text-right space-x-2">
                        <button onclick="runSubNow('${sub.id}')" class="bg-purple-600 hover:bg-purple-500 text-white px-2.5 py-1 rounded text-[11px]">立即运行</button>
                        <button onclick="deleteSub('${sub.id}')" class="bg-rose-900/60 hover:bg-rose-800 text-rose-200 px-2.5 py-1 rounded text-[11px]">删除</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" class="px-3.5 py-4 text-center text-rose-400">加载失败</td></tr>';
    }
}

async function runSubNow(subId) {
    try {
        const resp = await fetch('/api/subscriptions/run-now', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id: subId })
        });
        const res = await resp.json();
        alert(res.message || '已执行检视');
        loadModalSubscriptions();
    } catch (err) {
        alert('手动执行失败');
    }
}

async function deleteSub(subId) {
    if (!confirm('确定要删除该追剧任务吗？')) return;
    try {
        await fetch(`/api/subscriptions?id=${subId}`, { method: 'DELETE' });
        loadModalSubscriptions();
    } catch (err) {
        alert('删除失败');
    }
}

async function searchChaseCandidates() {
    const title = document.getElementById('chase-title-input').value.trim();
    if (!title) return alert('请输入要追剧的名称');

    const cookie = localStorage.getItem('quark_cookie') || '';
    const listContainer = document.getElementById('chase-candidates-list');
    listContainer.innerHTML = `<div class="text-xs text-slate-400 py-6 text-center"><i class="fa-solid fa-spinner fa-spin"></i> 正在全网并发检索频道...</div>`;
    document.getElementById('chase-candidates-container').classList.remove('hidden');

    try {
        const resp = await fetch('/api/search-candidates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movies: [{ title: title, tag: '电视剧' }],
                cookie: cookie
            })
        });
        const res = await resp.json();
        if (!res.success) {
            listContainer.innerHTML = `<div class="text-xs text-rose-400 py-2">检索失败: ${res.message}</div>`;
            return;
        }

        const candidatesMap = res.candidates_map || {};
        const candidates = candidatesMap[title] || [];

        if (candidates.length === 0) {
            listContainer.innerHTML = `<div class="text-xs text-amber-400 py-4 text-center">未在任何配置频道中找到匹配资源，请检查片名是否正确。</div>`;
            return;
        }

        listContainer.innerHTML = '';
        candidates.forEach((cand) => {
            const fileNames = cand.files.map((f) => `
                <label class="flex items-center gap-2 py-1 text-xs text-slate-300 hover:text-white cursor-pointer">
                    <input type="checkbox" name="chase-file-item" value="${f.fid}" class="chase-file-cb rounded bg-slate-900 border-slate-700 text-purple-600 focus:ring-0">
                    <span class="font-mono">${f.file_name}</span>
                </label>
            `).join('');

            const itemDiv = document.createElement('div');
            itemDiv.className = 'bg-slate-950 border border-slate-800 rounded-lg p-4 space-y-3';
            itemDiv.innerHTML = `
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold text-emerald-400"><i class="fa-brands fa-telegram"></i> 频道: ${cand.channel}</span>
                    <button onclick='selectThisChaseCandidate(${JSON.stringify(cand)}, this)' class="px-3.5 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded text-xs font-medium transition">
                        👈 锁定此源并追剧
                    </button>
                </div>
                <div class="text-xs text-slate-400">夸克短码: <span class="font-mono text-slate-200">${cand.pwd_id}</span> | 包含视频数: ${cand.files.length}</div>
                <div class="bg-slate-900 p-3 rounded-md max-h-48 overflow-y-auto space-y-1 border border-slate-800">
                    <div class="text-[11px] text-slate-400 mb-2 font-medium">勾选您需要监控/下载的具体集数或版本：</div>
                    ${fileNames}
                </div>
            `;
            listContainer.appendChild(itemDiv);
        });

    } catch (err) {
        listContainer.innerHTML = `<div class="text-xs text-rose-400 py-2">请求发生异常: ${err.message}</div>`;
    }
}

function selectThisChaseCandidate(candidate, btnElement) {
    currentChaseSelectedCandidate = candidate;
    document.querySelectorAll('#chase-candidates-list button').forEach(btn => {
        btn.className = "px-3.5 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded text-xs font-medium transition";
        btn.innerText = "👈 锁定此源并追剧";
    });
    btnElement.className = "px-3.5 py-1.5 bg-emerald-600 text-white rounded text-xs font-medium";
    btnElement.innerText = "✅ 已锁定此源";
    
    document.getElementById('btn-submit-chase').classList.remove('hidden');
    alert(`已成功锁定频道 [${candidate.channel}] 的分享源！请在下方设置存储目录和频率并点击保存。`);
}

async function submitSmartChase() {
    const title = document.getElementById('chase-title-input').value.trim();
    const intervalHours = parseInt(document.getElementById('chase-interval-select').value) || 6;
    const targetFid = document.getElementById('chase-target-fid').value;

    if (!title || !currentChaseSelectedCandidate) {
        return alert('请先输入名称并锁定一个有效的频道分享源！');
    }

    const checkboxes = document.querySelectorAll('input[name="chase-file-item"]:checked');
    const selectedFids = Array.from(checkboxes).map(cb => cb.value);

    if (selectedFids.length === 0) {
        return alert('请至少勾选一个需要监控的文件/集数！');
    }

    const filteredFiles = currentChaseSelectedCandidate.files.filter(f => selectedFids.includes(f.fid));
    const payload = {
        title: title,
        channel: currentChaseSelectedCandidate.channel,
        pwd_id: currentChaseSelectedCandidate.pwd_id,
        stoken: currentChaseSelectedCandidate.stoken,
        files: filteredFiles,
        interval_hours: intervalHours,
        target_fid: targetFid
    };

    try {
        const resp = await fetch('/api/subscriptions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const res = await resp.json();
        alert(res.message || '自动化追剧规则保存成功！');
        switchChaseTab('list');
    } catch (err) {
        alert('保存追剧任务失败');
    }
}
