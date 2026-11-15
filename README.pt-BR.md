# Arquimedes

Laboratorio em Python inspirado no FunSearch: propor funcoes candidatas, rodar cada uma em
sandbox isolado, medir com um verificador objetivo e guardar as melhores.

Status: MVP inicial.

## O que faz e onde estao os limites

Otimizar uma heuristica pequena com busca guiada e um verificador deterministico funciona
bem em problemas estreitos, nos quais qualquer resposta candidata pode ser conferida rapido.
Esse e o caminho usado por AlphaTensor (Fawzi et al., *Nature* 2022, multiplicacao de
matrizes), AlphaDev (Mankowitz et al., *Nature* 2023, rotinas curtas de ordenacao) e
FunSearch (Romera-Paredes et al., *Nature* 2024, evolucao de funcoes em Python para cap
sets e bin packing online).

O Arquimedes implementa esse ciclo em Python puro, comecando por bin packing online:

1. Parte de uma heuristica de referencia (`first-fit`, 221 bins no benchmark embutido).
2. Pede a um `Propositor` variantes da funcao de decisao
   `escolher_bin(item, livres) -> int`.
3. Valida a AST e executa cada candidata num processo `python -I` separado, sem rede, com
   timeout curto, builtins restritos e entrada/saida apenas por arquivos num diretorio
   temporario.
4. Reproduz e confere as atribuicoes no processo principal, conta os bins abertos e mantem
   as melhores candidatas num banco ordenado.

O que este MVP **nao** faz: descobrir sozinho uma "nova arquitetura que substitui o
Transformer" ou inventar algoritmos gerais sem um verificador explicito. Isso e norte de
pesquisa de longo prazo, nao entrega deste pacote.

## Seguranca

Todo candidato e codigo gerado e tratado como nao confiavel:

- O processo principal nunca chama `eval` nem `exec` sobre codigo candidato. Ele apenas faz
  o parse com `ast.parse` e barra imports, atributos dunder, classes, codigo assincrono e
  builtins perigosos antes de abrir o processo filho.
- A execucao acontece num subprocesso `python -I` novo, com ambiente limpo, diretorio
  temporario proprio, timeout, modulos de rede e de sistema bloqueados e uma lista curta de
  builtins permitidos.
- O processo principal nao confia no placar vindo do filho: ele recebe apenas a lista de
  atribuicoes em JSON e reexecuta a verificacao do zero.

Mesmo com essas camadas, o processo filho ainda roda com o usuario do sistema operacional.
Ao ligar um LLM real, rode o Arquimedes dentro de um container ou VM sem privilegios e sem
rede.

## Instalar e rodar

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
git config core.hooksPath .githooks
```

Para rodar o ciclo offline com o propositor deterministico de testes:

```bash
arquimedes rodar --problema bin_packing --iteracoes 5
```

Saida:

```text
Problema: bin_packing (pontuacao = custo, menor e melhor)
Iteracoes executadas: 4
Baseline: 221
Tentativas:
  iteracao 1: ok, pontuacao 221
  iteracao 1: ok, pontuacao 232
  iteracao 2: ok, pontuacao 218
Melhor: 218 (achado na iteracao 2)
Ganho sobre o baseline: 3 (1.36%)
```

## Como plugar um LLM real

Os testes e o CLI padrao usam `PropositorFake`, sem rede nem chaves de API. Para ligar um
modelo real (por exemplo via `nexcoder-core` ou servidor local), passe qualquer funcao
`prompt -> str` para `PropositorLLM`:

```python
from arquimedes.laboratorio import Laboratorio
from arquimedes.problema import BinPackingOnline
from arquimedes.propositor import PropositorLLM

propositor = PropositorLLM(gerar=minha_funcao_llm, quantidade=3)
relatorio = Laboratorio(BinPackingOnline(), propositor).rodar(iteracoes=10)
```

## Verificacao

```bash
ruff check .
python -m pytest
python scripts/check_no_emoji.py
```

Veja os detalhes dos modulos e do sandbox em `docs/ARCHITECTURE.md`. Licenca: MIT.
