from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import MessageChain

import asyncio
import datetime
import random
import json
import aiohttp
from typing import Dict, List

@register("daily_random", "YourName", "每日随机情话发送插件", "1.0.0")
class DailyRandomLoveMessagePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.chat_configs: Dict[str, Dict] = {}
        
        # 备用情话库
        self.fallback_messages = [
            "我见过最美的风景，是你微笑的样子 ✨",
            "你是我平淡生活里最温柔的意外 💖",
            "喜欢你是我做过最好的决定 💝",
            "遇见你是我所有美好故事的开始 🌟",
            "你的眼睛里有星辰大海 ⭐",
            "你是我最想留住的那个春天 🌸",
            "我希望有一天，你走在路上，突然听见有人喊你的名字，回头发现是我 💫",
            "你知道我最喜欢什么神吗？是你的眼神 👀",
        ]
        
        # API接口列表
        self.api_endpoints = [
            {
                "url": "https://api.uomg.com/api/rand.qinghua",
                "method": "GET",
                "response_key": "content"  # API返回的json中情话内容的key
            },
            {
                "url": "https://api.vvhan.com/api/love",
                "method": "GET",
                "response_key": None  # 直接返回文本的API
            },
            # 可以添加更多API
        ]
        
        self.running = True
        self.session = None  # aiohttp session
        asyncio.create_task(self.daily_checker())

    async def get_session(self):
        """获取或创建aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_random_love_message(self) -> str:
        """获取随机情话"""
        try:
            # 随机选择一个API端点
            api = random.choice(self.api_endpoints)
            session = await self.get_session()
            
            async with session.request(api["method"], api["url"]) as response:
                if response.status == 200:
                    if api["response_key"]:
                        # JSON响应
                        data = await response.json()
                        message = data[api["response_key"]]
                    else:
                        # 纯文本响应
                        message = await response.text()
                    return message.strip()
                else:
                    logger.warning(f"API请求失败: {response.status}")
                    return random.choice(self.fallback_messages)
                    
        except Exception as e:
            logger.error(f"获取情话失败: {str(e)}")
            return random.choice(self.fallback_messages)

    @filter.command("set_random_time")
    async def set_random_time(self, event: AstrMessageEvent):
        '''设置每日随机发送时间范围: /set_random_time HH:MM HH:MM
        例如: /set_random_time 09:00 18:00'''
        try:
            times = event.message_str.split()[1:]
            if len(times) != 2:
                yield event.plain_result("请输入正确的时间范围！例如: /set_random_time 09:00 18:00")
                return

            start_time, end_time = times
            # 验证时间格式
            datetime.datetime.strptime(start_time, "%H:%M")
            datetime.datetime.strptime(end_time, "%H:%M")
            
            next_send_time = self.generate_next_send_time(start_time, end_time)
            
            self.chat_configs[event.unified_msg_origin] = {
                "start_time": start_time,
                "end_time": end_time,
                "enabled": True,
                "next_send_time": next_send_time
            }
            
            # 测试API连接
            test_message = await self.get_random_love_message()
            
            yield event.plain_result(
                f"已设置每日随机发送时间范围:\n"
                f"开始时间: {start_time}\n"
                f"结束时间: {end_time}\n"
                f"下次发送时间: {next_send_time.strftime('%Y-%m-%d %H:%M')}\n"
                f"\n测试情话消息:\n{test_message}"
            )
            
        except ValueError:
            yield event.plain_result("时间格式错误！请使用 HH:MM 格式")
        except Exception as e:
            logger.error(f"设置失败: {str(e)}")
            yield event.plain_result(f"设置失败: {str(e)}")

    @filter.command("test_love_message")
    async def test_love_message(self, event: AstrMessageEvent):
        '''测试情话消息'''
        try:
            message = await self.get_random_love_message()
            yield event.plain_result(f"随机情话测试:\n{message}")
        except Exception as e:
            yield event.plain_result(f"测试失败: {str(e)}")

    async def send_random_message(self, unified_msg_origin: str):
        '''发送随机情话消息'''
        try:
            # 获取随机情话
            message = await self.get_random_love_message()
            # 构建消息链
            message_chain = MessageChain().message(message)
            # 发送消息
            await self.context.send_message(unified_msg_origin, message_chain)
            logger.info(f"已发送每日情话到 {unified_msg_origin}: {message}")
            
            # 生成下一次发送时间
            config = self.chat_configs[unified_msg_origin]
            config["next_send_time"] = self.generate_next_send_time(
                config["start_time"], 
                config["end_time"]
            )
            
        except Exception as e:
            logger.error(f"发送消息失败: {str(e)}")

    @filter.command("add_fallback")
    async def add_fallback_message(self, event: AstrMessageEvent):
        '''添加备用情话: /add_fallback <情话内容>'''
        try:
            message = event.message_str.split(maxsplit=1)[1]
            self.fallback_messages.append(message)
            yield event.plain_result(f"已添加备用情话: {message}")
        except IndexError:
            yield event.plain_result("请输入情话内容！")

    @filter.command("list_fallback")
    async def list_fallback_messages(self, event: AstrMessageEvent):
        '''列出所有备用情话'''
        result = "当前备用情话列表：\n"
        for i, msg in enumerate(self.fallback_messages):
            result += f"{i+1}. {msg}\n"
        yield event.plain_result(result)

    async def terminate(self):
        '''插件终止时清理'''
        self.running = False
        if self.session and not self.session.closed:
            await self.session.close()
        logger.info("每日随机情话插件已停止")

    # ... 其他方法保持不变 ...
