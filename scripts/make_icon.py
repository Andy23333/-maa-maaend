#!/usr/bin/env python3
"""生成应用图标 assets/icon.ico（开发辅助脚本，不参与运行时）。"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 深色圆角底
    d.rounded_rectangle((8, 8, 248, 248), radius=56, fill=(30, 36, 48, 255))

    # 时钟外环（开机定时概念）
    d.ellipse((36, 96, 172, 232), outline=(233, 236, 239, 255), width=14)
    d.line((104, 164, 104, 116), fill=(233, 236, 239, 255), width=12)
    d.line((104, 164, 140, 178), fill=(233, 236, 239, 255), width=12)

    # 绿色播放三角（开始跑日常）
    d.polygon([(150, 52), (232, 106), (150, 160)], fill=(46, 204, 113, 255))

    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    ico = out / "icon.ico"
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                         (64, 64), (128, 128), (256, 256)])
    img.convert("RGB").save(out / "icon_256.png")
    print("written:", ico)


if __name__ == "__main__":
    main()
