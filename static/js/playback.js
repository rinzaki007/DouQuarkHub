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
            const provider = providers.find(item => item.id === "quark_playback") || providers[0];
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
    if (window.movieSyncHls) {
        window.movieSyncHls.destroy();
        window.movieSyncHls = null;
    }
    player.removeAttribute("src");
    player.load();
    try {
        const result = await playbackApi("/api/playback/resolve?provider_id=" + encodeURIComponent(state.providerId)
            + "&fid=" + encodeURIComponent(file.fid));
        const playback = result.playback || {};
        if (!playback.url || !/^https:\/\//i.test(playback.url)) throw new Error("夸克未返回有效的 HTTPS 播放地址");
        // Stream through MovieSync so the backend can forward byte-range requests and
        // return an inline video response instead of a browser download attachment.
        const streamUrl = "/api/playback/stream?provider_id=" + encodeURIComponent(state.providerId)
            + "&fid=" + encodeURIComponent(file.fid);
        const isHls = String(playback.mime_type || "").toLowerCase().includes("mpegurl")
            || /\\.m3u8(?:$|\\?)/i.test(playback.url);
        if (isHls && window.Hls && window.Hls.isSupported()) {
            const hls = new window.Hls({
                enableWorker: true,
                lowLatencyMode: false,
                backBufferLength: 30
            });
            window.movieSyncHls = hls;
            hls.on(window.Hls.Events.ERROR, (_event, data) => {
                if (data && data.fatal) {
                    status.textContent = "HLS 视频流加载失败（" + String(data.type || "媒体错误") + "），请重新点击视频；若持续失败，请检查夸克播放地址是否过期。";
                }
            });
            hls.loadSource(streamUrl);
            hls.attachMedia(player);
        } else {
            // Safari and other native-HLS browsers can play the rewritten playlist directly.
            player.src = streamUrl;
            player.load();
        }
        status.textContent = "播放地址已获取" + (playback.resolution ? " · " + playback.resolution : "")
            + "，正在加载视频数据…";
        player.play().catch(() => {
            if (player.readyState < HTMLMediaElement.HAVE_METADATA) {
                status.textContent = "地址已获取，但浏览器尚未加载到视频信息。请稍后点击播放器的播放按钮；若仍失败，请检查浏览器控制台中的媒体请求状态。";
            }
        });
    } catch (error) {
        status.textContent = error.message || "获取播放地址失败";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const player = document.getElementById("video-player");
    const status = document.getElementById("play-status");
    player?.addEventListener("loadedmetadata", () => {
        if (Number.isFinite(player.duration) && player.duration > 0) {
            status.textContent = "视频已加载 · 时长 " + formatPlaybackDuration(player.duration);
        }
    });
    player?.addEventListener("error", () => {
        const mediaError = player.error;
        const details = mediaError ? ({
            1: "播放已取消",
            2: "视频数据读取失败（网络或上游响应异常）",
            3: "浏览器无法解码此视频（可能是编码或封装格式不受支持）",
            4: "浏览器不支持此视频格式或视频源返回了非视频内容"
        }[mediaError.code] || "未知媒体错误") : "未知媒体错误";
        status.textContent = details + "。可以重新点击视频获取新地址；如果仍失败，请检查该文件是否为浏览器支持的 MP4/H.264 格式。";
    });
    document.getElementById("refresh-files")?.addEventListener("click", loadDriveFiles);
    loadDriveFiles();
});

function formatPlaybackDuration(seconds) {
    const total = Math.floor(seconds);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const remainder = total % 60;
    return (hours ? hours + ":" : "")
        + String(minutes).padStart(2, "0") + ":"
        + String(remainder).padStart(2, "0");
}
