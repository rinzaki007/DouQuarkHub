let tasks = [];
let taskFilter = 'all';
let selectedCandidate = null;

document.addEventListener('DOMContentLoaded', () => {
    loadTasks();
    loadTaskCategories();
    const presetTitle = new URLSearchParams(window.location.search).get('title');
    if (presetTitle) setTimeout(() => openAddTask(), 120);
});

async function apiFetchTask(url, options = {}) {
    const init = { ...options, credentials: 'same-origin' };
    const method = (init.method || 'GET').toUpperCase();
    const headers = new Headers(init.headers || {});
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        const token = document.querySelector('meta[name=csrf-token]')?.content;
        if (token) headers.set('X-CSRF-Token', token);
    }
    init.headers = headers;
    const response = await window.fetch(url, init);
    if (response.status === 401) window.location.href = '/login';
    return response;
}

function escapeTask(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function taskToast(message) {
    const box = document.getElementById('task-toast');
    const el = document.createElement('div');
    el.className = 'pointer-events-auto rounded-lg border border-slate-700 bg-slate-900/95 px-4 py-3 text-xs text-slate-200 shadow-2xl';
    el.textContent = String(message || '');
    box.appendChild(el);
    setTimeout(() => el.remove(), 3200);
}

async function loadTaskCategories() {
    try {
        const resp = await apiFetchTask('/api/cards/quark/config');
        const res = await resp.json();
        if (!res.success || !res.config) return;
        const select = document.getElementById('task-target-fid');
        select.innerHTML = '';
        const cfg = res.config;
        const option = document.createElement('option');
        option.value = cfg.default_fid || '0';
        option.textContent = '默认目录';
        select.appendChild(option);
        for (const [name, fid] of Object.entries(cfg.category_fids || {})) {
            if (!fid) continue;
            const item = document.createElement('option');
            item.value = fid;
            item.textContent = name + '目录';
            select.appendChild(item);
            if (name === '电视剧') item.selected = true;
        }
    } catch (err) {
        taskToast('目录配置加载失败');
    }
}

async function loadTasks() {
    const list = document.getElementById('task-list');
    try {
        const resp = await apiFetchTask('/api/tasks');
        const res = await resp.json();
        if (!res.success) throw new Error(res.message || '加载失败');
        tasks = Array.isArray(res.tasks) ? res.tasks : [];
        renderStats();
        renderTasks();
        renderHistory();
    } catch (err) {
        list.innerHTML = '<div class="p-10 text-center text-xs text-rose-400">任务加载失败，请刷新重试。</div>';
    }
}

function taskState(task) {
    if (task.pending_save_keys && task.pending_save_keys.length) return {key:'pending', label:'待确认转存', cls:'text-amber-300 bg-amber-950/50 border-amber-800'};
    if (task.status === 'running') return {key:'running', label:'执行中', cls:'text-purple-300 bg-purple-950/50 border-purple-800'};
    if (task.status === 'failed' || task.last_error) return {key:'error', label:'异常', cls:'text-rose-300 bg-rose-950/50 border-rose-800'};
    if (task.status === 'success') return {key:'success', label:'已完成', cls:'text-emerald-300 bg-emerald-950/50 border-emerald-800'};
    if (task.status === 'queued') return {key:'waiting', label:'排队中', cls:'text-blue-300 bg-blue-950/50 border-blue-800'};
    if (task.next_run_at && Number(task.next_run_at) <= Date.now()/1000) return {key:'soon', label:'即将检查', cls:'text-amber-300 bg-amber-950/50 border-amber-800'};
    return {key:'waiting', label:'等待检查', cls:'text-blue-300 bg-blue-950/50 border-blue-800'};
}

function formatNextRun(ts) {
    if (!ts) return '等待调度';
    const diff = Math.max(0, Math.round(Number(ts) - Date.now()/1000));
    if (diff < 60) return '不到 1 分钟';
    const hours = Math.floor(diff / 3600);
    const mins = Math.floor((diff % 3600) / 60);
    if (hours) return hours + ' 小时 ' + mins + ' 分钟后';
    return mins + ' 分钟后';
}

function renderStats() {
    const total = tasks.length;
    const error = tasks.filter(t => ['error','failed'].includes(t.status) || !!t.last_error).length;
    const waiting = tasks.filter(t => ['waiting','queued'].includes(t.status)).length;
    const soon = tasks.filter(t => ['soon','pending','running'].includes(taskState(t).key) || ['running','pending'].includes(t.status)).length;
    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-waiting').textContent = waiting;
    document.getElementById('stat-error').textContent = error;
    document.getElementById('stat-soon').textContent = soon;
}

function setFilter(filter) {
    taskFilter = filter;
    document.querySelectorAll('.task-filter').forEach(btn => {
        const active = btn.dataset.filter === filter;
        btn.className = active ? 'task-filter rounded-md bg-slate-700 px-3 py-1.5 text-slate-100' : 'task-filter rounded-md px-3 py-1.5 text-slate-400 hover:text-white';
    });
    renderTasks();
}

function renderTasks() {
    const list = document.getElementById('task-list');
    let visible = tasks;
    if (taskFilter === 'error') visible = tasks.filter(t => ['error','failed'].includes(t.status) || !!t.last_error);
    if (taskFilter === 'waiting') visible = tasks.filter(t => ['waiting','queued'].includes(t.status));
    if (taskFilter === 'running') visible = tasks.filter(t => ['running','pending'].includes(taskState(t).key) || t.status === 'running');
    if (!visible.length) {
        list.innerHTML = '<div class="p-12 text-center text-xs text-slate-500">暂无符合条件的任务。</div>';
        return;
    }
    list.innerHTML = '';
    visible.forEach(task => {
        const state = taskState(task);
        const progress = Math.max(0, Math.min(100, Number(task.progress || 0)));
        const retryable = task.type === 'transfer' && task.status === 'failed';
        const card = document.createElement('article');
        card.className = 'glass-panel m-2 rounded-2xl p-4 transition hover:border-slate-600';
        const phase = escapeTask(task.phase_label || task.message || '等待执行');
        const cover = task.cover ? '/api/proxy-img?url=' + encodeURIComponent(task.cover) : '';
        card.innerHTML =
            '<div class="flex gap-3">' +
            (cover ? '<img src="' + cover + '" class="h-20 w-14 shrink-0 rounded-lg object-cover bg-slate-950" onerror="this.style.display=\'none\'">' : '') +
            '<div class="min-w-0 flex-1">' +
            '<div class="flex flex-wrap items-center gap-2">' +
            '<h3 class="truncate text-sm font-semibold text-slate-100">' + escapeTask(task.title) + '</h3>' +
            '<span class="rounded-full border px-2 py-0.5 text-[10px] ' + state.cls + '">' + state.label + '</span>' +
            '<span class="rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5 text-[10px] text-slate-400">' + escapeTask(task.kind || '任务') + '</span>' +
            '</div>' +
            '<div class="mt-3 flex items-center gap-3"><div class="h-2 flex-1 overflow-hidden rounded-full bg-slate-800"><div class="h-full rounded-full bg-purple-500 transition-all" style="width:' + progress + '%"></div></div><span class="w-10 text-right text-[10px] text-slate-400">' + progress + '%</span></div>' +
            '<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">' +
            '<span class="text-slate-300">' + phase + '</span>' +
            '<span>成功 ' + Number(task.success_count || 0) + '</span><span>跳过 ' + Number(task.skipped_count || 0) + '</span><span>失败 ' + Number(task.failed_count || 0) + '</span>' +
            (task.total ? '<span>文件 ' + Number(task.total) + '</span>' : '') +
            '</div>' +
            '<div class="mt-2 text-[11px] ' + ((task.status === 'failed' || task.last_error) ? 'text-rose-400' : 'text-slate-500') + '">' + escapeTask(task.message || task.last_error || '') + '</div>' +
            '</div>' +
            '<div class="flex shrink-0 flex-wrap content-start justify-end gap-2">' +
            '<button data-action="detail" data-id="' + escapeTask(task.id) + '" class="rounded-xl border border-slate-700/70 bg-slate-950/55 px-3 py-2 text-[11px] text-slate-300 hover:bg-slate-800/80"><i class="fa-solid fa-circle-info mr-1"></i>详情</button>' +
            (task.type === 'subscription' ? '<button data-action="run-sub" data-id="' + escapeTask(task.subscription_id) + '" class="rounded-xl bg-purple-600/90 px-3 py-2 text-[11px] font-medium text-white shadow-lg shadow-purple-600/15 hover:bg-purple-500"><i class="fa-solid fa-play mr-1"></i>立即检查</button>' : '') +
            ((task.type === 'subscription' || task.status === 'success' || task.status === 'failed' || task.status === 'error') ? '<button data-action="delete" data-id="' + escapeTask(task.id) + '" class="rounded-xl border border-slate-700/70 bg-slate-950/55 px-3 py-2 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-rose-300"><i class="fa-solid fa-trash mr-1"></i>删除</button>' : '') +
            (retryable ? '<button data-action="retry" data-id="' + escapeTask(task.id) + '" class="rounded-xl border border-amber-800/70 bg-amber-950/35 px-3 py-2 text-[11px] text-amber-300 hover:bg-amber-900/60"><i class="fa-solid fa-rotate-right mr-1"></i>失败重试</button>' : '') +
            '</div></div>';
        list.appendChild(card);
    });
    list.querySelectorAll('[data-action="detail"]').forEach(btn => btn.onclick = () => openTaskDetail(btn.dataset.id));
    list.querySelectorAll('[data-action="run-sub"]').forEach(btn => btn.onclick = () => runSubscription(btn.dataset.id));
    list.querySelectorAll('[data-action="retry"]').forEach(btn => btn.onclick = () => retryTask(btn.dataset.id));
    list.querySelectorAll('[data-action="delete"]').forEach(btn => btn.onclick = () => deleteTask(btn.dataset.id));
}

async function openTaskDetail(id) {
    try {
        const resp = await apiFetchTask('/api/tasks/' + encodeURIComponent(id));
        const res = await resp.json();
        if (!res.success) throw new Error(res.message || '任务不存在');
        renderTaskDetail(res.task);
        document.getElementById('task-detail-drawer').classList.remove('hidden');
    } catch (err) {
        taskToast(err.message || '无法读取任务详情');
    }
}

function closeTaskDetail() {
    document.getElementById('task-detail-drawer')?.classList.add('hidden');
}

function renderTaskDetail(task) {
    const title = document.getElementById('detail-title');
    const body = document.getElementById('detail-body');
    const state = taskState(task);
    const progress = Math.max(0, Math.min(100, Number(task.progress || 0)));
    title.textContent = task.title || '任务详情';
    const phases = [
        ['validate','校验资源'],
        ['list_files','获取文件列表'],
        ['create_folder','准备目标文件夹'],
        ['transfer','提交夸克转存'],
        ['completed','转存完成']
    ];
    const phaseIndex = task.status === 'failed' ? -1 : phases.findIndex(x => x[0] === task.phase);
    body.innerHTML =
        '<div class="flex gap-4 rounded-2xl border border-slate-700/60 bg-slate-950/55 p-4 backdrop-blur-xl">' +
        (task.cover ? '<img src="/api/proxy-img?url=' + encodeURIComponent(task.cover) + '" class="h-32 w-24 shrink-0 rounded-xl object-cover bg-slate-900" onerror="this.style.display=\'none\'">' : '') +
        '<div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-2"><span class="rounded-full border px-2 py-0.5 text-[10px] ' + state.cls + '">' + state.label + '</span><span class="text-[11px] text-slate-500">' + escapeTask(task.kind || '任务') + '</span></div>' +
        '<div class="mt-3 text-2xl font-semibold text-white">' + progress + '%</div><div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-800"><div class="h-full rounded-full bg-purple-500" style="width:' + progress + '%"></div></div>' +
        '<div class="mt-2 text-[11px] text-slate-400">' + escapeTask(task.phase_label || task.message || '') + '</div></div></div>' +
        '<div class="rounded-2xl border border-slate-800 bg-slate-950 p-4"><div class="text-xs font-semibold text-slate-200">执行阶段</div><div class="mt-4 space-y-3">' +
        phases.map((p,i) => {
            const done = task.status === 'success' || (phaseIndex >= 0 && i < phaseIndex);
            const active = task.status === 'running' && i === phaseIndex;
            const failed = task.status === 'failed' && i === Math.max(0, phases.findIndex(x => x[0] === task.phase));
            const cls = done ? 'text-emerald-400' : active ? 'text-purple-300' : failed ? 'text-rose-400' : 'text-slate-600';
            const icon = done ? 'fa-circle-check' : failed ? 'fa-circle-xmark' : active ? 'fa-spinner fa-spin' : 'fa-circle';
            return '<div class="flex items-center gap-3 text-xs ' + cls + '"><i class="fa-solid ' + icon + ' w-4 text-center"></i><span>' + p[1] + '</span>' + (active ? '<span class="text-[10px] text-slate-500">处理中</span>' : '') + '</div>';
        }).join('') +
        '</div></div>' +
        '<div class="grid gap-3 sm:grid-cols-2">' +
        '<div class="rounded-xl border border-slate-800 bg-slate-950 p-4"><div class="text-[10px] text-slate-500">资源信息</div><div class="mt-2 space-y-1 text-[11px] text-slate-300"><div>频道：' + escapeTask(task.source_channel || '—') + '</div><div>分享码：<span class="font-mono">' + escapeTask(task.share_code || '—') + '</span></div><div>文件数：' + Number(task.total || 0) + '</div></div></div>' +
        '<div class="rounded-xl border border-slate-800 bg-slate-950 p-4"><div class="text-[10px] text-slate-500">执行统计</div><div class="mt-2 space-y-1 text-[11px] text-slate-300"><div>成功：' + Number(task.success_count || 0) + '</div><div>跳过：' + Number(task.skipped_count || 0) + '</div><div>失败：' + Number(task.failed_count || 0) + '</div></div></div>' +
        '</div>' +
        '<div class="rounded-xl border border-slate-800 bg-slate-950 p-4"><div class="text-xs font-semibold text-slate-200">当前状态</div><div class="mt-2 text-[11px] leading-5 ' + (task.status === 'failed' ? 'text-rose-400' : 'text-slate-400') + '">' + escapeTask(task.message || '') + '</div></div>' +
        '<details class="rounded-xl border border-slate-800 bg-slate-950 p-4"><summary class="cursor-pointer text-xs font-semibold text-slate-300">执行日志</summary><div class="mt-3 space-y-2">' +
        (task.events || []).map(e => '<div class="flex gap-3 text-[11px]"><span class="shrink-0 font-mono text-slate-600">' + new Date(Number(e.at || 0)*1000).toLocaleTimeString() + '</span><span class="' + (e.level === 'error' ? 'text-rose-400' : e.level === 'success' ? 'text-emerald-400' : 'text-slate-400') + '">' + escapeTask(e.message) + '</span></div>').join('') +
        '</div></details>' +
        (task.status === 'failed' && task.type === 'transfer' ? '<button onclick="retryTask(\'' + escapeTask(task.id) + '\'); closeTaskDetail()" class="w-full rounded-xl bg-amber-600 px-4 py-3 text-xs font-medium text-white hover:bg-amber-500"><i class="fa-solid fa-rotate-right mr-1"></i>失败重试</button>' : '');
}

function renderHistory() {
    const box = document.getElementById('history-list');
    if (!box) return;
    const rows = [];
    tasks.forEach(task => {
        (task.run_history || []).forEach(item => rows.push({
            ...item,
            title: task.title,
            kind: task.kind || '任务'
        }));
    });
    tasks.filter(t => t.type === 'transfer').forEach(task => {
        rows.push({
            at: task.updated_at || task.created_at,
            success: task.status === 'success',
            message: task.message || '',
            success_count: task.success_count || 0,
            failed_count: task.failed_count || 0,
            title: task.title,
            kind: task.kind || '普通转存'
        });
    });
    rows.sort((a,b) => Number(b.at || 0) - Number(a.at || 0));
    const recent = rows.slice(0, 20);
    if (!recent.length) {
        box.innerHTML = '<div class="p-10 text-center text-xs text-slate-500">暂无执行记录。</div>';
        return;
    }
    box.innerHTML = recent.map(item => {
        const time = item.at ? new Date(Number(item.at) * 1000).toLocaleString() : '未知时间';
        const cls = item.success ? 'text-emerald-400' : 'text-rose-400';
        const icon = item.success ? 'fa-circle-check' : 'fa-circle-xmark';
        return '<div class="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">' +
            '<div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><i class="fa-solid ' + icon + ' ' + cls + '"></i>' +
            '<span class="text-xs font-medium text-slate-200">' + escapeTask(item.title) + '</span>' +
            '<span class="text-[10px] text-slate-500">' + escapeTask(item.kind) + '</span></div>' +
            '<div class="mt-1 text-[11px] text-slate-500">' + escapeTask(item.message) + '</div></div>' +
            '<div class="shrink-0 text-[10px] text-slate-600">' + escapeTask(time) + '</div></div>';
    }).join('');
}

function openAddTask() {
    selectedCandidate = null;
    document.getElementById('task-submit').disabled = true;
    document.getElementById('task-submit').classList.add('opacity-40');
    document.getElementById('task-form-status').textContent = '';
    document.getElementById('task-candidates').classList.add('hidden');
    document.getElementById('task-candidate-list').innerHTML = '';
    document.getElementById('task-drawer').classList.remove('hidden');
    loadTaskCategories();
    const params = new URLSearchParams(window.location.search);
    const presetTitle = params.get('title') || '';
    if (presetTitle) document.getElementById('task-title').value = presetTitle;
    setTimeout(() => document.getElementById('task-title').focus(), 50);
}

function closeAddTask() {
    document.getElementById('task-drawer').classList.add('hidden');
}

function formatTaskSize(bytes) {
    const n = Number(bytes || 0);
    if (!n) return '未知大小';
    const units = ['B','KB','MB','GB','TB'];
    let value = n, index = 0;
    while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
    return (value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)) + ' ' + units[index];
}

async function searchTaskCandidates() {
    const title = document.getElementById('task-title').value.trim();
    if (!title) return taskToast('请输入剧名');
    const box = document.getElementById('task-candidate-list');
    document.getElementById('task-candidates').classList.remove('hidden');
    box.innerHTML = '<div class="rounded-xl border border-slate-800 bg-slate-950 p-6 text-center text-xs text-slate-500"><i class="fa-solid fa-spinner fa-spin mr-1"></i>正在并发检索频道…</div>';
    selectedCandidate = null;
    document.getElementById('task-submit').disabled = true;
    document.getElementById('task-submit').classList.add('opacity-40');
    try {
        const resp = await apiFetchTask('/api/search-candidates', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({movies:[{title:title,tag:'电视剧'}]})});
        const res = await resp.json();
        if (!res.success) throw new Error(res.message || '检索失败');
        const candidates = (res.candidates_map || {})[title] || [];
        if (!candidates.length) {
            box.innerHTML = '<div class="rounded-xl border border-amber-900/50 bg-amber-950/20 p-5 text-center text-xs text-amber-300">没有找到匹配资源，请换一个剧名或检查频道配置。</div>';
            return;
        }
        document.getElementById('candidate-hint').textContent = '找到 ' + candidates.length + ' 个可用源';
        box.innerHTML = '';
        candidates.forEach((candidate, index) => {
            const row = document.createElement('div');
            const files = Array.isArray(candidate.files) ? candidate.files : [];
            const resolutions = Object.keys(candidate.resolutions || {});
            const resolutionText = resolutions.length ? resolutions.join(' / ') : [...new Set(files.map(f => f.resolution).filter(Boolean))].join(' / ') || '未知';
            const totalSize = candidate.total_size_text || formatTaskSize(files.reduce((sum, f) => sum + Number(f.size || 0), 0));
            const validFids = files.map(file => String(file.fid || '').trim()).filter(Boolean);
            const selectedFids = new Set(validFids);
            row.className = 'rounded-2xl border border-slate-800 bg-slate-950/80 p-4 transition hover:border-slate-700';
            row.innerHTML =
                '<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div class="min-w-0">' +
                '<div class="flex flex-wrap items-center gap-2"><span class="inline-flex items-center gap-1.5 rounded-lg border border-sky-900/60 bg-sky-950/40 px-2 py-1 text-[11px] font-semibold text-sky-300"><i class="fa-brands fa-telegram"></i>' + escapeTask(candidate.channel) + '</span>' +
                '<span class="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[10px] text-slate-500">' + escapeTask(candidate.pwd_id) + '</span></div>' +
                '<div class="mt-3 flex flex-wrap gap-2"><span class="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] text-slate-400"><i class="fa-solid fa-film mr-1"></i>' + files.length + ' 个视频</span>' +
                '<span class="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] text-slate-400"><i class="fa-solid fa-hard-drive mr-1"></i>' + escapeTask(totalSize) + '</span>' +
                '<span class="rounded-lg border border-blue-900/60 bg-blue-950/30 px-2 py-1 text-[10px] text-blue-300"><i class="fa-solid fa-display mr-1"></i>' + escapeTask(resolutionText) + '</span></div></div>' +
                '<button data-candidate="' + index + '" class="candidate-select shrink-0 rounded-xl border border-purple-700 bg-purple-950/40 px-4 py-2.5 text-[11px] font-medium text-purple-200 hover:bg-purple-900/50">选择此源</button></div>' +
                '<div class="mt-2 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2">' +
                '<span class="text-[11px] text-slate-400">已选 <strong data-selected-count class="text-slate-200">' + validFids.length + '</strong> / ' + validFids.length + ' 集</span>' +
                '<button type="button" data-toggle-files class="text-[11px] text-purple-300 hover:text-purple-200">' + (validFids.length ? '取消全选' : '全选') + '</button>' +
                '</div>' +
                '<div class="mt-2 max-h-60 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/80 p-2 space-y-1">' +
                files.map((file, fileIndex) => {
                    const fid = String(file.fid || '').trim();
                    if (!fid) return '';
                    return '<label class="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 hover:bg-slate-800/70"><input type="checkbox" data-file-index="' + fileIndex + '" class="task-episode-checkbox h-4 w-4 rounded border-slate-600 bg-slate-950 text-purple-600 focus:ring-purple-500" checked><span class="min-w-0 flex-1 truncate text-xs text-slate-300">' + escapeTask(file.file_name) + '</span><span class="shrink-0 text-[10px] text-slate-500">' + escapeTask(file.resolution || '未知') + ' · ' + escapeTask(file.size_text || formatTaskSize(file.size)) + '</span></label>';
                }).join('') +
                '</div>' +
                '<div class="mt-2 text-[10px] text-slate-500">默认选择当前已发现的全部集数；取消某些集只影响首次处理，后续新集仍会自动追更。</div>';
            const updateSelectionUi = () => {
                const checked = [...row.querySelectorAll('.task-episode-checkbox:checked')];
                const selected = new Set(checked.map(input => {
                    const file = files[Number(input.dataset.fileIndex)];
                    return String(file?.fid || '').trim();
                }).filter(Boolean));
                row.querySelector('[data-selected-count]').textContent = selected.size;
                row.querySelector('[data-toggle-files]').textContent = selected.size === validFids.length ? '取消全选' : '全选';
                if (selectedCandidate?.row === row) {
                    selectedCandidate.selectedFids = selected;
                    const enabled = selected.size > 0;
                    document.getElementById('task-submit').disabled = !enabled;
                    document.getElementById('task-submit').classList.toggle('opacity-40', !enabled);
                    document.getElementById('task-form-status').textContent = enabled
                        ? '已选择 ' + selected.size + ' 集；后续频道新增集数仍会自动追更。'
                        : '至少选择 1 集作为首次处理基线。';
                }
            };
            row.querySelectorAll('.task-episode-checkbox').forEach(input => input.addEventListener('change', updateSelectionUi));
            row.querySelector('[data-toggle-files]').onclick = () => {
                const shouldSelectAll = row.querySelectorAll('.task-episode-checkbox:checked').length !== validFids.length;
                row.querySelectorAll('.task-episode-checkbox').forEach(input => { input.checked = shouldSelectAll; });
                updateSelectionUi();
            };
            row.querySelector('.candidate-select').onclick = function() {
                const currentSelected = new Set([...row.querySelectorAll('.task-episode-checkbox:checked')].map(input => {
                    const file = files[Number(input.dataset.fileIndex)];
                    return String(file?.fid || '').trim();
                }).filter(Boolean));
                selectedCandidate = {candidate:candidate,row:row,selectedFids:currentSelected};
                document.querySelectorAll('.candidate-select').forEach(b => { b.className='candidate-select shrink-0 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-[11px] text-slate-400'; b.textContent='选择此源'; });
                this.className='candidate-select shrink-0 rounded-xl bg-emerald-600 px-4 py-2.5 text-[11px] font-medium text-white';
                this.textContent='已选择';
                document.getElementById('task-submit').disabled=false;
                document.getElementById('task-submit').classList.remove('opacity-40');
                document.getElementById('task-form-status').textContent='已选择 ' + selectedFids.size + ' 集；后续频道新增集数仍会自动追更。';
            };
            box.appendChild(row);
        });

    } catch (err) {
        box.innerHTML = '<div class="rounded-xl border border-rose-900/50 bg-rose-950/20 p-5 text-xs text-rose-300">检索失败：' + escapeTask(err.message) + '</div>';
    }
}

async function createTask() {
    if (!selectedCandidate) return taskToast('请先选择一个资源源');
    const title = document.getElementById('task-title').value.trim();
    const selectedFids = selectedCandidate.selectedFids || new Set();
    const files = (selectedCandidate.candidate.files || [])
        .filter(x => selectedFids.has(String(x.fid || '').trim()))
        .map(x => ({fid:x.fid}))
        .filter(x => x.fid);
    if (!files.length) return taskToast('请至少选择 1 集作为首次处理基线');
    const payload = {
        title:title,
        channel:selectedCandidate.candidate.channel,
        source_id:selectedCandidate.candidate.source_id || 'telegram',
        pwd_id:selectedCandidate.candidate.pwd_id,
        files:files,
        cover:selectedCandidate.candidate.cover || '',
        interval_hours:Number(document.getElementById('task-interval').value || 6),
        target_fid:document.getElementById('task-target-fid').value || '0'
    };
    const btn=document.getElementById('task-submit');
    btn.disabled=true;
    document.getElementById('task-form-status').textContent='正在保存…';
    try {
        const resp=await apiFetchTask('/api/subscriptions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        const res=await resp.json();
        if(!res.success) throw new Error(res.message || '保存失败');
        taskToast('追剧任务已创建');
        closeAddTask();
        await loadTasks();
    }catch(err){
        taskToast(err.message || '保存失败');
        btn.disabled=false;
    }
}

async function runSubscription(id) {
    try {
        const resp = await apiFetchTask('/api/subscriptions/run-now', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id})});
        const res = await resp.json();
        taskToast(res.message || (res.success ? '检查完成' : '检查失败'));
    } catch (err) {
        taskToast('手动检查失败');
    } finally {
        await loadTasks();
    }
}

async function retryTask(id) {
    try {
        const resp = await apiFetchTask('/api/tasks/' + encodeURIComponent(id) + '/retry', {method:'POST'});
        const res = await resp.json();
        if (!res.success) throw new Error(res.message || '重试失败');
        taskToast('已创建重试任务');
        await loadTasks();
    } catch (err) {
        taskToast(err.message || '重试失败');
    }
}

async function deleteTask(id) {
    const task=tasks.find(x=>String(x.id)===String(id));
    if(!task) return;
    if(!confirm('确定删除“' + task.title + '”吗？删除后不会影响已经转存到夸克的文件。')) return;
    try {
        const resp=await apiFetchTask('/api/tasks/' + encodeURIComponent(id),{method:'DELETE'});
        const res=await resp.json();
        if(!res.success) throw new Error(res.message || '删除失败');
        taskToast('任务已删除');
        await loadTasks();
    }catch(err){ taskToast(err.message || '删除失败'); }
}

async function clearHistory() {
    const terminal = tasks.filter(t => ['success','failed','error'].includes(t.status));
    if (!terminal.length) return taskToast('没有可清理的已结束任务');
    if (!confirm('确定清空全部已完成/失败任务及执行记录吗？正在执行中的任务不会受到影响。')) return;
    try {
        const resp=await apiFetchTask('/api/tasks/clear-history',{method:'POST'});
        const res=await resp.json();
        if(!res.success) throw new Error(res.message || '清理失败');
        taskToast(res.message || '历史已清空');
        await loadTasks();
    }catch(err){ taskToast(err.message || '清理失败'); }
}

setInterval(() => { if (!document.hidden && tasks.length) { renderStats(); renderTasks(); } }, 60000);
