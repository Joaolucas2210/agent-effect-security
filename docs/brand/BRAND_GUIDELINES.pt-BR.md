# Diretrizes da marca ADF

[English](BRAND_GUIDELINES.md) · **Português (Brasil)**

## Decision Boundary

O símbolo mostra um pedido entrando, uma fronteira visível com o losango da decisão, a continuação do caminho e um registro quadrado separado. Ele descreve a função do produto sem sugerir que o ADF contenha todo processo. Duas alternativas foram exploradas: um anel fechado (parecia contenção universal) e linhas paralelas como livro-razão (a decisão sumia em 24 px). A fronteira aberta foi escolhida porque continua legível em uma cor e representa a borda suportada com precisão. O desenho é original deste repositório; não passou por uma busca de marcas registradas.

## Assets e uso

| Asset | Uso |
| --- | --- |
| [`adf-mark.svg`](../assets/brand/adf-mark.svg) | Avatar quadrado, mínimo de 24 × 24 px. A base escura funciona em interfaces claras e escuras. |
| [`adf-wordmark-light.svg`](../assets/brand/adf-wordmark-light.svg) | Assinatura horizontal sobre fundo claro. |
| [`adf-wordmark-dark.svg`](../assets/brand/adf-wordmark-dark.svg) | Assinatura horizontal sobre fundo escuro. |
| [`adf-hero.svg`](../assets/brand/adf-hero.svg) | Banner conceitual opaco, 1200 × 260, para slides, posts e a página de release. O README usa um hero HTML nativo (símbolo a 72 px + texto), para a identidade não aparecer duas vezes e o título continuar sendo texto real. Nunca uma captura de cliente. |
| [`adf-architecture.svg`](../assets/brand/adf-architecture.svg) | Caminho de leitura em uma borda instalada, 1200 × 410. |
| [`adf-evidence-flow.svg`](../assets/brand/adf-evidence-flow.svg) | Diferenças entre provas, 1200 × 360. |
| [`adf-social-preview.png`](../assets/brand/adf-social-preview.png) | Card social opaco, 1280 × 640. O commit não configura a prévia do GitHub: um mantenedor faz upload em Settings → General → Social preview do repositório. |

Deixe uma margem livre em volta do símbolo igual a um quarto da largura da base. Não recorte a abertura, o losango ou o quadrado de registro. Em 24 px, use o símbolo isolado; não reduza a assinatura completa até o descritor ficar ilegível. Os SVGs têm fundos opacos quando necessário e usam fontes do sistema com fallbacks sans-serif/monospace. Não há fontes ou recursos externos embutidos.

## Cor e contraste

As proporções de luminância relativa WCAG abaixo foram calculadas para os pares reais de frente/fundo. Os pares de texto excedem 4,5:1; a linha de sinal sobre a base escura excede 3:1. A cor dá ênfase, mas nunca comunica a decisão sozinha.

| Papel | Frente / fundo | Proporção |
| --- | --- | ---: |
| Texto no claro | `#111827` / `#F6F8FB` | 16,67:1 |
| Texto no escuro | `#F3F7FC` / `#0B1220` | 17,40:1 |
| Secundário no escuro | `#B9C8D8` / `#0B1220` | 10,98:1 |
| Rótulo teal no claro | `#075E50` / `#F6F8FB` | 7,24:1 |
| Sinal teal no escuro | `#52D1B0` / `#0B1220` | 9,90:1 |

`#263548` é a superfície slate. `#E9A23B` é uma linha de atenção, não texto sobre branco. Vermelho é reservado para uma negação/erro explícito; os assets atuais usam rótulos e linhas tracejadas para negações precoces. Escreva “allow”, “deny” e “fora da cobertura” também em texto, além da forma ou padrão da linha. O corpo usa system-ui; código e rótulos técnicos usam ui-monospace. O sentido não depende de uma fonte específica instalada.

## Diagramas e linguagem

Setas sólidas representam o caminho do pedido. Linhas tracejadas representam uma fronteira de confiança ou ramo da evidência e recebem rótulos. `gate_only` significa que o ADF decidiu e a ferramenta nativa entregou bytes; `mediated` significa que o ADF devolveu bytes do snapshot. Uma entrada no journal marca uma tentativa anterior ao adapter, não um Evidence Bundle verificado. A telemetria opcional aparece só como visualização. Os próprios SVGs são a fonte destes diagramas; atualize SVG e texto alternativo juntos quando a fronteira mudar.

Exemplo em inglês: “Decisions at the boundary. Evidence with explicit limits.” Subtítulo: “Deterministic read-policy decisions at supported, installed coding-agent tool edges.”

Exemplo em português: “Decisões na fronteira. Evidências com limites explícitos.” Subtítulo: “Decisões determinísticas de leitura nas bordas instaladas e suportadas de ferramentas de agentes de código.”

Não adicione escudos, cadeados, cérebros, rostos de robô, efeitos neon, marcas de fornecedores ou alegações de contenção total. Reserve vermelho para uma negação real; não o use como ornamento.

## Reprodução e licença

Os SVGs foram escritos à mão, são estáticos e autocontidos. O PNG é gerado por `python3 docs/assets/brand/make-social-preview.py` com Pillow e uma fonte DejaVu Sans instalada; a fonte é rasterizada, não redistribuída, e o Pillow não grava metadados de texto ou data. `hooks/test-readme-presentation.sh` confere o tamanho (1280 × 640, ≤ 1 MB), que todo SVG da marca é autocontido e tem `<title>`/`<desc>`, e o hero do README (alt text, ≤ 3 badges, ordem de headings, paridade de imagens EN/PT-BR). Uma ilustração "editorial" raster foi considerada e não adotada: nenhuma existe no repositório, e uma imagem que não se regenera a partir de fonte enfraqueceria a regra de que toda imagem aqui é reproduzível. [O GIF da demo](../assets/README.md) é uma captura separada do hook/CLI reais com substituições de caminho documentadas. Os assets da marca são trabalho original do projeto distribuído sob a [Licença MIT](../../LICENSE). Nenhuma marca de terceiros foi incluída.
