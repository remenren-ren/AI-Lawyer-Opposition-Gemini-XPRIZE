import html
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUN_DIR = HERE / "runs" / "independent_18_dimension_experiment_20260713_123822"


def esc(value):
    return html.escape(str(value or ""))


def paragraphs(value):
    text = str(value or "").strip()
    return "".join(f"<p>{esc(part.strip())}</p>" for part in text.split("\n") if part.strip())


def list_items(values):
    values = values or []
    if isinstance(values, str):
        values = [values]
    return "<ul>" + "".join(f"<li>{esc(value)}</li>" for value in values if str(value).strip()) + "</ul>"


def build_report(run_dir):
    run_dir = Path(run_dir)
    reports = json.loads((run_dir / "00_manifest.json").read_text(encoding="utf-8"))
    total_weaknesses = sum(len(report.get("important_weaknesses") or []) for report in reports)
    toc = []
    sections = []

    for report in reports:
        number = int(report.get("review_number") or 0)
        dimension = str(report.get("dimension") or f"Dimension {number}")
        anchor = f"dimension-{number:02d}"
        weaknesses = report.get("important_weaknesses") or []
        toc.append(f'<a href="#{anchor}"><span>{number:02d}</span>{esc(dimension)}<b>{len(weaknesses)}</b></a>')

        highlights = []
        for index, weakness in enumerate(weaknesses, 1):
            side = str(weakness.get("affected_side") or "review").lower()
            side_class = "positive" if side.startswith("positive") else "negative" if side.startswith("negative") else "neutral"
            highlights.append(f'''
                <article class="highlight {side_class}">
                  <div class="highlight-top"><span>Key finding {index}</span><em>{esc(side.title())} side</em></div>
                  <h3>{esc(weakness.get("conclusion"))}</h3>
                  <p>{esc(weakness.get("surface_summary"))}</p>
                </article>''')
        if not highlights:
            highlights.append(f'<article class="highlight neutral"><h3>No material weakness selected</h3><p>{esc(report.get("no_finding_explanation"))}</p></article>')

        sections.append(f'''
          <section class="dimension" id="{anchor}">
            <header class="dimension-header">
              <div class="number">{number:02d}</div>
              <div><p>Independent whole-case review</p><h2>{esc(dimension)}</h2></div>
              <span>{esc(report.get("provider", ""))}</span>
            </header>
            <div class="highlight-grid">{''.join(highlights)}</div>
            <div class="report-body">
              <h3>Independent Internal Analysis</h3>
              {paragraphs(report.get("full_dimension_report"))}
            </div>
            <a class="back" href="#top">Back to report index</a>
          </section>''')

    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zhang Huan - 18 Independent Legal Reviews</title>
<style>
:root{{--ink:#eaf0f7;--muted:#9fb0c4;--bg:#0b111b;--panel:#121b29;--line:#2a3a4f;--cyan:#40d9cf;--pink:#ff91b4;--gold:#ffd166;--blue:#78aef8}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.58 "Segoe UI",Arial,sans-serif}}
.page{{max-width:1240px;margin:auto;padding:32px}} .hero{{border-bottom:1px solid var(--line);padding:28px 0 32px}} .hero p{{color:var(--muted);max-width:850px}}
h1{{font-size:40px;margin:0 0 10px;letter-spacing:0}} h2,h3,h4{{letter-spacing:0}} .metrics{{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}}
.metric{{background:var(--panel);border:1px solid var(--line);padding:12px 16px;min-width:170px}} .metric b{{display:block;color:var(--gold);font-size:24px}}
.toc{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px;margin:28px 0 56px}} .toc a{{display:grid;grid-template-columns:36px 1fr 28px;gap:8px;align-items:center;color:var(--ink);text-decoration:none;background:var(--panel);border:1px solid var(--line);padding:11px}}
.toc a:hover{{border-color:var(--cyan)}} .toc span{{color:var(--gold);font-weight:700}} .toc b{{color:var(--muted);text-align:right}}
.dimension{{margin:0 0 64px;padding-top:18px;border-top:1px solid var(--line)}} .dimension-header{{display:grid;grid-template-columns:64px 1fr auto;gap:16px;align-items:center;margin-bottom:18px}}
.dimension-header .number{{font-size:30px;font-weight:800;color:var(--gold)}} .dimension-header p{{margin:0;color:var(--muted)}} .dimension-header h2{{margin:0;font-size:28px}} .dimension-header>span{{color:var(--muted)}}
.highlight-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;margin:18px 0 24px}} .highlight{{background:#152235;border:1px solid var(--line);border-left:5px solid var(--gold);padding:16px}}
.highlight.positive{{border-left-color:var(--cyan)}} .highlight.negative{{border-left-color:var(--pink)}} .highlight-top{{display:flex;justify-content:space-between;color:var(--gold);font-size:13px;text-transform:uppercase;font-weight:700}}
.highlight.positive .highlight-top em{{color:var(--cyan)}} .highlight.negative .highlight-top em{{color:var(--pink)}} .highlight-top em{{font-style:normal}} .highlight h3{{margin:8px 0 10px;font-size:18px}}
.highlight p{{margin:7px 0;color:#dce6f1}} details{{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}} summary{{cursor:pointer;color:var(--blue);font-weight:700}}
.report-body{{background:var(--panel);border:1px solid var(--line);padding:22px}} .report-body>h3{{color:var(--gold);margin-top:8px}} .report-body p{{white-space:pre-wrap}}
.sides{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:22px}} .side{{border-top:3px solid var(--line);padding-top:10px}} .side.positive{{border-color:var(--cyan)}} .side.negative{{border-color:var(--pink)}} .side.positive h3{{color:var(--cyan)}} .side.negative h3{{color:var(--pink)}}
.back{{display:inline-block;margin-top:12px;color:var(--blue)}} @media(max-width:760px){{.page{{padding:18px}}h1{{font-size:30px}}.sides{{grid-template-columns:1fr}}.dimension-header{{grid-template-columns:52px 1fr}}.dimension-header>span{{grid-column:2}}}}
@media print{{body{{background:white;color:#111}}.page{{max-width:none}}.toc a,.report-body,.highlight{{background:white;color:#111}}.back,details{{display:none}}.dimension{{break-before:page}}}}
</style></head>
<body><main class="page" id="top">
<section class="hero"><h1>Zhang Huan Case</h1><h2>18 Independent Whole-Case Legal Reviews</h2>
<p>Each dimension independently reread the complete original matter. The highlighted blocks summarize the important findings; every full dimension report is delivered below without replacing its original reasoning.</p>
<div class="metrics"><div class="metric"><b>18</b>complete reports</div><div class="metric"><b>{total_weaknesses}</b>important findings</div><div class="metric"><b>1 case</b>reread per dimension</div></div></section>
<nav class="toc">{''.join(toc)}</nav>{''.join(sections)}
</main></body></html>'''

    output = run_dir / "00_COMPLETE_18_REPORTS.html"
    output.write_text(document, encoding="utf-8")
    return output


def main():
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else RUN_DIR
    print(build_report(run_dir))


if __name__ == "__main__":
    main()
