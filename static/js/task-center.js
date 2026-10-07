let tasks = [];
let taskFilter = 'all';
let selectedCandidate = null;

document.addEventListener('DOMContentLoaded', () => {
    loadTasks();
    loadTaskCategories();
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
        const resp = await apiFetchTask('/api/config');
        const res = await resp.json();
        if (!res.success || !res.config) return;
        const select = document.getElementById('task-target-fid');
        select.innerHTML = '';
        const cfg = res.config;
        const option = document.createElement('option');
        option.value = cfg.default_fid || '0';
        option.textContent = '默认全局目录';
        select.appendChild(option);
        for (const [name, fid] of Object.entries(cfg.category_fids || {})) {
            if (!fid) continue;
            const item = document.createElement('option');
            item.value = fid;
            item.textContent = name + '专属目录';
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
        const resp = await apiFetchTask('/api/subscriptions');
        const res = await resp.json();
        if (!res.success) throw new Error(res.message || '加载失败');
        tasks = Array.isArray(res.tasks) ? res.tasks : [];
        renderStats();
        renderTasks();
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
    if (!visible.length) {
        list.innerHTML = '<div class="p-12 text-center text-xs text-slate-500">暂无符合条件的任务。</div>';
        return;
    }
    list.innerHTML = '';
    visible.forEach(task => {
        const state = taskState(task);
        const total = Number(task.total || 0);
        const done = Number(task.success_count || 0) + Number(task.skipped_count || 0) + Number(task.failed_count || 0);
        const progress = Math.max(0, Math.min(100, Number(task.progress || 0)));
        const retryable = task.type === 'transfer' && task.status === 'failed';
        const card = document.createElement('article');
        card.className = 'p-4 hover:bg-slate-900/60 transition';
        card.innerHTML =
            '<div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">' +
            '<div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-2">' +
            '<h3 class="truncate text-sm font-semibold text-slate-100">' + escapeTask(task.title) + '</h3>' +
            '<span class="rounded-full border px-2 py-0.5 text-[10px] ' + state.cls + '">' + state.label + '</span>' +
            '<span class="rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5 text-[10px] text-slate-400">' + escapeTask(task.kind || '任务') + '</span>' +
            '</div>' +
            '<div class="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800"><div class="h-full rounded-full bg-purple-500 transition-all" style="width:' + progress + '%"></div></div>' +
            '<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">' +
            '<span>进度 ' + progress + '%</span><span>成功 ' + Number(task.success_count || 0) + '</span><span>跳过 ' + Number(task.skipped_count || 0) + '</span><span>失败 ' + Number(task.failed_count || 0) + '</span>' +
            (task.next_run_at ? '<span>下次：' + formatNextRun(task.next_run_at) + '</span>' : '') +
            '</div><div class="mt-2 text-[11px] ' + ((task.status === 'failed' || task.last_error) ? 'text-rose-400' : 'text-slate-500') + '">' +
            escapeTask(task.message || task.last_error || '') + '</div></div>' +
            '<div class="flex shrink-0 flex-wrap gap-2">' +
            (task.type === 'subscription' ? '<button data-action="run-sub" data-id="' + escapeTask(task.subscription_id) + '" class="rounded-lg bg-purple-600 px-3 py-2 text-[11px] font-medium text-white hover:bg-purple-500"><i class="fa-solid fa-play mr-1"></i>立即检查</button>' : '') +
            (retryable ? '<button data-action="retry" data-id="' + escapeTask(task.id) + '" class="rounded-lg border border-amber-800 bg-amber-950/40 px-3 py-2 text-[11px] text-amber-300 hover:bg-amber-900/60"><i class="fa-solid fa-rotate-right mr-1"></i>失败重试</button>' : '') +
            '</div></div>';
        list.appendChild(card);
    });
    list.querySelectorAll('[data-action="run-sub"]').forEach(btn => btn.onclick = () => runSubscription(btn.dataset.id));
    list.querySelectorAll('[data-action="retry"]').forEach(btn => btn.onclick = () => retryTask(btn.dataset.id));
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
    setTimeout(() => document.getElementById('task-title').focus(), 50);
}

function closeAddTask() {
    document.getElementById('task-drawer').classList.add('hidden');
}

async function searchTaskCandidates() {
    const title = document.getElementById('task-title').value.trim();
    if (!title) return taskToast('请输入剧名');
    const box = document.getElementById('task-candidate-list');
    document.getElementById('task-candidates').classList.remove('hidden');
    box.innerHTML = '<div class="rounded-lg border border-slate-800 bg-slate-950 p-6 text-center text-xs text-slate-500"><i class="fa-solid fa-spinner fa-spin mr-1"></i>正在并发检索频道…</div>';
    selectedCandidate = null;
    document.getElementById('task-submit').disabled = true;
    document.getElementById('task-submit').classList.add('opacity-40');
    try {
        const resp = await apiFetchTask('/api/search-candidates', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({movies:[{title:title,tag:'电视剧'}]})});
        const res = await resp.json();
        if (!res.success) throw new Error(res.message || '检索失败');
        const candidates = (res.candidates_map || {})[title] || [];
        if (!candidates.length) {
            box.innerHTML = '<div class="rounded-lg border border-amber-900/50 bg-amber-950/20 p-5 text-center text-xs text-amber-300">没有找到匹配资源，请换一个剧名或检查频道配置。</div>';
            return;
        }
        document.getElementById('candidate-hint').textContent = '找到 ' + candidates.length + ' 个可用源';
        box.innerHTML = '';
        candidates.forEach((candidate, index) => {
            const row = document.createElement('div');
            row.className = 'rounded-xl border border-slate-800 bg-slate-950 p-4';
            row.innerHTML =
                '<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div>' +
                '<div class="text-xs font-semibold text-emerald-400"><i class="fa-brands fa-telegram mr-1"></i>' + escapeTask(candidate.channel) + '</div>' +
                '<div class="mt-1 text-[11px] text-slate-500">分享码 ' + escapeTask(candidate.pwd_id) + ' · ' + candidate.files.length + ' 个文件</div></div>' +
                '<button data-candidate="' + index + '" class="candidate-select rounded-lg border border-purple-700 bg-purple-950/40 px-3 py-2 text-[11px] text-purple-200 hover:bg-purple-900/50">选择此源</button></div>' +
                '<div class="mt-3 max-h-52 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900/80 p-3 space-y-1">' +
                candidate.files.map(file => '<label class="flex cursor-pointer items-center gap-2 py-1 text-xs text-slate-300"><input type="checkbox" data-fid="' + escapeTask(file.fid) + '" class="task-file rounded border-slate-700 bg-slate-900 text-purple-600"> <span class="font-mono">' + escapeTask(file.file_name) + '</span></label>').join('') +
                '</div>';
            row.querySelector('.candidate-select').onclick = function() {
                selectedCandidate = {candidate:candidate,row:row};
                document.querySelectorAll('.candidate-select').forEach(b => { b.className='candidate-select rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-[11px] text-slate-400'; b.textContent='选择此源'; });
                this.className='candidate-select rounded-lg bg-emerald-600 px-3 py-2 text-[11px] text-white';
                this.textContent='已选择';
                document.getElementById('task-submit').disabled=false;
                document.getElementById('task-submit').classList.remove('opacity-40');
                document.getElementById('task-form-status').textContent='已选择资源源，请勾选需要持续监控的文件。';
            };
            box.appendChild(row);
        });
    } catch (err) {
        box.innerHTML = '<div class="rounded-lg border border-rose-900/50 bg-rose-950/20 p-5 text-xs text-rose-300">检索失败：' + escapeTask(err.message) + '</div>';
    }
}

async function createTask() {
    if (!selectedCandidate) return taskToast('请先选择一个资源源');
    const title = document.getElementById('task-title').value.trim();
    const checks = selectedCandidate.row.querySelectorAll('input[data-fid]:checked');
    if (!checks.length) return taskToast('请至少选择一个需要监控的文件');
    const files = Array.from(checks).map(x => ({fid:x.dataset.fid}));
    const payload = {title:title, channel:selectedCandidate.candidate.channel, pwd_id:selectedCandidate.candidate.pwd_id, files:files, interval_hours:Number(document.getElementById('task-interval').value || 6), target_fid:document.getElementById('task-target-fid').value || '0'};
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
        const resp=await apiFetchTask('/api/subscriptions?id='+encodeURIComponent(id),{method:'DELETE'});
        const res=await resp.json();
        if(!res.success) throw new Error(res.message || '删除失败');
        taskToast('任务已删除');
        await loadTasks();
    }catch(err){ taskToast(err.message || '删除失败'); }
}

setInterval(() => { if (!document.hidden && tasks.length) { renderStats(); renderTasks(); } }, 60000);
