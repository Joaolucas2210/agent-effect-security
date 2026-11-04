# Assets

[English](README.md) · **Português (Brasil)**

As [diretrizes da marca](../brand/BRAND_GUIDELINES.pt-BR.md) documentam os SVGs, contraste, semântica dos diagramas e a prévia social. `python3 docs/assets/brand/make-social-preview.py` regenera o PNG de 1280 × 640 com Pillow e uma fonte DejaVu Sans instalada. Um mantenedor precisa fazer upload do PNG em GitHub Settings → General → Social preview; apenas incluir o arquivo no commit não altera as prévias de links.

| Arquivo | O que mostra | Como é gerado |
| --- | --- | --- |
| `adf-demo.gif` | Comandos ADF reais numa fixture sintética: habilitar um projeto, criar a chave de evidência, permitir o payload `Read README.md` no formato Claude com bundle assinado, negar o payload `Read .env` pelo PDP com bundle, conferir `adf verify … --key` offline e contar motivos com `adf projects reasons`. ~12 s, ~400 KiB, 1048×410. | `python3 docs/assets/make-demo-gif.py` |

## Regeneração do GIF

`make-demo-gif.py` executa a CLI `adf` e o hook `PreToolUse` **reais**, com payloads sintéticos, em um repositório descartável e um `ADF_HOME` isolado. Captura a saída e gera os quadros de terminal com Pillow. Nenhuma linha no GIF é digitada à mão. É uma demo do contrato do hook, não a gravação de uma sessão do cliente Claude Code. Para facilitar a leitura, o repositório temporário é mostrado como `~/dev/my-app`, o `ADF_HOME` temporário como `~/.adf` e o caminho do bundle no comando `adf verify` é reduzido aos primeiros oito caracteres hexadecimais.

```bash
make install-dev                      # o script chama .venv/bin/adf
python3 -m pip install Pillow         # no Python que executa o script
python3 docs/assets/make-demo-gif.py  # regrava docs/assets/adf-demo.gif; falha acima de 3 MiB
```

Regenere o GIF quando mudar uma linha mostrada nele (reason codes, saída de `adf verify`, formato de `project-reasons`); os IDs dos bundles diferem a cada execução, como esperado.

## Gravação ao vivo (alternativa)

Para gravar um terminal interativo em vez de quadros renderizados, com `asciinema` e `agg` instalados:

```bash
asciinema rec docs/assets/adf-demo.cast --cols 92 --rows 17 --idle-time-limit 1.5
#   depois, manualmente, os mesmos seis passos do script (enable, key init, dois hook reads, verify, reasons)
agg --cols 92 --rows 17 --font-size 16 --speed 1.2 docs/assets/adf-demo.cast docs/assets/adf-demo.gif
```

Mantenha os seis passos e as mesmas substituições de caminho para os dois métodos mostrarem a mesma coisa. Nunca grave um repositório real nem um `~/.adf` real: caminhos de evidência e IDs de projeto são específicos do host.
