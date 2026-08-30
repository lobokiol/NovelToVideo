from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


WIDTH = 3840
HEIGHT = 2160
OUTPUT = Path(__file__).with_name("novel-import-flowchart-4k.png")

FONT_REGULAR = r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf"
FONT_MEDIUM = r"C:\Windows\Fonts\Noto Sans SC Medium (TrueType).otf"
FONT_BOLD = r"C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf"
FONT_MONO = r"C:\Windows\Fonts\CascadiaMono.ttf"
if not Path(FONT_MONO).exists():
    FONT_MONO = r"C:\Windows\Fonts\consola.ttf"


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


TITLE_FONT = load_font(FONT_BOLD, 58)
SUBTITLE_FONT = load_font(FONT_REGULAR, 25)
PANEL_FONT = load_font(FONT_BOLD, 33)
NODE_TITLE_FONT = load_font(FONT_BOLD, 27)
NODE_BODY_FONT = load_font(FONT_REGULAR, 21)
MONO_FONT = load_font(FONT_MONO, 18)
PILL_FONT = load_font(FONT_MEDIUM, 21)
FOOTER_FONT = load_font(FONT_REGULAR, 18)

BACKGROUND = (12, 15, 19)
PANEL_BACKGROUND = (20, 25, 31)
PANEL_BORDER = (62, 72, 84)
TEXT = (235, 241, 247)
MUTED = (157, 169, 183)
GRID = (27, 34, 42)

COLORS = {
    "manual": ((20, 66, 64), (62, 211, 183), (169, 244, 226)),
    "crawl": ((24, 49, 86), (96, 165, 250), (198, 221, 255)),
    "backend": ((61, 42, 74), (196, 144, 255), (235, 216, 255)),
    "storage": ((78, 59, 18), (245, 158, 11), (255, 232, 171)),
    "guard": ((78, 38, 38), (248, 113, 113), (255, 210, 210)),
}


image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
draw = ImageDraw.Draw(image)


def text_size(text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_line(line: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not line:
        return [""]
    if " " in line and sum(1 for char in line if ord(char) < 128) > len(line) * 0.45:
        words = line.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if text_size(candidate, font)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        wrapped: list[str] = []
        for item in lines:
            if text_size(item, font)[0] <= max_width:
                wrapped.append(item)
            else:
                wrapped.extend(wrap_line(item.replace(" ", ""), font, max_width))
        return wrapped

    lines = []
    current = ""
    for char in line:
        candidate = current + char
        if text_size(candidate, font)[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    result: list[str] = []
    for raw_line in text.split("\n"):
        result.extend(wrap_line(raw_line, font, max_width))
    return result


def rounded_panel(x: int, y: int, width: int, height: int, title: str, subtitle: str | None = None) -> None:
    draw.rounded_rectangle(
        (x, y, x + width, y + height),
        radius=30,
        fill=PANEL_BACKGROUND,
        outline=PANEL_BORDER,
        width=2,
    )
    draw.text((x + 28, y + 22), title, font=PANEL_FONT, fill=TEXT)
    if subtitle:
        draw.text((x + 28, y + 66), subtitle, font=FOOTER_FONT, fill=MUTED)


def node(
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    body: str,
    kind: str = "manual",
    tag: str | None = None,
) -> None:
    base, stroke, foreground = COLORS[kind]
    fill = tuple(max(0, int(channel * 0.72)) for channel in base)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=18, fill=fill, outline=stroke, width=2)
    draw.rectangle((x, y, x + 10, y + height), fill=stroke)
    draw.text((x + 24, y + 16), title, font=NODE_TITLE_FONT, fill=foreground)
    if tag:
        tag_width, _ = text_size(tag, MONO_FONT)
        draw.rounded_rectangle(
            (x + width - tag_width - 36, y + 16, x + width - 18, y + 47),
            radius=14,
            fill=(13, 17, 22),
            outline=stroke,
            width=1,
        )
        draw.text((x + width - tag_width - 27, y + 18), tag, font=MONO_FONT, fill=foreground)

    y_cursor = y + 56
    for line in wrap_text(body, NODE_BODY_FONT, width - 48):
        draw.text((x + 24, y_cursor), line, font=NODE_BODY_FONT, fill=TEXT)
        y_cursor += 29


def arrow(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple[int, int, int] = (137, 151, 168),
    label: str | None = None,
    bend: tuple[int, int] | None = None,
) -> None:
    import math

    points = [(x1, y1), (x2, y2)] if bend is None else [(x1, y1), bend, (x2, y2)]
    draw.line(points, fill=color, width=4, joint="curve")
    previous_x, previous_y = points[-2]
    angle = math.atan2(y2 - previous_y, x2 - previous_x)
    size = 14
    left = (x2 - size * math.cos(angle - 0.45), y2 - size * math.sin(angle - 0.45))
    right = (x2 - size * math.cos(angle + 0.45), y2 - size * math.sin(angle + 0.45))
    draw.polygon([(x2, y2), left, right], fill=color)
    if label:
        label_x = (x1 + x2) / 2 if bend is None else bend[0]
        label_y = (y1 + y2) / 2 if bend is None else bend[1]
        label_width, label_height = text_size(label, MONO_FONT)
        draw.rounded_rectangle(
            (
                label_x - label_width / 2 - 12,
                label_y - label_height / 2 - 8,
                label_x + label_width / 2 + 12,
                label_y + label_height / 2 + 8,
            ),
            radius=10,
            fill=(12, 15, 19),
            outline=color,
            width=1,
        )
        draw.text((label_x - label_width / 2, label_y - label_height / 2 - 1), label, font=MONO_FONT, fill=(225, 232, 240))


def draw_header() -> None:
    for x in range(0, WIDTH, 80):
        draw.line((x, 0, x, HEIGHT), fill=GRID, width=1)
    for y in range(0, HEIGHT, 80):
        draw.line((0, y, WIDTH, y), fill=GRID, width=1)

    draw.rounded_rectangle(
        (54, 42, WIDTH - 54, 230),
        radius=28,
        fill=(17, 22, 28),
        outline=(64, 74, 88),
        width=2,
    )
    draw.text((92, 68), "当前项目小说导入完整流程图", font=TITLE_FONT, fill=TEXT)
    draw.text(
        (92, 142),
        "基于实际代码梳理：全文导入、小说爬取、来源管理、预览过滤、流式爬取、后端入库、缓存与异常边界",
        font=SUBTITLE_FONT,
        fill=MUTED,
    )

    evidence_x, evidence_y, evidence_width, evidence_height = 2380, 70, 1340, 112
    draw.rounded_rectangle(
        (evidence_x, evidence_y, evidence_x + evidence_width, evidence_y + evidence_height),
        radius=18,
        fill=(24, 30, 38),
        outline=(78, 92, 110),
        width=2,
    )
    draw.text((evidence_x + 24, evidence_y + 18), "代码证据文件", font=PILL_FONT, fill=(215, 226, 240))
    evidence = (
        "Novel.vue / NovelImportDialog.vue / NovelCrawlDialog.vue / api/novel.ts / request/index.ts / "
        "routers·services·schemas·models/novel.py / novel_crawler.py"
    )
    draw.text((evidence_x + 24, evidence_y + 55), evidence, font=FOOTER_FONT, fill=MUTED)

    legend = [
        ("manual", "全文导入"),
        ("crawl", "小说爬取"),
        ("backend", "后端服务"),
        ("storage", "数据落点"),
        ("guard", "校验/异常"),
    ]
    x_cursor = 92
    for key, label in legend:
        fill, stroke, foreground = COLORS[key]
        draw.rounded_rectangle((x_cursor, 185, x_cursor + 150, 217), radius=16, fill=fill, outline=stroke, width=2)
        draw.text((x_cursor + 18, 187), label, font=FOOTER_FONT, fill=foreground)
        x_cursor += 170


def draw_manual_import() -> None:
    rounded_panel(72, 260, 1116, 1530, "A. 全文导入", "当前 UI 发送预览章节草稿；后端仍保留 rawText 解析兜底")
    x, width = 118, 1024
    nodes: list[tuple[int, int, str, str, str, str]] = [
        (340, 122, "1. 打开全文导入", "Novel.vue 点击“全文导入” → ensureProjectReady；弹出 NovelImportDialog。", "manual", "UI"),
        (492, 140, "2. 加载切分规则", "对话框可见时 GET /import-split-rules；服务端返回内置规则；自定义切分规则写入 localStorage。", "manual", "GET"),
        (662, 158, "3. 输入或解析文件", "支持粘贴全文，或上传 .txt / .docx / .pdf；.txt 自动识别 UTF-8/GBK；文件大小限制 ≤ 10MB。", "manual", "FE"),
        (850, 150, "4. 可选正文过滤", "启用正则规则移除网址、域名、广告/水印、邮箱、乱码、多余空行；可恢复最近一次过滤前原文。", "manual", "FE"),
        (1030, 172, "5. 前端预览切章", "parseNovelText 使用当前规则识别卷次、章节、裸数字标题；跳过短标题元信息；仅保留“标题 + 正文”章节，并提示过短/过长。", "manual", "FE"),
        (1232, 138, "6. 选择并提交草稿", "进入预览后默认全选；确认时 emit selected drafts；Novel.vue trim 后过滤空标题/空正文。", "manual", "emit"),
        (1400, 132, "7. 后端全文入库", "POST /projects/{id}/novels/import；校验项目权限；优先使用 chapters，否则 raw_text 走后端 parser。", "backend", "POST"),
        (1562, 162, "8. 创建 NovelChapter", "从 _next_chapter_index 续排；event=''、event_state=0、error_reason=None；crawl_md5=正文 MD5；commit 后返回章节记录。", "storage", "DB"),
    ]
    previous: tuple[int, int] | None = None
    for y, height, title, body, kind, tag in nodes:
        node(x, y, width, height, title, body, kind, tag)
        if previous:
            arrow(x + width // 2, previous[0] + previous[1], x + width // 2, y - 8, color=COLORS[kind][1])
        previous = (y, height)
    arrow(x + width, 1466, 1220, 1466, color=(140, 156, 178), label="POST /import")


def draw_crawl_import() -> None:
    rounded_panel(1220, 260, 2550, 1530, "B. 小说爬取导入", "来源配置驱动 HTTP JSON 接口，前端使用 NDJSON 流式爬取通道")
    client_x, client_width = 1270, 1166
    client_nodes: list[tuple[int, int, str, str, str, str]] = [
        (340, 150, "1. 来源准备与管理", "打开爬取弹窗或来源管理时加载 GET /crawl-sources；列表含 public + 当前项目 private；创建/编辑/删除后端只作用项目私有来源；可复制可见来源为私有。", "crawl", "sources"),
        (530, 148, "2. 搜索小说", "选择来源 + 输入关键词；先查 localStorage 搜索缓存，未命中才 POST /crawl/search；可清空“当前来源 + 关键词”缓存。", "crawl", "cache"),
        (720, 184, "3. 选择书籍并补全信息", "点击结果后保存选中书；若未加载详情则 POST /crawl/book-detail；若章节总数未知则 POST /crawl/book-chapter-count；默认结束章从 20 调整为总章数。", "crawl", "detail"),
        (950, 190, "4. 配置范围并发起爬取", "校验项目、来源、已选书籍、起止范围和最大章数；开始爬取清空旧草稿；继续爬取从已抓取最大 key + 1 开始。", "crawl", "range"),
        (1190, 174, "5. 前端读取流式进度", "命中章节缓存则直接恢复；否则 fetchWithAuthRetry + AbortController 读取 NDJSON；按 start/chapter/done/error 更新进度、upsert 并排序草稿。", "crawl", "stream"),
        (1408, 218, "6. 预览、过滤、清洗、移除", "进入预览默认全选；可按章节预览；过滤会重置 md5/event/eventState/errorReason；“清洗事件”为前端占位生成，正文 <80 字标记失败。", "crawl", "preview"),
        (1660, 100, "7. 确认导入", "检查已选章节和选中小说后 emit(drafts, book)，关闭爬取弹窗。", "crawl", "emit"),
    ]
    previous: tuple[int, int] | None = None
    for y, height, title, body, kind, tag in client_nodes:
        node(client_x, y, client_width, height, title, body, kind, tag)
        if previous:
            arrow(client_x + client_width // 2, previous[0] + previous[1], client_x + client_width // 2, y - 8, color=COLORS[kind][1])
        previous = (y, height)

    backend_x, backend_width = 2520, 1190
    backend_nodes: list[tuple[int, int, str, str, str, str]] = [
        (340, 150, "来源可见性与配置校验", "service 先取项目并校验权限；来源必须未禁用，且 scope=public 或 project_id=当前项目；sourceType 固定 api，Method 仅 GET/POST/PUT/PATCH/DELETE。", "backend", "svc"),
        (530, 148, "novel_crawler.search_books", "用 {q}/{keyword}/{sort} 渲染 URL/Body；请求必须返回 JSON；用简化 JSONPath 抽取 dirid/title/author/cover/lastchapter 等。", "backend", "JSON"),
        (720, 184, "详情与章节总数", "详情接口可选，未配置则返回原 book；章节列表接口可选，未配置则按 book.lastchapterid 生成 fallback metas；详情/总数会 upsert 爬取小说快照。", "backend", "book"),
        (950, 266, "流式爬取章节正文", "POST /crawl/chapters/stream 返回 application/x-ndjson；先取章节列表并切片 start/end；并发协程请求章节正文接口；字段来自章节列表或正文接口 JSONPath。", "backend", "NDJSON"),
        (1254, 326, "爬取章节入库服务", "POST /crawl/import：先 upsert CrawlBook；按 key/chapterid 排序；空标题或空正文 skipped；用 项目+来源+小说dirid+章节id 查重；未变化 skipped，变化则更新，否则新增。", "backend", "import"),
        (1620, 140, "前端刷新结果", "返回 created/updated/skipped/chapters；Novel.vue 提示统计，若新增则调整页码，随后 fetchNovels() 重新拉章节列表。", "crawl", "refresh"),
    ]
    for y, height, title, body, kind, tag in backend_nodes:
        node(backend_x, y, backend_width, height, title, body, kind, tag)

    endpoint_arrows = [
        (client_x + client_width, 604, backend_x, 604, "POST /crawl/search"),
        (client_x + client_width, 812, backend_x, 812, "detail / count"),
        (client_x + client_width, 1038, backend_x, 1080, "POST /crawl/chapters/stream"),
        (client_x + client_width, 1708, backend_x, 1418, "POST /crawl/import"),
    ]
    for x1, y1, x2, y2, label in endpoint_arrows:
        arrow(x1 + 12, y1, x2 - 12, y2, color=(140, 156, 178), label=label)

    arrow(backend_x + backend_width // 2, 490, backend_x + backend_width // 2, 522, color=COLORS["backend"][1])
    arrow(backend_x + backend_width // 2, 678, backend_x + backend_width // 2, 712, color=COLORS["backend"][1])
    arrow(backend_x + backend_width // 2, 904, backend_x + backend_width // 2, 942, color=COLORS["backend"][1])
    arrow(backend_x + backend_width // 2, 1216, backend_x + backend_width // 2, 1246, color=COLORS["backend"][1])
    arrow(backend_x + backend_width // 2, 1580, backend_x + backend_width // 2, 1612, color=COLORS["backend"][1])

    strip_y = 1798
    draw.rounded_rectangle((1220, strip_y, 3770, 1820), radius=11, fill=(28, 35, 44), outline=(80, 93, 110), width=1)
    cache_note = (
        "缓存与异常边界：localStorage key 前缀 novel-crawl-cache:v1；搜索缓存按 项目+来源+关键词，章节缓存按 "
        "项目+来源+dirid+start+end；流式爬取可取消，服务端异常转为 error 事件；axios/fetch 都带 JWT，401 时尝试刷新 token。"
    )
    draw.text((1244, strip_y - 1), cache_note, font=FOOTER_FONT, fill=(203, 215, 229))


def draw_storage() -> None:
    rounded_panel(72, 1830, 3698, 260, "C. 统一结果与数据落点", "两条入口最终都刷新 Novel.vue 的章节列表")
    boxes = [
        (118, 920, "af_novel_chapter", "最终章节表；全文导入新增；爬取导入按 crawl identity 更新/跳过/新增；保存 chapter_index、reel、正文、事件状态、crawl_* 元数据。"),
        (1068, 760, "af_novel_crawl_book", "爬取书籍快照；详情、章节总数和导入时 upsert；保存来源书籍 ID、标题、作者、分类、最新章节、raw_data。"),
        (1858, 770, "af_novel_crawl_source", "来源配置表；公共来源 + 项目私有来源；保存 URL 模板、HTTP Method、Headers/Body、各类 JSONPath。"),
        (2658, 1030, "Novel.vue 列表刷新", "导入成功后 fetchNovels()；按 chapter_index/id 排序分页；搜索框只按章节标题/卷次后端过滤。"),
    ]
    for x, width, title, body in boxes:
        node(x, 1910, width, 130, title, body, "storage", "data")

    arrow(118 + 1024 // 2, 1724, 500, 1902, color=COLORS["storage"][1], label="created")
    arrow(2520 + 1190 // 2, 1760, 780, 1902, color=COLORS["storage"][1], label="created / updated / skipped", bend=(2350, 1848))
    arrow(3300, 1760, 3300, 1902, color=COLORS["crawl"][1], label="fetchNovels()")

    note_y = 2098
    draw.rounded_rectangle((72, note_y, 3770, note_y + 42), radius=16, fill=(18, 23, 29), outline=(60, 72, 88), width=1)
    footer = (
        "核对结论：AI 分割/过滤按钮为禁用或占位；来源 AI 分析只返回 pending 草稿；UI 当前全文导入发送 chapters 而不是 rawText；"
        "公共来源编辑/删除按钮即使显示，也受后端“仅项目私有来源可改”约束。"
    )
    draw.text((96, note_y + 8), footer, font=FOOTER_FONT, fill=(213, 222, 234))


def draw_resolution_tag() -> None:
    resolution = "PNG 3840 x 2160"
    tag_width, _ = text_size(resolution, MONO_FONT)
    draw.rounded_rectangle(
        (WIDTH - tag_width - 112, HEIGHT - 68, WIDTH - 72, HEIGHT - 34),
        radius=14,
        fill=(12, 15, 19),
        outline=(94, 109, 128),
        width=1,
    )
    draw.text((WIDTH - tag_width - 92, HEIGHT - 63), resolution, font=MONO_FONT, fill=(180, 196, 215))


def main() -> None:
    draw_header()
    draw_manual_import()
    draw_crawl_import()
    draw_storage()
    draw_resolution_tag()
    image.save(OUTPUT, format="PNG", optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
