# Kokoro Reader

Leitor TTS local para CachyOS/Arch, KDE Wayland, Obsidian e Zed. Usa Kokoro-82M em CPU, `KPipeline(lang_code="p")`, voz inicial `pf_dora` e mpv/PipeWire. Sem Docker, CUDA, servidor HTTP ou API de síntese. Os atalhos leem a seleção primária Wayland e usam o clipboard como alternativa; nenhum comando altera o clipboard.

## Instalação

Clone o repositório e entre na pasta:

```bash
git clone https://github.com/JoaoLucasDaSilvaOliveira/TTS-local.git
cd TTS-local
```

Na pasta deste projeto:

```bash
sudo pacman -Syu --needed espeak-ng mpv
uv python install 3.12
uv sync --python 3.12 --locked
uv run --no-sync pytest
uv run --no-sync python scripts/install.py
cd ~/.local/share/kokoro-reader
uv run --no-sync kokoro-reader download
systemctl --user enable --now kokoro-reader.service
~/.local/bin/kokoro-readerctl status
```

O instalador copia o projeto para `~/.local/share/kokoro-reader`, cria um ambiente Python isolado nessa pasta, os launchers em `~/.local/bin`, configuração em `~/.config/kokoro-reader` e a unit em `~/.config/systemd/user`. Arquivos conflitantes da instalação são preservados em `.before-install` (com sufixo de tempo quando já existe um backup). Não copia nem modifica outros projetos. Instalações existentes mantêm voz e velocidade. Depois de atualizar uma instalação, use `systemctl --user restart kokoro-reader.service` para carregar o código atualizado.

Flags e ações:

- `pacman -S`: sincroniza/instala pacotes dos repositórios.
- `-y`: atualiza as bases de dados dos repositórios.
- `-u`: atualiza os pacotes instalados. Em Arch use a atualização completa `-Syu`, evitando atualização parcial.
- `--needed`: evita reinstalar pacotes que já estão atualizados.
- `sudo`: executa o gerenciador de pacotes com privilégios administrativos; pede sua senha.
- `uv python install 3.12`: baixa um Python 3.12 gerenciado pelo uv.
- `uv sync`: cria/sincroniza `.venv` com as dependências do projeto.
- `--python 3.12`: seleciona Python 3.12 para esse ambiente, sem trocar o Python do sistema.
- `--locked`: exige que `uv.lock` corresponda ao projeto; não atualiza versões silenciosamente.
- `--extra gui`: inclui Qt/PySide6 para o painel gráfico. O instalador usa esse extra por padrão; `scripts/install.py --without-gui` instala somente serviço/cliente de terminal.
- `uv run --no-sync`: executa no ambiente existente sem resolver/baixar dependências novamente.
- `systemctl --user`: opera o gerenciador systemd do usuário, sem sudo.
- `enable`: registra a unit para iniciar automaticamente na sessão gráfica do usuário.
- `--now`: além de habilitar, inicia o serviço imediatamente.

O download explícito instala somente configuração, pesos e três vozes oficiais do repositório `hexgrad/Kokoro-82M`, na revisão fixa declarada em `engine.py`. Python/dependências e pesos exigem rede uma vez. Síntese, amostras e reprodução posteriores usam arquivos locais, com `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`. A unit também restringe famílias de sockets a `AF_UNIX`. Um modelo ausente produz erro local, sem tentativa de baixar automaticamente.

Dependências diretas têm versões exatas e todas as transitivas estão no `uv.lock`; a origem de torch é o índice oficial CPU do PyTorch. `espeak-ng`, mpv e PipeWire são dependências do sistema, administradas pelo pacman.

## Uso e atalhos KDE

### Painel de controle

Abra **Kokoro Reader** pelo menu de aplicativos do KDE, ou execute:

```bash
kokoro-reader-panel
# Alternativa:
kokoro-readerctl panel
```

O painel oferece **Ler seleção / clipboard**, **Pausar**, **Retomar**, **Parar**, trecho **Anterior/Próximo**, recuo/avanço de **10 segundos dentro do trecho**, velocidade de 0,75x a 1,50x, voz Dora/Alex/Santa e progresso por trechos. A voz escolhida vale para a próxima leitura. Você pode marcar **Manter janela por cima** para deixar os controles acessíveis enquanto estuda. Mudanças de voz/velocidade continuam sendo salvas pelo serviço.

Ao fechar a janela, o painel fica na bandeja do KDE quando ela estiver disponível. Clique no ícone para reabrir, ou use o menu do ícone para controlar a fala. **Sair do painel** encerra apenas a interface; a leitura e o serviço continuam. Para encerrar a leitura, use **Parar**. Abrir novamente pelo menu reutiliza a janela existente. Se não houver bandeja, fechar a janela encerra o painel.

O painel mostra o estado do serviço e o trecho atual. Se o serviço estiver indisponível, pode iniciá-lo pelo botão **Iniciar serviço**; aguarde a carga do modelo. O progresso é por trechos, não por palavras. Avanço/recuo de 10 s respeita os limites do WAV atual; use Próximo/Anterior para navegar entre trechos.

O botão de leitura consulta a seleção primária Wayland e, quando vazia, o clipboard. Se o aplicativo perder a seleção ao focar o painel, copie com Ctrl+C antes de clicar em Ler. A interface não escreve no clipboard. Os atalhos globais abaixo também continuam funcionando.

Qt é opcional e só é carregado pelo painel; ele não carrega pesos nem cria outro motor de síntese. A interface consulta o serviço por socket privado e não abre porta de rede. Para instalar manualmente esse extra: `uv sync --python 3.12 --locked --extra gui`. O instalador também registra a entrada do menu em `~/.local/share/applications/kokoro-reader.desktop`.

### Atalhos globais

Em Configurações do Sistema → Teclado → Atalhos, use **Adicionar novo → Comando ou script** (os nomes podem variar entre versões do Plasma). Crie uma entrada para cada comando abaixo e atribua o atalho correspondente. Use o caminho absoluto, por exemplo `/home/dev_jao/.local/bin/kokoro-readerctl read`, porque `~`/PATH podem não ser expandidos pelo cadastro do KDE.

| Atalho | Comando após o caminho de `kokoro-readerctl` |
| --- | --- |
| Meta+Alt+R | `read` |
| Meta+Alt+Space | `toggle` |
| Meta+Alt+Left | `previous` |
| Meta+Alt+Right | `next` |
| Meta+Alt+Up | `faster` |
| Meta+Alt+Down | `slower` |
| Opcional: Meta+Alt+S | `stop` |

Selecione texto no Obsidian ou Zed e pressione Meta+Alt+R. Caso o aplicativo não publique seleção primária, copie com Ctrl+C e use o mesmo atalho. A seleção primária tem prioridade quando estiver preenchida — pode conter texto selecionado anteriormente em outro aplicativo. Para testar apenas texto explícito, use `read --text` ou `read --stdin`.

```bash
~/.local/bin/kokoro-readerctl read --text 'Ação, números e ciência: uma revisão local.'
~/.local/bin/kokoro-readerctl toggle
~/.local/bin/kokoro-readerctl pause
~/.local/bin/kokoro-readerctl play
~/.local/bin/kokoro-readerctl next
~/.local/bin/kokoro-readerctl previous
~/.local/bin/kokoro-readerctl seek-forward
~/.local/bin/kokoro-readerctl seek-backward
~/.local/bin/kokoro-readerctl faster
~/.local/bin/kokoro-readerctl slower
~/.local/bin/kokoro-readerctl speed 0.75
~/.local/bin/kokoro-readerctl voice pm_alex
~/.local/bin/kokoro-readerctl stop
```

Velocidade varia entre 0,75x e 1,50x; subir/descer soma/subtrai 0,10x e satura nos limites (o último passo pode ser menor). O mpv preserva o tom; mudanças têm efeito durante a reprodução. Voz e velocidade são salvas atomicamente em `preferences.json`. A mudança de voz vale para a próxima leitura, mantendo a voz da fila atual. `toggle` pausa/retoma inclusive durante buffering; anterior/próximo vai ao início do trecho, respeita pausa e limita-se à fila atual. Uma nova leitura substitui a anterior. Ao terminar, a fila e seus WAVs são removidos; anterior não revive uma leitura concluída.

## Limpeza, fila e privacidade

Remove frontmatter YAML inicial, comentários, imagens Markdown, marcadores, destinos de links e blocos de código com mais de duas linhas ou 120 caracteres. Mantém código curto, rótulos de links, nomes/aliases de wikilinks e texto com acentos/números. URLs soltas viram nomes de domínio. É um filtro conservador, não um parser completo de Markdown; tabelas, LaTeX e estruturas aninhadas podem ser lidas literalmente.

Parágrafos e frases geram trechos de até 220 caracteres. Frases curtas do mesmo parágrafo são agrupadas, buscando ao menos 100 caracteres quando couberem, para dar mais contexto à entonação e reduzir trocas de áudio. Parágrafos continuam separados. Decimais, algumas abreviações e siglas com pontos são preservados. O motor verifica o limite real de fonemas e subdivide antes de ultrapassá-lo, evitando truncamento silencioso em português. O tamanho máximo de uma leitura é 60 mil caracteres.

O modelo permanece carregado. Um executor único faz síntese em CPU com duas threads PyTorch (`KOKORO_THREADS` na unit permite ajuste), enquanto o laço assíncrono responde aos comandos. Até três trechos são sintetizados adiante; WAVs já ouvidos permanecem durante a leitura para permitir voltar. No início, após o primeiro WAV ficar pronto, espera até dois segundos adicionais pelo segundo WAV para reduzir interrupções. Leituras de um único trecho e navegação manual não têm essa espera adicional. A síntese continua com a mesma CPU e o mesmo modelo; esse ajuste não elimina limitações da voz. Não há promessa de transições sem qualquer intervalo: a troca de arquivo mpv e buffering podem introduzir pequenas pausas.

Sockets em `$XDG_RUNTIME_DIR/kokoro-reader`: `control.sock` (0600) e `mpv.sock`, dentro de diretório 0700. O serviço valida UID do cliente por `SO_PEERCRED`, usa lock exclusivo e não cria listener TCP. Áudio temporário fica em subdiretórios privados `audio-*`, é removido no fim/parada/troca e restos de encerramentos abruptos são limpos no próximo início. Não salva o texto nos logs; o endpoint local `status` retorna o trecho atual para o próprio usuário. Notificações locais sinalizam vazio, erro e início da reprodução.

## Amostras e desempenho

```bash
cd ~/.local/share/kokoro-reader
uv run --no-sync kokoro-reader samples --output samples
mpv samples/pf_dora.wav
mpv samples/pm_alex.wav
mpv samples/pm_santa.wav
```

O comando gera a mesma frase nas três vozes, WAV 24 kHz e `metrics.json` com carga do modelo, tempo de síntese, duração do áudio e fator de tempo real (síntese/duração, menor que 1 significa mais rápido que a fala). Arquivos de amostras são artefatos intencionais, não temporários; ficam até você removê-los. Os WAVs e a pasta `samples` não são versionados; gere-os com o comando acima. As medições da rodada inicial estão em [docs/voice-samples-results.json](docs/voice-samples-results.json).

`status` e o journal registram primeira síntese, tempo até o comando de primeira reprodução e duração total da sessão. O tempo até reprodução mede envio aceito pelo mpv, não latência física até o alto-falante. Consulte [docs/VALIDATION.md](docs/VALIDATION.md) para medições feitas e testes pendentes.

## Diagnóstico e inicialização no login

```bash
systemctl --user status kokoro-reader.service
journalctl --user -u kokoro-reader.service -b --no-pager
systemctl --user is-enabled kokoro-reader.service
systemctl --user is-active kokoro-reader.service
systemctl --user show-environment
ss -lxnp
ss -ltnp
```

Verifique no resultado de `ss -ltnp` que o PID do serviço e seu mpv não têm socket TCP em escuta. Outras aplicações podem ter listeners. A unit inicia com `graphical-session.target`; `is-enabled` confirma cadastro, mas confirmar um login real requer sair/entrar na sessão e repetir `is-active`/journal. Não é necessário habilitar linger: o leitor pertence à sessão gráfica. No início, `status` pode informar indisponível durante carga do modelo; consulte o journal.

O cliente precisa rodar na sessão Wayland com `WAYLAND_DISPLAY` e `XDG_RUNTIME_DIR`. Se notificações não aparecerem, confira `DBUS_SESSION_BUS_ADDRESS` no ambiente da sessão. O serviço não lê o clipboard; isso é feito pelo cliente invocado pelo KDE. Para parar/desabilitar: `systemctl --user disable --now kokoro-reader.service`.

## Integração futura

Protocolo JSON v1, uma requisição/uma resposta por conexão Unix: `{"protocol":1,"command":"read","text":"...","source":{"kind":"obsidian","note":"..."}}`. Comandos seguem os nomes do cliente; `voice`/`speed` aceitam `value`. Respostas contêm `ok`, estado, índice/quantidade, texto do trecho atual, origem, `session_id` e `segment_id`. Isso prepara consulta local de progresso por um futuro plugin Obsidian. Um highlight temporário por trecho poderá usar esses IDs e metadados; mapear posições no Markdown original e sincronizar palavras exige trabalho adicional. Nenhum plugin/extensão foi criado, e não há promessa de highlight no Zed.

## Desenvolvimento e versionamento

A `main` registra a base funcional com os controles e os ajustes de fluidez. O código-fonte é desenvolvido no clone; a cópia em `~/.local/share/kokoro-reader` é a instalação de execução. Para novas funcionalidades, crie branches a partir da `main`, rode `uv run --no-sync pytest` e revise as mudanças antes de integrá-las. O teste real `scripts/smoke.py` é opcional e reproduz áudio.

Para desenvolver e testar o painel, sincronize com `--extra gui`. `tests/test_panel.py` usa o backend Qt offscreen e é pulado quando o extra não estiver instalado.

O repositório inclui `uv.lock`, código, unit systemd, testes e relatórios de validação. Ambientes Python, pesos, áudio gerado, sockets e backups de instalação ficam fora do Git. Depois de atualizar o código e testar, reinstale com `scripts/install.py` e reinicie o serviço conforme descrito acima.

Fontes oficiais: [Kokoro pipeline](https://github.com/hexgrad/kokoro/blob/main/kokoro/pipeline.py), [modelo/vozes Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), [mpv IPC](https://mpv.io/manual/stable/#json-ipc).
