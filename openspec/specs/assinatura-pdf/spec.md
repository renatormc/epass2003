# assinatura-pdf Specification

## Purpose

Assina PDFs no padrão PAdES com o certificado ICP-Brasil guardado no token ePass2003. É o comportamento de assinatura usado pela linha de comando (`epass2003 assinar`) e pelo assinador local.

## Requirements

### Requirement: Descoberta do módulo PKCS#11
Se nenhum módulo PKCS#11 for informado, o sistema SHALL usar o primeiro que existir, nesta ordem: `/usr/lib/libcastle.so.1.0.0`, depois `/usr/lib/opensc-pkcs11.so`. Se nenhum existir, SHALL lançar um erro que orienta instalar o driver.

#### Scenario: Driver da Soluti instalado
- **WHEN** `/usr/lib/libcastle.so.1.0.0` existe e nenhum módulo foi informado
- **THEN** a assinatura usa esse módulo

#### Scenario: Somente OpenSC instalado
- **WHEN** só `/usr/lib/opensc-pkcs11.so` existe
- **THEN** a assinatura usa o módulo do OpenSC

#### Scenario: Nenhum módulo
- **WHEN** nenhum dos módulos padrão existe e nenhum foi informado
- **THEN** um `EPass2003Error` é lançado, sugerindo `epass2003 instalar-driver` ou informar o módulo

### Requirement: Seleção do certificado
O sistema SHALL considerar apenas os certificados do token que têm chave privada correspondente. Quando for informado um label, SHALL considerar só o certificado com esse label. Entre os certificados válidos na data atual, SHALL usar o que vence por último.

#### Scenario: Certificado renovado e vencido no token
- **WHEN** o token tem um certificado vencido e outro válido
- **THEN** a assinatura usa o certificado válido

#### Scenario: Vários certificados válidos
- **WHEN** há mais de um certificado válido elegível
- **THEN** a assinatura usa o que vence por último e registra um aviso no log com os labels encontrados

#### Scenario: Somente certificados vencidos
- **WHEN** todos os certificados elegíveis estão vencidos
- **THEN** um `EPass2003Error` informa que o certificado do token está vencido

#### Scenario: Nenhum certificado com chave
- **WHEN** nenhum certificado do token tem chave privada correspondente
- **THEN** um `EPass2003Error` informa que nenhum certificado com chave privada foi encontrado

### Requirement: Restrição por CPF do titular
Quando um CPF for informado, o sistema SHALL ignorar os caracteres que não são dígitos e usar apenas certificados desse titular. O CPF do certificado SHALL ser lido do CN, no formato `NOME:CPF`, e do otherName ICP-Brasil de OID `2.16.76.1.3.1`, posições 9 a 19. Se nenhum certificado for do CPF, SHALL lançar `CpfNaoConfere`.

#### Scenario: CPF confere
- **WHEN** o CPF informado está no CN ou no otherName ICP-Brasil de um certificado válido
- **THEN** a assinatura usa esse certificado

#### Scenario: CPF formatado
- **WHEN** o CPF é informado com pontos e traço
- **THEN** a comparação usa apenas os dígitos

#### Scenario: CPF não confere
- **WHEN** nenhum certificado do token pertence ao CPF informado
- **THEN** `CpfNaoConfere` é lançado

### Requirement: Assinatura PAdES
O sistema SHALL produzir uma assinatura PAdES com SHA-256. O motivo e o local SHALL ser incluídos quando informados.

#### Scenario: Assinatura invisível
- **WHEN** um PDF é assinado sem caixa de assinatura visível
- **THEN** o PDF resultante tem uma assinatura PAdES válida, sem aparência na página

#### Scenario: Motivo e local
- **WHEN** motivo e local são informados
- **THEN** eles constam nos metadados da assinatura

### Requirement: Assinaturas incrementais
O sistema SHALL acrescentar a assinatura de forma incremental, preservando as assinaturas existentes. O campo da nova assinatura SHALL se chamar `AssinaturaN`, com o menor N a partir de 1 que ainda não exista no documento.

#### Scenario: PDF sem assinaturas
- **WHEN** um PDF sem assinaturas é assinado
- **THEN** o campo de assinatura se chama `Assinatura1`

#### Scenario: PDF já assinado
- **WHEN** um PDF que já tem o campo `Assinatura1` é assinado
- **THEN** a nova assinatura fica no campo `Assinatura2` e a assinatura anterior continua válida

### Requirement: Assinatura visível
Quando uma caixa (x1, y1, x2, y2, em pontos, com origem no canto inferior esquerdo) for informada, o sistema SHALL desenhar a assinatura nessa área da página indicada (0 = primeira). O texto padrão é "Assinado digitalmente por / <titular> / Data: <data>" e aceita `%(signer)s` e `%(ts)s`.

#### Scenario: Somente texto
- **WHEN** a caixa é informada sem imagem
- **THEN** o texto da assinatura aparece dentro da caixa, na página indicada

#### Scenario: Imagem e texto
- **WHEN** a caixa, uma imagem e um texto não vazio são informados
- **THEN** a imagem ocupa cerca de 40% da caixa à esquerda e o texto ocupa o restante

#### Scenario: Somente imagem
- **WHEN** a caixa e uma imagem são informadas com texto vazio
- **THEN** só a imagem aparece, centralizada na caixa

#### Scenario: Opacidade da imagem
- **WHEN** uma opacidade entre 0 e 1 é informada
- **THEN** a imagem é desenhada com essa opacidade

#### Scenario: Imagem sem caixa
- **WHEN** uma imagem é informada sem caixa
- **THEN** um `ValueError` é lançado e nada é assinado

### Requirement: Carimbo de tempo
Quando a URL de um servidor de carimbo de tempo (RFC 3161) for informada, o sistema SHALL incluir na assinatura um carimbo de tempo obtido desse servidor.

#### Scenario: TSA informada
- **WHEN** a assinatura é feita com uma URL de TSA
- **THEN** a assinatura contém um carimbo de tempo dessa TSA

### Requirement: Erros do token
Todos os erros de driver, token, certificado ou assinatura SHALL ser lançados como `EPass2003Error` ou subclasses dele. Um PIN errado (ou com tamanho inválido) SHALL lançar `PinIncorreto`. Um PIN bloqueado SHALL informar que é preciso desbloquear com o PUK.

#### Scenario: PIN errado
- **WHEN** o PIN informado não confere
- **THEN** `PinIncorreto` é lançado

#### Scenario: PIN bloqueado
- **WHEN** o token está com o PIN bloqueado
- **THEN** um `EPass2003Error` informa que é preciso desbloquear o token com o PUK

#### Scenario: Falha de comunicação
- **WHEN** ocorre outro erro PKCS#11 ou um erro de assinatura
- **THEN** um `EPass2003Error` é lançado com a descrição do erro

### Requirement: Texto lateral opcional
A assinatura SHALL aceitar uma opção, desligada por padrão, para imprimir em todas as páginas o texto "Assinado eletronicamente por <nome>". O texto SHALL ser incluído na mesma revisão incremental da assinatura, de forma que fique coberto por ela. Com a opção desligada, as páginas SHALL ficar inalteradas.

#### Scenario: Opção ligada em PDF sem assinaturas
- **WHEN** um PDF de 3 páginas, sem assinaturas, é assinado com o texto lateral ligado
- **THEN** as 3 páginas mostram "Assinado eletronicamente por <nome>" e a assinatura é válida e cobre o documento inteiro, sem alterações posteriores

#### Scenario: Opção desligada
- **WHEN** um PDF é assinado sem a opção
- **THEN** o conteúdo das páginas não muda, como antes

### Requirement: Nome do titular no texto lateral
O `<nome>` SHALL ser o nome do titular do certificado usado na assinatura. Quando o CN tiver o formato ICP-Brasil `NOME:CPF`, SHALL ser só a parte antes dos dois pontos. Nos outros casos, SHALL ser o CN inteiro.

#### Scenario: CN com CPF
- **WHEN** o certificado tem CN `FULANO DE TAL:12345678900`
- **THEN** o texto é "Assinado eletronicamente por FULANO DE TAL"

#### Scenario: CN sem CPF
- **WHEN** o certificado tem CN `FULANO DE TAL`
- **THEN** o texto é "Assinado eletronicamente por FULANO DE TAL"

#### Scenario: Nome com acentos
- **WHEN** o nome do titular tem acentos ou cedilha (por exemplo, `JOÃO CONCEIÇÃO`)
- **THEN** os caracteres aparecem corretamente no PDF

### Requirement: Posição e aparência do texto lateral
O texto SHALL ficar na margem esquerda da página como ela é exibida (considerando `/Rotate` e o `CropBox`), a cerca de 1 cm da borda. SHALL ser lido de baixo para cima, centralizado na altura, em fonte Helvetica de 8 pt e cor cinza, desenhado por cima do conteúdo existente sem alterar o estado gráfico dele.

#### Scenario: Página retrato
- **WHEN** uma página A4 retrato sem rotação é assinada com o texto lateral
- **THEN** o texto aparece na vertical, junto à borda esquerda, centralizado na altura, lido de baixo para cima

#### Scenario: Página com rotação
- **WHEN** a página tem `/Rotate 90` (ou 180, ou 270)
- **THEN** o texto aparece na borda esquerda da página como ela é exibida, lido de baixo para cima

#### Scenario: Conteúdo com estado gráfico aberto
- **WHEN** o conteúdo original da página termina com uma transformação ou cor sem restaurar o estado gráfico
- **THEN** o texto lateral aparece na posição e cor especificadas, e o conteúdo original não muda de aparência

### Requirement: Texto lateral em PDF já assinado
Se o PDF já tiver ao menos uma assinatura preenchida, o sistema SHALL assinar sem imprimir o texto lateral, mesmo com a opção ligada, e SHALL informar que o texto foi omitido. Assim, as assinaturas anteriores continuam válidas.

#### Scenario: Segunda assinatura
- **WHEN** um PDF que já tem a assinatura `Assinatura1` é assinado com o texto lateral ligado
- **THEN** a nova assinatura é criada, as páginas não ganham texto novo, a assinatura anterior continua válida e é registrado um aviso de que o texto lateral foi omitido

#### Scenario: Campo de assinatura vazio
- **WHEN** o PDF tem apenas campos de assinatura vazios (não assinados)
- **THEN** o texto lateral é impresso normalmente

### Requirement: Verificação de PDF já assinado
O sistema SHALL oferecer uma verificação de um PDF já assinado por qualquer ferramenta. Ela SHALL conferir que o PDF tem ao menos uma assinatura íntegra, ou seja, com o conteúdo coberto inalterado, e, quando um CPF for informado, que ao menos uma assinatura íntegra é de um certificado desse CPF. O CPF do certificado é lido como em "Restrição por CPF do titular". A confiança na cadeia de certificados não é avaliada.

#### Scenario: PDF assinado pelo titular do CPF
- **WHEN** o PDF tem uma assinatura íntegra de um certificado com o CPF `12345678900` e esse CPF é informado
- **THEN** a verificação é aprovada

#### Scenario: PDF sem assinatura
- **WHEN** o PDF não tem nenhuma assinatura preenchida
- **THEN** um `EPass2003Error` informa que o PDF não está assinado

#### Scenario: Assinatura adulterada
- **WHEN** o PDF tem uma assinatura cujo conteúdo coberto foi alterado depois
- **THEN** essa assinatura não conta. Se não houver outra íntegra, um `EPass2003Error` informa que nenhuma assinatura do PDF é íntegra

#### Scenario: CPF de outra pessoa
- **WHEN** todas as assinaturas íntegras são de certificados de outro CPF
- **THEN** `CpfNaoConfere` é lançado

#### Scenario: Sem CPF informado
- **WHEN** o PDF tem uma assinatura íntegra e nenhum CPF é informado
- **THEN** a verificação é aprovada, qualquer que seja o signatário

#### Scenario: Arquivo que não é PDF
- **WHEN** o conteúdo não pode ser lido como PDF
- **THEN** um `EPass2003Error` informa que o arquivo não é um PDF válido
