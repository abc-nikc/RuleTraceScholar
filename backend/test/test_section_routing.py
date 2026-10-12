"""Regression tests for deterministic section routing."""

from rag.integration import classify_section_title


def test_common_english_headings():
    assert classify_section_title("Abstract") == "background"
    assert classify_section_title("2 Related Work") == "background"
    assert classify_section_title("2 RELATEDWORK") == "background"
    assert classify_section_title("3.2 Model Architecture") == "method"
    assert classify_section_title("3.3 ONLINEINFERENCE:FUNNELRETRIEVAL") == "method"
    assert classify_section_title("4.4 RESULTS") == "experiment"
    assert classify_section_title("4.1 SETUP") == "experiment"
    assert classify_section_title("5.3 Limitations and Future Work") == "conclusion"


def test_common_chinese_headings():
    assert classify_section_title("1 引言") == "background"
    assert classify_section_title("3 方法与模型架构") == "method"
    assert classify_section_title("4 实验结果与消融") == "experiment"
    assert classify_section_title("6 局限与未来工作") == "conclusion"


def test_unknown_heading_remains_other():
    assert classify_section_title("Appendix A") == "other"
