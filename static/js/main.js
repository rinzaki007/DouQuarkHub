let currentCategory = '电影';
let activeFilters = { sort: 'U', genre: '', country: '', year: '' };
let movieList = [];
let selectedMovies = new Set();

window.onload = () => {
    fetchMovies();
    initScrollCollapseFilter();
};

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
    document.getElementById('selected-count').textContent = selectedMovies.size;
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
    document.getElementById('selected-count').textContent = selectedMovies.size;
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

function subscribeSelected() {
    if (selectedMovies.size === 0) { alert('请先勾选影视！'); return; }
    const title = Array.from(selectedMovies)[0];
    document.getElementById('sub-modal').style.display = 'flex';
    document.getElementById('sub-title-input').value = title;
    autoSearchSubLink();
}

function closeSubModal() { document.getElementById('sub-modal').style.display = 'none'; }

async function autoSearchSubLink() {
    const title = document.getElementById('sub-title-input').value.trim();
    const cookie = localStorage.getItem('quark_cookie') || '';
    const pwdInput = document.getElementById('sub-pwd-input');
    pwdInput.value = '🔍 检索中...';
    try {
        const res = await fetch('/api/search-link-for-sub', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title, cookie})
        });
        const data = await res.json();
        if (data.success && data.pwd_id) pwdInput.value = data.pwd_id;
        else pwdInput.value = '';
    } catch (err) { pwdInput.value = ''; }
}

async function addSubscriptionFromModal() {
    const title = document.getElementById('sub-title-input').value.trim();
    const pwdId = document.getElementById('sub-pwd-input').value.trim();
    const cookie = localStorage.getItem('quark_cookie') || '';
    if (!title || !pwdId) { alert('请补充名称和夸克短码'); return; }
    await fetch('/api/subscriptions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title, pwd_id: pwdId, cookie})
    });
    alert('订阅关联成功！');
    closeSubModal();
}

async function startBatchTransfer() {
    if (selectedMovies.size === 0) { alert('请勾选目标'); return; }
    const cookie = localStorage.getItem('quark_cookie') || '';
    if (!cookie) { alert('请先在后台填入 Cookie！'); return; }
    const targets = Array.from(selectedMovies);
    const res = await fetch('/api/transfer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({movies: targets, cookie: cookie, folderId: localStorage.getItem('target_folder_id') || '0'})
    });
    alert('转存任务已提交！');
}
