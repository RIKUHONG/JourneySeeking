"""Deterministic Markdown and PDF rendering for stored itinerary versions."""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Final
from urllib.parse import quote

from backend.app.models.schemas import Activity, Itinerary, WeatherInfo


class TripExportError(RuntimeError):
    """Raised when a requested export cannot be rendered."""


try:
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError:
    reportlab = None
else:
    reportlab = True
_SAFE_FILENAME: Final = re.compile(r"[^\w\-.\u4e00-\u9fff]+")


def _text(value: object | None, fallback: str = "暂无数据") -> str:
    return fallback if value is None or value == "" else str(value)


def _weather_text(weather: WeatherInfo | None) -> str:
    if weather is None:
        return "天气未知（暂无来源）"
    if weather.status == "unknown":
        return f"天气未知（来源：{_text(weather.source, '暂无来源')}）"
    return f"{_text(weather.condition, '天气可用')}，{_text(weather.low_celsius, '-')}°C 至 {_text(weather.high_celsius, '-')}°C（来源：{_text(weather.source, '暂无来源')}）"


@dataclass(frozen=True)
class ExportActivity:
    time: str
    name: str
    description: str
    location: str
    cost: str
    poi: str
    route: str


@dataclass(frozen=True)
class ExportDay:
    date: str
    title: str
    weather: str
    advice: str
    activities: tuple[ExportActivity, ...]


@dataclass(frozen=True)
class ExportDocument:
    destination: str
    start_date: str
    end_date: str
    version: str
    summary: str
    total_cost: str
    map_status: str
    days: tuple[ExportDay, ...]


def _normalize_activity(activity: Activity) -> ExportActivity:
    poi = f"POI：{_text(activity.poi_id, '暂无来源')}；状态：{activity.poi_status}；地图来源：{_text(activity.map_source, '暂无来源')}"
    if activity.route_from_previous is None:
        route = f"路线：{activity.route_status}；来源：暂无来源"
    else:
        info = activity.route_from_previous
        route = f"路线：{info.mode} {info.distance_meters / 1000:.1f} km / {info.duration_seconds // 60} 分钟；来源：{_text(info.source, '暂无来源')}"
    return ExportActivity(
        _text(activity.time),
        _text(activity.name),
        _text(activity.description),
        _text(activity.location or activity.address),
        f"¥{activity.estimated_cost:g}",
        poi,
        route,
    )


def normalize_export(itinerary: Itinerary) -> ExportDocument:
    return ExportDocument(
        _text(itinerary.destination),
        itinerary.start_date.isoformat(),
        itinerary.end_date.isoformat(),
        _text(itinerary.version),
        _text(itinerary.summary),
        f"¥{itinerary.total_estimated_cost:g}",
        _text(itinerary.map_enrichment_status),
        tuple(
            ExportDay(
                day.date.isoformat(),
                _text(day.title),
                _weather_text(day.weather),
                "；".join(day.weather_advice) if day.weather_advice else "暂无建议",
                tuple(_normalize_activity(item) for item in day.activities),
            )
            for day in itinerary.days
        ),
    )


def render_markdown(itinerary: Itinerary) -> str:
    doc = normalize_export(itinerary)
    lines = [
        f"# {doc.destination}旅行行程",
        "",
        f"**日期**：{doc.start_date} 至 {doc.end_date}  ",
        f"**版本**：{doc.version}  ",
        f"**预计总费用**：{doc.total_cost}",
        "",
        doc.summary,
        "",
    ]
    for day in doc.days:
        lines += [
            f"## {day.date} · {day.title}",
            "",
            f"**天气**：{day.weather}",
            f"**天气建议**：{day.advice}",
            "",
        ]
        if not day.activities:
            lines += ["暂无安排。", ""]
        for item in day.activities:
            lines += [
                f"- **{item.time} {item.name}**：{item.description}",
                f"  - 地点：{item.location}；费用：{item.cost}",
                f"  - {item.poi}",
                f"  - {item.route}",
            ]
        lines.append("")
    lines += ["---", "", f"地图补全状态：{doc.map_status}", ""]
    return "\n".join(lines)


def safe_filename(destination: str, fmt: str) -> str:
    name = _SAFE_FILENAME.sub("_", destination).strip("._") or "trip"
    return f"{name}-行程.{fmt}"


def _p(value: str, *, br: bool = False) -> str:
    escaped = escape(value, quote=True)
    # Give ReportLab legal break opportunities for hostile or unspaced long text.
    escaped = "\u200b".join(escaped[index : index + 40] for index in range(0, len(escaped), 40))
    return escaped + ("<br/>" if br else "")


def _cell_text(value: str, limit: int = 600) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…（内容过长，已截断）"


def render_pdf(itinerary: Itinerary) -> bytes:
    if reportlab is None:
        raise RuntimeError("PDF 导出依赖未安装")
    font_name = _register_font("MiliTravelCJK")
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "MiliTitle",
        parent=styles["Title"],
        fontName=font_name,
        alignment=TA_CENTER,
        fontSize=20,
        leading=26,
        spaceAfter=10,
    )
    heading = ParagraphStyle(
        "MiliHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=14,
        leading=20,
        spaceBefore=10,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "MiliBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.5,
        leading=15,
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "MiliSmall",
        parent=body,
        fontSize=8.5,
        leading=13,
        textColor="#555555",
        wordWrap="CJK",
        splitLongWords=True,
    )
    doc = normalize_export(itinerary)
    story = [
        Paragraph(_p(f"{doc.destination}旅行行程"), title),
        Paragraph(
            _p(
                f"日期：{doc.start_date} 至 {doc.end_date} | 版本：{doc.version} | 预计总费用：{doc.total_cost}"
            ),
            body,
        ),
        Paragraph(_p(doc.summary), body),
        Spacer(1, 4 * mm),
    ]
    for day in doc.days:
        story += [
            Paragraph(_p(f"{day.date} · {day.title}"), heading),
            Paragraph(_p(f"天气：{day.weather}"), small),
            Paragraph(_p(f"天气建议：{day.advice}"), small),
        ]
        rows = [
            [
                Paragraph("时间", small),
                Paragraph("活动", small),
                Paragraph("地点与说明", small),
                Paragraph("来源与路线", small),
                Paragraph("费用", small),
            ]
        ]
        if day.activities:
            for item in day.activities:
                rows.append(
                    [
                        Paragraph(_p(item.time), small),
                        Paragraph(_p(item.name), small),
                        Paragraph(
                            _p(_cell_text(item.location), br=True)
                            + _p(_cell_text(item.description)),
                            small,
                        ),
                        Paragraph(
                            _p(_cell_text(item.poi), br=True) + _p(_cell_text(item.route)), small
                        ),
                        Paragraph(_p(item.cost), small),
                    ]
                )
        else:
            rows.append(
                [
                    Paragraph("-", small),
                    Paragraph("暂无安排", small),
                    Paragraph("暂无数据", small),
                    Paragraph("暂无来源", small),
                    Paragraph("¥0", small),
                ]
            )
        table = Table(rows, colWidths=[17 * mm, 30 * mm, 58 * mm, 57 * mm, 18 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("BACKGROUND", (0, 0), (-1, 0), "#E8EEF8"),
                    ("GRID", (0, 0), (-1, -1), 0.3, "#B8C2D1"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story += [table, Spacer(1, 4 * mm)]
    story.append(Paragraph(_p(f"地图补全状态：{doc.map_status}"), small))
    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"{doc.destination}旅行行程",
    ).build(story)
    return buffer.getvalue()


def _register_font(preferred_name: str) -> str:
    if preferred_name in pdfmetrics.getRegisteredFontNames():
        return preferred_name
    configured = os.getenv("MILITRAVEL_PDF_FONT", "").strip()
    path = (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[2] / "resources" / "fonts" / "msyh.ttc"
    )
    if not path.is_file():
        raise RuntimeError(f"PDF 中文字体资源不存在：{path}")
    try:
        pdfmetrics.registerFont(TTFont(preferred_name, str(path), subfontIndex=0))
    except (OSError, ValueError, IndexError) as exc:
        raise RuntimeError(f"PDF 中文字体资源无法加载：{path}") from exc
    return preferred_name


def content_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename) or "trip"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
