# Template Analysis

This analysis is based on the inspected reference files copied into `examples/`:

- `experiment-source.txt`: copied from `Sample_Experiment_Source_File.txt`; this file is empty.
- `source-notes.md`: copied from `Source_HTML_File.md`; this contains the actual experiment content discovered during inspection.
- `sample-report.docx`: copied from `Sample_Report_docx.docx`.
- `sample-report.pdf`: copied from `Sample_report_PDF.pdf`.

No reference file was modified during inspection.

## Experiment Source Structure

The usable experiment source is the Markdown/LMS export in `source-notes.md`. It contains:

- Heading: `Experiment-1.3`
- A `Completion requirements` line
- `Experiment 3:`
- CO mapping: `CO2,CO3`
- `Aim`
- `Easy Level`, `Medium Level`, and `Hard Level` problem statements
- Overall `Objective`
- `Input/Apparatus Used`
- `Reading Material`
- `Sample Code`
- Easy, Medium, and Hard Java code blocks represented as Markdown/plain text
- Output image links for Easy and Medium levels

The root text source that became `experiment-source.txt` is zero bytes, so future ingestion must not assume it is authoritative unless a populated version is supplied.

## Metadata Fields

The final DOCX contains these student metadata fields:

| Field | Observed value |
| --- | --- |
| Student Name | Mohammad Taha |
| UID | 24BCS12733 |
| Branch | BE-CSE |
| Section/Group | 719-A, with quote glyphs around A in the DOCX extraction |
| Semester | 5th |
| Date | 01/09/2026 |

The final DOCX contains these subject metadata fields:

| Field | Observed value |
| --- | --- |
| Subject Name | PBLJ |
| Subject Code | 24CSH-301 |

The source notes contain this experiment metadata:

| Field | Observed value |
| --- | --- |
| Experiment label | Experiment-1.3 |
| Report title | Experiment 3 |
| CO mapping | CO2, CO3 |
| Aim | Design Java programs showcasing exception handling through square root calculations, an ATM withdrawal system, and a university enrollment system with custom exceptions. |

The CO mapping appears in the source notes but was not found in the final DOCX body text.

## Report Sections

The final DOCX body follows this order:

1. `Experiment 3`
2. Student and subject metadata lines
3. `Aim`
4. `EASY LEVEL`
5. Easy problem statement
6. Easy objectives
7. Easy code
8. Easy output screenshot
9. `Problem -2`, which corresponds to the Medium level content
10. Medium problem statement
11. Medium objectives
12. Medium code
13. Medium output screenshot
14. `Hard Level`
15. Hard problem statement
16. Hard objectives
17. Hard code
18. Hard output screenshot
19. `5. Learning Outcome:`
20. Learning outcome bullets

## Easy, Medium, and Hard Structure

Each level in the final report contains:

- A visible level heading
- A problem statement
- An objective block
- A `Code:` heading
- Java code as one paragraph per line
- An `Output:` heading
- A terminal screenshot image

The final DOCX labels the second level as `Problem -2` rather than `Medium Level`. Future code should preserve the template label unless a deliberate template update is approved.

## Code Placement

Java code appears directly in the document body as plain Word paragraphs using the `Body Text` style. It is not stored in tables, fenced code blocks, or content controls. The inspected DOCX has 309 direct body paragraphs and no body tables.

The code in the final DOCX is not a byte-for-byte copy of the source notes. For example, the final Medium code includes a positive withdrawal amount check, and the final Hard code uses `Course coreJava = new Course("Core Java", 2, "")`, while the source notes show a capacity of 3. Future generation must treat the experiment source as authoritative and should record any intentional changes.

## Output Placement

Output screenshots appear immediately after an `Output:` heading for each level:

| Level | DOCX image | Native dimensions | Inserted size from DOCX XML |
| --- | --- | --- | --- |
| Easy | `image1.png` | 757 x 141 px | about 6.31 x 1.18 in |
| Medium | `image2.png` | 675 x 315 px | about 5.63 x 2.63 in |
| Hard | `image5.png` | 775 x 218 px | about 6.46 x 1.82 in |

The screenshots show terminal runs. Easy shows input `67` and a square-root result. Medium shows both an invalid PIN case and a successful withdrawal case. Hard shows a successful Advanced Java enrollment case.

The source notes include output image links for Easy and Medium. A Hard output link was not found in `source-notes.md`, but the final DOCX contains a Hard output screenshot.

## Learning Outcomes

Learning outcomes appear at the end of the final report under `5. Learning Outcome:`. The section contains bullet-style paragraphs covering Java exception handling, `try`, `catch`, `finally`, invalid input, `throw`, custom exceptions, multiple catch blocks, `throws`, and applying exception handling to calculators, ATMs, and university enrollment.

No learning outcome section was found in the source notes. This means learning outcomes are likely generated or supplied by another source before DOCX population.

## Formatting Characteristics

Observed DOCX/PDF characteristics:

- PDF page count: 9 pages.
- PDF page size: US Letter, 612 x 792 points.
- DOCX page size: 12240 x 15840 twips, matching US Letter.
- DOCX margins: top 1880 twips, right 1080 twips, bottom 280 twips, left 1440 twips.
- Header margin: 366 twips.
- Repeated header includes Chandigarh University logo imagery and `Discover. Learn. Empower.` branding.
- Normal style uses Times New Roman.
- `Body Text` is 12 pt.
- `Heading 1` is bold, 14 pt, with left indent.
- `List Paragraph` uses a left indent and hanging indent.
- Body content is flowing paragraph text, not a table-based form.
- The DOCX has no explicit page breaks; pagination is driven by content flow and image sizing.
- The PDF metadata reports Microsoft Word as creator/producer and 9 pages.

## Dynamic vs Static Content

Likely static template content:

- University header branding
- Page geometry and margins
- Heading styles
- General section order
- The template label style, including the observed `Problem -2` medium section label

Likely dynamic content:

- Student metadata
- Subject metadata if the user changes course context
- Experiment number/title
- Aim
- Problem statements
- Objectives
- Java code
- Program output text
- Output screenshots
- Learning outcomes

## Python-docx Risks and Limitations

- The source DOCX appears to be a converted Word report rather than a clean semantic template with content controls.
- Since content is flowing paragraphs, changes in code length or screenshot dimensions can change pagination.
- `python-docx` can preserve existing headers when editing a copy, but header images and relationship IDs must be handled carefully.
- `python-docx` does not provide a full layout engine. Final validation must render DOCX/PDF pages and inspect for clipping, overlap, and pagination drift.
- The template uses direct paragraphs for code rather than a semantic code block style. A future generator should define stable code formatting rules before replacing code.
- The bottom margin is very small, so page overflow risk is high.
- Encoding artifacts and quote glyphs appear in extracted source/report text. Future parsing should normalize text carefully without silently changing requirements.
- The DOCX and source notes differ in some code details. The pipeline must record source-vs-generated differences and should not silently override Easy, Medium, or Hard requirements.
