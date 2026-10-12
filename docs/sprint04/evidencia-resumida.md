# Evidência funcional - Sprint 04

**Execução:** 12/10/2026, 16:42 (horário de Brasília).  
**Resultado:** PASS.  
**Ambiente:** API FastAPI e PostgreSQL em Docker Compose local.

## O que foi verificado

1. Login ADMIN e comunicação com banco e motor C: `/health` retornou `status=ok`, `database=ok`, `engine=ok`.
2. Criação do ator de teste #11, leitura do PDF e associação ao documento #1.
3. Criação da demanda #8, cálculo e gravação do ranking. O ator de teste obteve score 1,0.
4. Rejeição de sete entradas inválidas, incluindo título curto, lista de competências vazia, peso zero, competência duplicada, orçamento negativo e PDF corrompido.
5. Conta `VIEWER`: leitura permitida (HTTP 200) e escrita/cálculo bloqueados (HTTP 403).
6. Reinício da API, novo login e nova leitura da demanda #8, do documento #1 e de três resultados gravados. `/health` continuou respondendo `ok`.
7. Navegação real com uma conta `VIEWER`: lista -> detalhe -> lista em desktop e celular; comandos de criação e cálculo ausentes para esse perfil; sem rolagem horizontal no celular. Resultado: `PASS`.

Os identificadores e resultados foram emitidos pelo [roteiro automático](../../api/scripts/smoke_sprint04.py) e permanecem no [registro bruto](evidencia-testes.txt). O `docker compose ps` desse registro foi capturado dois segundos após o reinício, quando o healthcheck do contêiner ainda mostrava `starting`; a verificação HTTP do próprio roteiro já havia retornado `ok`. A versão atualizada do roteiro aguarda também o healthcheck do Compose em futuras execuções.

Os nove testes locais de validação e segurança passaram (`api/tests/test_demand_validation.py` e `api/tests/test_security.py`). O conjunto completo de testes de ABI em C não pôde ser executado neste ambiente de automação por uma restrição de escrita nos diretórios temporários; isso não foi contado como PASS da Sprint 04.

As capturas estão em [lista no desktop](assets/lista-desktop.png), [detalhe no desktop](assets/detalhe-desktop.png), [lista no celular](assets/lista-celular.png) e [detalhe no celular](assets/detalhe-celular.png). A lista contém registros de testes anteriores, inclusive a demanda #7 com título curto criada antes de a validação ser corrigida.

