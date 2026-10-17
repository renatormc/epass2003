# linha-de-comando Specification

## Purpose

Oferece o comando `epass2003` para instalar o driver do token e assinar PDFs pelo terminal, sem precisar escrever código Python.

## Requirements

### Requirement: Subcomando instalar-driver
`epass2003 instalar-driver` SHALL executar a instalação do driver e terminar com o código de saída dela. Se a instalação não puder começar por falta de privilégios, SHALL terminar com a mensagem `Erro: <motivo>`.

#### Scenario: Instalação concluída
- **WHEN** o usuário roda `epass2003 instalar-driver` e a instalação termina com sucesso
- **THEN** o comando termina com código 0

#### Scenario: Falha na instalação
- **WHEN** a instalação termina com um código diferente de zero
- **THEN** o comando termina com esse mesmo código

### Requirement: Subcomando assinar
`epass2003 assinar <entrada>` SHALL assinar o PDF de entrada e imprimir o caminho do arquivo gerado. A saída padrão é `<entrada>-assinado.pdf`, ou o caminho passado em `-o/--saida`. O comando SHALL aceitar `--modulo`, `--slot`, `--certificado`, `--motivo`, `--local`, `--tsa`, `--texto` e `--opacidade` e repassá-los à assinatura.

#### Scenario: Assinatura simples
- **WHEN** o usuário roda `epass2003 assinar documento.pdf` e informa o PIN correto
- **THEN** é gravado `documento-assinado.pdf` e o comando imprime "PDF assinado salvo em: documento-assinado.pdf"

#### Scenario: Saída personalizada
- **WHEN** o usuário passa `-o assinado.pdf`
- **THEN** o PDF assinado é gravado em `assinado.pdf`

### Requirement: Origem do PIN
O PIN SHALL ser obtido nesta ordem: a opção `--pin`, depois a variável de ambiente `EPASS_PIN`, depois um prompt no terminal que não mostra o que é digitado.

#### Scenario: PIN pela variável de ambiente
- **WHEN** `EPASS_PIN` está definida e `--pin` não foi passado
- **THEN** o PIN da variável é usado, sem prompt

#### Scenario: PIN digitado
- **WHEN** nem `--pin` nem `EPASS_PIN` foram informados
- **THEN** o comando pede "PIN do token: " sem mostrar o que é digitado

### Requirement: Opção de assinatura visível
`--visivel` SHALL receber `PÁG,X1,Y1,X2,Y2`: cinco inteiros, com a página contada a partir de 0 e as coordenadas em pontos. Qualquer outro formato SHALL ser rejeitado com erro de uso. `--imagem` SHALL exigir `--visivel`.

#### Scenario: Formato válido
- **WHEN** o usuário passa `--visivel 0,50,50,300,120`
- **THEN** a assinatura é desenhada na primeira página, no retângulo (50,50)-(300,120)

#### Scenario: Formato inválido
- **WHEN** `--visivel` não tem exatamente cinco inteiros separados por vírgula
- **THEN** o comando termina com erro de uso antes de pedir o PIN

#### Scenario: Imagem sem visível
- **WHEN** o usuário passa `--imagem` sem `--visivel`
- **THEN** o comando termina com o erro de uso "--imagem exige --visivel"

### Requirement: Mensagens de erro
Os erros de token, certificado ou assinatura SHALL encerrar o comando com código diferente de zero e a mensagem `Erro: <descrição>`, sem traceback.

#### Scenario: PIN incorreto
- **WHEN** o PIN informado está errado
- **THEN** o comando termina com "Erro: PIN incorreto." e código diferente de zero

### Requirement: Subcomando testar-assinador
`epass2003 testar-assinador <pdf>` SHALL pedir ao assinador local em `127.0.0.1:3399` a assinatura de um PDF do disco, montando o mesmo pedido `GET /assinarPdf` que um sistema web faria. O `fileDownload` SHALL ser a URL do endpoint de teste com o caminho absoluto do arquivo. O comando SHALL funcionar sem carregar a interface gráfica nem o servidor do assinador.

#### Scenario: Assinatura de teste bem-sucedida
- **WHEN** o assinador está rodando com `--test` e ligado, e o usuário roda `epass2003 testar-assinador laudo.pdf` e digita o PIN correto no diálogo
- **THEN** o comando grava `laudo-assinado.pdf` e imprime "PDF assinado salvo em: laudo-assinado.pdf"

#### Scenario: Caminho relativo
- **WHEN** o PDF é informado com caminho relativo
- **THEN** o comando converte o caminho para absoluto antes de montar a URL de download

#### Scenario: Saída personalizada
- **WHEN** o usuário passa `-o assinado.pdf`
- **THEN** o PDF assinado é gravado em `assinado.pdf`

#### Scenario: CPF informado
- **WHEN** o usuário passa `--cpf 123.456.789-00`
- **THEN** o pedido envia esse CPF em Base64 no parâmetro `cpf`, e o assinador só usa um certificado desse titular

#### Scenario: Sem CPF
- **WHEN** `--cpf` não é informado
- **THEN** o pedido envia `cpf` vazio e o assinador não restringe o certificado por CPF

### Requirement: Verificação prévia do assinador
Antes de pedir a assinatura, `testar-assinador` SHALL conferir que o PDF existe e que o assinador responde em modo de teste. Se algo falhar, SHALL terminar com código diferente de zero e uma mensagem `Erro: <descrição>` que diga como resolver, sem abrir o diálogo de PIN.

#### Scenario: Arquivo inexistente
- **WHEN** o PDF informado não existe
- **THEN** o comando termina com erro dizendo que o arquivo não foi encontrado

#### Scenario: Assinador desligado
- **WHEN** nada responde em `127.0.0.1:3399`
- **THEN** o comando termina com erro orientando a iniciar `epass2003-assinador --test --ligado`

#### Scenario: Assinador fora do modo de teste
- **WHEN** o assinador responde, mas `/teste/pdf` devolve 404 sem JSON
- **THEN** o comando termina com erro dizendo que o assinador precisa ser reiniciado com `--test`

#### Scenario: Arquivo recusado pelo endpoint
- **WHEN** o endpoint de teste recusa o arquivo (por exemplo, porque ele não é um PDF)
- **THEN** o comando termina com erro mostrando a mensagem devolvida pelo endpoint

### Requirement: Resposta do assinador
`testar-assinador` SHALL esperar a resposta sem tempo limite de leitura, porque o usuário pode levar minutos para digitar o PIN. Uma resposta em Base64 SHALL ser decodificada e gravada. Uma resposta JSON com `status` SHALL encerrar o comando com código diferente de zero e a mensagem `Erro: <message>`.

#### Scenario: Usuário cancela no diálogo
- **WHEN** o usuário cancela o diálogo de PIN
- **THEN** o comando termina com "Erro: Assinatura cancelada pelo usuário." e nenhum arquivo é gravado

#### Scenario: CPF não confere
- **WHEN** o assinador responde com `status` 500 porque o CPF não corresponde ao token
- **THEN** o comando termina com a mensagem do assinador e nenhum arquivo é gravado
