from astrbot.api import (
    AstrBotConfig,
    event_message_type,
    EventMessageType,
    scheduled_task,
    get_bot
)
from datetime import datetime
import random
from .member_tracker import WxGroupMemberTracker

class WxGroupMemberMonitor:
    def __init__(self, config: AstrBotConfig):
        self.config = config.data
        self.tracker = WxGroupMemberTracker()
        self.bot = get_bot()
        self.activated_groups = set()

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_group_event(self, event):
        # 微信特殊ID过滤
        if not event.group_id.endswith('@chatroom'):
            return
        
        user_wxid = event.user_id
        group_wxid = event.group_id
        
        # 初始化群数据
        if group_wxid not in self.activated_groups:
            await self.init_group_members(group_wxid)
            self.activated_groups.add(group_wxid)
        
        # 跳过系统消息和排除名单
        if user_wxid in self.config.get('exclude_users', ['weixin']):
            return
        
        self.tracker.update_activity(group_wxid, user_wxid)

    async def init_group_members(self, group_id: str):
        """初始化群成员数据（需微信API支持）"""
        try:
            member_list = await self.bot.call_api(
                "get_group_member_list",
                group_id=group_id
            )
            for member in member_list:
                self.tracker.update_activity(group_id, member['wxid'])
        except Exception as e:
            print(f"初始化群成员失败 {group_id}: {str(e)}")

    @scheduled_task(interval=600)  # 每10分钟一次检查
    async def trigger_reminder(self):
        current_hour = datetime.now().hour
        if current_hour not in self.config.get('working_hours', []):
            return
        
        for group_id in self.activated_groups:
            inactive_users = self.tracker.check_inactive_users(
                group_id,
                self.config.get('user_timeout', 86400),
                self.config.get('remind_cooldown', 7200)
            )
            
            if not inactive_users:
                continue
            
            # 微信特殊@格式处理
            target_user = random.choice(inactive_users)
            await self.bot.send_message(
                receiver=group_id,
                message={
                    "msgtype": "text",
                    "text": {
                        "content": f"\u200B@{target_user}\u200B 召唤成功！快来一起聊聊天吧～",
                        "mentioned_list": [target_user]
                    }
                }
            )
            self.tracker.record_remind(group_id, target_user)

    @classmethod
    async def reload_handler(cls, config: AstrBotConfig):
        return cls(config)
