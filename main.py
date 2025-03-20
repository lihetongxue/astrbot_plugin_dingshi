# 在 /AstrBot/data/plugins/astbot_plugin_dingshi/main.py 中
import logging
from astrbot.api.all import *  # 导入所有API
from astrbot.api.event import filter  # 导入事件过滤器
from astrbot.api.provider import ProviderRequest  # 导入provider请求
import datetime
import random
import asyncio
import json
import time

logger = logging.getLogger(__name__)

@register("initiative_group_dialogue", "作者名称", "群组用户主动对话插件,监控指定群内特定用户的活跃度,在用户长时间未发言时主动发起对话", "1.0.0")
class InitiativeGroupUserDialogue(Star):
    """
    群组用户主动对话插件
    监控指定群内特定用户的活跃度,在用户长时间未发言时主动发起对话
    """
    
    def __init__(self, context: Context, config: AstrBotConfig = None):
        """
        初始化插件
        Args:
            context: 机器人上下文
            config: 插件配置
        """
        super().__init__(context, config)
        self.context = context
        self.config = config
        
        # 用户活跃记录管理 {group_id: {user_id: last_active_time}}
        self.user_records: Dict[str, Dict[str, float]] = {}
        
        # 消息任务管理 {group_id: {user_id: task}}
        self._message_tasks: Dict[str, Dict[str, asyncio.Task]] = {}
        
        # 已响应用户记录 {group_id: set(user_ids)}
        self.users_received_initiative: Dict[str, Set[str]] = {}
        
        # 定期检查任务
        self._check_task = None
        
        # 加载时间相关配置
        time_settings = config.get('time_settings', {})
        self.time_limit_enabled = time_settings.get('time_limit_enabled', True)
        self.inactive_time_seconds = time_settings.get('inactive_time_seconds', 7200)
        self.max_response_delay_seconds = time_settings.get('max_response_delay_seconds', 3600)
        self.activity_start_hour = time_settings.get('activity_start_hour', 8)
        self.activity_end_hour = time_settings.get('activity_end_hour', 23)
        self.max_consecutive_messages = time_settings.get('max_consecutive_messages', 3)

        # 初始化监控记录
        self._init_monitoring_records()

    async def start(self):
        """启动插件"""
        if not self._check_task:
            self._check_task = asyncio.create_task(self._periodic_check())
            logger.info("群聊用户主动对话插件已启动")

    async def stop(self):
        """停止插件"""
        await self.cleanup()
        logger.info("群聊用户主动对话插件已停止")

    def _init_monitoring_records(self):
        """初始化需要监控的群和用户记录"""
        monitored_groups = self.config.get('monitored_groups', {})
        if monitored_groups.get('enabled', True):
            groups = monitored_groups.get('groups', {})
            for group_id, group_config in groups.items():
                self.user_records[group_id] = {
                    user_id: 0 for user_id in group_config.get('user_ids', [])
                }
                self.users_received_initiative[group_id] = set()

    def is_monitored_user(self, group_id: str, user_id: str) -> bool:
        """
        检查是否是被监控的用户
        Args:
            group_id: 群ID
            user_id: 用户ID
        Returns:
            bool: 是否需要监控该用户
        """
        monitored_groups = self.config.get('monitored_groups', {})
        if not monitored_groups.get('enabled', True):
            return False
        
        groups = monitored_groups.get('groups', {})
        if group_id not in groups:
            return False
            
        return user_id in groups[group_id].get('user_ids', [])

    async def on_group_message(self, event: AstrMessageEvent):
        """
        处理群消息事件
        Args:
            event: 消息事件
        """
        if not self.config.get('monitored_groups', {}).get('enabled', False):
            return

        group_id = str(event.group_id)
        user_id = str(event.user_id)
        current_time = time.time()
        
        # 如果是监控的用户发言，更新活跃时间
        if self.is_monitored_user(group_id, user_id):
            if group_id not in self.user_records:
                self.user_records[group_id] = {}
            self.user_records[group_id][user_id] = current_time
            
            # 如果是对主动消息的回复，记录响应
            if group_id in self._message_tasks and user_id in self._message_tasks[group_id]:
                if group_id not in self.users_received_initiative:
                    self.users_received_initiative[group_id] = set()
                self.users_received_initiative[group_id].add(user_id)
                logger.info(f"用户 {user_id} 在群 {group_id} 中响应了主动消息")

    async def _periodic_check(self):
        """定期检查用户活跃状态的后台任务"""
        while True:
            try:
                current_time = time.time()
                current_hour = datetime.now().hour
                
                # 检查是否在活动时间内
                if self.time_limit_enabled:
                    if not (self.activity_start_hour <= current_hour < self.activity_end_hour):
                        await asyncio.sleep(60)
                        continue

                # 遍历所有监控的群组
                for group_id, user_records in self.user_records.items():
                    for user_id, last_active in user_records.items():
                        # 检查是否需要发送主动消息
                        if (current_time - last_active) >= self.inactive_time_seconds:
                            # 检查是否已有发送任务在运行
                            if (group_id in self._message_tasks and 
                                user_id in self._message_tasks[group_id] and 
                                not self._message_tasks[group_id][user_id].done()):
                                continue

                            # 创建新的发送任务
                            if group_id not in self._message_tasks:
                                self._message_tasks[group_id] = {}
                            
                            self._message_tasks[group_id][user_id] = asyncio.create_task(
                                self.send_initiative_message(group_id, user_id)
                            )
                            
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"检查不活跃用户时出错: {str(e)}")
                await asyncio.sleep(60)

    async def send_initiative_message(self, group_id: str, user_id: str):
        """
        发送主动消息到群聊
        Args:
            group_id: 群ID
            user_id: 用户ID
        """
        try:
            consecutive_count = 0
            
            while consecutive_count < self.max_consecutive_messages:
                # 随机延迟
                delay = random.randint(0, self.max_response_delay_seconds)
                await asyncio.sleep(delay)
                
                # 如果用户已经回复了，停止发送
                if (group_id in self.users_received_initiative and 
                    user_id in self.users_received_initiative[group_id]):
                    break
                    
                consecutive_count += 1
                prompt = self.get_prompt(consecutive_count, user_id)
                
                # 发送消息
                try:
                    await self.context.bot.send_group_message(
                        group_id=int(group_id),
                        message=Message([
                            MessageSegment.at(user_id=int(user_id)),
                            MessageSegment.text(f" {prompt}")
                        ])
                    )
                    logger.info(f"向群 {group_id} 的用户 {user_id} 发送了第 {consecutive_count} 次主动消息")
                except Exception as e:
                    logger.error(f"发送群主动消息失败: {str(e)}")
                    break
                    
        finally:
            # 清理任务记录
            if group_id in self._message_tasks and user_id in self._message_tasks[group_id]:
                del self._message_tasks[group_id][user_id]
                if not self._message_tasks[group_id]:
                    del self._message_tasks[group_id]
                    
            if group_id in self.users_received_initiative:
                self.users_received_initiative[group_id].discard(user_id)
                if not self.users_received_initiative[group_id]:
                    del self.users_received_initiative[group_id]

    def get_prompt(self, consecutive_count: int, user_id: str) -> str:
        """
        获取带有用户标记的提示语
        Args:
            consecutive_count: 连续发送次数
            user_id: 用户ID
        Returns:
            str: 完整的提示语
        """
        prompts = self.config.get('prompts', [])
        if not prompts:
            return "你好呀~"
            
        base_prompt = random.choice(prompts)
        if consecutive_count > 1:
            return f"{base_prompt}\n(这是第{consecutive_count}次尝试联系 {user_id})"
        return base_prompt

    async def cleanup(self):
        """清理插件资源"""
        # 取消定期检查任务
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            self._check_task = None
            
        # 取消所有正在运行的消息任务
        for group_tasks in self._message_tasks.values():
            for task in group_tasks.values():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    
        self._message_tasks.clear()
        self.user_records.clear()
        self.users_received_initiative.clear()



# 导出插件
Plugin = plugin_meta
