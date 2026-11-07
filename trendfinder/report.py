"""Portable monochrome / ordered-dither PDF. All claims retain evidence IDs."""
from __future__ import annotations

import io
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Flowable, HRFlowable, Image as PDFImage, KeepTogether, PageBreak,
                               Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from .scoring import WEIGHTS

INK = colors.HexColor("#171912")
PAPER = colors.HexColor("#f5f3e8")
GRAY = colors.HexColor("#e5e3d7")
WIDTH = A4[0] - 36 * mm


def fonts():
    roots = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path(reportlab.__file__).parent / "fonts"]
    pairs = [("consola.ttf", "consolab.ttf"), ("DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf"), ("Vera.ttf", "VeraBd.ttf")]
    for root, (regular, bold) in zip(roots, pairs):
        if (root / regular).exists() and (root / bold).exists():
            pdfmetrics.registerFont(TTFont("Radar", str(root / regular)))
            pdfmetrics.registerFont(TTFont("Radar-Bold", str(root / bold)))
            pdfmetrics.registerFontFamily("Radar", normal="Radar", bold="Radar-Bold", italic="Radar", boldItalic="Radar-Bold")
            return
    raise RuntimeError("No report font found (ReportLab's bundled Vera should be installed)")


def dither(width=600, height=50):
    matrix = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
    im = Image.new("RGB", (width, height), "#f5f3e8")
    pix = im.load()
    for y in range(height):
        for x in range(width):
            if matrix[y % 4][x % 4] / 16 < x / width:
                pix[x, y] = (23, 25, 18)
    out = io.BytesIO(); im.save(out, format="PNG"); out.seek(0)
    return PDFImage(out, width=WIDTH, height=12 * mm)


class SignalBars(Flowable):
    def __init__(self, signals):
        super().__init__(); self.signals = signals; self.width = WIDTH; self.height = 27 * mm

    def draw(self):
        c = self.canv
        for i, (name, value) in enumerate(self.signals.items()):
            y = self.height - 12 - i * 13
            c.setFont("Radar", 8); c.setFillColor(INK); c.drawString(0, y, name.upper())
            start = 100
            for cell in range(25):
                c.setFillColor(INK if cell < round(value / 4) else GRAY)
                c.rect(start + cell * 10, y, 7, 7, fill=1, stroke=0)
            c.setFillColor(INK); c.drawString(365, y, f"{value:.0f}/100")


class SearchChart(Flowable):
    def __init__(self, observations):
        super().__init__(); self.rows = observations; self.width = WIDTH; self.height = 53 * mm

    def draw(self):
        c = self.canv; left = 30; bottom = 30; w = WIDTH - 45; h = self.height - 48
        c.setStrokeColor(colors.HexColor("#c6c5b8")); c.setFont("Radar", 7)
        for v in (0, 50, 100):
            y = bottom + h * v / 100
            c.line(left, y, left + w, y); c.drawString(0, y - 2, str(v))
        for index, row in enumerate(self.rows[:3]):
            pts = sorted(row["series"], key=lambda p: p["date"])
            if len(pts) < 2: continue
            c.setStrokeColor(INK); c.setLineWidth(1.2); c.setDash(*[(), (5, 3), (1, 3)][index])
            p = c.beginPath()
            for i, point in enumerate(pts):
                x = left + w * i / (len(pts) - 1); y = bottom + h * max(0, min(100, point["value"])) / 100
                if i == 0: p.moveTo(x, y)
                else: p.lineTo(x, y)
            c.drawPath(p); c.setDash()
            c.drawString(left + index * 115, 12, row["market"] + [" solid", " dashed", " dotted"][index])
        c.drawString(left, 0, "Relative 0-100 index; not absolute volume or cross-country size.")


def generate(run: dict, path: Path, cfg: dict):
    fonts()
    s = getSampleStyleSheet()
    for name in ("Normal", "BodyText"):
        s[name].fontName = "Radar"; s[name].fontSize = 8.5; s[name].leading = 13; s[name].textColor = INK
    s.add(ParagraphStyle("TitleRadar", fontName="Radar-Bold", fontSize=34, leading=36, textColor=INK, spaceAfter=14))
    s.add(ParagraphStyle("H1Radar", fontName="Radar-Bold", fontSize=20, leading=24, textColor=INK, spaceAfter=12))
    s.add(ParagraphStyle("H2Radar", fontName="Radar-Bold", fontSize=11, leading=15, textColor=INK, spaceBefore=6, spaceAfter=4))
    s.add(ParagraphStyle("SmallRadar", parent=s["Normal"], fontSize=7, leading=10))
    story = []

    def p(text, style="BodyText"):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), s[style])

    def add(text, style="BodyText"):
        story.append(p(text, style)); story.append(Spacer(1, 2 * mm))

    def heading(number, title):
        add(f"{number} / {title}", "H1Radar")
        story.append(HRFlowable(width=WIDTH, thickness=1, color=INK, spaceAfter=10))

    def table(rows, widths, header=True):
        t = Table([[p(x, "SmallRadar") for x in row] for row in rows], colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), .7, INK),
            ("INNERGRID", (0, 0), (-1, -1), .35, INK), ("BACKGROUND", (0, 0), (-1, 0), GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story.append(t); story.append(Spacer(1, 4 * mm))

    demo = run["mode"] == "demo"
    stamp = "DEMO / SYNTHETIC DATA" if demo else "LIVE COLLECTION / COVERAGE LIMITED"
    add("CZ/SK  //  FIELD INTELLIGENCE", "H2Radar")
    story.append(Spacer(1, 15 * mm))
    add("MINECRAFT\nTREND\nRADAR_", "TitleRadar")
    story.append(dither()); story.append(Spacer(1, 10 * mm))
    add("Catch the format before the market catches up.", "H2Radar")
    add("Czechia + Slovakia | Minecraft server formats | Hosting product research")
    add(stamp, "H2Radar")
    add("Collected: " + run["created_at"] + "\nRun: " + run["id"] + "\nReport language: English")
    add("Evidence first. Uncertainty visible. No automatic purchases, deployments or claims of guaranteed demand.")
    if demo: add("Every metric in this report is a synthetic fixture for testing the tool and layout. Do not use these rankings as market research.", "H2Radar")
    story.append(PageBreak())

    heading("01", "Decision board")
    ready = [r for r in run["rankings"] if r["stage"] == "PILOT CANDIDATE"]
    if ready:
        add(f"{len(ready)} formats pass the pilot gate. Start with a small, reversible validation campaign; the score is a research heuristic, not a success probability.")
    else:
        add("NO VALIDATED OPPORTUNITY YET", "H2Radar")
        add("Current evidence does not justify calling any format an early winner. The ordered list below is a research watchlist; collect missing sources and repeat scans before investing.")
    table([["FORMAT", "SCORE / 100", "CONFIDENCE", "DECISION"]] +
          [[r["candidate"]["name"], str(r["score"]), str(r["confidence"]) + "% coverage", r["stage"]] for r in run["rankings"]],
          [WIDTH * .37, WIDTH * .15, WIDTH * .20, WIDTH * .28])
    add("Confidence is an evidence-coverage heuristic, not a statistical confidence interval. Recommendations are not estimates of player population.", "SmallRadar")
    heading("02", "Collection health")
    table([["SOURCE", "STATE / ITEMS", "DETAILS"]] + [[x["source"], f'{x["state"]} / {x["observations"]}', x["message"] or "Collected successfully; a zero match count is only a sampled result."] for x in run["sources"]],
          [WIDTH * .20, WIDTH * .19, WIDTH * .61])
    add("TikTok / Facebook: authorized RSS or CSV imports only. No private-group access is implied. Discord requires an authorized bot and configured channels. YouTube's official API requires a key; its public fallback is less complete.")
    story.append(PageBreak())

    heading("03", "Why the ranking works")
    add("The radar looks for convergence: mid-size creators adopting a format, sustained local search momentum, repeat hosting-intent questions, and measured ecosystem growth. It discounts sampled supply saturation and isolated search spikes. General trend reports are lagging context and receive zero score.")
    table([["SIGNAL", "WEIGHT", "MEASUREMENT"]] + [
        ["Creators", "25%", "Dated videos; views/subscribers breakout at 50k-500k subscribers; independent channels and local language signals."],
        ["Local search", "30%", "12-month CZ/SK weekly series; recent four weeks vs prior four; eight-week slope, low-volume and spike checks. US is a small corroborating signal."],
        ["Mod ecosystem", "15%", "Same-project download-counter change over >=24h; one snapshot gets only limited popularity points."],
        ["Community intent", "20%", "Unique, dated hosting/setup questions and recent-vs-prior 14-day counts."],
        ["Server adoption", "10%", "Positive tag-count change in comparable local first-page samples; no points for unobserved supply."],
    ], [WIDTH * .22, WIDTH * .12, WIDTH * .66])
    add("Formula: raw = sum(signal x weight). Score = max(0, raw - supply penalty - spike penalty) x (0.45 + 0.55 x coverage/100). Supply penalty is capped at 18; isolated local spikes add 8. Missing signals get no points; weights are never redistributed.")
    add("Pilot gate: score >=45, coverage >=60, at least three signal families, a temporal signal and local demand (sustained CZ/SK search, >=2 local hosting questions, or >=2 local creator channels). Coverage uses source-family breadth (12 points/family), local observations (up to 20), temporal evidence (12), and both local search markets (8).", "SmallRadar")
    add("An English-to-CZ/SK lag is reported only when both search series have detectable, maintained take-off points. Relative indices cannot establish market-size differences. Modpack discovery is automatic, but a newly popular project starts as a hypothesis.")
    story.append(PageBreak())

    evidence = {o["id"]: o for o in run["observations"]}
    appendix_ids = []
    for index, r in enumerate(run["rankings"][:cfg["report_top"]], 1):
        c = r["candidate"]
        heading(f"04.{index}", c["name"])
        add(f'{r["stage"]}  |  score {r["score"]}/100  |  coverage {r["confidence"]}%  |  local items {r["local_evidence"]}', "H2Radar")
        story.append(SignalBars(r["signals"])); story.append(Spacer(1, 4 * mm))
        add("Evidence and demand mechanism", "H2Radar")
        if not r["reasons"]: add("No usable evidence was collected. This is an unvalidated catalog hypothesis, not an investment recommendation.")
        for reason in r["reasons"]: add("+ " + reason)
        series = [evidence[i] for i in r["evidence_ids"] if evidence[i]["family"] == "search" and evidence[i]["series"]]
        if series: story.append(KeepTogether([p("Search momentum / complete observations", "H2Radar"), SearchChart(series)]))
        add("Why it could work for a local host", "H2Radar")
        add("Hypothesis: reduce the gap between watching a creator format and playing it with friends. A pinned server template, matching client instructions, Czech/Slovak onboarding and measured restore support can remove setup friction. This mechanism must be validated with signups and paid pilots; a popular video alone does not prove purchase intent.")
        selected = r["evidence_ids"][:10]
        # Include different families, not just ten projects from one collector.
        selected = list(dict.fromkeys([next((i for i in r["evidence_ids"] if evidence[i]["family"] == f), "") for f in WEIGHTS] + selected))
        selected = [i for i in selected if i][:12]
        appendix_ids.extend(selected)
        story.append(PageBreak())

        heading(f"05.{index}", "Build the hosting offer")
        add(c["name"] + " // " + c["stack"], "H2Radar")
        for n, step in enumerate(c["setup"], 1): add(f"{n}. {step}")
        add("Template acceptance checklist", "H2Radar")
        add("Pin Minecraft, loader, plugins/mods and Java versions. Verify upstream distribution rights. Keep credentials out of the image. Define storage and world-border limits. Test first boot, whitelist, reconnect, death/respawn, a scheduled backup and restore to a new instance. Record actual deployment time before advertising '2 minutes'.")
        add("Capacity and tariff model / assumptions, not measured capacity", "H2Radar")
        econ = r["economics"]
        table([["INPUT / OUTPUT", "ILLUSTRATIVE VALUE"], ["Starting RAM budget (load-test before sale)", f'{c["ram_gb"]} GB'],
               ["Proposed monthly price", f'{econ["price"]:.2f} {econ["currency"]}'],
               ["RAM + CPU/storage + support + payment costs", f'{econ["cost"]:.2f} {econ["currency"]}/month'],
               ["Contribution before tax, acquisition and overhead", f'{econ["contribution"]:.2f} {econ["currency"]} ({econ["margin_percent"]:.1f}%)']],
              [WIDTH * .64, WIDTH * .36])
        e = cfg["economics"]
        add(f'Inputs: RAM {e["ram_cost_per_gb"]} {e["currency"]}/GB; CPU/storage {e["cpu_storage_per_month"]}/month; support {e["support_minutes_per_month"]} min/month at {e["support_cost_per_hour"]}/hour; payment {e["payment_fee_percent"]}% + {e["fixed_fee"]}. Excludes VAT, licensing, bandwidth overages, marketing and fixed overhead. Edit config for your real costs.', "SmallRadar")
        add("Capacity experiment", "H2Radar")
        add(f'Start at {c["ram_gb"]} GB as a budget hypothesis. Benchmark with 6-10 actual players, exploration, busy bases and backup/restore. Target p95 tick duration <50 ms, no sustained swapping, and <80% RAM utilization. Increase price or reduce pack complexity if contribution is negative; never promise slots from RAM alone.')
        add("Risks: " + "; ".join(c["risks"]))
        story.append(PageBreak())

        heading(f"06.{index}", "Audit + launch experiment")
        add(c["name"], "H2Radar")
        add("What could falsify the thesis", "H2Radar")
        for caveat in r["caveats"]: add("- " + caveat, "SmallRadar")
        add("Evidence anchors / complete URLs in the ledger", "H2Radar")
        for eid in selected[:6]:
            o = evidence[eid]
            add(f'[{eid}] {o["source"]} / {o["market"]}: {o["title"][:130]} | {o["metric"]} = {o["value"]:,.1f}', "SmallRadar")
        if not selected: add("No source anchors: do not turn this catalog idea into a market claim.")
        add("CZ / SK short-video launch copy", "H2Radar")
        add("CZ: " + c["cz_copy"])
        add("SK: " + c["sk_copy"])
        add("Demo the actual install and client join. Invite one small creator and 5-10 friend groups. Measure installs, time-to-first-join, seven-day return, support time and paid conversion; do not buy a large fleet before this pilot.")
        story.append(PageBreak())

    heading("07", "14-day validation sprint")
    table([["WHEN", "ACTION", "DECISION RULE (PROPOSED TARGET)"] ,
           ["Days 1-2", "Repeat scans; audit source pages and choose one format with local temporal evidence.", "No local evidence: continue research, do not call it a launch."],
           ["Days 3-5", "Build a private template; validate license, Java/loader, first join and restore.", "No severe data-loss/security defects; restore within 15 minutes."],
           ["Days 6-9", "Recruit 5-10 CZ/SK friend groups and a small creator. Publish two localized setup demos.", "Track actual installation completion and support minutes per group."],
           ["Days 10-14", "Review paid conversion, day-seven retention and unit economics.", "Example gate: >=5 paying groups, >=50% day-seven group return, positive contribution. Adapt to your baseline."],
           ["Stop / revise", "Kill the offer if onboarding fails, search collapses, license blocks redistribution, or support erases margin.", "Record the rejection reason; retain data for the next scan."]], [WIDTH * .15, WIDTH * .43, WIDTH * .42])
    add("Automation and monitoring", "H2Radar")
    add("Schedule one live scan per day with Windows Task Scheduler. SQLite stores append-only live snapshots. Modpack and server-tag velocity requires >=24h between comparable snapshots. Keep a two-week observation window before interpreting acceleration. Review source failures and sample drift on every report.")
    add("Additional dimensions", "H2Radar")
    add("Check seasonality (holidays and school terms), licensing, crossplay demand, install friction, player age/moderation needs, creator dependence, CPU cost, retention, and competitive positioning. These are validation tasks, not automatically measured facts. A sustainable niche may beat a high-view, high-churn event format.")
    story.append(PageBreak())

    heading("08", "Optional local AI notes")
    add(run["ai"]["message"])
    for note in run["ai"]["notes"]:
        add("UNVERIFIED AI HYPOTHESIS / " + note["candidate_id"], "H2Radar")
        add(note["hypothesis"]); add("Test: " + note["experiment"])
        add("Evidence references: " + ", ".join(note["evidence_ids"]), "SmallRadar")
    add("The deterministic ranking and report work without AI. A 3B Q4 model via Ollama is a sensible starting point for a 4 GB VRAM GPU with a 2k-token context; actual VRAM depends on backend and GPU and may spill to system RAM. Model output cannot create evidence, change scores or authorize deployments. Laya or another model can be selected if installed in Ollama; compatibility is not assumed.")
    heading("09", "Evidence ledger")
    add("Links are original source citations. Timestamp, metric, raw series and all observations are in report.json. Private-community citations require your existing access. The PDF includes selected anchors; the JSON ledger contains every observation. Synthetic demo links use example.com.")
    for eid in dict.fromkeys(appendix_ids):
        o = evidence[eid]
        block = [p(f'[{eid}] {o["title"][:160]}', "SmallRadar"),
                 p(f'{o["source"]} | {o["market"]} | {o["metric"]} = {o["value"]:,.2f} | published {o["published_at"] or "unknown"}', "SmallRadar")]
        if o["url"]:
            link = escape(o["url"], {'"': '&quot;'})
            block.append(Paragraph(f'<link href="{link}"><u>{escape(o["url"][:130])}</u></link>', s["SmallRadar"]))
        block.append(Spacer(1, 4 * mm)); story.append(KeepTogether(block))
    add("Reproducibility", "H2Radar")
    add("Artifacts: report.pdf, report.json, observations.csv. Config snapshots omit credentials; credentials are read only from process environment. No private messages or usernames from Discord are persisted. Retain artifacts securely if authorized community sources are enabled.")

    def page(canvas, doc):
        canvas.saveState(); canvas.setFillColor(PAPER); canvas.rect(0, 0, *A4, fill=1, stroke=0)
        canvas.setStrokeColor(INK); canvas.setFillColor(INK); canvas.setFont("Radar", 7)
        canvas.drawString(18 * mm, A4[1] - 12 * mm, "CZ/SK  /  MINECRAFT TREND RADAR")
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 12 * mm, "SYNTHETIC DEMO" if demo else "EVIDENCE / NOT A FORECAST")
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.drawString(18 * mm, 10 * mm, run["created_at"][:10] + "  //  " + run["id"][:12])
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{doc.page:02d}")
        canvas.restoreState()

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=23 * mm, bottomMargin=23 * mm, title="CZ/SK Minecraft Trend Radar" + (" - Synthetic Demo" if demo else ""),
                            author="Minecraft Trendfinder", pageCompression=1)
    doc.build(story, onFirstPage=page, onLaterPages=page)
