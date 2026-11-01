import io
import zipfile

import pytest

from core.ingestion.extract import UnsupportedFile, condense, extract_text


def test_condense_drops_reading_material_but_keeps_sample_code():
    raw = (ROOT_SHEET := (
        "Experiment 3:\nAim: Build a calculator.\n\nEasy Level\nProblem Statement: add two numbers.\n\n"
        "Reading Material:\nJava was created in 1995. " + "Lots of tutorial text. " * 200 + "\n"
        "Sample Code:\nEasy Level\npublic class Add { public static void main(String[] a) {} }\n"
    ))
    text = condense(raw)
    assert "Aim: Build a calculator." in text
    assert "public class Add" in text
    assert "tutorial text" not in text
    assert len(text) < len(ROOT_SHEET) / 3


def test_condense_removes_word_export_blank_lines_and_links():
    raw = "Aim: x\n\nline one\n\nline two\n\nsee [docs](https://example.com/a)\n\n![img](a.png)\n"
    text = condense(raw)
    assert text == "Aim: x\nline one\nline two\nsee docs"


def test_sample_sheet_shrinks():
    raw = extract_text(open("examples/source-notes.md", "rb").read(), "source-notes.md")
    text = condense(raw)
    assert "Aim:" in text and "Hard Level" in text
    assert "Abstract Classes and Methods" not in text  # reading material is gone
    assert len(text) < 0.6 * len(raw)


def _pptx(slides: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i, text in enumerate(slides, start=1):
            xml = ('<p:sld xmlns:a="a" xmlns:p="p"><a:p><a:r><a:t>' + text + "</a:t></a:r></a:p></p:sld>")
            zf.writestr(f"ppt/slides/slide{i}.xml", xml)
    return buf.getvalue()


def test_pptx_slides_in_order():
    data = _pptx(["Experiment 2.1", "Aim: sort an array", "Write a program to sort numbers"] + ["x"] * 8)
    text = extract_text(data, "exp.pptx")
    assert text.index("Experiment 2.1") < text.index("Aim: sort an array")


def test_zip_project_skips_node_modules():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("exp/src/App.jsx", "export default function App() { return <h1>Hi</h1> }")
        zf.writestr("exp/node_modules/react/index.js", "module.exports = {}")
        zf.writestr("exp/package-lock.json", "{}")
    text = extract_text(buf.getvalue(), "project.zip")
    assert "file: exp/src/App.jsx" in text
    assert "node_modules" not in text and "package-lock" not in text


def test_unsupported_and_legacy_files_are_explained():
    with pytest.raises(UnsupportedFile, match="pptx"):
        extract_text(b"x", "slides.ppt")
    with pytest.raises(UnsupportedFile):
        extract_text(b"x", "movie.mp4")
