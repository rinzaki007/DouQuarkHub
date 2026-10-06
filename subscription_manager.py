import os
import json
import time
import threading
import schedule
from quark_engine import QuarkEngine, clean_tv_filename

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
SUB_FILE = os.path.join(DATA_DIR, 'subscriptions.json')

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

class SubscriptionManager:
    def __init__(self, get_cookie_func):
        self.get_cookie = get_cookie_func
        self.subscriptions = self.load_subscriptions()

    def load_subscriptions(self):
        if not os.path.exists(SUB_FILE):
            return []
        try:
            with open(SUB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_subscriptions(self):
        with open(SUB_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.subscriptions, f, ensure_ascii=False, indent=2)

    def get_subscriptions(self):
        return self.subscriptions

    def add_subscription(self, title, pwd_id, target_fid='0', interval_hours=6, start_ep=0, channel='', stoken='', files=None):
        sub_id = str(int(time.time()))
        try:
            start_ep = int(start_ep)
        except ValueError:
            start_ep = 0

        new_sub = {
            "id": sub_id,
            "title": title,
            "pwd_id": pwd_id,
            "target_fid": target_fid,
            "interval_hours": int(interval_hours),
            "start_ep": start_ep,  # 起始集数（如设为13，则自动忽略<=13集）
            "channel": channel,    # 🎯 记录锁定的 TG 频道名称
            "stoken": stoken,      # 🎯 记录分享口令
            "files": files or [],  # 🎯 记录用户勾选监控的具体文件/版本白名单
            "saved_episodes": [],  # 已转存的历史文件ID或集数记录
            "last_check": "从未检测"
        }
        self.subscriptions.append(new_sub)
        self.save_subscriptions()
        return new_sub

    def delete_subscription(self, sub_id):
        self.subscriptions = [s for s in self.subscriptions if s['id'] != sub_id]
        self.save_subscriptions()

    def check_subscription_now(self, sub_id):
        sub = next((s for s in self.subscriptions if s['id'] == sub_id), None)
        if not sub:
            return False, "未找到订阅任务"

        cookie = self.get_cookie()
        if not cookie:
            return False, "缺少夸克 Cookie"

        engine = QuarkEngine(cookie)
        files, fetched_stoken, err = engine.get_share_files(sub['pwd_id'])
        if not files:
            sub['last_check'] = time.strftime("%Y-%m-%d %H:%M") + " (解析失败)"
            self.save_subscriptions()
            return False, f"解析链接失败: {err}"

        saved_eps = set(sub.get('saved_episodes', []))
        target_files = sub.get('files', [])
        files_to_save = []
        new_eps_found = []

        # 🎯 核心逻辑判断：
        # 如果任务配置了精细化文件白名单（新版智能追剧），则按白名单精确监控；
        # 否则回退兼容旧版的按剧集名清洗（clean_tv_filename）逻辑。
        if target_files:
            target_fids = {f.get('fid') for f in target_files}
            for f in files:
                fid = f.get('fid')
                if fid in target_fids and fid not in saved_eps:
                    files_to_save.append({'fid': fid})
                    new_eps_found.append(fid)
        else:
            start_ep = sub.get('start_ep', 0)
            for f in files:
                raw_name = f.get('file_name', '')
                ep_num, _ = clean_tv_filename(raw_name, sub['title'])
                
                if ep_num is not None:
                    if ep_num <= start_ep:
                        continue  # 已看或已设为起始之前的集数，跳过
                    if ep_num not in saved_eps:
                        files_to_save.append({'fid': f.get('fid')})
                        new_eps_found.append(ep_num)

        if not files_to_save:
            sub['last_check'] = time.strftime("%Y-%m-%d %H:%M") + " (无新更新)"
            self.save_subscriptions()
            return True, f"《{sub['title']}》暂无新更新"

        # 执行增量转存
        target_fid = sub.get('target_fid') or '0'
        stoken_to_use = sub.get('stoken') or fetched_stoken
        ok, msg = engine.save_files(sub['pwd_id'], files_to_save, stoken_to_use, target_fid)
        
        if ok:
            sub['saved_episodes'] = sorted(list(saved_eps.union(new_eps_found)))
            sub['last_check'] = time.strftime("%Y-%m-%d %H:%M") + f" (成功转存{len(new_eps_found)}项)"
            self.save_subscriptions()
            return True, f"🎉 成功追更 {len(new_eps_found)} 项！"
        else:
            sub['last_check'] = time.strftime("%Y-%m-%d %H:%M") + " (转存失败)"
            self.save_subscriptions()
            return False, f"转存失败: {msg}"

    def _run_scheduler_loop(self):
        while True:
            schedule.run_pending()
            time.sleep(60)

    def start_scheduler(self):
        # 默认每小时触发一次扫描循环，内部可根据需要扩展
        schedule.every(1).hours.do(self._auto_check_all)
        t = threading.Thread(target=self._run_scheduler_loop, daemon=True)
        t.start()

    def _auto_check_all(self):
        for sub in self.subscriptions:
            try:
                self.check_subscription_now(sub['id'])
            except Exception:
                pass
