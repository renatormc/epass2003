# assinador-local Specification

## Purpose

Substitui no Linux o assinador local que, no Windows, sistemas web usam para assinar PDFs com o token. Atende o protocolo HTTP `/assinarPdf` na porta 3399, pede o PIN do token ao usuário e devolve o PDF assinado ao site.

## Requirements

### Requirement: Servidor local na porta 3399
O assinador SHALL escutar HTTP somente em `127.0.0.1:3399`, nunca em interfaces externas. Se a porta estiver ocupada, SHALL avisar o usuário e continuar desligado.

#### Scenario: Ligar o servidor
- **WHEN** o usuário clica em "Ligar"
- **THEN** o servidor passa a responder em `http://localhost:3399` e o status mostra "Ligado em http://localhost:3399"

#### Scenario: Porta ocupada
- **WHEN** o usuário clica em "Ligar" com a porta 3399 em uso
- **THEN** aparece uma mensagem de erro sobre a porta e o botão volta para "Ligar"

### Requirement: Controle Ligar/Desligar
A janela principal SHALL ter um botão que alterna entre ligar e desligar o servidor, além de uma linha de status. O aplicativo SHALL abrir desligado, a menos que receba `--ligado`. Ao desligar ou fechar a janela, SHALL parar o servidor e cancelar os pedidos de PIN em aberto.

#### Scenario: Abrir já ligado
- **WHEN** o aplicativo é iniciado com `--ligado`
- **THEN** o servidor começa a escutar sem que o usuário clique em nada

#### Scenario: Desligar com pedido pendente
- **WHEN** o usuário desliga o servidor enquanto uma janela de PIN está aberta
- **THEN** a janela de PIN é fechada, o pedido é tratado como cancelado e o status mostra "Desligado"

### Requirement: Parâmetros do pedido de assinatura
O endpoint `GET /assinarPdf` SHALL receber `cpf` (Base64, opcional) e `fileDownload` (Base64 de uma URL http ou https), e ignorar os demais parâmetros, como `nocache`. Se faltar `fileDownload`, se o Base64 for inválido ou se a URL não for http(s), SHALL responder com erro 400.

#### Scenario: Pedido válido
- **WHEN** o site chama `/assinarPdf?nocache=123&cpf=<b64>&fileDownload=<b64 de https://...>`
- **THEN** o assinador decodifica o CPF e a URL e começa o processo de assinatura

#### Scenario: Parâmetros inválidos
- **WHEN** falta `fileDownload` ou o Base64 é inválido
- **THEN** a resposta é o JSON `{"status": 400, "message": "Parâmetros inválidos: esperados cpf e fileDownload em Base64."}`

#### Scenario: Esquema de URL não suportado
- **WHEN** a URL decodificada não começa com http ou https
- **THEN** a resposta é o JSON com `status` 400 e a mensagem "URL de download inválida."

### Requirement: Download do PDF
O assinador SHALL baixar o arquivo da URL informada, com limite de 60 segundos e de 100 MB. O conteúdo SHALL começar com `%PDF`. Se o download falhar ou o arquivo não for um PDF válido, SHALL responder com erro 400 sem pedir o PIN.

#### Scenario: Download falha
- **WHEN** a URL não responde ou devolve um erro de rede
- **THEN** a resposta é um JSON com `status` 400 e a mensagem "Não foi possível baixar o PDF: <erro>"

#### Scenario: Arquivo não é PDF
- **WHEN** o arquivo baixado não começa com `%PDF` ou passa de 100 MB
- **THEN** a resposta é um JSON com `status` 400 e a mensagem "O arquivo baixado não é um PDF válido."

### Requirement: Diálogo de PIN
Para cada pedido, o assinador SHALL abrir sobre as outras janelas um diálogo com o site de origem (Origin, depois Referer, senão "desconhecida"), o servidor do arquivo, o CPF (se houver) e um select "Ação" com as opções "Assinar" (padrão) e "Substituir". Com "Assinar", o diálogo SHALL mostrar um campo de PIN mascarado e os botões "Assinar" e "Cancelar". O modo "Substituir" é descrito em "Substituição por PDF já assinado".

#### Scenario: Usuário confirma
- **WHEN** a ação é "Assinar" e o usuário digita o PIN e clica em "Assinar"
- **THEN** o PDF é assinado com esse PIN e com a restrição do CPF do pedido

#### Scenario: Ação padrão
- **WHEN** o diálogo de um novo pedido é aberto
- **THEN** a ação selecionada é "Assinar" e o campo de PIN está em foco

#### Scenario: Usuário cancela
- **WHEN** o usuário clica em "Cancelar" ou confirma com o PIN vazio
- **THEN** a resposta é um JSON com `status` 400 e a mensagem "Assinatura cancelada pelo usuário."

#### Scenario: Tempo esgotado
- **WHEN** ninguém responde ao diálogo em 5 minutos
- **THEN** o diálogo é fechado e o pedido é respondido como cancelado

### Requirement: Nova tentativa com PIN incorreto
Se o PIN estiver errado, o assinador SHALL mostrar o diálogo de novo com o aviso "PIN incorreto. Atenção: erros seguidos bloqueiam o token." e SHALL continuar no mesmo pedido até a assinatura dar certo, o usuário cancelar ou ocorrer outro erro.

#### Scenario: PIN errado e depois correto
- **WHEN** o usuário erra o PIN e depois digita o correto
- **THEN** o diálogo reaparece com o aviso em destaque e, na segunda tentativa, o PDF assinado é devolvido

### Requirement: Respostas do protocolo
Todas as respostas de `/assinarPdf` SHALL ter HTTP 200. Em caso de sucesso, o corpo SHALL ser o PDF assinado em Base64 (`text/plain`). Em caso de falha, SHALL ser o JSON `{"status": <código>, "message": <texto>}`: código 500 quando o CPF não confere e 400 nos demais erros.

#### Scenario: Sucesso
- **WHEN** a assinatura é concluída
- **THEN** a resposta é HTTP 200, `text/plain`, com o PDF assinado em Base64

#### Scenario: CPF não confere
- **WHEN** nenhum certificado do token pertence ao CPF do pedido
- **THEN** a resposta é o JSON com `status` 500 e a mensagem "O CPF informado (<cpf>) não corresponde ao TOKEN inserido."

#### Scenario: Outro erro do token
- **WHEN** a assinatura falha por PIN bloqueado, certificado vencido ou erro de comunicação
- **THEN** a resposta é um JSON com `status` 400 e a mensagem do erro

### Requirement: Uma assinatura por vez
O assinador SHALL processar um pedido de cada vez. Um pedido que chega enquanto outro está em andamento SHALL esperar o anterior terminar.

#### Scenario: Pedidos simultâneos
- **WHEN** dois pedidos chegam ao mesmo tempo
- **THEN** o segundo só baixa o PDF e abre o diálogo de PIN depois que o primeiro é respondido

### Requirement: CORS e acesso de sites da internet
Todas as respostas, exceto as do endpoint de teste `/teste/pdf`, SHALL incluir `Access-Control-Allow-Origin` igual ao `Origin` recebido (ou `*` se não houver), além de `Access-Control-Allow-Methods: GET, OPTIONS` e `Access-Control-Allow-Headers: *`. Quando o navegador enviar `Access-Control-Request-Private-Network`, a resposta SHALL incluir `Access-Control-Allow-Private-Network: true`.

#### Scenario: Preflight do Chrome
- **WHEN** um site da internet faz um preflight com `Access-Control-Request-Private-Network: true`
- **THEN** a resposta inclui `Access-Control-Allow-Private-Network: true` e a origem do site em `Access-Control-Allow-Origin`

### Requirement: Status visível ao usuário
A janela principal SHALL mostrar a etapa atual ("Baixando PDF de <servidor>...", "Assinando...", "PDF assinado e enviado ao site.") ou o último erro como "Erro: <mensagem>". Essas mensagens SHALL também ir para o log.

#### Scenario: Assinatura concluída
- **WHEN** um pedido é assinado com sucesso
- **THEN** o status mostra "PDF assinado e enviado ao site."

### Requirement: Modo de teste opt-in
O assinador SHALL entrar em modo de teste somente quando iniciado com a opção `--test`, que pode ser combinada com `--ligado`. No modo de teste, o título da janela principal SHALL indicar "modo de teste". Sem `--test`, o assinador SHALL se comportar como antes, sem nenhum endpoint de teste.

#### Scenario: Iniciar em modo de teste
- **WHEN** o aplicativo é iniciado com `epass2003-assinador --test --ligado`
- **THEN** o servidor começa a escutar, o título da janela indica modo de teste e o endpoint `/teste/pdf` responde

#### Scenario: Iniciar sem modo de teste
- **WHEN** o aplicativo é iniciado sem `--test`
- **THEN** `GET /teste/pdf` responde HTTP 404, como qualquer rota inexistente

### Requirement: Endpoint de teste para PDFs locais
No modo de teste, `GET /teste/pdf?caminho=<caminho absoluto>` SHALL devolver o conteúdo do arquivo com `Content-Type: application/pdf`. Só arquivos regulares que começam com `%PDF` e têm até 100 MB SHALL ser entregues. Nos outros casos, SHALL responder com um JSON `{"status": <código>, "message": <texto>}` e o código HTTP correspondente.

#### Scenario: PDF existente
- **WHEN** o endpoint é chamado com o caminho absoluto de um PDF legível
- **THEN** a resposta é HTTP 200, `application/pdf`, com o conteúdo do arquivo

#### Scenario: Caminho ausente ou relativo
- **WHEN** `caminho` não é informado ou não é absoluto
- **THEN** a resposta é HTTP 400 com JSON informando que é preciso um caminho absoluto

#### Scenario: Arquivo inexistente ou ilegível
- **WHEN** o caminho não existe, não é um arquivo regular ou não pode ser lido
- **THEN** a resposta é HTTP 404 com JSON informando que o arquivo não foi encontrado

#### Scenario: Arquivo que não é PDF
- **WHEN** o arquivo não começa com `%PDF` ou passa de 100 MB
- **THEN** a resposta é HTTP 415 com JSON informando que o arquivo não é um PDF válido, e o conteúdo não é enviado

#### Scenario: Assinatura usando o endpoint de teste
- **WHEN** `/assinarPdf` recebe em `fileDownload` a URL `http://127.0.0.1:3399/teste/pdf?caminho=...` de um PDF existente
- **THEN** o assinador baixa o PDF do próprio endpoint, abre o diálogo de PIN e responde como em qualquer outro pedido

### Requirement: Endpoint de teste sem CORS
As respostas do endpoint `/teste/pdf` SHALL NOT incluir cabeçalhos CORS (`Access-Control-Allow-*`). Assim, páginas abertas no navegador não conseguem ler o conteúdo dos arquivos locais.

#### Scenario: Site tenta ler um arquivo local
- **WHEN** uma página de outra origem faz `fetch` para `/teste/pdf` com o header `Origin`
- **THEN** a resposta não tem `Access-Control-Allow-Origin` e o navegador bloqueia a leitura

### Requirement: Texto lateral nas assinaturas do assinador local
Todo PDF assinado pelo assinador local SHALL ser assinado com o texto lateral "Assinado eletronicamente por <nome>" ligado. Quando o texto for omitido porque o PDF já tinha assinatura, o assinador SHALL mostrar isso no status da janela, e a resposta ao site SHALL continuar a mesma, com o PDF assinado em Base64.

#### Scenario: Pedido de um site com PDF sem assinaturas
- **WHEN** um site pede a assinatura de um PDF sem assinaturas e o usuário digita o PIN correto
- **THEN** o PDF devolvido tem o texto lateral em todas as páginas

#### Scenario: Pedido com PDF já assinado
- **WHEN** um site pede a assinatura de um PDF que já tem uma assinatura
- **THEN** o PDF devolvido tem a nova assinatura sem texto lateral novo, e o status da janela informa que o texto lateral foi omitido porque o PDF já estava assinado

#### Scenario: Pedido de teste pela linha de comando
- **WHEN** o usuário roda `epass2003 testar-assinador` com um PDF sem assinaturas
- **THEN** o PDF gravado tem o texto lateral em todas as páginas

### Requirement: Substituição por PDF já assinado
Com a ação "Substituir", o diálogo SHALL trocar o campo de PIN por um botão "Escolher PDF…", que abre o seletor de arquivos do sistema filtrando arquivos `.pdf`, e mostrar o nome do arquivo escolhido. O botão de confirmação SHALL se chamar "Enviar" e ficar desabilitado até que um arquivo seja escolhido. Aprovado na verificação, o arquivo SHALL ser devolvido ao site em Base64 exatamente como está no disco, sem usar o token e sem texto lateral.

#### Scenario: Enviar PDF assinado por outra ferramenta
- **WHEN** o usuário seleciona "Substituir", escolhe um PDF assinado com uma assinatura íntegra do CPF do pedido e clica em "Enviar"
- **THEN** a resposta ao site é HTTP 200 com o conteúdo do arquivo em Base64, byte a byte igual ao do disco, e o status da janela informa que o PDF escolhido foi enviado ao site

#### Scenario: Enviar sem escolher arquivo
- **WHEN** a ação é "Substituir" e nenhum arquivo foi escolhido
- **THEN** o botão "Enviar" fica desabilitado

#### Scenario: Seletor de arquivos cancelado
- **WHEN** o usuário abre o seletor e o fecha sem escolher um arquivo
- **THEN** o diálogo continua aberto com a escolha anterior (ou nenhuma)

#### Scenario: Voltar para Assinar
- **WHEN** o usuário troca a ação de "Substituir" para "Assinar"
- **THEN** o campo de PIN volta, o botão volta a se chamar "Assinar" e o arquivo escolhido é ignorado

### Requirement: Verificação do PDF substituto
Antes de enviar um PDF substituto, o assinador SHALL lê-lo (até 100 MB) e aplicar a verificação de PDF já assinado com o CPF do pedido. Se o arquivo não puder ser lido, não for PDF ou não tiver assinatura íntegra, o diálogo SHALL reaparecer em "Substituir" com o motivo em destaque. Se nenhuma assinatura íntegra for do CPF do pedido, a resposta SHALL ser o JSON `status` 500 com "O CPF informado (<cpf>) não corresponde ao PDF assinado escolhido."

#### Scenario: PDF sem assinatura
- **WHEN** o usuário escolhe um PDF que não tem assinatura
- **THEN** o diálogo reaparece em "Substituir" com o aviso de que o PDF escolhido não está assinado, e nada é enviado ao site

#### Scenario: Arquivo maior que o limite
- **WHEN** o arquivo escolhido passa de 100 MB ou não pode ser lido
- **THEN** o diálogo reaparece com o motivo e nada é enviado ao site

#### Scenario: Assinado por outro CPF
- **WHEN** o pedido tem CPF e o PDF escolhido só tem assinaturas íntegras de outros CPFs
- **THEN** a resposta é o JSON com `status` 500 e a mensagem "O CPF informado (<cpf>) não corresponde ao PDF assinado escolhido."

#### Scenario: Pedido sem CPF
- **WHEN** o pedido não tem CPF e o PDF escolhido tem uma assinatura íntegra de qualquer titular
- **THEN** o PDF é enviado ao site
