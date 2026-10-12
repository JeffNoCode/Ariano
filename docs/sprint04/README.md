# ARIANO - Sprint 04: primeiro módulo completo

**Curso:** Ciência da Computação, 8º período  
**Disciplina:** Fábrica de Software - Profa. Pryscilla de Barros Gonçalves  
**Integração:** Tópicos Avançados em Ciência da Computação - Prof. Antenor Jorge Parnaíba da Silva

**Equipe:** Matheus Augusto de Moura (01586638), Raul Anthony de Sousa Muniz (01633454), Jefferson de Souza Santo (01608589), Guilherme Andrade de Aguiar (01606498) e André Gomes dos Santos Filho (01586077). **Scrum Master:** Raul Anthony de Sousa Muniz.

## 1. Módulo entregue

O primeiro módulo completo é **Oportunidades**. A pessoa entra no sistema, abre a lista de demandas, cadastra uma oportunidade, opcionalmente envia um edital em PDF, revisa os campos extraídos, escolhe as competências obrigatórias ou desejáveis e seus pesos, salva a demanda, calcula o ranking e consulta o resultado. Demandas e rankings anteriores podem ser reabertos pela lista. A navegação também leva às telas de atores e, para administradores, usuários.

O PDF é um auxílio ao cadastro, não uma decisão automática: o scraper extrai título, prazo, orçamento e possíveis competências; uma pessoa confirma ou corrige esses dados e define os pesos antes de salvar. O cálculo do score é determinístico, realizado pela biblioteca em C a partir das competências do ator, da demanda e das relações entre tags. Não há modelo generativo atribuindo a nota. O detalhe por competência é armazenado junto ao resultado e pode ser consultado.

**Fluxo implementado:** login -> Oportunidades -> Nova demanda -> Ler PDF (opcional) -> Revisar e selecionar competências -> Salvar -> Calcular ranking -> Voltar à lista -> Reabrir demanda e ranking.

| Etapa | Interface / operação | Dados persistidos |
|---|---|---|
| Entrada | Login e controle ADMIN/EDITOR/VIEWER | `tb_users`, `tb_sessions` |
| Documento | Upload de PDF e revisão do que foi extraído | `tb_documents` (`payload` JSONB e hash) |
| Demanda | Formulário com solicitante, prazo, orçamento e tags | `tb_demands`, `tb_demand_tags` |
| Ranking | Execução do motor C e leitura da classificação | `tb_matches` (score e detalhes) |
| Retomada | Lista e detalhe de demandas existentes | Consultas às mesmas tabelas, sem dados simulados |

As competências dos atores vêm de `tb_actor_tags`; o vocabulário e as relações dirigidas entre competências vêm de `tb_tags` e `tb_tag_relationships`. A interface consome a API FastAPI, que conversa com PostgreSQL e com o motor C por `ctypes`. O scraper Python é chamado em processo separado. O Docker Compose sobe API e banco localmente.

## 2. Persistência comprovável

O roteiro `api/scripts/smoke_sprint04.py` cria um ator de teste, processa um PDF, cria uma demanda, calcula um ranking persistido e verifica as leituras. `api/scripts/run_sprint04_evidence.ps1` reinicia a API, faz novo login e verifica novamente documento, demanda, competências e resultados. Portanto a evidência não depende apenas do estado em memória do navegador. O PostgreSQL usa volume nomeado `ariano_pgdata`; reiniciar os serviços não apaga as tabelas. O roteiro grava o resultado em `docs/sprint04/evidencia-testes.txt` sem senha ou token.

Para demonstração manual, salve uma demanda e anote seu número; atualize a página ou feche e reabra o navegador, faça login, entre em **Oportunidades** e abra a mesma demanda. O PDF vinculado, as competências e o ranking salvo devem aparecer. Também é possível reiniciar a API entre as duas etapas.

## 3. Validações e mensagens

| Situação | Resultado esperado |
|---|---|
| Demanda sem título útil ou com menos de 3 caracteres | Não salva; o campo é identificado. |
| Nenhuma competência selecionada | Não salva; pede ao menos uma. |
| Competência repetida | API rejeita; evita ambiguidade no peso. |
| Peso zero, negativo ou inválido | Não salva; informa que o peso deve ser positivo. |
| Orçamento negativo | Não salva; informa o valor permitido. |
| Arquivo vazio, não PDF ou acima de 10 MB | Upload rejeitado com mensagem de validação. |
| PDF que não pode ser interpretado | Mensagem clara; não expõe o caminho temporário nem o erro interno do scraper. |
| Sessão expirada ou perfil sem permissão | Acesso negado; `VIEWER` não pode cadastrar ou calcular. |
| Servidor indisponível | Interface informa falha de conexão. |

O formulário mostra o erro perto da etapa afetada; a API também valida os dados, independentemente do navegador. As respostas `422` estruturadas são convertidas em nomes de campos legíveis. A seleção do PDF não salva a demanda automaticamente: para evitar vínculo incorreto, é preciso clicar em **Ler PDF** antes de **Salvar**.

## 4. Navegação e evidência funcional

Na barra lateral: **Oportunidades**, **Atores** e, para ADMIN, **Usuários**. Dentro de Oportunidades: lista -> formulário -> detalhe -> ranking, com retorno à lista. Um `VIEWER` pode consultar demandas e rankings, mas os comandos de criação e cálculo ficam ocultos e a API continua bloqueando a escrita. O fluxo utiliza os endpoints reais `POST /documents`, `GET /documents/{id}`, `POST /demands`, `GET /demands`, `GET /demands/{id}`, `POST /demands/{id}/match` e `GET /demands/{id}/matches`.

**Evidências reproduzíveis:** `docs/sprint04/evidencia-testes.txt` (gerado pelo roteiro) e demonstração ao vivo em `http://localhost:8000/app/`. Os testes locais de validação ficam em `api/tests/test_demand_validation.py`. As telas não são protótipos: as alterações lidas após o reinício vêm do banco.

## 5. Execução local

Pré-requisitos: Docker Desktop iniciado e uma conta ADMIN já criada conforme `api/README.md`. Na pasta `api`:

```powershell
docker compose --profile full up -d --build --wait api
```

Abra `http://localhost:8000/app/`. Para gerar a evidência de criação, erros e persistência, ainda na pasta `api`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_sprint04_evidence.ps1
```

O roteiro pede e-mail e senha sem mostrá-la no terminal. Não use `docker compose down -v`, pois essa opção remove o volume de dados. A documentação interativa da API fica em `http://localhost:8000/docs`.

## 6. Repositório e evolução

Repositório: [JeffNoCode/Ariano](https://github.com/JeffNoCode/Ariano). As mudanças da Sprint 04 devem aparecer em commits separados para API/validação, interface/fluxo e documentação/evidência. A autoria real é preservada; não se atribuem contribuições retroativas aos demais integrantes.

## 7. Dificuldades e próximos passos

O fluxo já tinha serviços separados, mas as telas de documento, demanda e ranking ainda não estavam integradas. Foi necessário listar demandas pela API, adaptar o envio de formulário com arquivo, mapear as competências extraídas para o catálogo e buscar o ranking persistido ao reabrir uma demanda. A extração do PDF pode falhar em documentos digitalizados ou de baixa qualidade; por isso os campos são revisáveis e o cadastro manual permanece disponível.

Próximos passos: ampliar os testes de navegação automatizada no navegador; paginar listas extensas; permitir edição/encerramento de demandas; melhorar segurança para implantação externa (HTTPS, segredos e proteção contra tentativas de login); evoluir o uso das relações entre competências. O armazenamento atual já representa relações dirigidas entre tags, mas **não** utiliza banco de grafos. Uma migração para tecnologia de grafos permanece uma possibilidade futura, não parte desta entrega.

## Observação sobre a entrega acadêmica

Este Markdown é o registro individual da Sprint 04. A instrução da disciplina pede **um PDF único com as Sprints 01 a 04**; portanto, este arquivo ainda precisa ser incorporado à versão final em PDF antes do envio pelo Scrum Master. O número do grupo não foi informado pela equipe e não é inventado aqui. O texto e os resultados devem ser conferidos pelo grupo antes da submissão.

