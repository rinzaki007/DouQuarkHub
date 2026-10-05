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

    def add_subscription(self, title, pwd_id, target_fid='0', interval_hours=6, start_ep=0):
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
            "start_ep": start_ep,  # 🎯 起始集数（如设为13，则自动忽略<=13集）
            "saved_episodes": [],
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
        files, stoken, err = engine.get_share_files(sub['pwd_id'])
        if not files:
            sub['last_check'] = time.strftime("%Y-%m-%d %H:%M") + " (解析失败)"
            self.save_subscriptions()
            return False, f"解析链接失败: {err}"

        start_ep = sub.get('start_ep', 0)
        saved_eps = set(sub.get('saved_episodes', []))
        files_to_save = []
        new_eps_found = []

        for f in files:
            raw_name = f.get('file_name', '')
            ep_num, _ = clean_tv_filename(raw_name, sub['title'])
            
            # 🎯 关键逻辑：过滤掉小等于起始集数的历史文件，且只保存未曾存过的新集数
            if ep_num is not None:
                if ep_num <= start_ep:
                    continue  # 已看或已设为起始之前的集数，跳过
                if ep_num not in saved_eps:
                    files_to_save.append({'fid': f.get('fid')})
                    new_eps_found.append(ep_num)

        if not files_to_save:
            sub['last_check'] = time.strftime("%Y-%m-%d %H:%M") + " (无新集数)"
            self.save_subscriptions()
            return True, f"暂无第 {start_ep} 集之后的新更新"

        # 执行增量转存
        target_fid = sub.get('target_fid') or '0'
        ok, msg = engine.save_files(sub['pwd_id'], files_to_save, stoken, target_fid)
        
        if ok:
            sub['saved_episodes'] = sorted(list(saved_eps.union(new_eps_found)))
            sub['last_check'] = time.strftime("%Y-%m-%d %H:%M") + f" (成功转存{len(new_eps_found)}集)"
            self.save_subscriptions()
            return True, f"🎉 成功追更 {len(new_eps_found)} 集！(集数: {new_eps_found})"
        else:
            sub['last_check'] = time.strftime("%Y-%m-%d %H:%M") + " (转存失败)"
            self.save_subscriptions()
            return False, f"转存失败: {msg}"

    def _run_scheduler_loop(self):
        while True:
            schedule.run_pending()
            time.sleep(60)

    def start_scheduler(self):
        schedule.every(1).hours.do(self._auto_check_all)
        t = threading.Thread(target=self._run_scheduler_loop, daemon=True)
        t.start()

    def _auto_check_all(self):
        for sub in self.subscriptions:
            self.check_subscription_now(sub['id'])
