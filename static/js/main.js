let currentCategory = '电影';
let activeFilters = { sort: 'U', genre: '', country: '', year: '' };
let movieList = [];
let selectedMovies = new Set();

window.onload = () => {
    fetchMovies();
    refreshHomeStatus();
    initScrollCollapseFilter();
};

// 🎯 刷新首页顶栏的夸克 Cookie 与 TG 频道连通状态
async function refreshHomeStatus() {
    const cookie = localStorage.getItem('quark_cookie') || '';
    const badge = document.getElementById('quark-status-badge');
    if (badge) {
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
            } catch (e) {
                badge.className = 'badge badge-danger';
                badge.textContent = '异常';
            }
        } else {
            badge.className = 'badge badge-danger';
            badge.textContent = '未配置';
        }
    }

    const chBadge = document.getElementById('channel-status-badge');
    if (chBadge) {
        try {
            const chRes = await fetch('/api/check-channels');
            const chData = await chRes.json();
            if (chData.success) {
                chBadge.className = 'badge badge-success';
                chBadge.textContent = `🟢 ${chData.valid_count}/${chData.total} 联通`;
            }
        } catch (e) {
            chBadge.className = 'badge badge-danger';
            chBadge.textContent = '超时';
        }
    }
}

// 🎯 监听海报网格滚动：向下滚动自动收起筛选栏，回顶自动展开
function initScrollCollapseFilter() {
    const gridContainer = document.getElementById('movie-grid-container');
    const filterPanel = document.getElementById('filter-panel');
    if (!gridContainer || !filterPanel) return;

    let lastScrollTop = 0;
    gridContainer.addEventListener('scroll', () => {
        const currentScroll = gridContainer.scrollTop;
        if (currentScroll > 20 && currentScroll > lastScrollTop) {
            filterPanel.classList.add('collapsed');
        } else if (currentScroll < 10) {
            filterPanel.classList.remove('collapsed');
        }
        lastScrollTop = currentScroll;
    });
}

// 🎯 首页日志抽屉控制
function toggleLogDrawer() {
    const drawer = document.getElementById('log-drawer');
    if (drawer) {
        drawer.classList.toggle('open');
    }
}

function clearHomeLog() {
    const logBody = document.getElementById('log-body');
    if (logBody) {
        logBody.textContent = '日志已清空...';
    }
}

function appendLog(text) {
    const logBody = document.getElementById('log-body');
    if (logBody) {
        logBody.textContent += (logBody.textContent ? '\n' : '') + text;
        logBody.scrollTop = logBody.scrollHeight;
    }
}

// 🎯 切换分类与筛选条件
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
    el.parentElement.querySelectorAll('.filter-item').forEach(i => i.classList.remove('active'));
    el.classList.add('active');
    fetchMovies();
}

// 🎯 获取与渲染豆瓣影视海报网格
async function fetchMovies() {
    const params = new URLSearchParams({ tag: currentCategory, ...activeFilters });
    try {
        const res = await fetch(`/api/get-movies?${params.toString()}`);
        const data = await res.json();
        if (data.success) {
            movieList = data.movies;
            renderGrid();
        }
    } catch (err) { console.error(err); }
}

async function searchMovies() {
    const q = document.getElementById('search-input').value.trim();
    if (!q) return;
    try {
        const res = await fetch(`/api/search-douban?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (data.success) {
            movieList = data.movies;
            renderGrid();
        }
    } catch (err) { console.error(err); }
}

function renderGrid() {
    const grid = document.getElementById('movie-grid');
    if (!grid) return;
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
                <div class="rate-tag">${m.rate}</div>
                <div class="check-box">${isSelected ? '✓' : ''}</div>
            </div>
            <div class="card-info">
                <div class="movie-title">${m.title}</div>
            </div>
        `;
        grid.appendChild(card);
    });
    const countEl = document.getElementById('selected-count');
    if (countEl) countEl.textContent = selectedMovies.size;
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
    const countEl = document.getElementById('selected-count');
    if (countEl) countEl.textContent = selectedMovies.size;
}

function selectAll() { movieList.forEach(m => selectedMovies.add(m.title)); renderGrid(); }
function clearSelection() { selectedMovies.clear(); renderGrid(); }

function openOpenList() {
    const url = localStorage.getItem('openlist_url');
    if (!url) { alert('请先前往【后台管理】设置 OpenList 页面地址！'); return; }
    window.open(url, '_blank');
}

function openQuarkApp() {
    window.open(localStorage.getItem('quark_app_url') || 'quark://', '_blank');
}

// 🎯 动态组装追剧弹窗里的目录下拉列表（包含电影、电视剧、综艺、动漫四大专属目录与默认全局目录）
function populateFolderSelectOptions() {
    const select = document.getElementById('sub-folder-select');
    if (!select) return;
    select.innerHTML = '';

    const defaultFid = localStorage.getItem('target_folder_id') || '0';
    const folderMovie = localStorage.getItem('folder_movie') || '';
    const folderTv = localStorage.getItem('folder_tv') || '';
    const folderShow = localStorage.getItem('folder_show') || '';
    const folderAnime = localStorage.getItem('folder_anime') || '';

    const options = [
        { label: `📁 默认全局目录 (${defaultFid})`, val: defaultFid }
    ];

    if (folderTv) options.unshift({ label: `📺 电视剧专属目录 (${folderTv})`, val: folderTv });
    if (folderAnime) options.unshift({ label: `🎨 动漫专属目录 (${folderAnime})`, val: folderAnime });
    if (folderShow) options.unshift({ label: `🎤 综艺专属目录 (${folderShow})`, val: folderShow });
    if (folderMovie) options.unshift({ label: `🎬 电影专属目录 (${folderMovie})`, val: folderMovie });

    options.forEach(opt => {
        const el = document.createElement('option');
        el.value = opt.val;
        el.textContent = opt.label;
        select.appendChild(el);
    });
}

// 🎯 触发一键追剧弹窗
function subscribeSelected() {
    if (selectedMovies.size === 0) { alert('请先勾选影视！'); return; }
    const title = Array.from(selectedMovies)[0];
    
    // 打开弹窗前重新组装下拉框，解决下拉框空白问题
    populateFolderSelectOptions();
    
    const modal = document.getElementById('sub-modal');
    if (modal) modal.style.display = 'flex';
    const input = document.getElementById('sub-title-input');
    if (input) input.value = title;
    
    autoSearchSubLink();
}

function closeSubModal() {
    const modal = document.getElementById('sub-modal');
    if (modal) modal.style.display = 'none';
}

async function autoSearchSubLink() {
    const input = document.getElementById('sub-title-input');
    if (!input) return;
    const title = input.value.trim();
    const cookie = localStorage.getItem('quark_cookie') || '';
    const pwdInput = document.getElementById('sub-pwd-input');
    if (pwdInput) pwdInput.value = '🔍 检索中...';
    
    try {
        const res = await fetch('/api/search-link-for-sub', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title, cookie})
        });
        const data = await res.json();
        if (data.success && data.pwd_id) {
            if (pwdInput) pwdInput.value = data.pwd_id;
        } else {
            if (pwdInput) pwdInput.value = '';
        }
    } catch (err) {
        if (pwdInput) pwdInput.value = '';
    }
}

async function addSubscriptionFromModal() {
    const title = document.getElementById('sub-title-input').value.trim();
    const pwdId = document.getElementById('sub-pwd-input').value.trim();
    const targetFid = document.getElementById('sub-folder-select').value || '0';
    const startEp = document.getElementById('sub-start-ep-input').value || 0;
    const cookie = localStorage.getItem('quark_cookie') || '';

    if (!title || !pwdId) { alert('请补充名称和夸克短码'); return; }

    try {
        const res = await fetch('/api/subscriptions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                title, 
                pwd_id: pwdId, 
                target_fid: targetFid,
                start_ep: parseInt(startEp),
                cookie
            })
        });
        const data = await res.json();
        if (data.success) {
            alert('追剧任务订阅成功！');
            closeSubModal();
        } else {
            alert('订阅失败: ' + (data.message || '未知错误'));
        }
    } catch (err) {
        alert('请求异常: ' + err.message);
    }
}

// 🎯 根据分类查找对应的专属存储目录 (电影/电视剧/综艺/动漫)，未配置则自动使用全局默认 FID
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

// 🎯 点击批量转存：自动展开首页底部日志抽屉，并实时输出流式过程
async function startBatchTransfer() {
    if (selectedMovies.size === 0) { alert('请先勾选需要转存的影视！'); return; }
    const cookie = localStorage.getItem('quark_cookie') || '';
    if (!cookie) { alert('请先在后台填入夸克 Cookie！'); return; }

    // 自动打开底部日志抽屉
    const drawer = document.getElementById('log-drawer');
    if (drawer) drawer.classList.add('open');
    
    const logBody = document.getElementById('log-body');
    if (logBody) logBody.textContent = '';

    const targets = Array.from(selectedMovies);
    const targetFolderId = getTargetFolderId();
    
    appendLog(`[系统] 🚀 开始处理批量转存 [分类: ${currentCategory}]，共 ${targets.length} 个目标...`);
    appendLog(`[系统] 📁 存储目标目录 FID: ${targetFolderId}`);

    try {
        const response = await fetch('/api/transfer', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
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
