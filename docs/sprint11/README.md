# Sprint 11 — Documentação e revisão do código

- [Manual do Usuário](manual-usuario.md)
- [Manual Técnico](manual-tecnico.md)
- [Documentação consolidada](documentacao-consolidada.md)
- [Contrato HTTP](../API.md)

A revisão acompanhou a ingestão de PDFs, autenticação, perfis, persistência,
integração ctypes, regras de ranking e navegação. Foram conferidos os arquivos
de configuração, as dependências, as migrações e os roteiros de teste.

O nome recebido no upload era usado no caminho temporário do parser. O
valor `..` fazia a gravação apontar para um diretório e causar falha. A API
agora usa um nome interno fixo e mantém nos metadados somente o nome de
origem normalizado. O teste também cobre nomes recebidos com separadores
Windows. A correção preserva o hash e os contratos HTTP.

A suíte da API aprovou 33 testes com ABI e a do parser aprovou 61 testes.
O navegador confirmou PDF, revisão, demanda, ranking e consulta móvel.
Um envio HTTP com nome `..` retornou 201 e pôde ser recuperado com o nome
`upload.pdf`, sem caminho temporário no campo de origem. As capturas do
manual usam dados fictícios da execução local.

A inspeção dos arquivos versionados verificou que os exemplos de ambiente
estão documentados e não encontrou assinaturas de chaves privadas ou
tokens nos padrões pesquisados no estado atual do repositório. A preparação
final inclui ensaiar no ambiente de apresentação e confirmar o acesso dos
avaliadores à implantação.
