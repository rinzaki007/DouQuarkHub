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

window.onload = () => {
    loadConfig();
    refreshStatus();
    fetchMovies();
    fetchChannels();
};

function loadConfig() {
    document.getElementById('quark-cookie-input').value = localStorage.getItem('quark_cookie') || '';
    document.getElementById('folder-id-input').value = localStorage.getItem('target_folder_id') || '0';
}

function refreshStatus() {
    checkQuarkStatus();
    checkChannelsHealth();
}

// 切换大类 (电影 / 电视剧 / 综艺 / 动漫)
function switchCategory(cat) {
    currentCategory = cat;
    ['电影', '电视剧', '综艺', '动漫'].forEach(c => {
        const btn = document.getElementById(`tab-${c}`);
        if (btn) btn.classList.toggle('active', c === cat);
    });
    fetchMovies();
}

// 设置组合筛选条件
function setFilter(type, value, el) {
    activeFilters[type] = value;
    
    // 更新按钮选中状态
    const container = el.parentElement;
    container.querySelectorAll('.filter-item').forEach(item => item.classList.remove('active'));
    el.classList.add('active');

    fetchMovies();
}

// 根据当前组合条件发起豆瓣数据请求
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
    document.getElementById('log-body').textContent = '系统就绪，等待触发转存任务...';
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
    const fid = document.getElementById('folder-id-input').value.trim() || '0';
    
    localStorage.setItem('quark_cookie', cookie);
    localStorage.setItem('target_folder_id', fid);

    try {
        await fetch('/api/channels', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channels: channelList })
        });
        alert('配置已保存！');
        closeConfigModal();
        refreshStatus();
    } catch (err) {
        alert('保存频道配置失败: ' + err.message);
    }
}

function openConfigModal() { document.getElementById('config-modal').style.display = 'flex'; }
function closeConfigModal() { document.getElementById('config-modal').style.display = 'none'; }

async function startBatchTransfer() {
    if (selectedMovies.size === 0) {
        alert('请先勾选需要转存的影视！');
        return;
    }

    const cookie = localStorage.getItem('quark_cookie') || '';
    const folderId = localStorage.getItem('target_folder_id') || '0';

    if (!cookie) {
        alert('请先填入夸克 Cookie！');
        openConfigModal();
        return;
    }

    document.getElementById('log-body').textContent = '';
    const targets = Array.from(selectedMovies);
    appendLog(`[系统] 🚀 开始处理本轮批量转存，共 ${targets.length} 个目标...`);

    try {
        const response = await fetch('/api/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movies: targets,
                cookie: cookie,
                folderId: folderId
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
    } catch (err) {
        appendLog(`\n❌ 网络请求异常: ${err.message}`);
    }
}
