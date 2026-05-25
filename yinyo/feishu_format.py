# feishu_format.py — Markdown 格式优化引擎 v1.0
# 对标 OpenClaw markdown-style.ts + Hermes feishu.py #9549
import re

# ── 常量 ─────────────────────────────────────────────────────────
CODE_BLOCK_MARK = '___CB_'
TABLE_BULLETS_THRESHOLD = 3  # ≤3 列用 bullets，>3 列用 code


# ── 公开 API ─────────────────────────────────────────────────────

def optimize(markdown: str) -> str:
    """主入口：飞书 Markdown 全流程优化。

    流程：代码块保护 → 标题降级 → 表格转换 → 列表规范化 → 代码块还原 → 压缩空行
    """
    if not markdown or not markdown.strip():
        return markdown

    code_blocks = []
    text = _protect_code_blocks(markdown, code_blocks)

    text = _demote_headings(text)
    text = _convert_tables(text)
    text = _normalize_lists(text)
    text = _restore_code_blocks(text, code_blocks)
    text = _compress_blank_lines(text)

    return text.strip()


def split_long_message(markdown: str, max_chars: int = 15000) -> list[str]:
    """长消息智能分段。段落边界切割 + 代码块完整性保护。

    Args:
        markdown: 要分段的 Markdown 文本
        max_chars: 单段最大字符数（飞书 Card 2.0 限制约 30KB，保守取 15K）

    Returns:
        分段列表，超长时自动加 (1/N) 标记
    """
    if len(markdown) <= max_chars:
        return [markdown]

    # 保护代码块
    code_blocks = []
    text = _protect_code_blocks(markdown, code_blocks)

    # 按段落分割
    paragraphs = text.split('\n\n')
    chunks = []
    current = ""

    for para in paragraphs:
        test = current + ('\n\n' if current else '') + para
        if len(test) <= max_chars:
            current = test
        else:
            if current:
                chunks.append(current)
            current = para if len(para) <= max_chars else _force_split(para, max_chars)

    if current:
        chunks.append(current)

    # 还原代码块
    result = []
    for chunk in chunks:
        chunk = _restore_code_blocks(chunk, code_blocks)
        result.append(chunk)

    # 分段标记
    if len(result) > 1:
        total = len(result)
        result = [f"({i+1}/{total})\n{r}" for i, r in enumerate(result)]

    return result


def strip_markdown_to_plain(text: str) -> str:
    """Markdown → 纯文本（Card 拒绝时降级用）。"""
    text = re.sub(r'#{1,6}\s+', '', text)       # 标题
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # 粗体
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # 斜体
    text = re.sub(r'`(.+?)`', r'\1', text)        # 行内代码
    text = re.sub(r'```[\s\S]*?```', '[代码块]', text)  # 代码块
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)     # 链接
    text = re.sub(r'!\[.*?\]\(.+?\)', '[图片]', text)   # 图片
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)  # 列表
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)   # 有序列表
    text = re.sub(r'\|.*?\|', '', text)             # 表格残留
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── 内部实现 ──────────────────────────────────────────────────────

def _protect_code_blocks(text: str, storage: list) -> str:
    """提取代码块到 storage，原位放占位符。返回处理后的文本。"""
    def _replace(m):
        storage.append(m.group(0))
        return f'{CODE_BLOCK_MARK}{len(storage) - 1}___'

    return re.sub(
        r'(^|\n)(```[^\n]*\n[\s\S]*?\n```)',
        lambda m: m.group(1) + _replace(m),
        text
    )


def _restore_code_blocks(text: str, storage: list) -> str:
    """还原代码块。"""
    for i, block in enumerate(storage):
        text = text.replace(f'{CODE_BLOCK_MARK}{i}___', block)
    return text


def _demote_headings(text: str) -> str:
    """标题降级：H1→H4，H2~H6→H5。

    对标 OpenClaw optimizeMarkdownStyle()：
    - 只降级以 # 开头的行标题（不处理 === 和 --- 风格）
    - 保证最小标题级别为 H4
    """
    has_h1_to_h3 = bool(re.search(r'^#{1,3} ', text, re.MULTILINE))
    if not has_h1_to_h3:
        return text

    # H2~H6 → H5（先处理，避免 H1→H4 后又被匹配）
    text = re.sub(r'^#{2,6} (.+)$', r'##### \1', text, flags=re.MULTILINE)
    # H1 → H4
    text = re.sub(r'^# (.+)$', r'#### \1', text, flags=re.MULTILINE)
    return text


def _convert_tables(text: str) -> str:
    """Markdown 表格 → 飞书兼容格式。

    飞书 md tag 不支持表格语法。对齐 OpenClaw convertMarkdownTables()：
    - ≤3 列 → bullet list（每行一条）
    - >3 列 → code block（保留表格结构）
    """
    table_re = re.compile(
        r'(?:^|\n)(\|.+\|[\t ]*\n\|[-| :]+\|[\t ]*\n(?:\|.+\|[\t ]*\n?)+)',
        re.MULTILINE
    )

    def _convert(m):
        table_text = m.group(1).strip()
        lines = [l for l in table_text.split('\n') if l.strip() and not re.match(r'^\|[-| :]+\|$', l)]

        if len(lines) < 2:
            return m.group(0)

        # 解析列数
        header = lines[0]
        cols = [c.strip() for c in header.split('|') if c.strip()]
        col_count = len(cols)

        if col_count <= TABLE_BULLETS_THRESHOLD:
            # 转换为 bullet list
            result = []
            for line in lines:
                cells = [c.strip() for c in line.split('|') if c.strip()]
                row_text = ', '.join(f'{cols[i]}: {cells[i]}' if i < len(cols)
                                     else cells[i] for i in range(len(cells)))
                result.append(f'• {row_text}')
            return '\n' + '\n'.join(result)
        else:
            # 转换为 code block
            return '\n```\n' + table_text + '\n```'

    return table_re.sub(_convert, text)


def _normalize_lists(text: str) -> str:
    """列表规范化。"""
    # 无序列表：- 后面的多个空格归一
    text = re.sub(r'^(-)\s{2,}', r'\1 ', text, flags=re.MULTILINE)
    # 有序列表：序号后确保一个空格
    text = re.sub(r'^(\d+)\.\s{2,}', r'\1. ', text, flags=re.MULTILINE)
    return text


def _compress_blank_lines(text: str) -> str:
    """压缩多余空行（3+ → 2）。"""
    return re.sub(r'\n{3,}', '\n\n', text)


def _force_split(text: str, max_chars: int) -> str:
    """强制在句子边界切割。"""
    if len(text) <= max_chars:
        return text
    # 尝试在句号/换行处切割
    cut = max_chars
    for sep in ['\n', '。', '. ', '；', '; ']:
        pos = text.rfind(sep, 0, max_chars)
        if pos > max_chars * 0.4:
            cut = pos + len(sep)
            break
    return text[:cut].strip()
