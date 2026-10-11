"""Deterministic Markdown and PDF rendering for stored itinerary versions."""

from __future__ import annotations

import io
import re
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
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError:  # pragma: no cover - exercised by dependency installation
    reportlab = None
else:
    reportlab = True

_SAFE_FILENAME: Final = re.compile(r"[^\w\-.\u4e00-\u9fff]+")


def _text(value: object | None, fallback: str = "暂无数据") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _weather_text(weather: WeatherInfo | None) -> str:
    if weather is None or weather.status == "unknown":
        return "天气未知"
    condition = _text(weather.condition, "天气可用")
    low = _text(weather.low_celsius, "-")
    high = _text(weather.high_celsius, "-")
    return f"{condition}，{low}°C 至 {high}°C"


def _activity_line(activity: Activity) -> str:
    details = [
        f"地点：{_text(activity.location or activity.address)}",
        f"费用：¥{activity.estimated_cost:g}",
    ]
    if activity.route_from_previous is not None:
        route = activity.route_from_previous
        details.append(
            f"路线：{route.mode} {route.distance_meters / 1000:.1f} km / {route.duration_seconds // 60} 分钟"
        )
    return f"- **{_text(activity.time)} {activity.name}**：{_text(activity.description)}（{'；'.join(details)}）"


def render_markdown(itinerary: Itinerary) -> str:
    lines = [
        f"# {_text(itinerary.destination)}旅行行程",
        "",
        f"**日期**：{itinerary.start_date.isoformat()} 至 {itinerary.end_date.isoformat()}  ",
        f"**版本**：{_text(itinerary.version)}  ",
        f"**预计总费用**：¥{itinerary.total_estimated_cost:g}",
        "",
        _text(itinerary.summary),
        "",
    ]
    for day in itinerary.days:
        lines.extend(
            [
                f"## {day.date.isoformat()} · {_text(day.title)}",
                "",
                f"**天气**：{_weather_text(day.weather)}",
                "",
            ]
        )
        if day.weather_advice:
            lines.append(f"**天气建议**：{'；'.join(day.weather_advice)}")
            lines.append("")
        if not day.activities:
            lines.extend(["暂无安排。", ""])
        else:
            lines.extend(_activity_line(activity) for activity in day.activities)
            lines.append("")
    lines.extend(["---", "", f"地图补全状态：{itinerary.map_enrichment_status}", ""])
    return "\n".join(lines)


def safe_filename(destination: str, fmt: str) -> str:
    name = _SAFE_FILENAME.sub("_", destination).strip("._") or "trip"
    return f"{name}-行程.{fmt}"


def render_pdf(itinerary: Itinerary) -> bytes:
    if reportlab is None:
        raise RuntimeError("PDF 导出依赖未安装")
    font_name = "MiliTravelCJK"
    font_name = _register_font(font_name)
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
    small = ParagraphStyle("MiliSmall", parent=body, fontSize=8.5, leading=13, textColor="#555555")
    story = [
        Paragraph(f"{_text(itinerary.destination)}旅行行程", title),
        Paragraph(
            f"日期：{itinerary.start_date} 至 {itinerary.end_date} | 版本：{_text(itinerary.version)} | 预计总费用：¥{itinerary.total_estimated_cost:g}",
            body,
        ),
        Paragraph(_text(itinerary.summary), body),
        Spacer(1, 4 * mm),
    ]
    for day in itinerary.days:
        story.append(Paragraph(f"{day.date} · {_text(day.title)}", heading))
        story.append(Paragraph(f"天气：{_weather_text(day.weather)}", small))
        if day.weather_advice:
            story.append(Paragraph(f"天气建议：{'；'.join(day.weather_advice)}", small))
        rows = [
            [
                Paragraph("时间", small),
                Paragraph("活动", small),
                Paragraph("地点与说明", small),
                Paragraph("费用", small),
            ]
        ]
        for activity in day.activities:
            rows.append(
                [
                    Paragraph(_text(activity.time), small),
                    Paragraph(_text(activity.name), small),
                    Paragraph(
                        f"{_text(activity.location or activity.address)}<br/>{_text(activity.description)}",
                        small,
                    ),
                    Paragraph(f"¥{activity.estimated_cost:g}", small),
                ]
            )
        if not day.activities:
            rows.append(
                [
                    Paragraph("-", small),
                    Paragraph("暂无安排", small),
                    Paragraph("暂无数据", small),
                    Paragraph("¥0", small),
                ]
            )
        table = Table(rows, colWidths=[20 * mm, 35 * mm, 105 * mm, 20 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("BACKGROUND", (0, 0), (-1, 0), "#E8EEF8"),
                    ("GRID", (0, 0), (-1, -1), 0.3, "#B8C2D1"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([table, Spacer(1, 4 * mm)])
    story.append(Paragraph(f"地图补全状态：{itinerary.map_enrichment_status}", small))
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"{itinerary.destination}旅行行程",
    )
    doc.build(story)
    return buffer.getvalue()


def _register_font(preferred_name: str) -> str:
    """Register an available CJK font, with a portable PDF-safe fallback."""
    if preferred_name in pdfmetrics.getRegisteredFontNames():
        return preferred_name
    candidates = [
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/msyh.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    candidates.extend(Path("/usr/share/fonts").glob("**/*NotoSansCJK*.ttf"))
    candidates.extend(Path("/usr/share/fonts").glob("**/*wqy*.ttf"))
    for path in candidates:
        if not path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(preferred_name, str(path)))
            return preferred_name
        except (OSError, ValueError, IndexError):
            continue
    return "Helvetica"


def content_disposition(filename: str) -> str:
    """Return an RFC 5987 header safe for Starlette's latin-1 header encoding."""
    ascii_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename) or "trip"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
