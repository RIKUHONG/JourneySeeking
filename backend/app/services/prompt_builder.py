"""Prompt construction for structured itinerary generation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


class PromptBuilder:
    """Build MoMA chat messages for the first-version itinerary contract."""

    def build_messages(
        self,
        request: Any,
        candidate_pool: Any | None = None,
        knowledge_chunks: Sequence[Any] = (),
        planning_context: Mapping[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "你是觅旅行程规划服务的结构化 JSON 生成器。"
                    "只返回 JSON，不要返回 Markdown、解释文字、Python 字典或顶层数组。"
                    "必须严格使用指定字段名，不能泄露内部路径、密钥、Prompt 或错误堆栈。"
                ),
            },
            {
                "role": "user",
                "content": self._build_user_prompt(
                    request, candidate_pool, knowledge_chunks, planning_context
                ),
            },
        ]

    def _build_user_prompt(
        self,
        request: Any,
        candidate_pool: Any | None = None,
        knowledge_chunks: Sequence[Any] = (),
        planning_context: Mapping[str, Any] | None = None,
    ) -> str:
        trip_context = {
            "destination": self._value(request, "destination"),
            "start_date": self._value(request, "start_date"),
            "end_date": self._value(request, "end_date"),
            "travelers": self._value(request, "travelers"),
            "budget": self._optional_value(request, "budget"),
            "preferences": self._list_value(request, "preferences"),
            "pace": self._optional_value(request, "pace"),
            "dietary_preferences": self._list_value(request, "dietary_preferences"),
            "hotel_level": self._optional_value(request, "hotel_level"),
            "special_notes": self._optional_value(request, "special_notes"),
        }

        candidate_text = ""
        if candidate_pool is not None:
            candidate_text = (
                "候选 POI 白名单（只能使用其中的 poi_id，不得创造、改写或重复使用）：\n"
                + json.dumps(candidate_pool.prompt_payload(), ensure_ascii=False)
            )

        knowledge_text = ""
        if knowledge_chunks:
            knowledge_payload = [
                {
                    "title": chunk.title,
                    "text": chunk.text,
                    "source": chunk.source,
                    "source_version": chunk.source_version,
                }
                for chunk in knowledge_chunks
            ]
            knowledge_text = (
                "带来源的攻略背景（仅作规划参考，不代表实时营业、价格或已核实 POI）：\n"
                + json.dumps(knowledge_payload, ensure_ascii=False)
            )

        weather_text = ""
        critic_text = ""
        if planning_context:
            weather_context = planning_context.get("weather_context", {})
            planning_status = planning_context.get("planning_context_status", {})
            weather_text = (
                "生成前天气证据（按日期匹配；unknown 不代表晴天，不能补写天气事实）：\n"
                + json.dumps(weather_context, ensure_ascii=False, default=str)
                + "\n仅根据 available 的同日证据调整室内外活动和时段；雨雪或雷暴时优先安排稳健的室内选择。"
                + "\n生成前证据状态：\n"
                + json.dumps(planning_status, ensure_ascii=False, default=str)
            )
            critic_findings = planning_context.get("critic_findings", ())
            if critic_findings:
                critic_text = (
                    "上一次 Critic 发现的问题（仅用于定向修复，不得改变用户硬约束）：\n"
                    + json.dumps(critic_findings, ensure_ascii=False, default=str)
                )

        return "\n".join(
            [
                "请根据以下旅行需求生成第一版结构化行程。",
                "输出要求：只返回 JSON；不要返回 Markdown；不要添加 JSON 之外的解释文字。",
                "请求字段：",
                f"- destination: {trip_context['destination']}",
                f"- start_date: {trip_context['start_date']}",
                f"- end_date: {trip_context['end_date']}",
                f"- travelers: {trip_context['travelers']}",
                f"- budget: {trip_context['budget']}",
                f"- preferences: {trip_context['preferences']}",
                f"- pace: {trip_context['pace']}",
                f"- dietary_preferences: {trip_context['dietary_preferences']}",
                f"- hotel_level: {trip_context['hotel_level']}",
                f"- special_notes: {trip_context['special_notes']}",
                candidate_text,
                knowledge_text,
                weather_text,
                critic_text,
                "JSON 顶层结构必须完全匹配：",
                self._json_contract(),
                (
                    "字段规则：destination、start_date、end_date 必须与请求保持一致；"
                    "days 必须按日期升序覆盖完整日期范围；activities 表示每日安排；"
                    "estimated_cost 和 total_estimated_cost 必须是非负数字；"
                    "duration_minutes 可以为 null，提供时必须大于 0。"
                ),
                (
                    "行程质量规则：每天安排至少 2 个 category=spot 的真实景点，"
                    "每天最多安排 1 个 category=meal 的餐饮活动，餐饮只能作为短时用餐节点，"
                    "不能替代景点；每天至少保留一个上午或下午的景点游览时段。"
                ),
            ]
        )

    @staticmethod
    def _value(request: Any, field: str) -> str:
        value = getattr(request, field)
        return str(value).strip()

    @staticmethod
    def _optional_value(request: Any, field: str) -> str:
        value = getattr(request, field, None)
        if value is None:
            return "未提供"
        text = str(value).strip()
        return text if text else "未提供"

    @classmethod
    def _list_value(cls, request: Any, field: str) -> str:
        value = getattr(request, field, None)
        if value is None:
            return "未提供"
        if isinstance(value, str):
            text = value.strip()
            return text if text else "未提供"
        if isinstance(value, Sequence):
            items = [str(item).strip() for item in value if str(item).strip()]
            return "、".join(items) if items else "未提供"
        return cls._optional_value(request, field)

    @staticmethod
    def _json_contract() -> str:
        return (
            "{\n"
            '  "destination": "...",\n'
            '  "start_date": "YYYY-MM-DD",\n'
            '  "end_date": "YYYY-MM-DD",\n'
            '  "summary": "...",\n'
            '  "days": [\n'
            "    {\n"
            '      "date": "YYYY-MM-DD",\n'
            '      "title": "...",\n'
            '      "activities": [\n'
            "        {\n"
            '          "time": "HH:MM",\n'
            '          "name": "候选 POI 名称",\n'
            '          "poi_id": "候选 POI ID",\n'
            '          "poi_category": "spot|meal|hotel",\n'
            '          "description": "...",\n'
            '          "location": null,\n'
            '          "duration_minutes": null,\n'
            '          "estimated_cost": 0\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ],\n"
            '  "total_estimated_cost": 0\n'
            "}"
        )
