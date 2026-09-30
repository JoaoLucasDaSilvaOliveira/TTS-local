# Validação

Executado em 30/09/2026 no CachyOS, Intel Core i5-1235U (12 CPUs lógicas), CPU com duas threads PyTorch. Não foi usado CUDA. Os resultados abaixo distinguem verificações objetivas de testes ainda pendentes na interface.

## Resultados executados

- Base: 21 testes passaram antes da validação dos controles. Com os controles: **25 testes passaram**, incluindo limpeza, segmentação, seleção primária/fallback, validação de vozes, persistência, navegação pausada, progressão EOF, parada durante síntese e remoção de arquivos.
- Instalação efetiva: `~/.local/share/kokoro-reader`, configuração em `~/.config/kokoro-reader`, launchers em `~/.local/bin`, pesos oficiais locais (~314 MiB). Python 3.12.14 e torch 2.6.0+cpu, `torch.version.cuda = None`.
- Serviço: `active` e `enabled`; symlink em `graphical-session.target.wants`. `RestrictAddressFamilies=AF_UNIX` efetivo. O modelo carregou em 8,432 s na primeira inicialização medida.
- Sockets privados: diretório 0700, `control.sock` e `mpv.sock` 0600. `ss -lxnp` mostrou somente Unix para leitor/mpv; `ss -ltnp` não mostrou listener TCP desses processos. Há listeners de outras aplicações da máquina.
- Reprodução real: `current-ao = pipewire`. Pausa manteve `time-pos`, navegação carregou WAV correto e conservou pausa, retomada progrediu até EOF, velocidade 0,75/1,00/1,10/1,50 foi confirmada no mpv. Conclusão e parada limparam `audio-*`.
- Persistência real: configurados `pm_alex` e 1,25x, serviço reiniciado; `status` confirmou os dois valores. Ao final, restaurados `pf_dora` e 1,00x.
- Hash do clipboard permaneceu igual antes/depois do teste; o cliente implementa somente chamadas `wl-paste`.
- Texto real enviado ao leitor inclui acentos, números, moeda, siglas e URL. A saída foi sintetizada/reproduzida; inteligibilidade exige audição humana.
- O teste real pode ser repetido por `uv run --no-sync python scripts/smoke.py`; ele reproduz áudio, usa controles, restaura voz/velocidade e escreve [smoke-results.json](smoke-results.json).

## Medições

Primeira leitura medida no serviço: primeiro trecho sintetizado em **2,453 s**, áudio de 2,500 s, comando de reprodução aceito em **2,530 s**. Essa rodada coincidiu com outro processo gerando amostras, portanto não é uma medida isolada.

Rodada posterior, serviço quente, sem geração simultânea de amostras: primeiro trecho em **1,355 s**, reprodução acionada em **1,372 s**. Teste contínuo independente, quatro trechos com `pf_dora`, velocidade 1,00: **4,949 s** de síntese total para **9,425 s** de áudio (RTF ≈ 0,525); primeira síntese **1,306 s**, primeiro comando de reprodução **1,331 s**, sessão total **10,201 s**. Esperas observadas nas três transições somaram **0,251 s**; incluem polling/troca de arquivo e não medem a latência física do dispositivo.

Amostras iguais, arquivo [voice-samples-results.json](voice-samples-results.json), carga do modelo 4,657 s:

| Voz | Síntese (s) | Áudio (s) | RTF |
| --- | ---: | ---: | ---: |
| pf_dora | 5,281 | 7,750 | 0,681 |
| pm_alex | 4,916 | 7,900 | 0,622 |
| pm_santa | 8,980 | 7,850 | 1,144 |

Essa comparação também ocorreu com o serviço fazendo síntese; não é benchmark isolado nem garantia de tempo real. `pm_santa` foi mais lenta que a duração de fala nessa rodada. Energia, carga da máquina e comprimento do texto afetam o resultado.

As três amostras são WAVs reais 24 kHz em `samples/` e foram reproduzidas em sequência pelo mpv com saída PipeWire; o processo concluiu com código zero. Isso confirma reprodução técnica, não avaliação humana da pronúncia. Pronúncia de números/siglas depende do eSpeak/Kokoro; houve um aviso de contagem de palavras do phonemizer em uma frase numérica, sem falha da síntese.

## Pendências explícitas

Cadastro e disparo dos atalhos no KDE; seleção/clipboard nos aplicativos Obsidian e Zed; audição humana de acentos/números/siglas nas três vozes; visualização das notificações; e logout/login real. Não executados nesta sessão. Não foi usado controle de interface do Orca após o usuário pedir que ele não fosse utilizado. O cadastro da unit comprova configuração para iniciar na sessão gráfica; não comprova um ciclo de login que ainda não aconteceu.

## Ajuste de fluidez — 30/09/2026

Após relato de voz robótica e pausas, frases curtas do mesmo parágrafo passaram a ser agrupadas, buscando 100 caracteres sem ultrapassar os 220 existentes. O início aguarda até dois segundos adicionais pelo segundo WAV depois que o primeiro estiver pronto. Não houve troca de modelo, dependências ou aumento de threads de CPU. Navegação manual permanece sem essa espera adicional; voltar/próximo navega por grupos de frases quando elas foram agrupadas.

**27 testes passaram**, incluindo agrupamento sem perda de texto, respeito aos parágrafos e limite da espera inicial. O teste real de pausa/retomada, navegação pausada, velocidade, EOF, limpeza e clipboard passou novamente. Resultado: [smoke-grouped-results.json](smoke-grouped-results.json).

Leitura contínua com duas unidades de áudio: 4,236 s de síntese para 8,450 s de áudio, início em 4,275 s e espera de transição de 0,083 s. A fraseologia é a da rodada anterior, agora com separação em dois parágrafos; a saída mudou com o agrupamento, portanto não é uma comparação controlada de duração/qualidade. A rodada anterior tinha 0,251 s somados de transições. A espera inicial aumentou: melhora da continuidade tem custo de latência de início. Isso não garante eliminar pausas em textos longos ou sob carga, e naturalidade exige audição humana.

O [OpenJarvis indicado](https://github.com/open-jarvis/OpenJarvis) oferece múltiplos backends: [Kokoro local](https://github.com/open-jarvis/OpenJarvis/blob/main/src/openjarvis/speech/kokoro_tts.py), Cartesia e OpenAI TTS. Seu backend Kokoro usa por padrão `af_heart` (inglês americano). Sem saber qual voz/backend estava no exemplo ouvido, não se pode atribuir a diferença ao projeto em si. As limitações de trechos muito curtos são descritas nas [vozes oficiais do Kokoro](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

## Painel de controle — branch feat/control-panel

Painel Qt opcional com menu KDE, ícone de bandeja, leitura seleção/clipboard, pausar/retomar/parar, anterior/próximo, avanço/recuo 10 s no trecho, velocidade, voz e janela por cima. O painel usa somente o socket do serviço e um socket Unix próprio para reutilizar a janela quando aberto novamente. Não carrega modelo TTS. Qt/PySide6 é instalado pelo extra `gui` (download de aproximadamente 73,5 MiB nesta máquina); instalação somente de terminal continua possível.

**32 testes passaram**, incluindo interface Qt offscreen, estados dos botões, comandos explícitos idempotentes, encaminhamento dos botões, preservação de preferências no polling e fila de ações quando há consulta de status em andamento. O painel foi aberto na sessão **Wayland real**, conectou ao serviço e a captura da própria janela foi inspecionada visualmente (`scripts/check_panel.py`). A entrada `.desktop` foi validada com `desktop-file-validate`.

O teste de áudio real foi reexecutado com os novos comandos de serviço; resultados em [smoke-panel-service-results.json](smoke-panel-service-results.json). A validação automática da interface não substitui o teste humano de clique na bandeja do KDE ou seleção dentro de Obsidian/Zed.

## Correções de prévia, releitura e conexão

- Prévia da seleção/clipboard limitada a 180 caracteres; texto completo preservado somente em memória. O botão Ler usa o texto da prévia, inclusive para repetir após EOF. A captura ignora seleção primária pertencente a controles do app quando já há um texto externo capturado. Os controles editáveis de velocidade foram substituídos por botões −/+ e rótulo sem seleção de texto, evitando que o app publique números como seleção primária.
- Cada quebra de linha real separa trechos, mesmo sem linha em branco; frases curtas só são agrupadas dentro da mesma linha.
- O journal mostrou `ConnectionResetError` no encerramento do IPC do mpv durante reinício do serviço. `KillMode=mixed` permite ao processo principal encerrar seu mpv; fechamento de streams tolera reset/pipe fechado. Clientes que desconectam durante resposta também são tratados sem traceback. Erros fatais do daemon vão para o journal, sem gerar uma notificação a cada reinício automático.
- O app reconecta por consultas silenciosas de status; mensagens de conexão são compreensíveis e notificações repetidas de ações manuais são limitadas a uma por 30 segundos.
- **38 testes passaram**, incluindo quebra de linha, cache/releitura do texto completo, proteção contra seleção interna `0`, fechamento do mpv com reset e limite de notificações.
- App aberto e conferido na sessão Wayland com prévia truncada. Reinício do serviço confirmou `KillMode=mixed`, serviço ativo e encerramento sem traceback no journal. Teste real ampliado: [smoke-input-fixes-results.json](smoke-input-fixes-results.json).

O comportamento nos aplicativos Obsidian/Zed depende de como cada aplicativo publica a seleção Wayland; a prévia permite verificar exatamente qual texto será enviado antes de clicar em Ler.

## Checklist manual em Obsidian e Zed

Em cada aplicativo, selecionar/copiar o texto abaixo e disparar o atalho cadastrado:

> Ação e coração: revisão de ciência. Em 2026, são 25 minutos e R$ 12,50. CPU, INSS e TTS. Veja https://example.com/estudo. Primeiro parágrafo.

> Segundo parágrafo: pausa, retomada, anterior e próximo. Acentos: á, ê, í, ó, ú e ç.

- Seleção primária funciona; seleção vazia usa clipboard; conteúdo copiado permanece igual.
- Pronúncia de acentos, números, siglas e domínio é inteligível nas três vozes.
- Pause por alguns segundos e retome do mesmo ponto.
- Próximo/anterior vão ao início do trecho e funcionam quando pausado.
- Velocidade responde durante fala e fica limitada a 0,75–1,50.
- Parar remove WAVs; leitura concluída remove WAVs; erro/vazio/início aparecem como notificação.
- Reiniciar serviço preserva voz/velocidade; sair/entrar no KDE inicia o serviço.
- Conferir PID em `ss -ltnp`: nenhum listener TCP do leitor ou mpv.

Não marque o checklist manual como aprovado com base apenas nos testes automatizados.

## Doca e documentos — 30/09/2026

As duas features foram desenvolvidas por agentes com escopos separados, em
`feat/top-dock` e `feat/file-input`, ambas iniciadas em `7af97b4`. A integração
foi revisada numa terceira branch antes do merge em `main`.

**76 testes passaram** com o extra Qt: expansão/recolhimento interrompível,
Escape, foco/nome acessível dos controles, movimento reduzido, fonte maior,
rolagem, limites e falhas de arquivos, drag/drop local, carregamento em thread,
releitura integral, prioridade do arquivo na doca e retorno ao clipboard.
O script KWin também foi executado no Qt JavaScript com janelas simuladas.

Na sessão KDE/Wayland real, `scripts/check_panel.py` conectou ao serviço e
capturas compacta/expandida/com arquivo foram inspecionadas. Um script temporário
de diagnóstico consultou **somente janelas do próprio leitor** no compositor:
compacto 302×60 e expandido com largura 480, centro horizontal, 12 px abaixo da
área disponível e `keepAbove=true`. Verificação em áreas disponíveis 1920×1080
e 1920×1034. A integração não redefine monitores ou outras regras.

Essa verificação encontrou três problemas que foram corrigidos antes de
publicar: sinal `windowShown` inexistente, hint Qt de “por cima” ignorado pelo
Wayland e ausência de recarga do script ao reinstalar. O KWin agora define
`keepAbove` apenas no leitor; o instalador descarrega e recarrega somente seu
plugin. O diagnóstico temporário foi descarregado após a verificação.

`scripts/check_documents.py` gerou fixtures públicas TXT/MD/PDF e confirmou
metadados, síntese CPU, início de reprodução via mpv, pausa/retomada e remoção
dos WAVs. Primeira síntese / início: TXT 1,994 / 3,563 s, MD 0,477 / 2,212 s,
PDF 1,494 / 1,502 s. Estes tempos variam com texto e carga e medem comando aceito
pelo mpv, não latência física ou qualidade percebida.

O smoke geral foi repetido: navegação pausada, ±10 s, velocidade, EOF,
releitura da mesma seleção, separação por newline e clipboard inalterado.
Na leitura contínua: 3,578 s de síntese para 8,450 s de áudio, início em
3,592 s, espera de transição 0,084 s. Resultados:
[dock-files-results.json](dock-files-results.json).

Serviço confirmado `active`/`enabled`, `RestrictAddressFamilies=AF_UNIX` e
variáveis offline. `ss -ltnp` não mostrou listener do leitor ou do mpv.
Não foi realizado novo login, nem automação de interface dentro de Obsidian
ou Zed; o checklist humano acima continua pendente. Não há OCR ou avaliação
humana da pronúncia nesta validação.

As skills `frontend-design` e `ui-ux-pro-max` foram instaladas no ambiente do
agente e influenciaram hierarquia, ícones originais, foco, contraste, fonte do
sistema e movimento reduzido. A implementação permanece Qt nativa e offline;
não incorpora frameworks web, serviços remotos ou assets protegidos do Coucou.

## Rodada de bugfix — controles compactos

Na branch `fix/compact-playback-controls`, o cabeçalho passa a ter o único
conjunto de play/retomar, pause e stop. Antes, ele copiava `isEnabled()` dos
botões internos, que herdavam o estado desabilitado do painel ao recolher.
Agora os controles usam diretamente o estado do serviço e ficam fora do corpo
recolhível. O corpo mantém anterior/próximo, ±10 s e iniciar uma nova leitura.

78 testes passaram. Os dois testes novos falhavam antes da correção e cobrem
cliques após recolher, durante transição e ausência de instâncias duplicadas.
`scripts/check_compact_controls.py` testa cliques Qt contra o serviço real em
Wayland, incluindo um ciclo após expandir/recolher, sem usar seleção privada.
Houve uma falha inicial nessa verificação real; diagnóstico adicional foi
incluído no script e a repetição passou. Isso não substitui o teste humano.

**E2E do usuário pendente:** ler com a doca recolhida, pausar, retomar e parar;
expandir/recolher e repetir. A correção é instalada para essa validação, mas a
`main` permanece inalterada até aprovação. Nenhuma otimização de síntese ou
mudança do ciclo de janela foi implementada nesta rodada. As skills de UI
orientaram o conjunto único de controles e seus estados acessíveis.

## Aprovação do bugfix e integração de latência/doca — 2026-09-30

O usuário aprovou o E2E dos controles compactos ("bugfix green"). A correção,
a remoção da opção visível de movimento reduzido e o rótulo "Iniciar leitura"
foram integrados e publicados na `main` em `6068b5f`.

As duas features seguintes partiram desse mesmo HEAD, em worktrees e agentes
separados. A integração permanece em `feat/latency-stable-integration` até
aprovação humana. A suíte integrada passou com **97 testes**. Os testes antigos
de foco foram ajustados: a janela agora é permanentemente capaz de receber
foco; os botões compactos usam `NoFocus`. O teste de fonte ampliada mostra sua
janela explicitamente, sem depender de expansão para abri-la.

O probe real Qt Wayland realizou 23 transições sem trocar QWindow, winId,
flags ou superfície e sem hide/show/close no top-level. Um observador temporário
do KWin, filtrado pelo título e identidade do leitor, registrou uma única
adição e uma única remoção do mesmo ID no início/fim do processo; nenhuma
recriação intermediária. O observador foi descarregado após o teste. Isso não
substitui a aceitação visual dos efeitos configurados pelo usuário.

A checagem de áudio real encontrou uma corrida: o ACK de `loadfile` chega antes
de mpv disponibilizar suas propriedades. A checagem EOF agora tenta novamente
somente para `mpv: property unavailable`; desconexões e demais erros continuam
visíveis. Há regressões para recuperação e propagação dos erros reais. O smoke
aguarda abertura do WAV antes de medir posição ou testar seek.

O IPC de `loadfile` agora aguarda tanto o ACK quanto `file-loaded`, em qualquer
ordem e com timeout, antes de liberar consultas EOF. Isso impede consultar o
estado do arquivo anterior durante abertura. Desconexões, falhas de decodificação
e demais erros não são silenciados.

Smoke final com cache reiniciado: saída PipeWire, início de leitura contínua
em 1,653 s, 5,929 s de síntese para 8,875 s de áudio e espera de transição
registrada de 0,026 s. Releitura: início em 0,808 s sem cache e 0,018 s com cache.
Pausa, retomada, navegação, seek, velocidade, EOF, newline, limpeza e clipboard
passaram. Resultado: [latency-smoke-results.json](latency-smoke-results.json).
Métricas de fim usam EOF do mpv, não esgotamento físico do buffer do PipeWire:
tempo de sessão pode ser menor que duração de áudio com dados já enfileirados.
Não comprovam ausência de cortes ou lacunas audíveis; isso exige E2E humano.

Serviço `active`/`enabled`, restrito a AF_UNIX; nenhum listener TCP do leitor/mpv.

Medições de síntese CPU, estratégia, limites de cache e riscos de buffer:
[LATENCY.md](LATENCY.md). Início medido por IPC não equivale à primeira amostra
audível. A janela persistente conserva o visual existente; `frontend-design`
e `ui-ux-pro-max` orientaram foco, reversão de animações e acessibilidade.
Nenhuma skill/ferramenta Orca foi usada. Novo login e uso dentro de Obsidian/Zed
não foram automatizados; a próxima aprovação E2E permanece pendente.

## Ajuste final e autorização de merge — 2026-09-30

Após autorização do usuário para merge com ajuste das quebras, a limpeza
remove quebras simples antes da síntese e conserva linhas em branco. Regressões
na limpeza, segmentação e serviço validam exatamente: `Texto\nquebrado`
vira um trecho, `Texto.\nquebrado` preserva o ponto e suas duas frases, e
`Texto\n\nquebrado` mantém dois parágrafos. Nenhum WAV recebe newline literal.
**116 testes passaram.** Notificações do desktop estão desativadas; erros de
interface permanecem na doca, CLI em stderr e serviço no journal.

Merge autorizado não equivale a uma nova validação humana de prosódia/efeitos,
nem confirma teste dentro de Obsidian/Zed ou novo login.
