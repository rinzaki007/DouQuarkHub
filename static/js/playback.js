/* MovieSync playback page: browse own Quark drive and resolve short-lived stream URLs. */
const state = { providerId: "", parentFid: "0", path: [{ fid: "0", name: "我的网盘" }] };

function escapePlaybackHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
}

async function playbackApi(url) {
    const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) window.location.href = "/login";
    if (!response.ok || !result.success) throw new Error(result.message || "请求失败");
    return result;
}

function renderBreadcrumbs() {
    const target = document.getElementById("breadcrumbs");
    target.innerHTML = state.path.map((item, index) => {
        const label = escapePlaybackHtml(item.name);
        if (index === state.path.length - 1) return '<span class="text-slate-200">' + label + '</span>';
        return '<button class="hover:text-white" data-path-index="' + index + '">' + label + '</button><span>/</span>';
    }).join("");
    target.querySelectorAll("[data-path-index]").forEach(button => {
        button.addEventListener("click", () => {
            const index = Number(button.dataset.pathIndex);
            state.path = state.path.slice(0, index + 1);
            state.parentFid = state.path[state.path.length - 1].fid;
            loadDriveFiles();
        });
    });
}

async function loadDriveFiles() {
    const status = document.getElementById("file-status");
    const list = document.getElementById("file-list");
    renderBreadcrumbs();
    status.textContent = "正在读取目录…";
    list.replaceChildren();
    try {
        if (!state.providerId) {
            const providerResult = await playbackApi("/api/playback/providers");
            const providers = providerResult.providers || [];
            const provider = providers.find(item => item.id === "quark-playback") || providers[0];
            if (!provider) throw new Error("尚未安装并启用在线播放卡片，请在「设置 → 卡片管理」中安装 quark_playback.py");
            if (!provider.configured) throw new Error("请先在夸克存储卡片中配置 Cookie");
            state.providerId = provider.id;
        }
        const result = await playbackApi("/api/playback/files?provider_id=" + encodeURIComponent(state.providerId)
            + "&parent_fid=" + encodeURIComponent(state.parentFid));
        const files = Array.isArray(result.files) ? result.files : [];
        const visible = files.filter(item => item && (item.is_dir || item.is_video));
        if (!visible.length) {
            status.textContent = "这个目录没有子目录或支持的视频文件。";
            return;
        }
        status.textContent = "共 " + visible.length + " 项";
        for (const file of visible) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-3 text-left hover:border-slate-700 hover:bg-slate-800/80";
            const icon = file.is_dir ? "fa-folder text-amber-300" : "fa-circle-play text-sky-300";
            const size = Number(file.size) > 0 ? " · " + (Number(file.size) / (1024 * 1024 * 1024)).toFixed(2) + " GB" : "";
            button.innerHTML = '<i class="fa-solid ' + icon + ' w-5 text-center"></i><span class="min-w-0 flex-1 break-words text-sm">'
                + escapePlaybackHtml(file.file_name) + '<span class="block text-xs text-slate-500">'
                + (file.is_dir ? "文件夹" : "视频" + size) + '</span></span>';
            button.addEventListener("click", () => file.is_dir ? openFolder(file) : playFile(file));
            list.appendChild(button);
        }
    } catch (error) {
        status.textContent = error.message || "读取网盘目录失败";
    }
}

function openFolder(file) {
    state.parentFid = String(file.fid);
    state.path.push({ fid: state.parentFid, name: String(file.file_name || "文件夹") });
    loadDriveFiles();
}

async function playFile(file) {
    const status = document.getElementById("play-status");
    const title = document.getElementById("now-playing");
    const player = document.getElementById("video-player");
    title.textContent = file.file_name || "正在播放";
    status.textContent = "正在向夸克申请播放地址…";
    player.pause();
    player.removeAttribute("src");
    player.load();
    try {
        const result = await playbackApi("/api/playback/resolve?provider_id=" + encodeURIComponent(state.providerId)
            + "&fid=" + encodeURIComponent(file.fid));
        const playback = result.playback || {};
        if (!playback.url || !/^https:\/\//i.test(playback.url)) throw new Error("夸克未返回有效的 HTTPS 播放地址");
        player.src = playback.url;
        player.load();
        status.textContent = "播放地址已获取" + (playback.resolution ? " · " + playback.resolution : "")
            + "。如果无法播放，请检查视频编码是否受浏览器支持。";
        player.play().catch(() => {});
    } catch (error) {
        status.textContent = error.message || "获取播放地址失败";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("refresh-files")?.addEventListener("click", loadDriveFiles);
    loadDriveFiles();
});
