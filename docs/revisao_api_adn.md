# Revisão da integração com o ADN — 3 de novembro de 2026

## Diagnóstico com as evidências disponíveis

O código anterior consultava `GET https://adn.nfse.gov.br/contribuintes/DFe/{NSU}?cnpj=...`. O contrato OpenAPI fornecido define o parâmetro como **`cnpjConsulta`**, com o CNPJ completo do estabelecimento. `cnpj` não consta entre os parâmetros dessa operação. Essa incompatibilidade foi corrigida.

O log de produção enviado pelo usuário registra, às 15:19:23 de 03/11/2026, consulta a partir do NSU 387, seguida de HTTP 400, `TipoConsulta: InscricaoCertificado`, `StatusProcessamento: REJEICAO`, `Erros: []`, `TipoAmbiente: PRODUCAO` e `VersaoAplicativo: 1.0.0.0`. Em seguida, a interface anunciava conclusão com zero documentos.

O retorno é compatível com consulta pelo titular do certificado, em vez de seleção explícita pelo CNPJ configurado. Entretanto, a ausência de código e descrição na resposta **não permite provar que o parâmetro incorreto seja a causa do HTTP 400**. Também não permite atribuir a falha a certificado expirado, procuração, cadeia de certificação ou indisponibilidade do serviço. Não foi efetuada chamada à API com certificado real.

## Comparação do contrato

O arquivo `swagger (1).json` fornecido descreve OpenAPI **3.0.1**, título **API NFS-e - ADN Contribuinte**, versão **v1**. Essa identificação não contém uma data de revisão imutável.

| Aspecto | Implementação anterior | Implementação corrigida |
| --- | --- | --- |
| Método e rota | GET `/contribuintes/DFe/{NSU}` | Método e rota preservados |
| CNPJ consultado | `cnpj` | `cnpjConsulta`, enviado por `params` |
| Lote | Implícito | `lote=true` explícito |
| NSU | Inteiro preenchido com zeros até 20 posições | Inteiro decimal, mantendo a semântica exclusiva |
| Retorno | Sem preferência explícita de formato | `Accept: application/json` |
| Autenticação | Certificado PFX convertido em PEM, com cadeia | Preservada; validação TLS permanece habilitada |
| Ambiente | Produção fixada no código | Produção ou produção restrita selecionável |
| HTTP 400 | Texto exibido, seguido de anúncio de sucesso | Exceção com resposta completa; sem sucesso nem avanço de NSU |
| Fim de distribuição | Apenas HTTP 204 | HTTP 404 com E2220/E2230, além das respostas antigas suportadas |
| Eventos | Podiam sobrescrever a nota com a mesma chave | Arquivo próprio com NSU no nome |
| PDF | API DANFSe v1 | Rotina e opção removidas por desativação oficial |

O manual atualmente vinculado no portal oficial, versão 1.0 de 12/02/2026, confirma consultas por NSU, eventos e o uso de certificado com a mesma raiz de CNPJ. O Swagger fornecido detalha `cnpjConsulta`, `cpfConsulta`, `lote` e `TipoConsulta`, incluindo autorização mediante procuração. O programa permanece focado em CNPJ e não implementa interface para consultas por CPF.

**Limitação de atualidade:** o índice Swagger indicado pelo usuário e as URLs de JSON tentadas não ficaram acessíveis pela ferramenta de consulta web. O ambiente de execução também não conseguiu estabelecer conexão com seu proxy. Não havia ferramenta de navegador conectada disponível. Assim, a compatibilidade foi verificada contra o Swagger fornecido e as publicações oficiais acessíveis, mas a igualdade com o JSON mais recente do servidor **não está confirmada**. Não se presumiu que a versão `v1` garantisse revisão idêntica entre produção e produção restrita.

## Certificado da matriz

Para consultar uma filial, selecione o certificado da matriz e informe o CNPJ completo da filial. A requisição passa a enviar, por exemplo:

```http
GET /contribuintes/DFe/387?cnpjConsulta=11222333000262&lote=true
Accept: application/json
```

O CNPJ do exemplo é ilustrativo. Conforme o contrato fornecido, a API autoriza a mesma raiz (oito primeiros caracteres) sem procuração e informa `TipoConsulta: CnpjBase`. Para outra raiz, o Swagger exige procuração válida; o erro documentado para sua ausência é E2245. Essa autorização é verificada no servidor e não foi simulada como prova de autorização real nos testes.

O PFX e sua senha continuam sendo usados para abrir a conexão TLS; o parâmetro identifica o contribuinte consultado. O programa mantém um controle de NSU por estabelecimento e por ambiente. Não há descoberta automática ou consulta simultânea de todas as filiais.

O CNPJ é normalizado, removendo a máscara e preservando letras para o formato alfanumérico, contemplado no histórico oficial de produção em 10/08/2026. O formato local exige 14 caracteres, com os dois verificadores numéricos; os dígitos e a autorização são validados pela API.

## PDF e DANFSe

O histórico oficial de implantações registra em **03/08/2026** a desativação da API de DANFSe do ADN, versão 1.0. A notícia de 14/07/2026 já havia prorrogado a adequação para essa data. A decisão de retirar a função se baseia nessas publicações e não em uma falha isolada de download.

Não foi identificada API oficial substituta para o download automatizado do PDF nesse fluxo. A geração permanece disponível pelos portais (Consulta Pública, Portal do Contribuinte e Painel Administrativo Municipal). A geração local pelo próprio software, conforme a NT 008, é outro desenvolvimento e não foi incluída nesta correção.

Foram removidos o módulo de download de PDF, sua exportação, o campo de configuração e a opção na interface. O carregamento de configurações antigas ignora `download_pdf`; ao salvar, o campo é eliminado. PDFs já existentes não são excluídos.

## Validação realizada

Executados **22 testes de regressão offline**, incluindo múltiplos cenários por teste:

- URL realmente preparada pelo `requests`, GET sem corpo, parâmetros, cabeçalho JSON, certificado selecionado, timeout e verificação TLS;
- consulta de dois estabelecimentos com o mesmo certificado selecionado e checkpoints separados;
- produção e produção restrita com hosts e NSUs separados;
- resposta HTTP 400 de produção com `Erros` vazio, conservando resposta completa e NSU;
- códigos E2210–E2214, E2243–E2247 e E999 preservados;
- HTTP 404 esperado e inesperado, JSON inválido, HTTP 503 e falha TLS de transporte;
- download, descompactação e gravação dos XMLs, separação dos eventos e lotes fora de ordem;
- interrupção entre documentos, falha de gravação e GZip inválido, sem avanço indevido de NSU;
- leitura de configuração antiga, normalização de CNPJ e rejeição de ambiente inválido;
- falha no início automático mantendo o erro disponível na interface;
- conversão de PFX de teste com chave, certificado e cadeia, e remoção do PEM temporário, inclusive em exceções.

Foram utilizados Python 3.13.5, requests 2.32.3 e cryptography 43.0.0, já instalados no Python do sistema. O adaptador HTTP é simulado; o processamento das requisições e a biblioteca criptográfica são reais. O certificado gerado nos testes é local e não corresponde a um certificado ICP-Brasil autorizado na API.

Comando de execução:

```bash
python -m unittest discover -s tests -p test_adn_api.py -v
```

Também foram verificadas a compilação dos módulos Python e a ausência de erros de espaços no diff. A suíte legada de funções do pytest não foi executada pelo pytest, que não está instalado neste ambiente. Seus stubs globais de criptografia foram removidos para não mascararem os testes reais, e o teste legado da requisição foi atualizado ao novo contrato.

Permanecem pendentes a execução com certificado real no ambiente escolhido, a confirmação de que a rejeição de produção foi resolvida, a obtenção do Swagger online para comparação integral e o teste visual da interface em ambiente gráfico. O pacote entregue contém código-fonte; não foi gerado executável Windows nem publicada uma release.

## Fontes oficiais consultadas

- [Swagger de produção restrita indicado pelo usuário](https://adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html) — acesso online indisponível; contrato fornecido em anexo utilizado como referência técnica.
- [Documentação atual de produção](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual) — página atualizada em 31/10/2026.
- [Manual de contribuintes: APIs do ADN](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf) — versão 1.0, de 12/02/2026; confirma o certificado com a mesma raiz de CNPJ.
- [Endereços das APIs em produção e produção restrita](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao) — distinção dos ambientes. A presença de links antigos de DANFSe nessa relação não foi tratada como prova de continuidade da API.
- [Histórico de atualizações e implantações](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/atualizacoes-e-implantacoes/atualizacoes-e-implantacoes) — página atualizada em 21/10/2026; confirma desativação da API de PDF em 03/08/2026 e tratamento do CNPJ alfanumérico em 10/08/2026.
- [DANFSE: ajustes e prorrogação do prazo](https://www.gov.br/nfse/pt-br/noticias/danfse-novos-ajustes-de-leiaute-e-prorrogacao-do-prazo-para-adequacao) — notícia de 14/07/2026, atualizada em 15/07/2026; NT 008 versão 1.02 e prazo de 03/08/2026.
- [Evoluções da plataforma e cronograma de implantação](https://www.gov.br/nfse/pt-br/noticias/plataforma-nfs-e-disponibiliza-novas-evolucoes-em-producao-restrita-e-divulga-cronograma-de-implantacao) — confirma disponibilização de DANFSe pelos portais e mudança do fluxo de geração.
