"""Desenha os ícones PNG do app do celular a partir do mesmo desenho de robo.svg (grade 64x64).

Uso: python ferramentas/gerar_icones_celular.py robo/painel/estaticos   (precisa do Pillow)
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

def desenhar(tam, cheio):
    k = 4  # supersampling
    T = tam * k
    img = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    # degradê diagonal #3B6CF6 -> #1D3FB0
    grad = Image.new("RGBA", (T, T))
    px = grad.load()
    a, b = (0x3B, 0x6C, 0xF6), (0x1D, 0x3F, 0xB0)
    for y in range(T):
        for x in range(T):
            t = (x + y) / (2 * T - 2)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (T, T), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, T - 1, T - 1), radius=0 if cheio else 15 * T / 64, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # ícone "maskable": o desenho fica na zona segura (80% central)
    esc = (0.72 if cheio else 1.0) * T / 64
    off = (T - 64 * esc) / 2
    P = lambda *v: [off + c * esc for c in v]
    branco, azul, verde = "#FFFFFF", "#1D3FB0", "#7FE0B4"
    d.rounded_rectangle(P(14, 22, 50, 50), radius=8 * esc, fill=branco)
    d.line(P(32, 12, 32, 22), fill=branco, width=round(3.5 * esc))
    d.ellipse(P(28.5, 7.5, 35.5, 14.5), fill=verde)
    d.ellipse(P(20.5, 31, 28.5, 39), fill=azul)
    d.ellipse(P(35.5, 31, 43.5, 39), fill=azul)
    d.line(P(25, 43.5, 39, 43.5), fill=azul, width=round(3 * esc))
    for x in (9, 55):
        d.line(P(x, 32, x, 40), fill=branco, width=round(3.5 * esc))
    return img.resize((tam, tam), Image.LANCZOS)

pasta = Path(sys.argv[1])
desenhar(192, False).save(pasta / "icone-192.png", optimize=True)
desenhar(512, False).save(pasta / "icone-512.png", optimize=True)
desenhar(512, True).save(pasta / "icone-maskable-512.png", optimize=True)
desenhar(180, True).convert("RGB").save(pasta / "icone-180.png", optimize=True)  # iOS: sem transparência
