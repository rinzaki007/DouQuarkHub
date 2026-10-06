let currentTag = '电影';
let currentSort = 'U';
let moviesData = [];
let selectedIndices = new Set();

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
        const resp = await fetch('/api/config');
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
        const localCookie = localStorage.getItem('quark_cookie') || '';
        const resp = await fetch('/api/check-cookie', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cookie: localCookie })
        });
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
        const resp = await fetch('/api/check-channels');
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
        const resp = await fetch(url);
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
        const resp = await fetch(`/api/search-douban?q=${encodeURIComponent(query)}`);
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

    moviesData.forEach((movie, idx) => {
        const coverUrl = movie.cover ? `/api/proxy-img?url=${encodeURIComponent(movie.cover)}` : 'https://via.placeholder.com/150x220?text=No+Cover';
        const isSelected = selectedIndices.has(idx);

        const card = document.createElement('div');
        card.className = `relative group bg-slate-900/90 backdrop-blur border ${isSelected ? 'border-blue-500 ring-1 ring-blue-500' : 'border-slate-800/80'} rounded-lg overflow-hidden card-shadow cursor-pointer transition`;
        card.onclick = (e) => {
            if (!e.target.closest('a')) {
                toggleSelect(idx);
            }
        };

        card.innerHTML = `
            <div class="aspect-[2/3] w-full bg-slate-950 relative overflow-hidden">
                <img src="${coverUrl}" alt="${movie.title}" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" loading="lazy">
                <div class="absolute top-2 left-2 z-10">
                    <input type="checkbox" ${isSelected ? 'checked' : ''} class="w-4 h-4 rounded border-slate-600 bg-slate-900/80 text-blue-600 focus:ring-0 pointer-events-none">
                </div>
                <div class="absolute top-2 right-2 bg-slate-900/90 backdrop-blur text-amber-400 text-[11px] font-bold px-1.5 py-0.5 rounded border border-slate-700/50">
                    ${movie.rate || '暂无'}
                </div>
            </div>
            <div class="p-2.5">
                <div class="font-medium text-xs text-slate-200 line-clamp-1 group-hover:text-blue-400 transition" title="${movie.title}">${movie.title}</div>
                <div class="mt-1.5 flex items-center justify-between text-[11px]">
                    <span class="text-slate-400 text-[10px]">豆瓣影视</span>
                    <a href="${movie.url}" target="_blank" class="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 bg-blue-950/60 px-2 py-0.5 rounded border border-blue-900/50 transition">
                        <span>详情</span>
                        <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                    </a>
                </div>
            </div>
        `;
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
                <span class="px-2 py-0.5 bg-blue-950/80 text-blue-300 border border-blue-800/60 rounded text-xs font-medium truncate max-w-[280px]" title="${selectedTitles.join(', ')}">
                    ${displayText}
                </span>
            `;
        }
    }
}
