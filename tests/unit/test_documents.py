from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

from core.documents.generator import ReportWriter, comment_line
from core.schemas import CodeFile, MetaField, ReportDraft, Task
from core.screenshots.terminal_renderer import render_console

FIELDS = [MetaField(label=k, value=v) for k, v in [
    ("Student Name", "Asha Rao"), ("UID", "24BCS00001"), ("Branch", "BE-CSE"), ("Section/Group", "719-A"),
    ("Semester", "5th"), ("Date", "01/11/2026"), ("Subject Name", "Fundamentals of Image Processing"),
    ("Subject Code", "24CSH-305"), ("Faculty", "Dr. K"),
]]


def task(title="Easy Level", files=None):
    return Task(title=title, problem="Add two numbers.", objectives=["Use variables"], language="python",
                files=files or [CodeFile(name="main.py", code="print(1 + 2)")], output="3", status="passed")


def text_of(path):
    return "\n".join(p.text for p in Document(str(path)).paragraphs)


def test_single_task_uses_numbered_sections(tmp_path):
    shot = tmp_path / "c.png"
    render_console("3", shot, command="python main.py")
    draft = ReportDraft(experiment_no="1.1", title="Experiment 1.1", aim="Learn addition.", tasks=[task()],
                        learning_outcomes=["Added numbers."])
    out = ReportWriter().write("cu-cse", tmp_path / "r.docx", FIELDS, draft, [[(shot, 192)]], signature="Asha Rao - 24BCS00001")
    text = text_of(out)
    for expected in ("Experiment 1.1", "1.  Aim:", "Implementation/Code:", "Output:", "Learning Outcome:",
                     "# Asha Rao - 24BCS00001", "print(1 + 2)", "Faculty: Dr. K"):
        assert expected in text
    doc = Document(str(out))
    assert len(doc.inline_shapes) == 1
    # The department header survives even though the template's first section was removed.
    final = doc.element.body.find(qn("w:sectPr"))
    assert final.find(qn("w:headerReference")) is not None


def test_long_value_gets_its_own_line(tmp_path):
    draft = ReportDraft(experiment_no="2", aim="x", tasks=[task()])
    out = ReportWriter().write("cu-cse", tmp_path / "r.docx", FIELDS, draft, [[]])
    lines = [p.text for p in Document(str(out)).paragraphs[:9]]
    assert "Subject Name: Fundamentals of Image Processing" in lines


def test_several_tasks_get_headings_and_missing_output_is_flagged(tmp_path):
    draft = ReportDraft(experiment_no="3", aim="Exceptions.", tasks=[task("Easy Level"), task("Hard Level")])
    out = ReportWriter().write("plain", tmp_path / "r.docx", FIELDS[:2], draft, [[], []])
    text = text_of(out)
    assert "Easy Level" in text and "Hard Level" in text
    assert text.count("[Attach output screenshot]") == 2


def test_multi_file_code_is_labelled(tmp_path):
    files = [CodeFile(name="App.jsx", code="export default function App() {}"),
             CodeFile(name="main.jsx", code="render(<App />)")]
    draft = ReportDraft(experiment_no="1", aim="React.", tasks=[task(files=files)])
    text = text_of(ReportWriter().write("plain", tmp_path / "r.docx", FIELDS[:2], draft, [[]]))
    assert "App.jsx:" in text and "main.jsx:" in text


def test_comment_syntax_follows_the_file():
    assert comment_line("A", "python", "main.py") == "# A"
    assert comment_line("A", "html", "index.html") == "<!-- A -->"
    assert comment_line("A", "react", "App.css") == "/* A */"
    assert comment_line("A", "java", "Main.java") == "// A"


def test_console_render_size(tmp_path):
    w, h = render_console("line\n" * 5, tmp_path / "o.png", command="java Main")
    assert w >= 1040 and h > 200


def test_wrapped_code_lines_keep_their_indentation(tmp_path):
    code = "class A {\n    void run() {\n        System.out.println(1);\n    }\n}"
    t = task(files=[CodeFile(name="A.java", code=code)])
    t.language = "java"
    draft = ReportDraft(title="Experiment 2", aim="x", tasks=[t])
    out = ReportWriter().write("plain", tmp_path / "r.docx", FIELDS, draft, [[]])
    paras = {p.text: p.paragraph_format for p in Document(str(out)).paragraphs}
    outer, inner = paras["class A {"], paras["System.out.println(1);"]
    # Each line starts at its own indentation; a wrapped remainder hangs 4 characters further in.
    assert inner.left_indent - outer.left_indent == Pt(6 * 8)
    assert inner.first_line_indent == outer.first_line_indent == -Pt(6 * 4)


def test_long_output_is_cut_to_one_page():
    from core.screenshots.terminal_renderer import PAGE_LINES, fit_output

    out = fit_output("\n".join(f"row {i}" for i in range(500)))
    rows = out.split("\n")
    assert len(rows) == PAGE_LINES and rows[0] == "row 0" and rows[-1] == "row 499"
    assert any("more lines" in r for r in rows)
    assert fit_output("short\noutput") == "short\noutput"


def test_cu_header_is_a_picture_not_font_dependent_text(tmp_path):
    import zipfile

    out = ReportWriter().write("cu-cse", tmp_path / "r.docx", FIELDS,
                               ReportDraft(title="Experiment 1", aim="x", tasks=[task()]), [[]])
    z = zipfile.ZipFile(out)
    headers = [z.read(n).decode() for n in z.namelist() if n.startswith("word/header") and n.endswith(".xml")]
    assert headers and all("<wp:anchor" in h and "Impact" not in h and "<w:t>" not in h for h in headers)
