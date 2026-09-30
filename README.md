<img src="src/kokoro_reader/assets/kokoro.svg" alt="Logo: livro aberto com uma onda de voz" width="64" height="64">

# Kokoro Reader

Leitor de texto em voz alta para estudos em português brasileiro, com síntese local em CPU e uma doca nativa para KDE Wayland.

Selecione um texto no Obsidian, no Zed ou em outro aplicativo e acione um atalho para ouvir sem enviar o conteúdo a um serviço externo. Também aceita TXT, Markdown e PDFs pesquisáveis. O projeto integra inferência, processamento de documentos, comunicação entre processos e interface desktop em um fluxo offline.

**Python 3.12 · Kokoro-82M · PyTorch CPU · Qt/PySide6 · asyncio · systemd · mpv/PipeWire**

## Funcionalidades

- Seleção primária Wayland com clipboard como alternativa, sem modificá-lo.
- Doca compacta com play, pause e stop; expansão animada na mesma janela nativa, sem fechar/reabrir.
- Navegação entre trechos, avanço/recuo de 10 segundos e velocidade de 0,75× a 1,50× com preservação de tom.
- Importação por seletor ou arrastar/soltar de `.txt`, `.md` e PDFs com camada de texto.
- Vozes brasileiras Dora (`pf_dora`), Alex (`pm_alex`) e Santa (`pm_santa`); voz e velocidade persistidas.
- Prévia, identificação do arquivo e estado da leitura na doca, sem notificações do desktop.

A integração com Obsidian e Zed usa seleção/clipboard e atalhos do sistema: não exige plugins ou extensões.

## Arquitetura e decisões técnicas

O modelo permanece carregado em um serviço separado da interface. Isso evita carregar pesos a cada ação e mantém a inferência fora do processo Qt.

```text
Seleção / clipboard / TXT / Markdown / PDF
                    │
              Cliente CLI ou doca Qt
                    │ JSON via socket Unix privado
              Serviço systemd --user
                    │ Limpeza → segmentação → Kokoro em CPU
                    │ Fila de WAVs locais
              mpv via IPC Unix → PipeWire
```

- **IPC local:** sem HTTP ou listener TCP; socket de controle `0600`, diretório `0700` e validação do UID do cliente.
- **Concorrência controlada:** laço assíncrono de comandos e executor dedicado à síntese, com produção adiantada limitada.
- **Início mais rápido:** primeiro trecho de até 100 caracteres, priorizando pontuação; os seguintes mantêm até 220. Sem espera artificial pelo segundo WAV.
- **Cache limitado:** reutilização por texto/voz em RAM, até 32 MiB e 64 entradas. Velocidade aplicada no mpv, sem ressíntese.
- **Ciclo de vida explícito:** cancelamento, limpeza de áudio temporário e espera pelo evento `file-loaded` do mpv antes de consultar EOF.
- **Reprodutibilidade:** dependências diretas fixadas, `uv.lock`, índice CPU do PyTorch e revisão fixa dos pesos oficiais.

Quebras simples de linha viram espaços; linhas em branco preservam parágrafos. A limpeza de Markdown prioriza texto, reduz URLs a domínios e ignora metadados e blocos longos de código.

## Instalação

Ambiente alvo: **CachyOS/Arch Linux, KDE Plasma 6 e Wayland**, com PipeWire, `uv` e `wl-clipboard` disponíveis. Desenvolvido e medido em Intel Core i5-1235U usando CPU, sem CUDA ou Docker.

```bash
git clone https://github.com/JoaoLucasDaSilvaOliveira/TTS-local.git
cd TTS-local

sudo pacman -Syu --needed espeak-ng mpv
uv python install 3.12
uv sync --python 3.12 --locked --extra gui
uv run --no-sync pytest
uv run --no-sync python scripts/install.py

cd ~/.local/share/kokoro-reader
uv run --no-sync kokoro-reader download
systemctl --user enable --now kokoro-reader.service
~/.local/bin/kokoro-readerctl status
~/.local/bin/kokoro-reader-panel
```

Python, dependências e pesos exigem rede na instalação inicial. Depois disso, síntese e reprodução usam arquivos locais, com modo offline do Hugging Face habilitado e o serviço restrito a sockets `AF_UNIX`. Pesos ausentes geram erro local, sem download automático.

O instalador usa `~/.local/share/kokoro-reader` e `~/.config/kokoro-reader`, preserva preferências e cria backups de arquivos conflitantes. No KDE, instala um script KWin que posiciona apenas a janela do leitor no centro superior da área disponível. Habilitar o serviço não abre a doca automaticamente.

<details>
<summary>Flags dos comandos de instalação</summary>

| Opção | Significado |
| --- | --- |
| `sudo` | Executa o pacman com privilégios administrativos. |
| `pacman -S` | Instala/sincroniza pacotes dos repositórios. |
| `-y` | Atualiza as bases de dados dos repositórios. |
| `-u` | Atualiza os pacotes instalados; `-Syu` faz a atualização completa, evitando atualização parcial no Arch. |
| `--needed` | Não reinstala pacotes que já estão atualizados. |
| `uv python install 3.12` | Instala Python gerenciado pelo uv. |
| `uv sync` | Cria/sincroniza o ambiente isolado `.venv`. |
| `--python 3.12` | Seleciona Python 3.12 para o ambiente, sem substituir o Python do sistema. |
| `--locked` | Exige um lockfile compatível, sem atualizar versões silenciosamente. |
| `--extra gui` | Inclui Qt/PySide6 para a doca e seus testes. |
| `uv run --no-sync` | Executa no ambiente existente sem sincronizar dependências novamente. |
| `systemctl --user` | Opera o systemd do usuário, sem sudo. |
| `enable` | Configura o serviço para iniciar com a sessão gráfica do usuário. |
| `--now` | Além de habilitar, inicia o serviço imediatamente. |

</details>

## Uso rápido

Abra **Kokoro Reader** no menu do KDE. Selecione ou copie texto e clique em play. Clique no nome/logo para expandir; `Escape` recolhe. Para arquivos, use **Abrir arquivo…** ou arraste um documento para a doca e escolha **Ler arquivo**.

```bash
kokoro-readerctl read --text 'Ação, ciência e tecnologia: uma revisão local.'
kokoro-readerctl read --file '/caminho/apostila.pdf'
kokoro-readerctl pause
kokoro-readerctl play
kokoro-readerctl speed 1.25
kokoro-readerctl stop
```

Em **Configurações do Sistema → Teclado → Atalhos**, adicione comandos/scripts e use o caminho absoluto do cliente, por exemplo `/home/SEU_USUARIO/.local/bin/kokoro-readerctl read`.

| Atalho sugerido | Comando |
| --- | --- |
| `Meta+Alt+R` | `kokoro-readerctl read` |
| `Meta+Alt+Space` | `kokoro-readerctl toggle` |
| `Meta+Alt+Left` / `Right` | `kokoro-readerctl previous` / `next` |
| `Meta+Alt+Up` / `Down` | `kokoro-readerctl faster` / `slower` |
| `Meta+Alt+S` | `kokoro-readerctl stop` |

Se o editor não publicar seleção primária, copie com `Ctrl+C`. O compositor pode ativar a doca ao clicar; o cache de seleção e os atalhos globais ajudam a preservar o fluxo. Consulte o [manual](docs/USAGE.md) para todos os controles e detalhes operacionais.

Os botões/atalhos de velocidade usam a escala `0,75 → 0,80 → 0,90 → 1,00 → … → 1,50`: passos de 0,10, exceto a ligação de 0,05 com o mínimo. É possível voltar a 1,00 após atingir qualquer limite. Valores manuais como 1,25 continuam válidos; o próximo −/+ vai ao vizinho da escala.

## Testes e desempenho

A suíte registrada contém **127 testes**, cobrindo limpeza e segmentação, seleção/clipboard, documentos, preferências, controles, cancelamento, cache e ciclo de vida da janela. Testes Qt usam backend offscreen; scripts opt-in verificam reprodução e a superfície nativa em Wayland. A validação foi executada localmente; não há badge de CI ou alegação de cobertura percentual.

```bash
uv sync --python 3.12 --locked --extra gui
uv run --no-sync pytest -q
KOKORO_THREADS=2 uv run --no-sync python scripts/benchmark_latency.py --long-opening
```

Uma medição CPU com `pf_dora` comparou a estratégia anterior com o limite inicial menor:

| Estratégia | Caracteres no primeiro trecho | Tempo de síntese |
| --- | ---: | ---: |
| Primeiro trecho anterior | 196 | 8,17 s |
| Primeiro trecho limitado, cortado na vírgula | 92 | 3,45 s |

Redução de aproximadamente **58% no tempo da primeira síntese dessa amostra**, por gerar menos texto antes de começar. Não representa aceleração de 58% do modelo inteiro, benchmark estatístico ou latência até o alto-falante. Textos novos ainda exigem inferência; cache beneficia repetições. Método, resultados e limites: [latência](docs/LATENCY.md) e [validação](docs/VALIDATION.md).

## Limites conhecidos

- Pronúncia e pausas dependem da voz, do texto e da segmentação. Início instantâneo e transições sem lacunas não são garantidos.
- PDFs precisam ter camada de texto: sem OCR; colunas e tabelas podem ter ordem de leitura diferente da visual. TXT/MD usam UTF-8. Limite de entrada: 60 mil caracteres.
- Inferência PyTorch em execução não é interrompida imediatamente; uma nova leitura pode aguardar seu término.
- Posicionamento da doca é específico do KWin/Plasma 6. Outros desktops não têm suporte equivalente validado.
- Não há plugin Obsidian, extensão Zed ou highlight sincronizado. IDs de sessão/trecho e metadados de origem preparam uma futura integração local do Obsidian.

## Explore o projeto

| Local | Responsabilidade |
| --- | --- |
| [src/kokoro_reader](src/kokoro_reader) | Motor, serviço, IPC, cliente, documentos e interface Qt. |
| [tests](tests) | Testes automatizados e regressões. |
| [scripts](scripts) | Instalador, benchmarks e verificações reais opt-in. |
| [systemd](systemd) / [kwin](kwin) | Integração da sessão gráfica e posicionamento da doca. |
| [Manual](docs/USAGE.md) | Instalação, atalhos, controles, diagnóstico e protocolo local. |
| [Arquivos](docs/FILE_INPUT.md) | Formatos, limites e extração de documentos. |
| [Janela persistente](docs/STABLE_DOCK.md) | Transições, foco e verificação da superfície Wayland. |

O clone é o código de desenvolvimento; `~/.local/share/kokoro-reader` é a instalação em execução. Para atualizar, teste, rode novamente `scripts/install.py` e reinicie o serviço. O reinício encerra a leitura atual.

## Créditos

Síntese com [Kokoro](https://github.com/hexgrad/kokoro) e os pesos/vozes oficiais de [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M). Reprodução com [mpv](https://mpv.io/manual/stable/#json-ipc). Os pesos não são redistribuídos neste repositório; dependências e modelos mantêm suas próprias licenças. A marca e os ícones SVG do leitor são originais do projeto.
