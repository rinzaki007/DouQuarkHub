let currentCategory = '电影';
let activeFilters = { sort: 'U', genre: '', country: '', year: '' };
let movieList = [];
let selectedMovies = new Set();

window.onload = () => {
    fetchMovies();
    refreshHomeStatus();
    initScrollCollapseFilter();
};

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

function toggleLogDrawer() {
    const drawer = document.getElementById('log-drawer');
    if (drawer) drawer.classList.toggle('open');
}

function clearHomeLog() {
    const logBody = document.getElementById('log-body');
    if (logBody) logBody.textContent = '日志已清空...';
}

function appendLog(text) {
    const logBody = document.getElementById('log-body');
    if (logBody) {
        logBody.textContent += (logBody.textContent ? '\n' : '') + text;
        logBody.scrollTop = logBody.scrollHeight;
    }
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
    el.parentElement.querySelectorAll('.filter-item').forEach(i => i.classList.remove('active'));
    el.classList.add('active');
    fetchMovies();
}

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

    if (movieList.length === 0) {
        grid.innerHTML = `<div style="grid-column: 1 / -1; text-align:center; color:#64748b; padding:40px;">暂无满足条件的影视资源</div>`;
        return;
    }

    movieList.forEach(m => {
        const isSelected = selectedMovies.has(m.title);
        const card = document.createElement('div');
        card.className = `movie-card ${isSelected ? 'selected' : ''}`;
        card.onclick = () => toggleSelect(m.title, card);

        const coverSrc = m.cover ? `/api/proxy-img?url=${encodeURIComponent(m.cover)}` : '';
        const detailUrl = m.url || '#';

        card.innerHTML = `
            <div class="cover-box">
                <img src="${coverSrc}" alt="${m.title}" loading="lazy">
                <div class="rate-tag">${m.rate}</div>
                <div class="check-box">${isSelected ? '✓' : ''}</div>
            </div>
            <div class="card-info">
                <div class="movie-title" title="${m.title}">${m.title}</div>
                <a href="${detailUrl}" target="_blank" class="douban-link" onclick="event.stopPropagation()">🔗 详情</a>
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

function subscribeSelected() {
    if (selectedMovies.size === 0) { alert('请先勾选影视！'); return; }
    const title = Array.from(selectedMovies)[0];
    
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

// ==========================================
// 🎬 核心重构：第一阶段（搜刮候选并弹出交互窗口）
// ==========================================
async function startBatchTransfer() {
    if (selectedMovies.size === 0) { alert('请先勾选需要转存的影视！'); return; }
    const cookie = localStorage.getItem('quark_cookie') || '';
    if (!cookie) { alert('请先在后台填入夸克 Cookie！'); return; }

    const drawer = document.getElementById('log-drawer');
    if (drawer) drawer.classList.add('open');
    
    const logBody = document.getElementById('log-body');
    if (logBody) logBody.textContent = '';

    const targets = Array.from(selectedMovies);
    const selectedObjs = targets.map(title => movieList.find(m => m.title === title)).filter(Boolean).map(m => ({
        title: m.title,
        tag: currentCategory || '电影',
        cover: m.cover,
        url: m.url
    }));
    
    appendLog(`[系统] 🔍 正在各大 TG 频道中深度搜刮候选资源，请稍候...`);

    try {
        const response = await fetch('/api/search-candidates', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                movies: selectedObjs,
                cookie: cookie
            })
        });

        const res = await response.json();
        if (!res.success) {
            appendLog(`[系统] ❌ 搜刮失败: ${res.message || '未知错误'}`);
            return;
        }

        appendLog(`[系统] ✅ 搜刮完成，正在弹出候选资源选择窗口...`);
        showCandidateSelectionModal(selectedObjs, res.candidates_map || {});
    } catch (err) {
        appendLog(`[系统] ❌ 请求异常: ${err.message}`);
    }
}

// 📌 渲染候选资源交互选择弹窗
function showCandidateSelectionModal(movies, candidatesMap) {
    let existing = document.getElementById('custom-candidate-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'custom-candidate-modal';
    modal.style.cssText = "position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.7); z-index:9999; display:flex; justify-content:center; align-items:center;";

    let htmlContent = `
        <div style="background:#1e293b; color:#f8fafc; width:700px; max-height:85vh; border-radius:8px; padding:20px; overflow-y:auto; box-shadow:0 10px 25px rgba(0,0,0,0.5); border:1px solid #334155;">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:10px; margin-bottom:15px;">
                <h3 style="margin:0; font-size:18px; color:#38bdf8;"><i class="fa-solid fa-list-check"></i> 选择要转存的资源版本</h3>
                <button onclick="document.getElementById('custom-candidate-modal').remove()" style="background:none; border:none; color:#94a3b8; font-size:20px; cursor:pointer;">&times;</button>
            </div>
            <div>
    `;

    movies.forEach(movie => {
        const title = movie.title;
        const candidates = candidatesMap[title] || [];

        htmlContent += `<div style="margin-bottom:15px; background:#0f172a; padding:12px; border-radius:6px; border:1px solid #1e293b;">`;
        htmlContent += `<div style="font-weight:bold; color:#60a5fa; margin-bottom:8px;">🎬 《${title}》 (找到 ${candidates.length} 个候选源)</div>`;

        if (candidates.length === 0) {
            htmlContent += `<div style="color:#f43f5e; font-size:13px;">未能在配置的频道中找到匹配资源</div>`;
        } else {
            candidates.forEach((cand) => {
                const fileNames = cand.files.map(f => f.file_name).join('<br>');
                const movieStr = encodeURIComponent(JSON.stringify(movie));
                const candStr = encodeURIComponent(JSON.stringify(cand));

                htmlContent += `
                    <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:10px; margin-top:8px; font-size:13px;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:6px; color:#34d399;">
                            <span>🌐 频道: ${cand.channel}</span>
                            <span style="color:#94a3b8;">包含 ${cand.files.length} 个视频文件</span>
                        </div>
                        <div style="background:#020617; padding:8px; border-radius:4px; max-height:90px; overflow-y:auto; font-family:monospace; font-size:12px; color:#cbd5e1; margin-bottom:8px;">
                            ${fileNames}
                        </div>
                        <div style="text-align:right;">
                            <button onclick='executeConfirmedTransfer("${movieStr}", "${candStr}")' style="background:#059669; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer; font-weight:500;">
                                🚀 确认转存此版本
                            </button>
                        </div>
                    </div>
                `;
            });
        }
        htmlContent += `</div>`;
    });

    htmlContent += `
            </div>
            <div style="text-align:right; margin-top:15px; border-top:1px solid #334155; padding-top:10px;">
                <button onclick="document.getElementById('custom-candidate-modal').remove()" style="background:#475569; color:white; border:none; padding:6px 14px; border-radius:4px; cursor:pointer;">关闭</button>
            </div>
        </div>
    `;

    modal.innerHTML = htmlContent;
    document.body.appendChild(modal);
}

// ==========================================
// 🎯 核心重构：第二阶段（用户确认后执行指定转存）
// ==========================================
async function executeConfirmedTransfer(movieEncoded, candEncoded) {
    const modal = document.getElementById('custom-candidate-modal');
    if (modal) modal.remove();

    const movie = JSON.parse(decodeURIComponent(movieEncoded));
    const candidate = JSON.parse(decodeURIComponent(candEncoded));
    const cookie = localStorage.getItem('quark_cookie') || '';

    const drawer = document.getElementById('log-drawer');
    if (drawer) drawer.classList.add('open');
    
    appendLog(`[系统] 📥 正在为《${movie.title}》创建专属文件夹并转存选中版本...`);

    try {
        const response = await fetch('/api/transfer-selected', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movie: movie,
                candidate: candidate,
                cookie: cookie
            })
        });

        const res = await response.json();
        if (res.success) {
            appendLog(`[完成] 🎉 ${res.message}`);
        } else {
            appendLog(`[完成] ❌ 转存失败: ${res.message}`);
        }
    } catch (err) {
        appendLog(`[系统] ❌ 转存请求异常: ${err.message}`);
    }
}
