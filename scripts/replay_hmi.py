#!/usr/bin/env python3
# Host-local HMI overlay (hardcoded DB creds)

import io, re, os
from datetime import datetime, timezone
import psycopg2
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
try:
    import cairosvg
except Exception:
    cairosvg = None

# -------- CONFIG (paths) --------
SVG_PATH = "data/hmi/pid_overlay.svg"
HMI_HTML = "data/hmi/pid_valve_states.html"   # your exported page with LS_* triggers
OUT_PNG  = "data/hmi/replay.png"
OUT_HTML = "data/hmi/pid_valve_states.generated.html"

# -------- CONFIG (DB: hardcoded) --------
DB = dict(
    host="localhost",
    port=5433,
    dbname="telemetry",
    user="admin",
    password="admin",
)

# -------- COLORS --------
GREEN = (42, 214, 47, 255)
RED   = (214, 35, 35, 255)
LABEL = (230, 230, 230, 255)

def parse_layout_from_html(html_path: str):
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    layout = []
    rects = soup.select('div[id^="TcHmiRectangle_"]')
    for r in rects:
        try:
            left = float(r.get("data-tchmi-left"));  top = float(r.get("data-tchmi-top"))
            width = float(r.get("data-tchmi-width")); height = float(r.get("data-tchmi-height"))
        except (TypeError, ValueError):
            continue
        ls_tag = None
        for script in r.find_all("script"):
            txt = script.get_text(" ", strip=True)
            m = re.search(r"ADS\.PLC1\.GVL_Valves\.LS_[A-Za-z0-9_]+", txt)
            if m: ls_tag = m.group(0); break
        if not ls_tag: continue
        label = None
        sib = r.find_previous_sibling("div")
        if sib and "TcHmiToggleButton" in (sib.get("id") or ""):
            label = sib.get("data-tchmi-text")
        layout.append(dict(
            tag=ls_tag, label=label or ls_tag.rsplit("LS_", 1)[-1],
            left_pct=left, top_pct=top, width_pct=width, height_pct=height
        ))
    return layout

def normalize_db_bool(value):
    if isinstance(value, bool): return value
    if isinstance(value, (int, float)): return bool(int(value))
    s = str(value).strip().lower()
    if s in ("t","true","1","yes","y","on"):  return True
    if s in ("f","false","0","no","n","off"): return False
    return False

def fetch_states(ts_iso: str, tags):
    try:
        t = datetime.fromisoformat(ts_iso)
    except Exception:
        t = datetime.fromisoformat(ts_iso.replace(" ", "T"))
    t = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)

    sql = """
    WITH wanted AS (
      SELECT DISTINCT ON (s.symbol)
             s.symbol, r.value, r.updated
      FROM record_6 r
      JOIN symboldata_6 s ON r.symbolid = s.id
      WHERE s.symbol = ANY(%s) AND r.updated <= %s
      ORDER BY s.symbol, r.updated DESC
    )
    SELECT symbol, value FROM wanted LIMIT 5000;
    """
    conn = psycopg2.connect(**DB)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, (tags, t))
            return {sym: normalize_db_bool(val) for sym, val in cur.fetchall()}
    finally:
        conn.close()

def rasterize_svg(svg_path: str):
    if cairosvg is not None:
        try:
            png_bytes = cairosvg.svg2png(url=svg_path, dpi=150)
            return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        except Exception:
            pass
    # fallback canvas
    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'xml')
        tag = soup.find('svg')
        ws, hs = tag.get('width', '1200'), tag.get('height', '800')
        w = int(float(ws.split('mm')[0]) * 3.78) if 'mm' in ws else int(float(ws.split('px')[0])) if 'px' in ws else 1200
        h = int(float(hs.split('mm')[0]) * 3.78) if 'mm' in hs else int(float(hs.split('px')[0])) if 'px' in hs else 800
    except Exception:
        w, h = 1200, 800
    img = Image.new('RGBA', (w, h), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([10,10,w-10,h-10], outline=(0,0,0,255), width=3)
    try: font = ImageFont.truetype("arial.ttf", 24)
    except: font = ImageFont.load_default()
    d.text((20,20), "P&ID Diagram - Valve Overlay (fallback)", fill=(0,0,0,255), font=font)
    return img

def draw_overlay(img, layout, states):
    draw = ImageDraw.Draw(img, "RGBA"); W, H = img.size
    try: font = ImageFont.truetype("arial.ttf", 14)
    except: font = ImageFont.load_default()
    for item in layout:
        tag = item["tag"]; val = normalize_db_bool(states.get(tag, False))
        color = GREEN if val else RED
        x = int(item["left_pct"]/100.0*W); y = int(item["top_pct"]/100.0*H)
        w = max(int(item["width_pct"]/100.0*W),6); h = max(int(item["height_pct"]/100.0*H),6)
        draw.rounded_rectangle([x,y,x+w,y+h], radius=max(2,h//3), fill=color)
        if item.get("label"):
            try: th = draw.textbbox((0,0), item["label"], font=font)[3]
            except: th = font.getsize(item["label"])[1]
            draw.text((x, max(0, y-th-2)), item["label"], fill=LABEL, font=font)
    return img

def emit_html(layout, states, out_html, svg_path):
    def rgba(val): return "rgba(42,214,47,0.7)" if val else "rgba(214,35,35,0.7)"
    parts = []
    parts += [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Valve Overlay</title>",
        "<style>body{margin:0;background:#222;color:#eee;font-family:sans-serif;}",
        ".container{position:relative;width:100vw;height:100vh;overflow:hidden;}",
        ".pid{position:absolute;inset:0;}.valve{position:absolute;border-radius:6px;}</style></head><body>",
        "<div class='container'>",
        f"<img class='pid' src='{svg_path}' style='object-fit:contain;width:100%;height:100%;' />"
    ]
    for it in layout:
        val = normalize_db_bool(states.get(it['tag'], False))
        parts.append(
            f"<div class='valve' title='{it['tag']}' "
            f"style='left:{it['left_pct']}%;top:{it['top_pct']}%;"
            f"width:{it['width_pct']}%;height:{it['height_pct']}%;background:{rgba(val)};'></div>"
        )
    parts += ["</div></body></html>"]
    with open(out_html, "w", encoding="utf-8") as f: f.write("".join(parts))

def run(timestamp_iso: str):
    layout = parse_layout_from_html(HMI_HTML)
    if not layout: raise SystemExit(f"No LS_* rectangles found in {HMI_HTML}")
    tags = [it["tag"] for it in layout]
    states = fetch_states(timestamp_iso, tags)
    base = rasterize_svg(SVG_PATH)
    out = draw_overlay(base, layout, states)
    out.save(OUT_PNG); print(f"Wrote {OUT_PNG}")
    emit_html(layout, states, OUT_HTML, SVG_PATH); print(f"Wrote {OUT_HTML}")

if __name__ == "__main__":
    # change default timestamp as needed, or pass one via argv[1]
    import sys
    ts = sys.argv[1] if len(sys.argv) > 1 else "2025-08-08T20:16:58.696469"
    run(ts)
