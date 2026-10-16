"""Audit U4: Color contrast ratio and accessibility verification (WCAG 2.1 AA requirement: >= 4.5:1 for normal text)."""

def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def luminance(hex_code):
    hex_code = hex_code.lstrip("#")
    r, g, b = [int(hex_code[i:i+2], 16) for i in (0, 2, 4)]
    return 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)

def contrast_ratio(hex1, hex2):
    l1 = luminance(hex1)
    l2 = luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)

import json
from pathlib import Path

def run_u4_contrast():
    tokens_file = Path(__file__).resolve().parent.parent.parent / "api" / "tokens.json"
    with open(tokens_file, "r", encoding="utf-8") as f:
        tdata = json.load(f)
    theme = tdata["theme_tokens"]
    bg_paper = theme["paper_base"]
    bg_sunken = theme["paper_sunken"]
    bg_elevated = theme["paper_elevated"]

    inks = {
        "ink-primary": theme["ink_primary"],
        "ink-secondary": theme["ink_secondary"],
        "ink-muted": theme["ink_muted"],
        "signal-taint": theme["signal_inks"]["tainted"],
        "signal-reaffirm": theme["signal_inks"]["reaffirmed"],
        "signal-suspect": theme["signal_inks"]["suspect"],
        "signal-neutral": theme["signal_inks"]["neutral"],
    }

    print(f"Base Paper Background: {bg_paper} (Luminance: {luminance(bg_paper):.4f})\n")
    print(f"{'Token':<18} {'Hex':<10} {'Contrast vs Paper':<20} {'WCAG AA (>= 4.5:1)':<18}")
    print("-" * 68)

    failures = []
    for name, hex_val in inks.items():
        cr = contrast_ratio(hex_val, bg_paper)
        passes = cr >= 4.5
        status_str = "PASS" if passes else "FAIL (< 4.5:1)"
        print(f"{name:<18} {hex_val:<10} {cr:.2f}:1{'':<14} {status_str}")
        if not passes:
            failures.append((name, hex_val, cr))

    print("\nContrast against Elevated Paper (#EFECE3):")
    for name, hex_val in inks.items():
        cr = contrast_ratio(hex_val, bg_elevated)
        passes = cr >= 4.5
        print(f"  {name:<18}: {cr:.2f}:1 -> {'PASS' if passes else 'FAIL'}")

    if failures:
        print(f"\nU4 Contrast Failures detected ({len(failures)} token(s) fail WCAG 4.5:1):")
        for f in failures:
            print(f"  - {f[0]} ({f[1]}): {f[2]:.2f}:1")
    else:
        print("\nAll ink tokens meet WCAG 4.5:1 against base paper.")

def test_u4_contrast():
    run_u4_contrast()


if __name__ == "__main__":
    run_u4_contrast()
