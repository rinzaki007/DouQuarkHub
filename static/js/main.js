let currentTab = 'movie';
let movieList = [];
let selectedMovies = new Set();
let logAutoClearTimer = null;
let channelList = [];

window.onload = () => {
    loadConfig();
    fetchMovies('movie');
    fetchChannels();
};

function loadConfig() {
    document.getElementById('quark-cookie-input').value = localStorage.getItem('quark_cookie') || '';
    document.getElementById('folder-id-input').value = localStorage.getItem('target_folder_id') || '0';
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
    container.innerHTML = '';
    if (channelList.length === 0) {
        container.innerHTML = `<div style="text-align:center; color:#64748b; font-size:12px; padding:8px;">暂无设定频道</div>`;
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

// 📥 批量导入 JSON 频道核心函数
function importChannelsJson() {
    const jsonStr = prompt("请粘贴你的频道 JSON 数据（数组格式）：", '[{"name": "示例频道", "id": "example_channel"}]');
    if (!jsonStr) return;
    
    try {
        const parsed = JSON.parse(jsonStr);
        if (!Array.isArray(parsed)) {
            alert("导入失败：JSON 格式错误，必须是以方括号包裹的数组 [...]");
            return;
        }

        let addedCount = 0;
        parsed.forEach(item => {
            // 兼容兼容 name/title，id/channel_id 字段
            const name = item.name || item.title || "";
            const id = item.id || item.channel_id || "";
            if (name && id) {
                // 自动去重
                if (!channelList.some(c => c.id === id)) {
                    channelList.push({ name, id });
                    addedCount++;
                }
            }
        });

        renderChannels();
        alert(`成功导入 ${addedCount} 个新频道！\n\n请不要忘记点击配置弹窗右下角的“💾 保存配置”按钮！`);
    } catch (err) {
        alert("解析 JSON 失败，请检查格式是否为标准 JSON！\n错误细节: " + err.message);
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
        alert('所有配置与频道已成功保存！');
        closeConfigModal();
    } catch (err) {
        alert('保存频道配置失败: ' + err.message);
    }
}

function openConfigModal() { document.getElementById('config-modal').style.display = 'flex'; }
function closeConfigModal() { document.getElementById('config-modal').style.display = 'none'; }

async function fetchMovies(type) {
    appendLog(`[系统] 正在获取豆瓣【${type === 'movie' ? '热门电影' : '热门电视剧'}】列表...`);
    try {
        const res = await fetch(`/api/get-movies?type=${type}`);
        const data = await res.json();
        if (data.success) {
            movieList = data.movies;
            renderGrid();
        }
    } catch (err) {
        appendLog(`[系统] ❌ 获取影视失败: ${err.message}`);
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

function switchTab(type) {
    currentTab = type;
    document.getElementById('tab-movie').classList.toggle('active', type === 'movie');
    document.getElementById('tab-tv').classList.toggle('active', type === 'tv');
    fetchMovies(type);
}

function renderGrid() {
    const grid = document.getElementById('movie-grid');
    grid.innerHTML = '';
    movieList.forEach(m => {
        const isSelected = selectedMovies.has(m.title);
        const card = document.createElement('div');
        card.className = `movie-card ${isSelected ? 'selected' : ''}`;
        card.onclick = () => toggleSelect(m.title, card);

        const coverSrc = m.cover ? `/api/proxy-img?url=${encodeURIComponent(m.cover)}` : '';

        card.innerHTML = `
            <div class="cover-box">
                <img src="${coverSrc}" alt="${m.title}" loading="lazy">
                ${m.rate ? `<div class="rate-tag">${m.rate}</div>` : ''}
                <div class="check-box">${isSelected ? '✓' : ''}</div>
            </div>
            <div class="movie-title">${m.title}</div>
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
    document.getElementById('log-body').textContent = '系统就绪，等待任务触发...';
    if (logAutoClearTimer) {
        clearTimeout(logAutoClearTimer);
        logAutoClearTimer = null;
    }
}

async function startBatchTransfer() {
    if (selectedMovies.size === 0) {
        alert('请先勾选需要转存的影视！');
        return;
    }

    const cookie = localStorage.getItem('quark_cookie') || '';
    const folderId = localStorage.getItem('target_folder_id') || '0';

    if (!cookie) {
        alert('请先点击右上角“配置设置”填入夸克 Cookie！');
        openConfigModal();
        return;
    }

    if (logAutoClearTimer) {
        clearTimeout(logAutoClearTimer);
        logAutoClearTimer = null;
    }

    clearLog();
    const targets = Array.from(selectedMovies);
    appendLog(`[系统] 🚀 开始处理批量转存，共 ${targets.length} 个目标...`);

    try {
        const res = await fetch('/api/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movies: targets,
                cookie: cookie,
                folderId: folderId
            })
        });

        const data = await res.json();
        if (data.success) {
            for (const [movieName, logs] of Object.entries(data.results)) {
                appendLog(`\n--- [${movieName}] ---`);
                logs.forEach(l => appendLog(l));
            }
            appendLog(`\n✨ 批量任务执行完毕！(日志将在 20 秒后自动清空)`);

            logAutoClearTimer = setTimeout(() => {
                clearLog();
            }, 20000);

        } else {
            appendLog(`\n❌ 转存请求异常: ${data.message}`);
        }
    } catch (err) {
        appendLog(`\n❌ 网络或者服务对接错误: ${err.message}`);
    }
}
