# Plano De Migracao Para Whisper.cpp

## Objetivo

Avaliar e preparar uma migracao futura do servico atual `whisper-asr` para uma alternativa baseada em `whisper.cpp`, com foco em reduzir uso de CPU/memoria e dar mais controle ao `legendas-webui` sobre quando gerar legendas a partir de audio.

Por enquanto, o setup continua usando o `whisper-asr` atual.

## Estado Atual

- O Compose usa `onerahmet/openai-whisper-asr-webservice` como `whisper-asr`.
- O servico usa `faster_whisper` com modelo configuravel por `WHISPER_MODEL`.
- O Bazarr ainda consegue chamar Whisper quando o provider `whisperai` esta habilitado.
- A direcao desejada e remover Whisper do fluxo automatico do Bazarr e disparar transcricao pelo `legendas-webui` como ultimo recurso.

## Por Que Avaliar Whisper.cpp

- Melhor eficiencia em CPU, especialmente com modelos quantizados.
- Menos overhead que stack Python completa.
- Binario simples e previsivel para homelab.
- Boa opcao quando nao ha GPU dedicada.
- Facil de rodar com `/media` montado como somente leitura.

## Riscos E Cuidados

- API diferente da API atual do `whisper-asr`.
- Pode exigir wrapper HTTP proprio ou chamada CLI controlada pelo `legendas-webui`.
- Qualidade e timestamps precisam ser comparados com `faster-whisper` atual.
- Modelos quantizados podem reduzir qualidade.
- Transcricao de anime/audio japones para ingles pode variar bastante por modelo.
- Nao deve escrever diretamente em `media/`; escrita deve continuar no `legendas-webui` rodando como `${PUID}:${PGID}`.

## Estrategia Recomendada

Rodar `whisper.cpp` em paralelo ao `whisper-asr`, sem substituir o servico atual inicialmente.

1. Manter `whisper-asr` atual funcionando.
2. Adicionar um novo servico experimental, por exemplo `whisper-cpp`.
3. Montar `./media:/media:ro` no `whisper-cpp` apenas se a integracao usar path local.
4. Montar modelos em `./config/whisper.cpp:/models`.
5. Fazer o `legendas-webui` escolher entre backend `whisper-asr` e `whisper-cpp` por variavel de ambiente.
6. Comparar resultado em episodios reais antes de trocar o padrao.

## Opcoes De Integracao

### Opcao A: Whisper.cpp Via CLI

O `legendas-webui` chama um container/servico ou executa comando que roda `whisper.cpp` sobre um arquivo em `/media`.

Vantagens:

- Simples de depurar.
- Controle total sobre argumentos.
- Facil salvar `.en.srt` temporario e mover para destino final.

Desvantagens:

- Precisa cuidar de concorrencia e timeout.
- Menos limpo que API HTTP.
- Pode exigir permissao para executar comandos no container correto.

### Opcao B: Whisper.cpp Server

Rodar `whisper.cpp` com modo servidor, se a imagem escolhida suportar API HTTP estavel.

Vantagens:

- Mais parecido com `whisper-asr` atual.
- Melhor isolamento.
- Facil para o `legendas-webui` chamar via HTTP.

Desvantagens:

- API pode nao ser compativel com a atual.
- Pode haver menos imagens prontas/maduras.
- Upload de arquivos grandes pode ser pesado se nao houver suporte a path local.

## Modelos A Testar

Comecar com modelos que equilibrem qualidade e custo:

- `large-v3-turbo`: primeira opcao para desempenho, se qualidade for suficiente.
- `medium`: fallback mais leve.
- `large-v3`: comparar qualidade com o setup atual, mas pode ser pesado.
- Quantizacoes `q5_0` ou `q8_0`: testar impacto em qualidade e performance.

## Mudancas De Compose Previstas

Adicionar, futuramente, um servico experimental:

```yaml
whisper-cpp:
  image: <imagem-whisper-cpp-a-definir>
  container_name: whisper-cpp
  restart: unless-stopped
  environment:
    - TZ=${TZ}
  volumes:
    - ./config/whisper.cpp:/models
    - ./media:/media:ro
  networks:
    - media_net
```

Notas:

- `./media` deve ser `:ro` no `whisper-cpp`.
- `whisper-cpp` nao deve criar `.srt` diretamente em `media/`.
- `legendas-webui` continua responsavel por gravar arquivos finais em `media/`.
- Se o backend usar upload em vez de path local, o mount `./media:/media:ro` pode ser dispensado.

## Mudancas No Legendas-Webui

Adicionar configuracao:

```dotenv
WHISPER_BACKEND=whisper-asr
WHISPER_ASR_URL=http://whisper-asr:9000
WHISPER_CPP_URL=http://whisper-cpp:<porta>
```

Comportamento desejado:

- `WHISPER_BACKEND=whisper-asr`: usa servico atual.
- `WHISPER_BACKEND=whisper-cpp`: usa novo backend experimental.
- Botao manual `Gerar legenda por audio` usa o backend configurado.
- Auto-Whisper, se existir no futuro, so roda quando nao houver legenda textual externa ou embutida.

## Plano De Teste

Usar os mesmos videos para comparar backends:

- Episodio com audio japones e legenda existente para comparar timing.
- Episodio sem legenda textual.
- Episodio com fala rapida/anime.
- Episodio com musica/ruido.

Medir:

- Tempo total de transcricao.
- Pico de CPU.
- Pico de memoria.
- Qualidade dos timestamps.
- Qualidade do texto em ingles.
- Compatibilidade do `.srt` gerado com Jellyfin/Bazarr.

## Criterios Para Migrar O Padrao

Migrar de `whisper-asr` para `whisper.cpp` apenas se:

- O tempo de transcricao for claramente melhor ou o uso de recurso for menor.
- A qualidade do texto/timestamps for aceitavel.
- A integracao com `legendas-webui` ficar estavel.
- O fluxo respeitar ownership: apenas `legendas-webui` escreve em `media/`.
- Houver rollback simples para `WHISPER_BACKEND=whisper-asr`.

## Decisao Atual

Nao migrar agora. Continuar com `whisper-asr` atual enquanto o pipeline principal e ajustado para:

- Remover Whisper automatico do Bazarr.
- Priorizar legendas textuais externas/embutidas.
- Deixar Whisper como ultimo recurso acionado pelo `legendas-webui`.
