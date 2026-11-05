# ADF brand guidelines

**English** · [Português (Brasil)](BRAND_GUIDELINES.pt-BR.md)

## Decision Boundary

The mark shows an incoming request, a visible boundary with a decision diamond, a continued path, and a separate square record. It describes the product's job without suggesting that ADF contains every process. Two alternatives were explored: a closed ring (read as universal containment) and a ledger of parallel lines (lost the decision at 24 px). The open boundary was chosen because it remains legible in one color and represents the supported edge accurately. The design is original to this repository; it has not undergone a trademark clearance search.

## Assets and use

| Asset | Use |
| --- | --- |
| [`adf-mark.svg`](../assets/brand/adf-mark.svg) | Square avatar, minimum 24 × 24 px. Its dark tile works on light and dark UI. |
| [`adf-wordmark-light.svg`](../assets/brand/adf-wordmark-light.svg) | Horizontal lockup on a light background. |
| [`adf-wordmark-dark.svg`](../assets/brand/adf-wordmark-dark.svg) | Horizontal lockup on a dark background. |
| [`adf-hero.svg`](../assets/brand/adf-hero.svg) | Opaque concept banner, 1200 × 260, for slides, posts and the release page. The README uses a native HTML hero (mark at 72 px + text) instead, so the identity is not shown twice and the title stays real text. Never a client screenshot. |
| [`adf-architecture.svg`](../assets/brand/adf-architecture.svg) | Read path at an installed edge, 1200 × 410. |
| [`adf-evidence-flow.svg`](../assets/brand/adf-evidence-flow.svg) | Proof differences, 1200 × 360. |
| [`adf-social-preview.png`](../assets/brand/adf-social-preview.png) | 1280 × 640 opaque social card. Committing it does not set GitHub's preview: a maintainer uploads it in repository Settings → General → Social preview. |

Keep clear space around the mark equal to one quarter of its tile width. Do not crop the gap, decision diamond or record square. At 24 px, use the isolated mark; do not shrink the full wordmark until its descriptor becomes unreadable. SVGs have opaque backgrounds where needed and use system fonts with sans-serif/monospace fallbacks. No font files or external resources are embedded.

## Color and contrast

WCAG relative luminance ratios below were computed for the actual foreground/background pairs. Text pairs exceed 4.5:1; the signal line on the dark tile exceeds 3:1. Color carries emphasis, never the decision alone.

| Role | Foreground / background | Ratio |
| --- | --- | ---: |
| Light text | `#111827` / `#F6F8FB` | 16.67:1 |
| Dark text | `#F3F7FC` / `#0B1220` | 17.40:1 |
| Secondary on dark | `#B9C8D8` / `#0B1220` | 10.98:1 |
| Teal label on light | `#075E50` / `#F6F8FB` | 7.24:1 |
| Teal signal on dark | `#52D1B0` / `#0B1220` | 9.90:1 |

`#263548` is the slate surface. `#E9A23B` is a caution line, not text on white. Red is reserved for an explicit deny/error state; the current assets use labels and dashed lines for early denies. Use “allow”, “deny”, and “outside coverage” in text as well as shape or line pattern. Body copy uses system-ui; code and technical labels use ui-monospace. Do not depend on a specific installed font for meaning.

## Diagrams and language

Solid arrows mean a request path. Dashed lines mean a trust boundary or evidence branch and are labeled. `gate_only` means ADF decided and the native tool delivered bytes; `mediated` means ADF returned snapshot bytes. A journal entry marks a pre-adapter attempt, not a verified Evidence Bundle. Optional telemetry is shown as a view only. The SVG diagrams here are their own source of truth; update the SVG and its alt text together when the boundary changes.

English example: “Decisions at the boundary. Evidence with explicit limits.” Subline: “Deterministic read-policy decisions at supported, installed coding-agent tool edges.”

Portuguese example: “Decisões na fronteira. Evidências com limites explícitos.” Subline: “Decisões determinísticas de leitura nas bordas instaladas e suportadas de ferramentas de agentes de código.”

Do not add shields, locks, brains, robot faces, neon effects, vendor marks, or claims of complete containment. Keep red for an actual deny; do not use it for a decorative accent.

## Reproduction and license

The SVGs are hand-authored, static and self-contained. The PNG is rendered by `python3 docs/assets/brand/make-social-preview.py` with Pillow and an installed DejaVu Sans font; the font is rasterized, not redistributed, and Pillow writes no text or time metadata. `hooks/test-readme-presentation.sh` checks its size (1280 × 640, ≤ 1 MB), that every brand SVG is self-contained with `<title>`/`<desc>`, and the README hero (alt text, ≤ 3 badges, heading order, EN/PT-BR image parity). A raster "editorial" illustration was considered and not adopted: none exists in the repository, and a picture that cannot be regenerated from source would weaken the rule that every image here is reproducible. [The demo GIF](../assets/README.md) is a separate real hook/CLI capture with documented path substitutions. Brand assets are original project work distributed under the repository's [MIT License](../../LICENSE). No third-party logos are included.
