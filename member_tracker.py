from collections import defaultdict
from datetime import datetime
import time

class WxGroupMemberTracker:
    def __init__(self):
        # 存储结构示例: {'group1@chatroom': {'user1': {'active': 1620000000, 'reminded': 0}}}
        self.group_data = defaultdict(lambda: defaultdict(lambda: {
            'last_active': 0.0,
            'last_reminded': 0.0
        }))

    def update_activity(self, group_id: str, user_id: str):
        """更新用户最后活跃时间戳"""
        self.group_data[group_id][user_id]['last_active'] = time.time()

    def check_inactive_users(self, group_id: str, timeout: int, cooldown: int) -> list:
        """返回需要提醒的用户列表"""
        now = time.time()
        remind_list = []
        
        for user_id, status in self.group_data[group_id].items():
            is_inactive = (now - status['last_active']) > timeout
            not_recently_reminded = (now - status['last_reminded']) > cooldown
            
            if is_inactive and not_recently_reminded:
                remind_list.append(user_id)
        
        return remind_list

    def record_remind(self, group_id: str, user_id: str):
        """记录最近提醒时间"""
        self.group_data[group_id][user_id]['last_reminded'] = time.time()
