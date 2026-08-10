"""
Renderer de marca: PostSpec → 3 slides HTML → PNG 1440×1800.

Reemplaza al renderer de Pillow. La razón está en la propia spec del kit
(`brand/SKILL.md`): "No reconstruyas el motor: copia una plantilla HTML
existente, edita el texto y renderiza". Dibujar con Pillow obligaba a
reimplementar a mano el degradado radial del orbe, el tracking negativo de
los titulares y el logo, y nunca iba a coincidir con lo que ya está shipeado.

Tokens de `brand/references/brand-and-compliance.md`. No inventar valores acá:
si algo falta, va primero al brand guide.

    python -m pipeline.render_html out/2026-08-10-costo-barrera   # solo PNG
"""
from __future__ import annotations

import html
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BRAND = Path(__file__).resolve().parents[1] / "brand"
W, H = 1440, 1800

# --- tokens ---------------------------------------------------------------
NAVY = "#0B1626"
MIDNIGHT = "#0A0F18"
CYAN = "#0AA6C9"
CYAN_DARK = "#22C2E0"      # acento sobre fondo oscuro
CYAN_TEXT = "#07728C"      # acento sobre fondo claro (contraste)
MIST = "#F4F7F9"
PAPER = "#FFFFFF"
TINT = "#E2F1F5"
SLATE = "#586575"

FONTS = ("https://fonts.googleapis.com/css2?"
         "family=Schibsted+Grotesk:wght@400;700;800"
         "&family=Hanken+Grotesk:wght@400;500"
         "&family=Space+Mono:wght@400;700&display=swap")

SWIPE = "Desliza &rarr;"
SAVE = "Guarda este post"


@dataclass
class Frame:
    """Un slide. `dark` alterna el fondo; el logo cambia con él."""
    kicker: str
    dark: bool
    body_html: str


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _css(dark: bool) -> str:
    bg = MIDNIGHT if dark else MIST
    fg = MIST if dark else NAVY
    accent = CYAN_DARK if dark else CYAN_TEXT
    orb = (f".glow-orb{{position:absolute;width:900px;height:900px;"
           f"border-radius:50%;background:radial-gradient(circle,"
           f"rgba(10,166,201,.18) 0%,transparent 65%);top:-200px;right:-250px;"
           f"pointer-events:none;}}" if dark else "")
    return f"""
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
body{{width:{W}px;height:{H}px;overflow:hidden;
 font-family:'Hanken Grotesk',sans-serif;background:{bg};color:{fg};
 position:relative;}}
{orb}
.safe{{position:absolute;inset:110px;display:flex;flex-direction:column;}}
.top{{display:flex;justify-content:space-between;align-items:center;}}
.kicker{{font-family:'Space Mono',monospace;font-size:22px;font-weight:700;
 letter-spacing:6px;text-transform:uppercase;color:{accent};}}
.frame-num{{font-family:'Space Mono',monospace;font-size:20px;
 letter-spacing:3px;color:{SLATE};}}
.content{{flex:1;display:flex;flex-direction:column;justify-content:center;}}
.dots{{display:flex;gap:10px;margin-bottom:56px;}}
.dot{{width:50px;height:4px;border-radius:2px;background:rgba(88,101,117,.3);}}
.dot.on{{background:{CYAN};}}
h1{{font-family:'Schibsted Grotesk',sans-serif;font-weight:800;
 font-size:88px;line-height:1.04;letter-spacing:-2.5px;color:{fg};}}
h1 .accent{{color:{accent};}}
.bignum{{font-family:'Schibsted Grotesk',sans-serif;font-weight:800;
 font-size:190px;line-height:.9;letter-spacing:-6px;color:{accent};
 white-space:nowrap;margin-bottom:24px;}}
.sub{{font-size:30px;font-weight:400;line-height:1.55;color:{SLATE};
 margin-top:44px;max-width:940px;}}
.sub strong{{color:{fg};font-weight:500;}}
.stats{{display:flex;gap:28px;margin-top:56px;}}
.stat{{flex:1;background:{PAPER if not dark else 'rgba(255,255,255,.04)'};
 border:1px solid {TINT if not dark else 'rgba(34,194,224,.22)'};
 border-radius:20px;padding:44px 38px;}}
.stat.feature{{background:{TINT if not dark else 'rgba(10,166,201,.10)'};
 border-color:rgba(10,166,201,.3);}}
.snum{{font-family:'Schibsted Grotesk',sans-serif;font-weight:800;
 font-size:80px;line-height:1;letter-spacing:-2px;color:{fg};
 white-space:nowrap;}}
.snum.cyan{{color:{accent};}}
.slabel{{font-size:24px;color:{SLATE};line-height:1.4;margin-top:18px;}}
.chain{{font-family:'Space Mono',monospace;font-size:26px;letter-spacing:2px;
 color:{accent};margin-top:40px;}}
.src{{font-family:'Space Mono',monospace;font-size:17px;letter-spacing:2px;
 color:{SLATE};text-transform:uppercase;margin-top:34px;opacity:.75;}}
.bottom{{display:flex;justify-content:space-between;align-items:flex-end;}}
.swipe{{font-family:'Space Mono',monospace;font-size:18px;letter-spacing:3px;
 color:{SLATE};text-transform:uppercase;}}
.save{{display:flex;align-items:center;gap:10px;font-family:'Space Mono',
 monospace;font-size:18px;letter-spacing:3px;color:{SLATE};
 text-transform:uppercase;}}
"""


def _page(frame: Frame, n: int, total: int) -> str:
    logo = "logo-cyan.png" if frame.dark else "logo-ink.png"
    dots = "".join(
        f'<div class="dot{" on" if i == n - 1 else ""}"></div>'
        for i in range(total)
    )
    last = n == total
    foot = (f'<div class="save"><svg width="16" height="20" viewBox="0 0 16 20"'
            f' fill="none"><path d="M2 2h12v16l-6-4-6 4V2z" stroke="{SLATE}"'
            f' stroke-width="1.5" stroke-linejoin="round"/></svg>{SAVE}</div>'
            if last else f'<span class="swipe">{SWIPE}</span>')
    orb = '<div class="glow-orb"></div>' if frame.dark else ""
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width={W}">
<title>DentRead — {n:02d}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<style>{_css(frame.dark)}</style></head>
<body>{orb}
<div class="safe">
  <div class="top"><span class="kicker">{_esc(frame.kicker)}</span>
  <span class="frame-num">{n:02d} / {total:02d}</span></div>
  <div class="content">
    <div class="dots">{dots}</div>
{frame.body_html}
  </div>
  <div class="bottom">
    <img src="{logo}" alt="DentRead"
         style="height:120px;width:auto;object-fit:contain;">
    {foot}
  </div>
</div>
</body></html>
"""


# --------------------------------------------------------------------------

def _br(text: str, every: int = 26) -> str:
    """
    Corta el titular en líneas cortas. Con 88px y tracking -2.5 un renglón
    largo se pasa del safe zone; el kit siempre trae los <br> a mano.
    """
    words, lines, cur = _esc(text).split(), [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > every:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "<br>".join(lines)


def frames_for(spec) -> list[Frame]:
    """
    PostSpec → 3 frames. Alterna oscuro / claro / oscuro: el brand guide pide
    alternar, y el slide de datos va en claro porque las tarjetas `.stat`
    necesitan fondo papel para leerse.
    """
    out: list[Frame] = []
    for s in spec.slides:
        if s.role == "hook":
            big = (f'<div class="bignum">{_esc(s.stat)}</div>'
                   if s.stat else "")
            src = f'<div class="src">{_esc(s.source)}</div>' if s.source else ""
            sub = f'<p class="sub">{_esc(s.body)}</p>' if s.body else ""
            out.append(Frame(s.kicker, True,
                             f'{big}<h1>{_br(s.headline)}</h1>{sub}{src}'))

        elif s.role == "data":
            # La primera tarjeta es la destacada (fondo tint, cifra en cian):
            # es la que aporta el dato nuevo respecto del gancho.
            cards = ""
            for i, st in enumerate(s.stats):
                cls = "stat" if i else "stat feature"
                num = "snum" if i else "snum cyan"
                cards += (f'<div class="{cls}"><div class="{num}">'
                          f'{_esc(st.number)}</div>'
                          f'<div class="slabel">{_esc(st.label)}</div></div>')
            body = f'<p class="sub">{_esc(s.body)}</p>' if s.body else ""
            src = f'<div class="src">{_esc(s.source)}</div>' if s.source else ""
            out.append(Frame(s.kicker, False,
                             f'<h1>{_br(s.headline)}</h1>'
                             f'<div class="stats">{cards}</div>{body}{src}'))

        else:                                   # close
            head = _br(s.headline)
            if s.accent:
                head += f'<br><span class="accent">{_br(s.accent)}</span>'
            chain = f'<div class="chain">{s.chain}</div>' if s.chain else ""
            body = f'<p class="sub">{_esc(s.body)}</p>' if s.body else ""
            out.append(Frame(s.kicker, True, f'<h1>{head}</h1>{chain}{body}'))
    return out


def write_html(frames: list[Frame], folder: Path) -> list[Path]:
    """Escribe los HTML y deja los logos al lado (las rutas son relativas)."""
    folder.mkdir(parents=True, exist_ok=True)
    for logo in ("logo-cyan.png", "logo-ink.png"):
        src = BRAND / logo
        if src.exists():
            shutil.copy2(src, folder / logo)
    out = []
    for i, f in enumerate(frames, 1):
        p = folder / f"slide-{i:02d}.html"
        p.write_text(_page(f, i, len(frames)), encoding="utf-8")
        out.append(p)
    return out


def render(html_files: list[Path]) -> list[Path]:
    """
    HTML → PNG con Playwright. La espera de 3,5 s es por las Google Fonts:
    sin ella los titulares salen con la fuente de sistema y el tracking
    negativo se ve mal. El brand guide dice explícitamente que no se baje.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta Playwright:\n"
                 "  pip install playwright\n"
                 "  python -m playwright install chromium")

    pngs = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=1)
        for f in html_files:
            out = f.with_suffix(".png")
            page.goto(f"file://{f.resolve()}")
            page.wait_for_timeout(3500)
            page.screenshot(path=str(out),
                            clip={"x": 0, "y": 0, "width": W, "height": H})
            print(f"   {out.name}")
            pngs.append(out)
        browser.close()
    return pngs


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not folder or not folder.exists():
        sys.exit("uso: python -m pipeline.render_html out/<carpeta>")
    files = sorted(folder.glob("slide-*.html"))
    if not files:
        sys.exit(f"no hay slide-*.html en {folder}")
    render(files)


if __name__ == "__main__":
    main()
