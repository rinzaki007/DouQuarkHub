async function fetchSubscriptions() {
    const res = await fetch('/api/subscriptions');
    const data = await res.json();
    if (data.success) {
        const box = document.getElementById('sub-list-box');
        box.innerHTML = '';
        if (data.subscriptions.length === 0) {
            box.innerHTML = `<div style="text-align:center; color:#64748b; font-size:12px; padding:10px;">暂无自动追剧订阅</div>`;
            return;
        }
        data.subscriptions.forEach(sub => {
            const item = document.createElement('div');
            item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:8px; border-bottom:1px solid #1e293b; font-size:12px;';
            item.innerHTML = `
                <div>
                    <b style="color:#60a5fa;">${sub.title}</b> 
                    <span style="color:#38bdf8; font-size:11px; margin-left:4px;">[ID: ${sub.pwd_id || '未知'}]</span>
                    <span style="color:#f59e0b; font-size:11px; margin-left:4px;">(跳过前 ${sub.start_ep || 0} 集 | 已存 ${sub.saved_episodes.length} 集)</span>
                    <div style="font-size:10px; color:#94a3b8;">上次检查: ${sub.last_check} | 间隔: ${sub.interval_hours}小时</div>
                </div>
                <div>
                    <button class="btn-sm" style="background:#0284c7; margin-right:4px;" onclick="runSubNow('${sub.id}')">🔄 立即检测</button>
                    <button class="btn-del" onclick="deleteSub('${sub.id}')">✕</button>
                </div>
            `;
            box.appendChild(item);
        });
    }
}
