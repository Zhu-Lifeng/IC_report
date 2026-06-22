"""
report_gen.py — 从站点数据（property + report）生成 IC 报告 PDF

改编自 generate_report.py：不再读 xlsx，而是直接消费 Flask 端的 JSON 数据结构。

数据来源约定：
  prop     物业 {id, name, address, rooms:[{id,name,items:[{id,name,type,description}]}]}
  report   报告 {type:"check-in"|"check-out", createdAt, photos:{itemId:[url]},
                 texts:{itemId:{condition,comments}}}
  baseline check-out 时对应的 check-in 报告（check-in 时为 None）
  config   封面配置 dict（report_config.json）

编号规则：房间按顺序为第 1..N 节，条目为「节.项」（如 3.2）。
中文用 reportlab 内置 CID 字体 STSong-Light 渲染，无需外部字体文件。
"""
import os
from collections import OrderedDict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image,
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ── 中文字体注册（reportlab 内置，无需外部文件） ─────────────
_CJK = "STSong-Light"
try:
    pdfmetrics.registerFont(UnicodeCIDFont(_CJK))
except Exception:
    _CJK = "Helvetica"   # 极端情况下回退（中文会变方块，但不崩）

# ── 页面与样式 ──────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_L = MARGIN_R = 14 * mm
MARGIN_T = 22 * mm
MARGIN_B = 18 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

_S = getSampleStyleSheet()
H_COVER = ParagraphStyle("HCover", parent=_S["Heading1"], fontName=_CJK,
                         fontSize=24, leading=28, alignment=TA_CENTER, spaceAfter=10)
H_SEC = ParagraphStyle("HSec", parent=_S["Heading2"], fontName=_CJK,
                       fontSize=14, leading=18, spaceBefore=2, spaceAfter=6)
BODY = ParagraphStyle("Body", parent=_S["BodyText"], fontName=_CJK, fontSize=9, leading=12)
SMALL_CAP = ParagraphStyle("Cap", parent=_S["BodyText"], fontName=_CJK, fontSize=7.5,
                           leading=9, alignment=TA_CENTER, textColor=colors.HexColor("#555"))
CELL = ParagraphStyle("Cell", parent=_S["BodyText"], fontName=_CJK, fontSize=9, leading=11)
CELL_HDR = ParagraphStyle("CellH", parent=_S["BodyText"], fontName=_CJK, fontSize=9, leading=11)

TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
    ("FONTNAME", (0, 0), (-1, -1), _CJK),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#999")),
    ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#BBB")),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
])

NOTES_INV = (
    "本入住报告（Inventory & Check-In）记录租期开始时房屋的内容物与状况，"
    "包括交付的钥匙、各条目状况与清洁情况。租客在收到报告后 7 天内可提出书面异议或补充，"
    "逾期未回复则视为认可本报告为房屋状况的准确记录。"
)
NOTES_CO = (
    "本退房报告（Check-Out）为租期结束时的对比报告，列出租期内房屋发生的显著变化，"
    "包括损坏、缺失、遗留物品及需要的额外清洁。报告与照片用于评估押金扣减等事宜。"
)
DISCL = (
    "房屋的装修、固定装置与家具均被逐项描述并检查可见的明显缺陷或清洁问题。"
    "锁住的柜子、阁楼、未照明区域等不易触及之处不在检查范围内。电器仅测试通电与否。"
    "本报告不对任何结构、电器或服务的安全性作出保证。"
)


def P(t, style=CELL):
    if t is None or t == "":
        return ""
    return Paragraph(str(t).replace("\n", "<br/>"), style)


def make_table(rows, col_widths):
    body = [[P(c, CELL_HDR if ri == 0 else CELL) for c in r] for ri, r in enumerate(rows)]
    t = Table(body, colWidths=col_widths, repeatRows=1)
    t.setStyle(TABLE_STYLE)
    return t


def photo_grid(photos):
    """photos = list of (caption, abs_path)。4 列网格。"""
    photos = [(c, p) for c, p in photos if p and os.path.isfile(p)]
    if not photos:
        return Spacer(1, 1)
    cell_w = (CONTENT_W - 3 * 4 * mm) / 4
    img_w, img_h = cell_w, cell_w * 3 / 4
    rows, row = [], []
    for cap, path in photos:
        try:
            img = Image(path, width=img_w, height=img_h)
        except Exception:
            continue
        cell = Table([[img], [Paragraph(f"Ref # {cap}", SMALL_CAP)]], colWidths=[cell_w])
        cell.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        row.append(cell)
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        while len(row) < 4:
            row.append("")
        rows.append(row)
    if not rows:
        return Spacer(1, 1)
    grid = Table(rows, colWidths=[cell_w] * 4, hAlign="LEFT")
    grid.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return grid


class HeaderFooterCanvas(canvas.Canvas):
    def __init__(self, *args, header_left="", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []
        self._header_left = header_left

    def showPage(self):
        self._saved.append(dict(self.__dict__)); self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw(total)
            super().showPage()
        super().save()

    def _draw(self, total):
        if self._pageNumber == 1:
            return
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#333"))
        self.drawString(MARGIN_L, PAGE_H - 12 * mm, self._header_left)
        self.drawRightString(PAGE_W - MARGIN_R, 10 * mm, f"Page {self._pageNumber-1} of {total-1}")


# ── 数据辅助 ────────────────────────────────────────────────

def _abs_paths(upload_dir, urls):
    out = []
    for u in (urls or []):
        if not u:
            continue
        name = u.split("/uploads/")[-1] if "/uploads/" in u else u
        out.append(os.path.join(upload_dir, name))
    return out


def _date_str(iso):
    return (iso or "").split("T")[0]


# ── 各节构建 ────────────────────────────────────────────────

def _build_cover(story, prop, report, config):
    is_co = report["type"] == "check-out"
    title = "Check-Out Report" if is_co else "Inventory & Check-In Report"
    line2 = ", ".join(x for x in [prop.get("name", ""), prop.get("address", ""),
                                  config.get("postcode", "")] if x)
    story += [
        Spacer(1, 60 * mm),
        Paragraph(title, H_COVER),
        Paragraph(line2, ParagraphStyle("CA", parent=BODY, alignment=TA_CENTER, fontSize=12, leading=16)),
        Paragraph(_date_str(report.get("createdAt", "")),
                  ParagraphStyle("CD", parent=BODY, alignment=TA_CENTER, fontSize=11, spaceBefore=6)),
        Spacer(1, 20 * mm),
        Paragraph("On behalf of", ParagraphStyle("CL", parent=BODY, alignment=TA_CENTER, fontSize=9)),
        Paragraph(config.get("client", ""),
                  ParagraphStyle("CC", parent=BODY, alignment=TA_CENTER, fontSize=11, spaceBefore=2)),
        Spacer(1, 15 * mm),
        Paragraph("Created by", ParagraphStyle("CL2", parent=BODY, alignment=TA_CENTER, fontSize=9)),
        Paragraph(config.get("agent_name", ""),
                  ParagraphStyle("CN", parent=BODY, alignment=TA_CENTER, fontSize=11, spaceBefore=2)),
        Paragraph(config.get("agent_phone", ""), ParagraphStyle("CP", parent=BODY, alignment=TA_CENTER, fontSize=9)),
        Paragraph(config.get("agent_email", ""), ParagraphStyle("CE", parent=BODY, alignment=TA_CENTER, fontSize=9)),
        PageBreak(),
    ]


def _build_notes(story, is_co):
    story += [Paragraph("Notes", H_SEC), Paragraph(NOTES_CO if is_co else NOTES_INV, BODY),
              Spacer(1, 6 * mm),
              Paragraph("Disclaimers", H_SEC), Paragraph(DISCL, BODY), PageBreak()]


def _texts(report, item_id):
    return (report.get("texts", {}) or {}).get(item_id, {}) or {}


def _build_room_inv(story, sec, room, report, upload_dir):
    story += [Paragraph(f"{sec}. {room['name']}", H_SEC)]
    table = [["Ref", "Name", "Description", "Condition", "Comments"]]
    photos = []
    for j, it in enumerate(room["items"], start=1):
        ref = f"{sec}.{j}"
        tx = _texts(report, it["id"])
        table.append([ref, it.get("name", ""), it.get("description", ""),
                      tx.get("condition", ""), tx.get("comments", "")])
        for p in _abs_paths(upload_dir, report.get("photos", {}).get(it["id"])):
            photos.append((ref, p))
    story += [make_table(table, [16 * mm, 30 * mm, 50 * mm, 45 * mm, None]), Spacer(1, 4)]
    if photos:
        story += [photo_grid(photos)]
    story += [PageBreak()]


def _build_room_co(story, sec, room, report, baseline, upload_dir):
    story += [Paragraph(f"{sec}. {room['name']}", H_SEC)]
    table = [["Ref", "Name", "Description", "状况(入住时)", "状况(退房时)", "Comments"]]
    photos = []
    for j, it in enumerate(room["items"], start=1):
        ref = f"{sec}.{j}"
        tx_co = _texts(report, it["id"])
        tx_inv = _texts(baseline, it["id"]) if baseline else {}
        table.append([ref, it.get("name", ""), it.get("description", ""),
                      tx_inv.get("condition", ""), tx_co.get("condition", ""),
                      tx_co.get("comments", "")])
        # 退房对比照
        for p in _abs_paths(upload_dir, report.get("photos", {}).get(it["id"])):
            photos.append((ref, p))
    story += [make_table(table, [14 * mm, 26 * mm, 40 * mm, 38 * mm, 38 * mm, None]), Spacer(1, 4)]
    if photos:
        story += [photo_grid(photos)]
    story += [PageBreak()]


def _build_declaration(story, is_co):
    story += [
        Paragraph("Declaration", H_SEC),
        Paragraph("本人确认：如在收到报告后七日内未提出书面异议，则接受本报告为房屋于所述日期"
                  "内容物与状况的准确记录。", BODY),
        Spacer(1, 12 * mm),
        Paragraph("Tenant 签字: __________________________   日期: ____ / ____ / ______", BODY),
    ]


# ── 入口 ────────────────────────────────────────────────────

def build_report_pdf(prop, report, baseline, upload_dir, out_path, config=None):
    config = config or {}
    is_co = report["type"] == "check-out"
    header_left = ", ".join(x for x in [prop.get("name", ""), prop.get("address", "")] if x)
    header_left = (header_left + "    Date: " + _date_str(report.get("createdAt", ""))).strip()

    story = []
    _build_cover(story, prop, report, config)
    _build_notes(story, is_co)
    for i, room in enumerate(prop.get("rooms", []), start=1):
        if not room.get("items"):
            continue
        if is_co:
            _build_room_co(story, i, room, report, baseline, upload_dir)
        else:
            _build_room_inv(story, i, room, report, upload_dir)
    _build_declaration(story, is_co)

    def make_canvas(*a, **k):
        return HeaderFooterCanvas(*a, header_left=header_left, **k)

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=MARGIN_L, rightMargin=MARGIN_R,
                            topMargin=MARGIN_T, bottomMargin=MARGIN_B,
                            title=("Check-Out" if is_co else "Inventory") + " Report")
    doc.build(story, canvasmaker=make_canvas)
    return out_path
