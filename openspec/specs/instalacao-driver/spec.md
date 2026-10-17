# instalacao-driver Specification

## Purpose

Deixa um sistema Debian/Ubuntu x86_64 pronto para usar o token ePass2003. Instala o driver PKCS#11 oficial da Soluti (`libcastle`), as dependências PC/SC e as permissões de acesso USB, tudo com um único comando.

## Requirements

### Requirement: Execução com privilégios de root
A instalação SHALL rodar como root. Se o usuário não for root e o `sudo` existir, o sistema SHALL reexecutar a instalação com `sudo`. Se o `sudo` não existir, SHALL falhar com uma mensagem de erro, sem instalar nada.

#### Scenario: Usuário comum com sudo
- **WHEN** um usuário comum pede a instalação e o `sudo` está disponível
- **THEN** a instalação é executada via `sudo` e o código de saída dela é devolvido a quem chamou

#### Scenario: Usuário comum sem sudo
- **WHEN** um usuário comum pede a instalação e o `sudo` não existe
- **THEN** o sistema informa que é preciso ser root e nada é instalado

### Requirement: Plataformas suportadas
A instalação SHALL aceitar apenas sistemas com `apt-get` (Debian/Ubuntu) e arquitetura x86_64. Em qualquer outra plataforma, SHALL abortar antes de alterar o sistema.

#### Scenario: Sistema sem apt
- **WHEN** a instalação roda em um sistema sem `apt-get`
- **THEN** ela aborta com um erro informando que é só para Debian/Ubuntu

#### Scenario: Arquitetura diferente de x86_64
- **WHEN** a instalação roda em uma arquitetura que não é x86_64
- **THEN** ela aborta com um erro que informa a arquitetura atual

### Requirement: Remoção do driver conflitante awp
Se o pacote `awp` (driver Oberthur/IDEMIA, que trava o ePass2003) estiver instalado, a instalação SHALL removê-lo antes de continuar.

#### Scenario: awp instalado
- **WHEN** o pacote `awp` está instalado
- **THEN** ele é removido antes da instalação das dependências

#### Scenario: awp ausente
- **WHEN** o pacote `awp` não está instalado
- **THEN** a instalação segue sem tentar removê-lo

### Requirement: Dependências do sistema
A instalação SHALL instalar pelo apt: curl, usbutils, pcscd, libpcsclite1, libccid, pcsc-tools, opensc e libnss3-tools.

#### Scenario: Dependências instaladas
- **WHEN** a instalação termina com sucesso
- **THEN** todos esses pacotes estão instalados no sistema

### Requirement: Download verificado do driver oficial
A instalação SHALL baixar o pacote `ePass2003_Castle_20141128.tar.gz` do servidor da Soluti e conferir o SHA-256 dele com um valor fixo. Se o checksum não conferir, SHALL abortar sem instalar o driver.

#### Scenario: Checksum confere
- **WHEN** o arquivo baixado tem o SHA-256 esperado
- **THEN** ele é extraído e a instalação continua

#### Scenario: Checksum diverge
- **WHEN** o arquivo baixado não tem o SHA-256 esperado
- **THEN** a instalação aborta com o erro "checksum do arquivo baixado não confere"

### Requirement: Local de instalação do driver
O driver SHALL ser instalado em `/usr/lib/ePass2003-Linux-x64` (caminho reconhecido pelo Assinador Serpro), substituindo uma instalação anterior. A biblioteca SHALL ficar disponível em `/usr/lib/libcastle.so.1.0.0`, com o link `/usr/lib/libcastle.so`.

#### Scenario: Biblioteca disponível
- **WHEN** a instalação termina com sucesso
- **THEN** `/usr/lib/libcastle.so.1.0.0` existe e `/usr/lib/libcastle.so` aponta para ela

#### Scenario: Reinstalação
- **WHEN** a instalação roda com o driver já instalado
- **THEN** o conteúdo de `/usr/lib/ePass2003-Linux-x64` é substituído pelo do pacote baixado

### Requirement: Acesso ao token por usuários comuns
A instalação SHALL criar uma regra udev que libera os dispositivos USB do fabricante `096e` (Feitian) para usuários comuns. SHALL também remover a regra obsoleta `epass_token-2.rules` e recarregar as regras udev.

#### Scenario: Regra udev criada
- **WHEN** a instalação termina com sucesso
- **THEN** `/etc/udev/rules.d/epass_token-1.rules` dá acesso de leitura e escrita aos dispositivos USB de idVendor `096e`

### Requirement: Serviço PC/SC ativo
A instalação SHALL habilitar o socket do `pcscd` e reiniciar o serviço.

#### Scenario: pcscd habilitado
- **WHEN** a instalação termina com sucesso
- **THEN** o `pcscd.socket` está habilitado e o `pcscd` foi reiniciado

### Requirement: Teste de comunicação sem falhar a instalação
Ao final, a instalação SHALL tentar listar o token pela biblioteca instalada, com limite de 20 segundos. Se o token não estiver plugado ou não responder, SHALL apenas orientar o usuário, sem considerar a instalação falha.

#### Scenario: Token plugado
- **WHEN** o token está conectado na USB
- **THEN** os slots do token são listados

#### Scenario: Token ausente
- **WHEN** nenhum dispositivo `096e` está conectado
- **THEN** o usuário é orientado a plugar o token e testar manualmente, e a instalação termina com sucesso
