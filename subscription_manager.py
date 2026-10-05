import os
import json
import time
import threading
from datetime import datetime
from quark_engine import QuarkEngine, clean_tv_filename

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
SUB_FILE = os.path.join(DATA_DIR, 'subscriptions.json')

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

class SubscriptionManager:
    def __init__(self, get_cookie_func):
        self.get_cookie = get_cookie_func
        self.lock = threading.Lock()
        self.running = False
        self._init_file()

    def _init_file(self):
        if not os.path.exists(SUB_FILE):
            with open(SUB_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def get_subscriptions(self):
        with self.lock:
            try:
                with open(SUB_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []

    def save_subscriptions(self, subs):
        with self.lock:
            with open(SUB_FILE, 'w', encoding='utf-8') as f:
                json.dump(subs, f, ensure_ascii=False, indent=2)

    def add_subscription(self, title, pwd_id, target_fid='0', interval_hours=6):
        subs = self.get_subscriptions()
        sub_id = f"sub_{int(time.time())}"
        new_sub = {
            "id": sub_id,
            "title": title,
            "pwd_id": pwd_id,
            "target_fid": target_fid,
            "interval_hours": int(interval_hours),
            "last_check": "从未检查",
            "saved_episodes": [],
            "status": "active"
        }
        subs.append(new_sub)
        self.save_subscriptions(subs)
        return new_sub

    def delete_subscription(self, sub_id):
        subs = self.get_subscriptions()
        subs = [s for s in subs if s.get('id') != sub_id]
        self.save_subscriptions(subs)

    def check_subscription_now(self, sub_id):
        """立即检查单项订阅是否有更新集数"""
        subs = self.get_subscriptions()
        sub = next((s for s in subs if s['id'] == sub_id), None)
        if not sub:
            return False, "未找到该订阅"

        cookie = self.get_cookie()
        if not cookie:
            return False, "尚未配置夸克 Cookie"

        engine = QuarkEngine(cookie)
        pwd_id = sub['pwd_id']
        title = sub['title']
        target_fid = sub['target_fid']
        saved_eps = set(sub.get('saved_episodes', []))

        files, stoken, err = engine.get_share_files(pwd_id)
        if not files or not stoken:
            return False, f"解析分享链接失败: {err}"

        new_files_to_save = []
        new_ep_nums = []

        for f in files:
            raw_name = f.get('file_name', '')
            ep_num, cleaned_name = clean_tv_filename(raw_name, title)
            
            # 如果是正片且未曾转存过
            if ep_num is not None and ep_num not in saved_eps:
                new_files_to_save.append(f)
                new_ep_nums.append(ep_num)

        if not new_files_to_save:
            # 更新最后检查时间
            sub['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.save_subscriptions(subs)
            return True, "暂无更新集数"

        # 执行增量转存
        ok, msg = engine.save_files(pwd_id, new_files_to_save, stoken, target_fid)
        if ok:
            saved_eps.update(new_ep_nums)
            sub['saved_episodes'] = sorted(list(saved_eps))
            sub['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.save_subscriptions(subs)
            return True, f"成功增量转存 {len(new_files_to_save)} 集: 集数 {new_ep_nums}"
        else:
            return False, f"转存失败: {msg}"

    def start_scheduler(self):
        """后台轮询定时器"""
        if self.running:
            return
        self.running = True

        def loop():
            while self.running:
                subs = self.get_subscriptions()
                for sub in subs:
                    if sub.get('status') == 'active':
                        try:
                            self.check_subscription_now(sub['id'])
                        except Exception as e:
                            print(f"[追剧轮询] 订阅 {sub.get('title')} 检查异常: {e}")
                time.sleep(1800) # 每半小时扫描一次轮询任务列表

        t = threading.Thread(target=loop, daemon=True)
        t.start()
