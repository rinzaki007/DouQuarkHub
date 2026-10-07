/* MovieSync 主页面 JavaScript
 * 用途：负责豆瓣列表加载/渲染、搜索、选择影片、资源候选弹窗、白名单转存、日志、频道状态和自动追剧。
 * 维护说明：apiFetch() 统一携带同源 Cookie 与 CSRF；当前版本还提供 getNoCoverImage()，避免无海报时因缺少函数导致整页渲染中断。 */
let currentTag = '电影';
let currentSort = 'U';

let moviesData = [];
let selectedIndices = new Set();
let currentChaseSelectedCandidate = null;
let candidateModalState = null;
let chaseCandidateState = [];
let movieRequestSeq = 0;
let searchRequestSeq = 0;

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
    const requestId = ++movieRequestSeq;
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

        if (requestId !== movieRequestSeq) return;

        if (res.success) {
            moviesData = Array.isArray(res.movies) ? res.movies : [];
            renderGrid();
            updateEmptyState();
        } else if (requestId === movieRequestSeq) {
            showToast(res.message || '加载影片失败', 'error');
        }
    } catch (err) {
        if (requestId === movieRequestSeq) {
            console.error(err);
            showToast('影片加载失败，请稍后重试', 'error');
        }
    } finally {
        if (requestId === movieRequestSeq) {
            loading.classList.add('hidden');
            grid.classList.remove('hidden');
        }
    }
}

async function doSearch() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;

    const requestId = ++searchRequestSeq;
    const loading = document.getElementById('loading');
    const grid = document.getElementById('movie-grid');
    loading.classList.remove('hidden');
    grid.classList.add('hidden');
    selectedIndices.clear();
    updateSelectedCount();

    try {
        const resp = await apiFetch(`/api/search-douban?q=${encodeURIComponent(query)}`);
        const res = await resp.json();

        if (requestId !== searchRequestSeq) return;

        if (res.success) {
            moviesData = Array.isArray(res.movies) ? res.movies : [];
            renderGrid();
            updateEmptyState();
        } else if (requestId === searchRequestSeq) {
            showToast(res.message || '搜索失败', 'error');
        }
    } catch (err) {
        if (requestId === searchRequestSeq) {
            console.error(err);
            showToast('搜索失败，请稍后重试', 'error');
        }
    } finally {
        if (requestId === searchRequestSeq) {
            loading.classList.add('hidden');
            grid.classList.remove('hidden');
        }
    }
}


function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    const icon = type === 'error'
        ? 'fa-circle-exclamation'
        : type === 'success'
            ? 'fa-circle-check'
            : 'fa-circle-info';

    toast.className = 'pointer-events-auto flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/95 px-4 py-3 text-xs text-slate-200 shadow-2xl backdrop-blur';
    toast.innerHTML = `<i class="fa-solid ${icon}"></i><span></span>`;
    toast.querySelector('span').textContent = String(message || '');
    container.appendChild(toast);

    window.setTimeout(() => {
        toast.classList.add('opacity-0');
        toast.style.transition = 'opacity 180ms ease';
        window.setTimeout(() => toast.remove(), 220);
    }, 3200);
}

function updateEmptyState() {
    const grid = document.getElementById('movie-grid');
    const empty = document.getElementById('empty-state');
    if (!grid || !empty) return;

    const hasMovies = Array.isArray(moviesData) && moviesData.length > 0;
    empty.classList.toggle('hidden', hasMovies);
    grid.classList.toggle('hidden', !hasMovies);
}

function getNoCoverImage() {
    const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 600">
            <rect width="400" height="600" fill="#020617"/>
            <rect x="90" y="150" width="220" height="250" rx="16" fill="#1e293b"/>
            <path d="M120 350l55-65 45 50 35-40 45 55" fill="none" stroke="#475569" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="175" cy="225" r="22" fill="#475569"/>
            <text x="200" y="455" text-anchor="middle" fill="#64748b" font-size="24" font-family="Arial, sans-serif">No Poster</text>
        </svg>
    `;
    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
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
            if (!e.target.closest('a, input, button')) {
                openMovieDetail(idx);
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

let activeMovieDetailIndex = null;

function openMovieDetail(idx) {
    const movie = moviesData[idx];
    if (!movie) return;
    activeMovieDetailIndex = idx;
    const noCoverImage = getNoCoverImage();
    const cover = document.getElementById('movie-detail-cover');
    cover.src = movie.cover ? '/api/proxy-img?url=' + encodeURIComponent(movie.cover) : noCoverImage;
    cover.onerror = () => { cover.onerror = null; cover.src = noCoverImage; };
    document.getElementById('movie-detail-title').textContent = movie.title || '影视详情';
    document.getElementById('movie-detail-name').textContent = movie.title || '未命名影视';
    document.getElementById('movie-detail-meta').innerHTML =
        '<div><span class="text-slate-500">分类：</span>' + escapeHtml(movie.tag || currentTag) + '</div>' +
        '<div><span class="text-slate-500">评分：</span>' + escapeHtml(movie.rate || '暂无') + '</div>' +
        '<div><span class="text-slate-500">操作：</span>选择下面的资源转存或自动追剧</div>';
    const douban = document.getElementById('movie-detail-douban');
    douban.href = movie.url || '#';
    document.getElementById('movie-detail-drawer').classList.remove('hidden');
}

function closeMovieDetail() {
    document.getElementById('movie-detail-drawer')?.classList.add('hidden');
    activeMovieDetailIndex = null;
}

function movieDetailTransfer() {
    const movie = moviesData[activeMovieDetailIndex];
    if (!movie) return;
    closeMovieDetail();
    const selectedMovie = {
        title: movie.title,
        tag: movie.tag || currentTag || '电影',
        cover: movie.cover,
        url: movie.url
    };
    searchAndOpenCandidates([selectedMovie]);
}

function movieDetailChase() {
    const movie = moviesData[activeMovieDetailIndex];
    if (!movie) return;
    closeMovieDetail();
    const params = new URLSearchParams({
        title: movie.title || '',
        tag: movie.tag || currentTag || '电视剧',
        cover: movie.cover || ''
    });
    window.location.href = '/tasks?' + params.toString();
}

async function searchAndOpenCandidates(selectedMovies) {
    showToast('正在检索资源，请稍候…', 'info');
    try {
        const response = await apiFetch('/api/search-candidates', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({movies: selectedMovies})
        });
        const res = await response.json();
        if (!res.success) return showToast(res.message || '无法搜索资源', 'error');
        const candidatesMap = res.candidates_map || {};
        const totalFound = selectedMovies.reduce((sum, movie) => sum + ((candidatesMap[movie.title] || []).length), 0);
        if (!totalFound) return showToast('没有找到可用资源', 'warning');
        showToast('找到 ' + totalFound + ' 个可用资源版本', 'success');
        openCandidateModal(selectedMovies, candidatesMap);
    } catch (err) {
        showToast(err.message || '资源检索异常', 'error');
    }
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

async function batchTransfer() {
    if (selectedIndices.size === 0) return alert('请先选择至少一部影片');
    const selectedMovies = Array.from(selectedIndices).map(idx => {
        const item = moviesData[idx];
        return {title:item.title, tag:currentTag || '电影', cover:item.cover, url:item.url};
    });
    showToast('正在检索 ' + selectedMovies.length + ' 部影视的资源…', 'info');
    try {
        const response = await apiFetch('/api/search-candidates', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({movies:selectedMovies})
        });
        const res=await response.json();
        if(!res.success) return showToast(res.message || '资源检索失败','error');
        const candidatesMap=res.candidates_map || {};
        const totalFound=selectedMovies.reduce((sum,m)=>sum+((candidatesMap[m.title]||[]).length),0);
        if(!totalFound) return showToast('没有找到可用资源','warning');
        showToast('找到 '+totalFound+' 个可用资源版本','success');
        openCandidateModal(selectedMovies,candidatesMap);
    } catch(err) {
        showToast(err.message || '资源检索异常','error');
    }
}


function openCandidateModal(movies, candidatesMap) {
    candidateModalState = { movies, candidatesMap };
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
    try {
        const response = await apiFetch('/api/transfer-selected', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({movie, candidate, target_fid: targetFid})
        });
        const res = await response.json();
        if (!res.success) {
            showToast(res.message || '无法创建转存任务', 'error');
            return;
        }
        const taskId = res.task?.id;
        showTaskCreatedToast(movie?.title || '资源', taskId);
    } catch (err) {
        showToast('创建转存任务失败：' + (err.message || '未知错误'), 'error');
    }
}

function showTaskCreatedToast(title, taskId) {
    const box = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = 'pointer-events-auto rounded-xl border border-emerald-800/70 bg-slate-900/95 px-4 py-3 shadow-2xl';
    el.innerHTML =
        '<div class="flex items-start gap-3">' +
        '<div class="mt-0.5 text-emerald-400"><i class="fa-solid fa-circle-check"></i></div>' +
        '<div class="min-w-0 flex-1"><div class="text-xs font-semibold text-white">转存任务已创建</div>' +
        '<div class="mt-1 truncate text-[11px] text-slate-400">《' + escapeHtml(title) + '》已进入任务中心</div>' +
        '<div class="mt-2 flex gap-2">' +
        '<a href="/tasks" class="rounded-md bg-purple-600 px-2.5 py-1.5 text-[10px] font-medium text-white hover:bg-purple-500">查看任务</a>' +
        '<button onclick="this.closest(\'div.pointer-events-auto\')?.remove()" class="rounded-md border border-slate-700 px-2.5 py-1.5 text-[10px] text-slate-400">继续浏览</button>' +
        '</div></div></div>';
    box.appendChild(el);
    setTimeout(() => el.remove(), 8000);
}



