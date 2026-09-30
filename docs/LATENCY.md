# Latência local e continuidade

O modelo continua sendo Kokoro 0.9.4 / PyTorch 2.6 CPU, com duas threads,
pesos e três vozes locais. Nenhuma dependência foi adicionada.

## Mudanças

- O primeiro WAV toca assim que fica pronto; foi removida a espera artificial
  de até dois segundos pelo segundo trecho.
- A primeira frase completa fica separada das seguintes. A regra normal de
  agrupamento de 100 caracteres continua nos demais trechos; o limite máximo
  de 220 caracteres e as fronteiras de linha continuam iguais. Uma frase
  longa continua exigindo a síntese de seu trecho inteiro.
- O produtor acorda o serviço quando um WAV fica pronto. O EOF é verificado
  a cada 20 ms, em vez de 80 ms, e o próximo WAV disponível é carregado na
  mesma verificação. Antes era necessário esperar outra verificação.
- Um aquecimento explícito é executado antes de abrir o socket de controle,
  usando a voz salva. Isso desloca a inicialização tardia para o início do
  serviço; não elimina o custo de inferência de texto novo.
- A geração inteira usa `torch.inference_mode()`. O modelo já usava
  `no_grad`; por isso essa mudança sozinha não promete um grande ganho.
- Um LRU em RAM reutiliza áudio para o mesmo texto e voz, limitado a 32 MiB
  de amostras e 64 entradas. A velocidade continua aplicada no mpv, portanto
  mudar velocidade não exige outra síntese. Nenhum texto/cache novo é salvo
  em disco. Os WAVs temporários da sessão continuam removidos ao parar.

## Medição reproduzível

Execute, com os pesos locais já instalados:

```sh
KOKORO_THREADS=2 PYTHONPATH=src .venv/bin/python scripts/benchmark_latency.py
```

O script não usa o serviço instalado nem toca áudio. Ele mede carregamento,
aquecimento, primeira frase, trecho completo e reutilização em RAM.

Em i5-1235U CPU, medições isoladas em 2026-09-30 com `pf_dora`:

| Amostra | Antes | Depois |
| --- | ---: | ---: |
| Trecho novo de 120 caracteres (7,2 s de áudio) | 4,026 s; repetição 3,737 s | 4,217 s |
| Primeira frase do mesmo texto, 40 caracteres (2,55 s de áudio) | agrupada no trecho de 120 caracteres | 1,297 s |
| Repetição do mesmo trecho de 120 caracteres | 3,737 s | 0,000004 s, cache RAM |

O aquecimento consumiu 1,195 s. O carregamento variou de 7,865 s antes para
4,866 s depois; essa diferença de carregamento não é atribuída à mudança
de código. São poucas amostras, sujeitas a carga e frequência da CPU. A
inferência de um trecho longo novo continua na ordem de segundos.

Uma comparação adicional no mesmo processo/modelo aquecido, sem cache,
alternou o método anterior e `inference_mode` para os mesmos 120 caracteres:
4,483 / 3,706 s e 3,922 / 3,807 s, respectivamente. Essa amostra pequena
reforça que o ganho principal vem do trecho inicial, do agendamento e da
reutilização, e não de uma redução radical da inferência CPU.

## Limites e verificação de ponta a ponta

`first_playback_seconds` termina quando os comandos mpv foram respondidos;
não mede diretamente a primeira amostra audível no PipeWire. O cache evita
inferência repetida, mas ainda há escrita do WAV e abertura pelo mpv. A
continuidade ainda depende de o produtor alcançar a velocidade de leitura;
uma primeira frase muito curta ou velocidade alta pode esgotar o buffer.
A redução da espera inicial é deliberada, e não promete áudio instantâneo
nem reprodução perfeitamente sem lacunas.

Uma inferência PyTorch em andamento não pode ser interrompida com segurança:
parar cancela o produtor e remove sua sessão imediatamente, mas uma leitura
nova pode aguardar a inferência anterior terminar no executor único. Seu
resultado não recria WAVs da sessão cancelada.

Os testes cobrem ausência de espera pelo segundo WAV, carregamento do próximo
na mesma verificação, despertar do produtor, limites LRU/separação por voz,
integridade das frases/linhas e cancelamento sem recriar arquivos. A aceitação
audível no desktop ainda precisa verificar velocidade, pausas, navegação e
troca de leitura com os três perfis de voz. O protocolo Unix permanece igual.
