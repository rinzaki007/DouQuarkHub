let logTimerInterval = null;
let logTimerSeconds = 0;
let logAutoCloseTimer = null;

function toggleLogBox(show = true) {
    const panel = document.getElementById('log-panel');
    if (show) {
        panel.classList.remove('hidden');
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

    const cookie = localStorage.getItem('quark_cookie') || '';
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
        const response = await fetch('/api/search-candidates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movies: selectedMovies,
                cookie: cookie
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
                    appendLogLine(`    [源 ${idx + 1}] 频道名称: "${cand.channel}" | 夸克短码: ${cand.pwd_id} | 包含视频文件: ${cand.files.length} 个`, 'info');
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
            <span>🎬 《${title}》</span>
            <span class="text-xs text-slate-400 font-normal">找到 ${candidates.length} 个候选源版本</span>
        </div>`;

        if (candidates.length === 0) {
            html += `<div class="text-xs text-rose-400 py-2">未能在配置的频道中找到匹配资源</div>`;
        } else {
            html += `<div class="space-y-3 mt-2">`;
            candidates.forEach((cand, cIdx) => {
                const fileCheckboxes = cand.files.map((f) => `
                    <label class="flex items-center gap-2 py-1 text-xs text-slate-300 hover:text-white cursor-pointer">
                        <input type="checkbox" name="batch-file-${mIdx}-${cIdx}" value="${f.fid}" class="rounded bg-slate-900 border-slate-700 text-blue-600 focus:ring-0">
                        <span class="font-mono">${f.file_name}</span>
                    </label>
                `).join('');

                html += `
                    <div class="bg-slate-900 border border-slate-800/80 rounded-lg p-3 text-xs space-y-2">
                        <div class="flex items-center justify-between text-slate-300">
                            <span class="font-semibold text-emerald-400"><i class="fa-brands fa-telegram"></i> 频道: ${cand.channel}</span>
                            <span class="text-slate-400 font-mono text-[11px]">短码: ${cand.pwd_id} | 包含 ${cand.files.length} 个文件</span>
                        </div>
                        <div class="bg-slate-950 p-2.5 rounded-md max-h-40 overflow-y-auto space-y-1 border border-slate-800">
                            <div class="text-[11px] text-slate-400 mb-1 font-medium">勾选您需要转存的具体文件：</div>
                            ${fileCheckboxes}
                        </div>
                        <div class="text-right pt-1">
                            <button onclick='confirmBatchTransferForCandidate(${mIdx}, ${cIdx}, ${JSON.stringify(movie)}, ${JSON.stringify(cand)})' class="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium transition shadow flex items-center gap-1 ml-auto">
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

function confirmBatchTransferForCandidate(mIdx, cIdx, movie, candidate) {
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
    const cookie = localStorage.getItem('quark_cookie') || '';
    
    toggleLogBox(true);
    clearLog();
    startLogTimer();

    appendLogLine(`[转存启动] 📥 正在为《${movie.title}》创建专属云端文件夹并转存选中版本...`, 'info');
    appendLogLine(`  -> 目标频道: ${candidate.channel}`, 'info');
    appendLogLine(`  -> 提取短码: ${candidate.pwd_id}`, 'info');

    const startTime = Date.now();
    try {
        const response = await fetch('/api/transfer-selected', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                movie: movie,
                candidate: candidate,
                cookie: cookie,
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
