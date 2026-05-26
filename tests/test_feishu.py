# test_feishu.py — 飞书适配层基础测试
"""测试 feishu_format 核心功能（不依赖真实飞书 API）。"""

import pytest


class TestMessageSplitting:
    """长消息分段测试。"""

    def test_short_message_no_split(self):
        from feishu_format import split_long_message
        msg = "Hello world"
        parts = split_long_message(msg, max_chars=500)
        assert len(parts) == 1

    def test_long_message_splits(self):
        from feishu_format import split_long_message
        msg = "\n\n".join(["段落" + str(i) for i in range(50)])  # 50 paragraphs
        parts = split_long_message(msg, max_chars=200)
        assert len(parts) >= 2

    def test_no_crash_with_long_input(self):
        from feishu_format import split_long_message
        msg = "hello world\n" * 500
        parts = split_long_message(msg, max_chars=500)
        assert len(parts) >= 1


class TestHeaderDemotion:
    """标题降级测试。"""

    def test_h1_to_h4(self):
        from feishu_format import _demote_headings
        result = _demote_headings("# Title")
        assert "####" in result

    def test_h2_demoted(self):
        from feishu_format import _demote_headings
        result = _demote_headings("## Section")
        assert "#####" in result

    def test_no_header_unchanged(self):
        from feishu_format import _demote_headings
        result = _demote_headings("normal text")
        assert "normal text" in result


class TestTableConversion:
    """表格转换测试。"""

    def test_simple_table(self):
        from feishu_format import _convert_tables
        md = "| A | B |\n|:--|:--|\n| 1 | 2 |"
        result = _convert_tables(md)
        assert "A" in result
        assert "B" in result


class TestCodeBlockProtection:
    """代码块保护测试。"""

    def test_fenced_code_roundtrip(self):
        from feishu_format import _protect_code_blocks, _restore_code_blocks
        md = "text\n```python\nprint('hello')\n```\nmore"
        storage = []
        protected = _protect_code_blocks(md, storage)
        restored = _restore_code_blocks(protected, storage)
        assert "print('hello')" in restored


class TestStripMarkdown:
    """纯文本提取测试。"""

    def test_strip_basic(self):
        from feishu_format import strip_markdown_to_plain
        result = strip_markdown_to_plain("# Title\n**bold** text")
        assert "Title" in result
        assert "bold" in result


class TestOptimize:
    """optimize 集成测试。"""

    def test_optimize_no_crash(self):
        from feishu_format import optimize
        md = "# Title\n## Sub\nnormal text\n- list item"
        result = optimize(md)
        assert isinstance(result, str)
        assert len(result) > 0


class TestMentionParsing:
    """@提及解析测试。"""

    def test_mention_pattern(self):
        import re
        pattern = r'<at[^>]*user_id="([^"]+)"[^>]*>([^<]*)</at>'
        text = '<at user_id="ou_123">@user</at> hello'
        matches = re.findall(pattern, text)
        assert len(matches) == 1
        assert matches[0][0] == "ou_123"
