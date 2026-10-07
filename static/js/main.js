let currentTag = '电影';
let currentSort = 'U';

let moviesData = [];
let selectedIndices = new Set();
let currentChaseSelectedCandidate = null;
let candidateModalState = null;
let chaseCandidateState = [];

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>\"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[char]));
}

async function apiFetch(url, options = {}) {
    const init = { ...options, credentials: 'same-origin' };
    const method = (init.method || 'GET').toUpperCase();
    const headers = new Headers(init.headers || {});
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        const token = document.querySelector('meta[name=csrf-token]')?.content;
        if (token) headers.set('X-CSRF-Token', token);
    }
    init.headers = headers;
    const response = await window.fetch(url, init);
    if (response.status === 401) {
        window.location.href = '/login';
    }
    return response;
}

let logTimerInterval = null;
let logTimerSeconds = 0;
let logAutoCloseTimer = null;

document.addEventListener("DOMContentLoaded", () => {
    fetchMovies();
    checkSystemHealth();
    loadCategoryOptions();
    applyGlassmorphismStyles();
});

function applyGlassmorphismStyles() {
    const topNavs = document.querySelectorAll('header, nav');
    topNavs.forEach(el => {
        el.classList.add('backdrop-blur-md', 'bg-slate-900/80', 'border-b', 'border-slate-800/80');
    });
}

async function loadCategoryOptions() {
    try {
        const resp = await apiFetch('/api/config');
        const res = await resp.json();
        if (res.success && res.config) {
            const cfg = res.config;
            const selects = document.querySelectorAll('.global-category-select');
            
            selects.forEach(selectEl => {
                selectEl.innerHTML = '';

                const defaultFid = cfg.default_fid || '0';
                const optDefault = document.createElement('option');
                optDefault.value = defaultFid;
                optDefault.textContent = `默认全局目录 (FID: ${defaultFid})`;
                selectEl.appendChild(optDefault);

                const catFids = cfg.category_fids || {};
                for (const [catName, fid] of Object.entries(catFids)) {
                    if (fid) {
                        const opt = document.createElement('option');
                        opt.value = fid;
                        opt.textContent = `${catName}专属目录 (FID: ${fid})`;
                        selectEl.appendChild(opt);
                    }
                }

                if (selectEl.id === 'batch-target-fid') {
                    let matched = false;
                    for (let opt of selectEl.options) {
                        if (opt.textContent.includes(currentTag + '专属')) {
                            opt.selected = true;
                            matched = true;
                            break;
                        }
                    }
                    if (!matched && selectEl.options.length > 0) {
                        selectEl.selectedIndex = 0;
                    }
                } else if (selectEl.id === 'chase-target-fid') {
                    for (let opt of selectEl.options) {
                        if (opt.textContent.includes('电视剧专属')) {
                            opt.selected = true;
                            break;
                        }
                    }
                }
            });
        }
    } catch (err) {
        console.error("加载后台目录配置失败:", err);
    }
}

async function checkSystemHealth() {
    try {
        const resp = await apiFetch('/api/check-cookie', { method: 'POST' });
        const res = await resp.json();
        const badge = document.getElementById('cookie-status-badge');
        if (res.valid) {
            badge.className = "px-2 py-1 text-xs rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800 flex items-center gap-1";
            badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-500"></span><span>Cookie 有效</span>`;
        } else {
            badge.className = "px-2 py-1 text-xs rounded bg-rose-950/80 text-rose-400 border border-rose-800 flex items-center gap-1";
            badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-500"></span><span>Cookie 失效</span>`;
        }
    } catch (err) {
        console.error("初始化检测异常", err);
    }

    try {
        const resp = await apiFetch('/api/check-channels');
        const res = await resp.json();
        if (res.success) {
            document.getElementById('channel-count-text').innerText = `频道 ${res.valid_count}/${res.total}`;
        }
    } catch (err) {
        console.error("频道检测异常", err);
    }
}

function changeTag(tag) {
    currentTag = tag;
    document.querySelectorAll('.nav-tag').forEach(btn => {
        btn.className = btn.dataset.tag === tag 
            ? 'nav-tag px-3.5 py-1.5 rounded text-sm font-medium transition bg-blue-600 text-white shadow-md'
            : 'nav-tag px-3.5 py-1.5 rounded text-sm font-medium transition bg-slate-800/80 text-slate-300 hover:bg-slate-700';
    });
    loadCategoryOptions();
    fetchMovies();
}

function changeSort(sort) {
    currentSort = sort;
    document.querySelectorAll('.sort-tag').forEach(btn => {
        if (btn.dataset.sort === sort) {
            btn.className = "sort-tag px-3 py-1 rounded-md font-medium transition bg-blue-600 text-white shadow";
        } else {
            btn.className = "sort-tag px-3 py-1 rounded-md font-medium transition text-slate-400 hover:text-white";
        }
    });
    fetchMovies();
}

async function fetchMovies() {
    const loading = document.getElementById('loading');
    const grid = document.getElementById('movie-grid');
    loading.classList.remove('hidden');
    grid.classList.add('hidden');
    selectedIndices.clear();
    updateSelectedCount();

    try {
        const url = `/api/get-movies?tag=${encodeURIComponent(currentTag)}&sort=${currentSort}`;
        const resp = await apiFetch(url);
        const res = await resp.json();
        if (res.success) {
            moviesData = res.movies || [];
            renderGrid();
        }
    } catch (err) {
        console.error(err);
    } finally {
        loading.classList.add('hidden');
        grid.classList.remove('hidden');
    }
}

async function doSearch() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;

    const loading = document.getElementById('loading');
    const grid = document.getElementById('movie-grid');
    loading.classList.remove('hidden');
    grid.classList.add('hidden');
    selectedIndices.clear();
    updateSelectedCount();

    try {
        const resp = await apiFetch(`/api/search-douban?q=${encodeURIComponent(query)}`);
        const res = await resp.json();
        if (res.success) {
            moviesData = res.movies || [];
            renderGrid();
        }
    } catch (err) {
        console.error(err);
    } finally {
        loading.classList.add('hidden');
        grid.classList.remove('hidden');
    }
}


function renderGrid() {
    const grid = document.getElementById('movie-grid');
    grid.innerHTML = '';

    const noCoverImage = getNoCoverImage();

    moviesData.forEach((movie, idx) => {
        const coverUrl = movie.cover
            ? `/api/proxy-img?url=${encodeURIComponent(movie.cover)}`
            : noCoverImage;

        const isSelected = selectedIndices.has(idx);

        const card = document.createElement('div');

        card.className = `relative group bg-slate-900/90 backdrop-blur border ${
            isSelected
                ? 'border-blue-500 ring-1 ring-blue-500'
                : 'border-slate-800/80'
        } rounded-lg overflow-hidden card-shadow cursor-pointer transition`;

        card.onclick = (e) => {
            if (!e.target.closest('a')) {
                toggleSelect(idx);
            }
        };

        card.innerHTML = `
            <div class="aspect-[2/3] w-full bg-slate-950 relative overflow-hidden">
                <img
                    src="${coverUrl}"
                    alt="${escapeHtml(movie.title)}"
                    class="movie-cover w-full h-full object-cover group-hover:scale-105 transition duration-300"
                    loading="lazy"
                >

                <div class="absolute top-2 left-2 z-10">
                    <input
                        type="checkbox"
                        ${isSelected ? 'checked' : ''}
                        class="w-4 h-4 rounded border-slate-600 bg-slate-900/80 text-blue-600 focus:ring-0 pointer-events-none"
                    >
                </div>

                <div class="absolute top-2 right-2 bg-slate-900/90 backdrop-blur text-amber-400 text-[11px] font-bold px-1.5 py-0.5 rounded border border-slate-700/50">
                    ${escapeHtml(movie.rate || '暂无')}
                </div>
            </div>

            <div class="p-2.5">
                <div
                    class="font-medium text-xs text-slate-200 line-clamp-1 group-hover:text-blue-400 transition"
                    title="${escapeHtml(movie.title)}"
                >
                    ${escapeHtml(movie.title)}
                </div>

                <div class="mt-1.5 flex items-center justify-between text-[11px]">
                    <span class="text-slate-400 text-[10px]">
                        豆瓣影视
                    </span>

                    <a
                        href="${escapeHtml(movie.url)}"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 bg-blue-950/60 px-2 py-0.5 rounded border border-blue-900/50 transition"
                    >
                        <span>详情</span>
                        <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                    </a>
                </div>
            </div>
        `;

        const cover = card.querySelector('.movie-cover');

        if (cover) {
            cover.addEventListener('error', () => {
                if (cover.dataset.fallback === '1') {
                    return;
                }

                cover.dataset.fallback = '1';
                cover.src = noCoverImage;
            });
        }

        grid.appendChild(card);
    });
}

function toggleSelect(idx) {
    if (selectedIndices.has(idx)) selectedIndices.delete(idx);
    else selectedIndices.add(idx);
    updateSelectedCount();
    renderGrid();
}

function selectAll(select) {
    if (select) moviesData.forEach((_, idx) => selectedIndices.add(idx));
    else selectedIndices.clear();
    updateSelectedCount();
    renderGrid();
}

function updateSelectedCount() {
    const count = selectedIndices.size;
    document.getElementById('selected-count').innerText = count;

    const countSpan = document.getElementById('selected-count');
    let parentContainer = countSpan ? countSpan.closest('div') : null;

    if (parentContainer) {
        let previewTag = document.getElementById('selected-titles-preview');
        if (!previewTag) {
            previewTag = document.createElement('div');
            previewTag.id = 'selected-titles-preview';
            previewTag.className = 'flex items-center gap-1.5 overflow-hidden ml-2';
            parentContainer.appendChild(previewTag);
        }

        if (count === 0) {
            previewTag.innerHTML = '';
        } else {
            const selectedTitles = Array.from(selectedIndices).map(idx => moviesData[idx]?.title).filter(Boolean);
            const displayText = selectedTitles.length > 2
                ? `《${selectedTitles[0]}》等 ${selectedTitles.length} 部影片`
                : selectedTitles.map(t => `《${t}》`).join(', ');

            previewTag.innerHTML = `
                <span class="text-slate-400 text-xs shrink-0">已选:</span>
                <span class="px-2 py-0.5 bg-blue-950/80 text-blue-300 border border-blue-800/60 rounded text-xs font-medium truncate max-w-[280px]" title="${escapeHtml(selectedTitles.join(', '))}">
                    ${escapeHtml(displayText)}
                </span>
            `;
        }
    }
}

function toggleLogBox(show = true) {
    const panel = document.getElementById('log-panel');
    if (show) {
        panel.classList.remove('hidden'); // 不再强制覆盖不透明背景，保持 HTML 中的透明毛玻璃样式
    } else {
        panel.classList.add('hidden');
    }
}

function clearLog() {
    document.getElementById('log-box').innerHTML = '';
}

function startLogTimer() {
    logTimerSeconds = 0;
    if (logAutoCloseTimer) {
        clearInterval(logAutoCloseTimer);
        logAutoCloseTimer = null;
    }
    const badge = document.getElementById('log-timer-badge');
    badge.classList.remove('hidden');
    badge.innerText = `耗时: 0 秒`;
    if (logTimerInterval) clearInterval(logTimerInterval);
    logTimerInterval = setInterval(() => {
        logTimerSeconds++;
        badge.innerText = `耗时: ${logTimerSeconds} 秒`;
    }, 1000);
}

function stopLogTimer() {
    if (logTimerInterval) {
        clearInterval(logTimerInterval);
        logTimerInterval = null;
    }
}

function appendLogLine(text, type = 'info') {
    const logBox = document.getElementById('log-box');
    if (!text) return;
    const lines = text.split('\n');
    lines.forEach(line => {
        if (line.trim().length > 0) {
            const div = document.createElement('div');
            let colorClass = 'text-sky-400';
            if (type === 'success') colorClass = 'text-emerald-400 font-semibold';
            else if (type === 'warn') colorClass = 'text-amber-400';
            else if (type === 'error') colorClass = 'text-rose-400 font-bold';

            div.className = `py-0.5 font-mono leading-relaxed ${colorClass} border-b border-slate-900/40`;
            div.textContent = line;
            logBox.appendChild(div);
        }
    });
    logBox.scrollTop = logBox.scrollHeight;
}

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
        const resp = await apiFetch('/api/subscriptions');
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
                    <td class="px-3.5 py-3 font-medium text-slate-200">${escapeHtml(sub.title)}</td>
                    <td class="px-3.5 py-3 text-emerald-400">${escapeHtml(sub.channel || '默认频道')}</td>
                    <td class="px-3.5 py-3 text-slate-400">${sub.interval_hours} 小时</td>
                    <td class="px-3.5 py-3 text-slate-400">${escapeHtml(sub.last_check || '等待触发')}</td>
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
        const resp = await apiFetch('/api/subscriptions/run-now', {
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
        await apiFetch(`/api/subscriptions?id=${subId}`, { method: 'DELETE' });
        loadModalSubscriptions();
    } catch (err) {
        alert('删除失败');
    }
}

async function searchChaseCandidates() {
    const title = document.getElementById('chase-title-input').value.trim();
    if (!title) return alert('请输入要追剧的名称');

    const listContainer = document.getElementById('chase-candidates-list');
    listContainer.innerHTML = `<div class="text-xs text-slate-400 py-6 text-center"><i class="fa-solid fa-spinner fa-spin"></i> 正在全网并发检索频道...</div>`;
    document.getElementById('chase-candidates-container').classList.remove('hidden');

    try {
        const resp = await apiFetch('/api/search-candidates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movies: [{ title: title, tag: '电视剧' }],
            })
        });
        const res = await resp.json();
        if (!res.success) {
            listContainer.innerHTML = `<div class="text-xs text-rose-400 py-2">检索失败: ${escapeHtml(res.message)}</div>`;
            return;
        }

        const candidatesMap = res.candidates_map || {};
        const candidates = candidatesMap[title] || [];

        if (candidates.length === 0) {
            listContainer.innerHTML = `<div class="text-xs text-amber-400 py-4 text-center">未在任何配置频道中找到匹配资源，请检查片名是否正确。</div>`;
            return;
        }

        listContainer.innerHTML = '';
        chaseCandidateState = candidates;
        candidates.forEach((cand, idx) => {
            const fileNames = cand.files.map((f) => `
                <label class="flex items-center gap-2 py-1 text-xs text-slate-300 hover:text-white cursor-pointer">
                    <input type="checkbox" name="chase-file-item" value="${escapeHtml(f.fid)}" class="chase-file-cb rounded bg-slate-900 border-slate-700 text-purple-600 focus:ring-0">
                    <span class="font-mono">${escapeHtml(f.file_name)}</span>
                </label>
            `).join('');

            const itemDiv = document.createElement('div');
            itemDiv.className = 'bg-slate-950 border border-slate-800 rounded-lg p-4 space-y-3';
            itemDiv.innerHTML = `
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold text-emerald-400"><i class="fa-brands fa-telegram"></i> 频道: ${escapeHtml(cand.channel)}</span>
                    <button onclick='selectThisChaseCandidate(${idx}, this)' class="px-3.5 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded text-xs font-medium transition">
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
        listContainer.innerHTML = `<div class="text-xs text-rose-400 py-2">请求发生异常: ${escapeHtml(err.message)}</div>`;
    }
}

function selectThisChaseCandidate(index, btnElement) {
    const candidate = chaseCandidateState[index];
    if (!candidate) return;
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
        files: filteredFiles.map(({fid}) => ({fid})),
        interval_hours: intervalHours,
        target_fid: targetFid
    };

    try {
        const resp = await apiFetch('/api/subscriptions', {
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

async function batchTransfer() {
    if (selectedIndices.size === 0) return alert('请先选择至少一部影片');

    const selectedMovies = Array.from(selectedIndices).map(idx => {
        const item = moviesData[idx];
        return {
            title: item.title,
            tag: currentTag || '电影',
            cover: item.cover,
            url: item.url
        };
    });
    
    toggleLogBox(true);
    clearLog();
    startLogTimer();

    appendLogLine(`[任务发起] 🚀 准备开始并发多线程搜刮，共选中 ${selectedMovies.length} 部目标影片...`, 'info');
    selectedMovies.forEach(m => appendLogLine(`  -> 目标解析: 《${m.title}》 (${m.tag})`, 'info'));
    appendLogLine(`[网络交互] ⏳ 正在向后端发送检索请求，请耐心等待所有TG频道响应...`, 'warn');
    
    const startTime = Date.now();
    try {
        const response = await apiFetch('/api/search-candidates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movies: selectedMovies,
            })
        });

        const res = await response.json();
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        stopLogTimer();

        if (!res.success) {
            appendLogLine(`[系统错误] ❌ 搜刮失败 (耗时 ${elapsed}秒): ${res.message || '未知错误'}`, 'error');
            return;
        }

        appendLogLine(`[并发搜刮] ✅ 后端多线程检索顺利完成！总耗时: ${elapsed} 秒`, 'success');

        const candidatesMap = res.candidates_map || {};
        let totalFound = 0;

        for (const movie of selectedMovies) {
            const title = movie.title;
            const candidates = candidatesMap[title] || [];
            totalFound += candidates.length;

            if (candidates.length === 0) {
                appendLogLine(`[结果统计] ⚠️ 《${title}》：未能在任何配置的 TG 频道中检索到有效候选资源。`, 'warn');
            } else {
                appendLogLine(`[结果统计] 🎯 《${title}》：成功匹配到 ${candidates.length} 个可用版本。`, 'success');
                candidates.forEach((cand, idx) => {
                    appendLogLine(`    [源 ${idx + 1}] 频道名称: "${cand.channel}" | 夸克短码: ${escapeHtml(cand.pwd_id)} | 包含视频文件: ${cand.files.length} 个`, 'info');
                });
            }
        }

        appendLogLine(`[系统完成] 📦 全网检索汇总完毕：共找到 ${totalFound} 个候选资源，正在为您弹出交互选择窗口...`, 'success');
        openCandidateModal(selectedMovies, candidatesMap);
    } catch (err) {
        stopLogTimer();
        appendLogLine(`[异常捕获] ❌ 请求过程发生异常: ${err.message}`, 'error');
    }
}

function openCandidateModal(movies, candidatesMap) {
    candidateModalState = { movies, candidatesMap };
    toggleLogBox(false);
    loadCategoryOptions();

    const container = document.getElementById('candidate-content');
    container.innerHTML = '';
    
    movies.forEach((movie, mIdx) => {
        const title = movie.title;
        const candidates = candidatesMap[title] || [];

        const movieSection = document.createElement('div');
        movieSection.className = 'bg-slate-950 border border-slate-800 rounded-lg p-4 space-y-3';
        
        let html = `<div class="font-bold text-sm text-blue-400 flex items-center justify-between border-b border-slate-800 pb-2">
            <span>🎬 《${escapeHtml(title)}》</span>
            <span class="text-xs text-slate-400 font-normal">找到 ${candidates.length} 个候选源版本</span>
        </div>`;

        if (candidates.length === 0) {
            html += `<div class="text-xs text-rose-400 py-2">未能在配置的频道中找到匹配资源</div>`;
        } else {
            html += `<div class="space-y-3 mt-2">`;
            candidates.forEach((cand, cIdx) => {
                const fileCheckboxes = cand.files.map((f) => `
                    <label class="flex items-center gap-2 py-1 text-xs text-slate-300 hover:text-white cursor-pointer">
                        <input type="checkbox" name="batch-file-${mIdx}-${cIdx}" value="${escapeHtml(f.fid)}" class="rounded bg-slate-900 border-slate-700 text-blue-600 focus:ring-0">
                        <span class="font-mono">${escapeHtml(f.file_name)}</span>
                    </label>
                `).join('');

                html += `
                    <div class="bg-slate-900 border border-slate-800/80 rounded-lg p-3 text-xs space-y-2">
                        <div class="flex items-center justify-between text-slate-300">
                            <span class="font-semibold text-emerald-400"><i class="fa-brands fa-telegram"></i> 频道: ${escapeHtml(cand.channel)}</span>
                            <span class="text-slate-400 font-mono text-[11px]">短码: ${escapeHtml(cand.pwd_id)} | 包含 ${cand.files.length} 个文件</span>
                        </div>
                        <div class="bg-slate-950 p-2.5 rounded-md max-h-40 overflow-y-auto space-y-1 border border-slate-800">
                            <div class="text-[11px] text-slate-400 mb-1 font-medium">勾选您需要转存的具体文件：</div>
                            ${fileCheckboxes}
                        </div>
                        <div class="text-right pt-1">
                            <button onclick='confirmBatchTransferForCandidate(${mIdx}, ${cIdx})' class="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium transition shadow flex items-center gap-1 ml-auto">
                                <i class="fa-solid fa-cloud-arrow-down"></i> 确认转存勾选项
                            </button>
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        }
        movieSection.innerHTML = html;
        container.appendChild(movieSection);
    });

    document.getElementById('candidate-modal').classList.remove('hidden');
}

function closeCandidateModal() {
    document.getElementById('candidate-modal').classList.add('hidden');
}

function confirmBatchTransferForCandidate(mIdx, cIdx) {
    const movie = candidateModalState?.movies?.[mIdx];
    const title = movie?.title || "未知影片";
    const candidate = candidateModalState?.candidatesMap?.[title]?.[cIdx];
    if (!movie || !candidate) return alert('候选资源已失效，请重新搜索');
    const checkboxes = document.querySelectorAll(`input[name="batch-file-${mIdx}-${cIdx}"]:checked`);
    const selectedFids = Array.from(checkboxes).map(cb => cb.value);

    if (selectedFids.length === 0) {
        return alert('请至少勾选一个要转存的文件！');
    }

    const filteredFiles = candidate.files.filter(f => selectedFids.includes(f.fid));
    const customCandidate = { ...candidate, files: filteredFiles };
    const targetFid = document.getElementById('batch-target-fid').value;
    confirmTransferAndSave(movie, customCandidate, targetFid);
}

async function confirmTransferAndSave(movie, candidate, targetFid = '0') {
    closeCandidateModal();
    
    toggleLogBox(true);
    clearLog();
    startLogTimer();

    appendLogLine(`[转存启动] 📥 正在为《${movie.title}》创建专属云端文件夹并转存选中版本...`, 'info');
    appendLogLine(`  -> 目标频道: ${candidate.channel}`, 'info');
    appendLogLine(`  -> 提取短码: ${candidate.pwd_id}`, 'info');

    const startTime = Date.now();
    try {
        const response = await apiFetch('/api/transfer-selected', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                movie: movie,
                candidate: candidate,
                target_fid: targetFid
            })
        });

        const res = await response.json();
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        stopLogTimer();

        if (res.success) {
            appendLogLine(`[转存成功] 🎉 ${res.message} (耗时 ${elapsed}秒)`, 'success');
            appendLogLine(`[系统提示] ⏳ 转存成功，日志将在 3 秒后自动收起...`, 'info');
            
            if (logAutoCloseTimer) clearInterval(logAutoCloseTimer);
            let countdown = 3;
            const badge = document.getElementById('log-timer-badge');
            if (badge) badge.innerText = `成功 · ${countdown}s后收起`;
            
            logAutoCloseTimer = setInterval(() => {
                countdown--;
                if (badge) badge.innerText = `成功 · ${countdown}s后收起`;
                if (countdown <= 0) {
                    clearInterval(logAutoCloseTimer);
                    logAutoCloseTimer = null;
                    toggleLogBox(false);
                }
            }, 1000);
        } else {
            if (logAutoCloseTimer) {
                clearInterval(logAutoCloseTimer);
                logAutoCloseTimer = null;
            }
            appendLogLine(`[转存失败] ❌ ${res.message} (耗时 ${elapsed}秒)`, 'error');
            appendLogLine(`[系统提示] ⚠️ 转存发生错误，日志保持一直显示以便排查。`, 'warn');
        }
    } catch (err) {
        stopLogTimer();
        if (logAutoCloseTimer) {
            clearInterval(logAutoCloseTimer);
            logAutoCloseTimer = null;
        }
        appendLogLine(`[异常捕获] ❌ 转存请求发生异常: ${err.message}`, 'error');
        appendLogLine(`[系统提示] ⚠️ 发生异常，日志保持一直显示。`, 'warn');
    }
}
