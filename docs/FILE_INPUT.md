# Arquivos locais

O leitor aceita `.txt`, `.md` e `.pdf` (extensão sem distinção de maiúsculas).
Texto e Markdown devem usar UTF-8; BOM UTF-8 é aceito. Outros encodings,
arquivos vazios e bytes nulos são recusados com uma mensagem explícita.
O Markdown original chega ao serviço, que aplica o `clean_markdown` existente.

PDFs precisam conter uma camada de texto pesquisável. A extração ocorre
offline com `pypdf==6.19.0`, sem OCR, downloads, APIs externas ou modelo extra.
PDFs sem texto, criptografados ou inválidos são recusados. A ordem de leitura
é aproximada: colunas, tabelas, cabeçalhos e rodapés podem sair em ordem
diferente da página visual. Quebras de linha e separadores entre páginas são
preservados na entrada; a segmentação habitual do serviço continua valendo.
Não há associação de destaque com as coordenadas do PDF original.

Limites: 60.000 caracteres, 240.003 bytes para TXT/MD, 10 MiB para PDF,
500 páginas e 2 MiB de conteúdo descomprimido por página. Documentos maiores
são recusados, nunca truncados silenciosamente. O parser ainda precisa
descomprimir um stream antes de verificar seu tamanho; estes limites não
constituem isolamento de memória para PDFs hostis.

Na interface expandida, abrir ou arrastar um único arquivo local prepara
a prévia e mostra nome, extensão e ícone nativo do tipo. O nome longo usa
reticências no meio; o tooltip permite consultar o caminho completo. Somente
o botão de leitura inicia a síntese. Remover retorna ao modo seleção/clipboard.
Falha ao substituir mantém o arquivo anterior e mostra o erro. Extração usa
um pool separado com uma thread; tarefas substituídas na fila são descartadas.
Nenhum destes controles escreve ou lê o clipboard.

CLI:

```bash
kokoro-reader read --file /caminho/guia.md
```

`--file`, `--text` e `--stdin` são mutuamente exclusivos. Os metadados enviados
ao serviço são `kind="file"`, `name`, `extension` e, para PDF, `page_count`.
O caminho completo e o conteúdo não são gravados nas preferências.

## Integração Qt (o módulo não altera panel.py)

`FileControls` expõe `loaded(Document)`, `cleared()`, `busy(bool)`, `error(str)`,
`document`, `read_payload`, `load_path(path)`, `open_dialog()` e `clear()`.
`Document` contém `path`, texto original `text`, `page_count`, `source` e
`read_payload={"text": ..., "source": ...}`. `DocumentController` tem os mesmos
sinais, `document`, `read_payload` e `is_busy`. Não conecta ao serviço.

Exemplo de cola (adaptar nomes dos callbacks à UI):

```python
from .file_controls import FileControls
self.files = FileControls(self)
self.input_layout.addWidget(self.files)
self.files.loaded.connect(self.show_file_preview)
self.files.cleared.connect(self.show_selection_preview)
self.files.busy.connect(lambda _: self.update_controls())
self.files.error.connect(lambda message: self.state.setText(message))
# Em submit, antes do override da seleção:
if command == "read" and "text" not in kwargs and self.files.read_payload:
    kwargs.update(self.files.read_payload)
# Em update_controls, incluir na condição do botão Ler:
can_read = can_read and not self.files.controller.is_busy
# No polling: atualizar SelectionCache normalmente, mas só exibir a seleção se:
if self.files.document is None:
    self.show_selection_preview()
```

`show_file_preview(document)` usa `document.text` para a prévia e `source`
para o título. O callback de clear deve exibir o cache atual e retomar sua
atualização normal. O widget já aceita drop em si; o Panel pode encaminhar
um drop local para `files.load_path(path)` e expandir a dock, se desejado.

Referências: [extração e limitações do pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html),
[criptografia](https://pypdf.readthedocs.io/en/stable/user/encryption-decryption.html).
