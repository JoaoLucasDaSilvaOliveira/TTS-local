# Dock nativo do Kokoro Reader

O painel inicia recolhido: marca original de livro/onda, ler/retomar, pausar e
parar. Clique no nome ou na marca para abrir os controles. Escape recolhe.
O ícone na bandeja e uma segunda execução abrem o painel existente. A janela
fica sempre por cima no KDE com o helper habilitado.

O dock recolhido usa `WindowDoesNotAcceptFocus` e `WA_ShowWithoutActivating`:
clicar nos controles de reprodução não ativa o painel nem toma a seleção do
editor. Abrir os controles explicitamente permite foco de teclado; Tab percorre
os botões e opções, Space/Enter os ativa. A prévia usa texto simples e preserva
o cache da seleção/clipboard. As opções da bandeja continuam disponíveis.

A superfície azul de leitura, a marca lavanda e os SVGs em
`src/kokoro_reader/assets/` são originais deste projeto. O conceito compacto
que se abre no topo foi inspirado em [Coucou](https://github.com/Louis-CFM/coucou);
nenhum personagem, ícone, som ou mídia desse projeto foi copiado.

As transições de 180 ms só ocorrem ao abrir/recolher. A opção “Reduzir movimento”
foi removida da interface a pedido do usuário. O override técnico
`KOKORO_REDUCED_MOTION=1` e a preferência antiga em `dock.ini` continuam disponíveis
para acessibilidade, sem acrescentar controles ao painel. Não há animação
perpétua ou temporizador de reposicionamento. O polling existente continua em
750 ms para acompanhar seleção e serviço; o processo Qt não carrega modelo/áudio.

## Posicionamento no KDE / Wayland

Wayland entrega posicionamento ao compositor: `QWidget.move()` não garante
coordenadas. No Plasma 6, o instalador instala o pacote próprio
`kwin/kokoro-reader-dock` e habilita somente a chave
`[Plugins] kokoro-reader-dockEnabled` com `kwriteconfig6`. Descarrega somente o
script `kokoro-reader-dock` antes de reconfigure/start para recarregar seu código
nas atualizações, pois reconfigure sozinho pode manter a instância anterior.
O script define `keepAbove = true` apenas na janela do Kokoro Reader, porque
Wayland pode ignorar o hint de empilhamento solicitado pelo Qt.
Arquivos diferentes do mesmo pacote são preservados como `.before-install`.
Nenhuma regra global, painel, monitor ou configuração de outro app é alterada.
Isso não inicia o Kokoro automaticamente.

O script identifica o app `kokoro-reader` e o título `Kokoro Reader`, usa a área
disponível por monitor (`KWin.MaximizeArea`) para respeitar o painel superior e
mantém uma folga de 12 px. Ele reage a criação/exibição/mudança de tamanho do
dock, inclusive expansão, sem ativar a janela. Usa `workspace.windowAdded` e
`window.frameGeometryChanged`, sem depender de `windowShown`, que não está
exposto no objeto de janela dessa sessão Plasma 6. A opção `--without-kwin` ignora
essa integração. Para instalar manualmente:

```sh
kpackagetool6 --type=KWin/Script -i kwin/kokoro-reader-dock
kwriteconfig6 --file kwinrc --group Plugins --key kokoro-reader-dockEnabled true
qdbus6 org.kde.KWin /Scripting unloadScript kokoro-reader-dock
qdbus6 org.kde.KWin /KWin reconfigure
qdbus6 org.kde.KWin /Scripting start
```

Para desligar, desmarque “Kokoro Reader top dock” em Configurações do Sistema →
Gerenciamento de Janelas → Scripts do KWin, ou altere somente a chave acima para
`false` e rode reconfigure. Plasma 5 e outros compositores não são cobertos pelo
script. Fora do KWin, a janela pede posicionamento superior central pelo Qt;
funciona em X11 quando o gerenciador aceita, mas em Wayland depende do compositor.

Referências oficiais: [empacotamento e ativação de scripts](https://develop.kde.org/docs/plasma/kwin/)
e [API de geometria e área disponível](https://develop.kde.org/docs/plasma/kwin/api/).

## Extensão de fontes

`Panel.input_layout` é um `QVBoxLayout` público, imediatamente antes da prévia e
do botão de leitura, para anexar um widget de arquivo sem reconstruir o dock.
Depois de anexar um widget, a próxima expansão calcula a altura usando o conteúdo;
em telas baixas, os controles ficam em uma área com rolagem.

Os testes offscreen verificam estado, comandos, flags de foco e ciclo da animação;
não comprovam coordenadas reais no Wayland. Verifique a colocação numa sessão
Plasma 6 com o pacote habilitado, além da seleção num editor externo.
