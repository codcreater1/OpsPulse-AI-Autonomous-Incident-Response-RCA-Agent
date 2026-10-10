"""The README demo recording is generated, so its renderer must stay safe and honest."""

import xml.dom.minidom

from scripts.render_demo_svg import COMMAND, main

LOCAL_PATH = "report: C:/Users/someone/private/path.json"
RAW = "\n".join(
    ["=== 1. tests", "1 failed, 2 passed in 0.1s", LOCAL_PATH]
    + ["<b>&\"' markup in a log line"] * 8
    + ["RESULT: tests pass after the proposed patch"]
)


def test_render_is_valid_xml_escapes_markup_and_drops_local_paths(tmp_path):
    src, out = tmp_path / "demo.txt", tmp_path / "demo.svg"
    src.write_text(RAW, encoding="utf-8")
    assert main(["--input", str(src), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "someone" not in text and "private" not in text  # the local report path is never published
    assert "&lt;b&gt;" in text and "<b>" not in text
    assert COMMAND in text and "MOCK" in text  # the recording says the model is scripted
    parsed = xml.dom.minidom.parseString(text)  # noqa: S318 - parsing our own generated file
    assert len(parsed.getElementsByTagName("text")) > 5


def test_nothing_is_written_for_an_empty_capture(tmp_path):
    src, out = tmp_path / "empty.txt", tmp_path / "demo.svg"
    src.write_text("\n", encoding="utf-8")
    assert main(["--input", str(src), "--out", str(out)]) == 1 and not out.exists()
