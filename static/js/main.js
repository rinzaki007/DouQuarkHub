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
    initScrollCollapseFilter(); // 🎯 初始化滚动自动收起筛选面板
};

// 🎯 核心新功能：滚动时自动缩放/收起筛选面板
function initScrollCollapseFilter() {
    const gridContainer = document.getElementById('movie-grid-container');
    const filterPanel = document.getElementById('filter-panel');
    if (!gridContainer || !filterPanel) return;

    let lastScrollTop = 0;
    gridContainer.addEventListener('scroll', () => {
        const currentScroll = gridContainer.scrollTop;
        if (currentScroll > 20 && currentScroll > lastScrollTop) {
            // 向下滚动：自动收起筛选面板
            filterpanelAddCollapsed(filterPanel, true);
        } else if (currentScroll < 10) {
            // 滚动回顶部：自动展开筛选面板
            filterpanelAddCollapsed(filterPanel, false);
        }
        lastScrollTop = currentScroll;
    });
}

function filterpanelAddCollapsed(panel, collapse) {
    if (collapse) {
        panel.classList.add('collapsed');
    } else {
        panel.classList.remove('collapsed');
    }
}

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
        alert('请先在右侧【⚙️ 配置设置】中填入 OpenList 地址！');
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
    appendLog(`[系统] 正在加载豆瓣【${currentCategory}】...`);
    const params = new URLSearchParams({
        tag: currentCategory,
        sort: activeFilters.sort,
        genre: activeFilters.genre,
        country: activeFilters.country,
        year: activeFilters.year
    });

    try {
        const res = await fetch(`/api/get-movies?${params.toString()}`);
        const contentType = res.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            appendLog(`[系统] ❌ 服务端响应页面异常`);
            return;
        }

        const data = await res.json();
        if (data.success) {
            movieList = data.movies;
            renderGrid();
        } else {
            appendLog(`[系统] ⚠️ ${data.message || '获取列表失败'}`);
        }
    } catch (err) {
        appendLog(`[系统] ❌ 加载网络失败: ${err.message}`);
    }
}

async function searchMovies() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;
    appendLog(`[系统] 🔍 正在豆瓣搜索：${query}...`);
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
        grid.innerHTML = `<div style="grid-column: span 8; text-align:center; color:#64748b; padding:40px;">暂无筛选资源或请求受限</div>`;
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
                <a href="${m.url}" target="_blank" class="douban-link" onclick="event.stopPropagation()">🔗 详情</a>
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
        chBadge.textContent = '检测超时';
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
        }
    } catch (err) {
        console.error("加载频道失败", err);
    }
}

function renderChannels() {
    const container = document.getElementById('channel-list-box');
    if (!container) return;
    container.innerHTML = '';
    if (channelList.length === 0) {
        container.innerHTML = `<div style="text-align:center; color:#64748b; font-size:12px; padding:10px;">暂无设定频道</div>`;
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
        alert('请输入频道名称与 ID！');
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

async function saveConfig() {
    const cookie = document.getElementById('quark-cookie-input').value.trim();
    const defaultFid = document.getElementById('folder-id-input').value.trim() || '0';

    localStorage.setItem('quark_cookie', cookie);
    localStorage.setItem('target_folder_id', defaultFid);

    localStorage.setItem('folder_movie', document.getElementById('folder-movie-input').value.trim());
    localStorage.setItem('folder_tv', document.getElementById('folder-tv-input').value.trim());
    localStorage.setItem('folder_show', document.getElementById('folder-show-input').value.trim());
    localStorage.setItem('folder_anime', document.getElementById('folder-anime-input').value.trim());

    localStorage.setItem('openlist_url', document.getElementById('openlist-url-input').value.trim());
    localStorage.setItem('quark_app_url', document.getElementById('quark-app-input').value.trim() || 'quark://');

    try {
        await fetch('/api/channels', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channels: channelList })
        });
        alert('配置成功保存！');
        closeConfigModal();
        refreshStatus();
    } catch (err) {
        alert('保存失败: ' + err.message);
    }
}

function openConfigModal() { 
    document.getElementById('config-modal').style.display = 'flex'; 
    fetchChannels();
}

function closeConfigModal() { document.getElementById('config-modal').style.display = 'none'; }

function populateFolderSelectOptions() {
    const select = document.getElementById('sub-folder-select');
    if (!select) return;
    select.innerHTML = '';

    const defaultFid = localStorage.getItem('target_folder_id') || '0';
    const folderTv = localStorage.getItem('folder_tv') || '';

    const options = [
        { label: `📺 电视剧专属目录 (${folderTv || '默认'})`, val: folderTv || defaultFid },
        { label: `📁 默认目录 (${defaultFid})`, val: defaultFid }
    ];

    options.forEach(opt => {
        const el = document.createElement('option');
        el.value = opt.val;
        el.textContent = opt.label;
        select.appendChild(el);
    });
}

function openSubModal() {
    populateFolderSelectOptions();
    document.getElementById('sub-modal').style.display = 'flex';
    fetchSubscriptions();
}
function closeSubModal() { document.getElementById('sub-modal').style.display = 'none'; }

function subscribeSelected() {
    if (selectedMovies.size === 0) {
        alert('请先在页面上勾选你需要自动追更的剧集或动漫！');
        return;
    }
    const targets = Array.from(selectedMovies);
    const title = targets[0];

    openSubModal();
    document.getElementById('sub-title-input').value = title;
    document.getElementById('sub-pwd-input').value = '';
    autoSearchSubLink();
}

async function autoSearchSubLink() {
    const title = document.getElementById('sub-title-input').value.trim();
    if (!title) return;

    const pwdInput = document.getElementById('sub-pwd-input');
    pwdInput.value = '🔍 正在 TG 检索链接...';

    const cookie = localStorage.getItem('quark_cookie') || '';
    try {
        const res = await fetch('/api/search-link-for-sub', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, cookie })
        });

        const data = await res.json();
        if (data.success && data.pwd_id) {
            pwdInput.value = data.pwd_id;
        } else {
            pwdInput.value = '';
            alert(data.message || '未在频道找到对应资源，请手动填写');
        }
    } catch (err) {
        pwdInput.value = '';
        alert('检索异常: ' + err.message);
    }
}

async function fetchSubscriptions() {
    try {
        const res = await fetch('/api/subscriptions');
        const data = await res.json();
        if (data.success) {
            const box = document.getElementById('sub-list-box');
            if (!box) return;
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
                        <b style="color:#60a5fa;">${sub.title}</b> 
                        <span style="color:#38bdf8; font-size:11px;">[ID: ${sub.pwd_id || '未知'}]</span>
                        <span style="color:#f59e0b; font-size:11px;">(跳过前 ${sub.start_ep || 0} 集 | 已存 ${sub.saved_episodes.length} 集)</span>
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
    } catch (err) {
        console.error("加载订阅失败", err);
    }
}

async function addSubscription() {
    const title = document.getElementById('sub-title-input').value.trim();
    const pwdId = document.getElementById('sub-pwd-input').value.trim();
    const targetFid = document.getElementById('sub-folder-select').value || '0';
    const intervalHours = document.getElementById('sub-interval-input').value;
    const startEp = document.getElementById('sub-start-ep-input').value || 0;

    if (!title || !pwdId) {
        alert('请输入剧集名称和夸克链接 ID！');
        return;
    }

    const cookie = localStorage.getItem('quark_cookie') || '';
    await fetch('/api/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            title, 
            pwd_id: pwdId, 
            target_fid: targetFid, 
            interval_hours: intervalHours,
            start_ep: parseInt(startEp)
        })
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
            appendLog(`\n❌ 服务异常 (${response.status}): ${text.substring(0, 100)}`);
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
    } catch (err) {
        appendLog(`\n❌ 转存网络请求异常: ${err.message}`);
    }
}
