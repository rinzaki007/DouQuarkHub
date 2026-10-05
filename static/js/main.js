let currentCategory = '电影';
let activeFilters = {
    sort: 'U',
    genre: '',
    country: '',
    year: ''
};

let movieList = [];
let selectedMovies = new Set();
let channelList = [];
let currentParseData = null;

window.onload = () => {
    loadConfig();
    refreshStatus();
    fetchMovies();
    fetchChannels();
};

function loadConfig() {
    document.getElementById('quark-cookie-input').value = localStorage.getItem('quark_cookie') || '';
    document.getElementById('folder-id-input').value = localStorage.getItem('target_folder_id') || '0';

    document.getElementById('folder-movie-input').value = localStorage.getItem('folder_movie') || '';
    document.getElementById('folder-tv-input').value = localStorage.getItem('folder_tv') || '';
    document.getElementById('folder-show-input').value = localStorage.getItem('folder_show') || '';
    document.getElementById('folder-anime-input').value = localStorage.getItem('folder_anime') || '';

    document.getElementById('openlist-url-input').value = localStorage.getItem('openlist_url') || '';
    document.getElementById('quark-app-input').value = localStorage.getItem('quark_app_url') || 'quark://';
}

function refreshStatus() {
    checkQuarkStatus();
    checkChannelsHealth();
}

function openOpenList() {
    const url = localStorage.getItem('openlist_url');
    if (!url) {
        alert('请先在右侧【⚙️ 配置设置】中填入你 NAS 部署的 OpenList 访问地址！');
        openConfigModal();
        return;
    }
    window.open(url, '_blank');
}

function openQuarkApp() {
    const appUrl = localStorage.getItem('quark_app_url') || 'quark://';
    if (appUrl.startsWith('http://') || appUrl.startsWith('https://')) {
        window.open(appUrl, '_blank');
        return;
    }
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = appUrl;
    document.body.appendChild(iframe);
    setTimeout(() => { document.body.removeChild(iframe); }, 2000);
}

function switchCategory(cat) {
    currentCategory = cat;
    ['电影', '电视剧', '综艺', '动漫'].forEach(c => {
        const btn = document.getElementById(`tab-${c}`);
        if (btn) btn.classList.toggle('active', c === cat);
    });
    fetchMovies();
}

function setFilter(type, value, el) {
    activeFilters[type] = value;
    const container = el.parentElement;
    container.querySelectorAll('.filter-item').forEach(item => item.classList.remove('active'));
    el.classList.add('active');
    fetchMovies();
}

async function fetchMovies() {
    appendLog(`[系统] 正在筛选豆瓣【${currentCategory}】...`);
    const params = new URLSearchParams({
        tag: currentCategory,
        sort: activeFilters.sort,
        genre: activeFilters.genre,
        country: activeFilters.country,
        year: activeFilters.year
    });

    try {
        const res = await fetch(`/api/get-movies?${params.toString()}`);
        const data = await res.json();
        if (data.success) {
            movieList = data.movies;
            renderGrid();
        } else {
            appendLog(`[系统] ❌ 获取列表失败: ${data.message || '豆瓣服务异常'}`);
        }
    } catch (err) {
        appendLog(`[系统] ❌ 网络获取失败: ${err.message}`);
    }
}

async function searchMovies() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;
    appendLog(`[系统] 🔍 正在豆瓣全站搜索：${query}...`);
    try {
        const res = await fetch(`/api/search-douban?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        if (data.success) {
            movieList = data.movies;
            renderGrid();
        }
    } catch (err) {
        appendLog(`[系统] ❌ 搜索失败: ${err.message}`);
    }
}

function renderGrid() {
    const grid = document.getElementById('movie-grid');
    grid.innerHTML = '';
    if (movieList.length === 0) {
        grid.innerHTML = `<div style="grid-column: span 8; text-align:center; color:#64748b; padding:40px;">未检索到符合条件的作品</div>`;
        return;
    }
    movieList.forEach(m => {
        const isSelected = selectedMovies.has(m.title);
        const card = document.createElement('div');
        card.className = `movie-card ${isSelected ? 'selected' : ''}`;
        card.onclick = () => toggleSelect(m.title, card);

        const coverSrc = m.cover ? `/api/proxy-img?url=${encodeURIComponent(m.cover)}` : '';

        card.innerHTML = `
            <div class="cover-box">
                <img src="${coverSrc}" alt="${m.title}" loading="lazy">
                <div class="rate-tag">${m.rate}</div>
                <div class="check-box">${isSelected ? '✓' : ''}</div>
            </div>
            <div class="card-info">
                <div class="movie-title">${m.title}</div>
                <a href="${m.url}" target="_blank" class="douban-link" onclick="event.stopPropagation()">🔗 豆瓣详情</a>
            </div>
        `;
        grid.appendChild(card);
    });
    updateCount();
}

function toggleSelect(title, card) {
    if (selectedMovies.has(title)) {
        selectedMovies.delete(title);
        card.classList.remove('selected');
        card.querySelector('.check-box').textContent = '';
    } else {
        selectedMovies.add(title);
        card.classList.add('selected');
        card.querySelector('.check-box').textContent = '✓';
    }
    updateCount();
}

function selectAll() {
    movieList.forEach(m => selectedMovies.add(m.title));
    renderGrid();
}

function clearSelection() {
    selectedMovies.clear();
    renderGrid();
}

function updateCount() {
    document.getElementById('selected-count').textContent = selectedMovies.size;
}

function appendLog(text) {
    const logBody = document.getElementById('log-body');
    logBody.textContent += (logBody.textContent ? '\n' : '') + text;
    logBody.scrollTop = logBody.scrollHeight;
}

function clearLog() {
    document.getElementById('log-body').textContent = 'MovieSync 就绪，等待触发转存任务...';
}

async function checkChannelsHealth() {
    const chBadge = document.getElementById('channel-status-badge');
    chBadge.className = 'badge badge-warning';
    chBadge.textContent = '探测中...';

    try {
        const res = await fetch('/api/check-channels');
        const data = await res.json();
        if (data.success) {
            if (data.total === 0) {
                chBadge.className = 'badge badge-warning';
                chBadge.textContent = '未配置频道';
            } else if (data.valid_count === data.total) {
                chBadge.className = 'badge badge-success';
                chBadge.textContent = `🟢 ${data.valid_count}/${data.total} 个联通`;
            } else if (data.valid_count > 0) {
                chBadge.className = 'badge badge-warning';
                chBadge.textContent = `🟡 ${data.valid_count}/${data.total} 个联通`;
            } else {
                chBadge.className = 'badge badge-danger';
                chBadge.textContent = `🔴 0/${data.total} 无法访问`;
            }
        }
    } catch (err) {
        chBadge.className = 'badge badge-danger';
        chBadge.textContent = '检测异常';
    }
}

async function checkQuarkStatus() {
    const cookie = localStorage.getItem('quark_cookie') || '';
    const badge = document.getElementById('quark-status-badge');
    if (!cookie) {
        badge.className = 'badge badge-danger';
        badge.textContent = '未配置';
        return;
    }
    badge.className = 'badge badge-warning';
    badge.textContent = '校验中...';

    try {
        const res = await fetch('/api/check-cookie', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cookie: cookie })
        });
        const data = await res.json();
        if (data.valid) {
            badge.className = 'badge badge-success';
            badge.textContent = '🟢 有效';
        } else {
            badge.className = 'badge badge-danger';
            badge.textContent = '🔴 已失效';
        }
    } catch (err) {
        badge.className = 'badge badge-danger';
        badge.textContent = '接口异常';
    }
}

async function fetchChannels() {
    try {
        const res = await fetch('/api/channels');
        const data = await res.json();
        if (data.success) {
            channelList = data.channels;
            renderChannels();
            checkChannelsHealth();
        }
    } catch (err) {
        console.error("加载频道失败", err);
    }
}

function renderChannels() {
    const container = document.getElementById('channel-list-box');
    container.innerHTML = '';
    if (channelList.length === 0) {
        container.innerHTML = `<div style="text-align:center; color:#64748b; font-size:13px; padding:10px;">暂无设定频道</div>`;
        return;
    }
    channelList.forEach((ch, idx) => {
        const item = document.createElement('div');
        item.className = 'channel-item';
        item.innerHTML = `
            <div>
                <b>${ch.name}</b>
                <span class="ch-id">(${ch.id})</span>
            </div>
            <button class="btn-del" onclick="removeChannel(${idx})">✕</button>
        `;
        container.appendChild(item);
    });
}

function addChannel() {
    const name = document.getElementById('new-ch-name').value.trim();
    const id = document.getElementById('new-ch-id').value.trim();
    if (!name || !id) {
        alert('请同时输入频道名称和频道 ID！');
        return;
    }
    channelList.push({ name, id });
    renderChannels();
    document.getElementById('new-ch-name').value = '';
    document.getElementById('new-ch-id').value = '';
}

function removeChannel(idx) {
    channelList.splice(idx, 1);
    renderChannels();
}

function importChannelsJson() {
    const jsonStr = prompt("请粘贴你的频道 JSON 数据（数组格式）：", '[{"name": "示例", "id": "example"}]');
    if (!jsonStr) return;
    try {
        const parsed = JSON.parse(jsonStr);
        if (!Array.isArray(parsed)) {
            alert("导入失败：JSON 必须是数组格式 [...]");
            return;
        }
        let addedCount = 0;
        parsed.forEach(item => {
            const name = item.name || item.title || "";
            const id = item.id || item.channel_id || "";
            if (name && id) {
                if (!channelList.some(c => c.id === id)) {
                    channelList.push({ name, id });
                    addedCount++;
                }
            }
        });
        renderChannels();
        alert(`成功导入 ${addedCount} 个新频道！请点击配置弹窗右下角“保存配置”以保存更改。`);
    } catch (err) {
        alert("解析 JSON 失败，请检查格式！\n错误: " + err.message);
    }
}

async function saveConfig() {
    const cookie = document.getElementById('quark-cookie-input').value.trim();
    const defaultFid = document.getElementById('folder-id-input').value.trim() || '0';

    const folderMovie = document.getElementById('folder-movie-input').value.trim();
    const folderTv = document.getElementById('folder-tv-input').value.trim();
    const folderShow = document.getElementById('folder-show-input').value.trim();
    const folderAnime = document.getElementById('folder-anime-input').value.trim();

    const openlistUrl = document.getElementById('openlist-url-input').value.trim();
    const quarkAppUrl = document.getElementById('quark-app-input').value.trim() || 'quark://';
    
    localStorage.setItem('quark_cookie', cookie);
    localStorage.setItem('target_folder_id', defaultFid);

    localStorage.setItem('folder_movie', folderMovie);
    localStorage.setItem('folder_tv', folderTv);
    localStorage.setItem('folder_show', folderShow);
    localStorage.setItem('folder_anime', folderAnime);

    localStorage.setItem('openlist_url', openlistUrl);
    localStorage.setItem('quark_app_url', quarkAppUrl);

    try {
        await fetch('/api/channels', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channels: channelList })
        });
        alert('配置已成功保存！');
        closeConfigModal();
        refreshStatus();
    } catch (err) {
        alert('保存频道配置失败: ' + err.message);
    }
}

function openConfigModal() { document.getElementById('config-modal').style.display = 'flex'; }
function closeConfigModal() { document.getElementById('config-modal').style.display = 'none'; }

function openSubModal() {
    document.getElementById('sub-modal').style.display = 'flex';
    fetchSubscriptions();
}
function closeSubModal() { document.getElementById('sub-modal').style.display = 'none'; }

function closeSelectFilesModal() { document.getElementById('select-files-modal').style.display = 'none'; }

function getTargetFolderId() {
    const defaultFid = localStorage.getItem('target_folder_id') || '0';
    const catFidMap = {
        '电影': localStorage.getItem('folder_movie'),
        '电视剧': localStorage.getItem('folder_tv'),
        '综艺': localStorage.getItem('folder_show'),
        '动漫': localStorage.getItem('folder_anime')
    };

    const specificFid = catFidMap[currentCategory];
    if (specificFid && specificFid.trim() !== '') {
        return specificFid.trim();
    }
    return defaultFid;
}

/* 🎬 选集解析与转存 */
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
    files.forEach((f) => {
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

/* 📺 追剧订阅 API */
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

async function startBatchTransfer() {
    if (selectedMovies.size === 0) {
        alert('请先勾选需要转存的影视！');
        return;
    }

    const cookie = localStorage.getItem('quark_cookie') || '';
    if (!cookie) {
        alert('请先填入夸克 Cookie！');
        openConfigModal();
        return;
    }

    const targetFolderId = getTargetFolderId();

    document.getElementById('log-body').textContent = '';
    const targets = Array.from(selectedMovies);
    appendLog(`[系统] 🚀 开始处理批量转存 [分类: ${currentCategory}]，共 ${targets.length} 个目标...`);
    appendLog(`[系统] 📁 存储目标目录 FID: ${targetFolderId}`);

    try {
        const response = await fetch('/api/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movies: targets,
                cookie: cookie,
                folderId: targetFolderId
            })
        });

        if (!response.ok) {
            const text = await response.text();
            appendLog(`\n❌ 网关/服务器异常 (${response.status}): ${text.substring(0, 100)}`);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            appendLog(chunk);
        }

        const openlistUrl = localStorage.getItem('openlist_url');
        if (openlistUrl) {
            appendLog(`\n👉 提示：你可以点击顶栏【▶️ OpenList 云播】直接播放本轮转存视频！`);
        }
    } catch (err) {
        appendLog(`\n❌ 网络请求异常: ${err.message}`);
    }
}
