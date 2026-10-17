# configuracao-navegadores Specification

## Purpose

Faz o token ePass2003 aparecer no Firefox, no Chrome/Chromium, no LibreOffice e no Okular. Para isso, registra o driver PKCS#11 nos bancos de certificados NSS do usuário com um único comando, sem `sudo`.

## Requirements

### Requirement: Bancos NSS configurados
`epass2003 configurar-navegadores` SHALL registrar o driver do token em cada banco NSS do usuário:
- em cada perfil listado nos `profiles.ini` de `~/.config/mozilla/firefox` e de `~/.mozilla/firefox`;
- em `~/.pki/nssdb`, que SHALL ser criado, sem senha, se não existir.

Para cada banco, o comando SHALL informar o caminho e o resultado: configurado, já configurado, em uso ou falha.

#### Scenario: Perfil do Firefox no caminho novo
- **WHEN** o usuário tem o perfil `abc.default-release` em `~/.config/mozilla/firefox` e roda o comando com o Firefox fechado
- **THEN** o driver passa a constar nesse perfil e o comando informa "configurado"

#### Scenario: Sem ~/.pki/nssdb
- **WHEN** `~/.pki/nssdb` não existe
- **THEN** o banco é criado sem senha e o driver é registrado nele

#### Scenario: Sem Firefox
- **WHEN** não existe nenhum perfil do Firefox
- **THEN** só o `~/.pki/nssdb` é configurado, e o comando termina com sucesso

### Requirement: Registro sem duplicação
Se a biblioteca do driver já estiver registrada num banco, com qualquer nome de módulo, o comando SHALL deixar esse banco como está e informar "já configurado". Rodar o comando várias vezes SHALL dar o mesmo resultado.

#### Scenario: Segunda execução
- **WHEN** o comando é rodado duas vezes seguidas
- **THEN** na segunda vez todos os bancos aparecem como "já configurado" e nenhum ganha um módulo repetido

#### Scenario: Módulo registrado à mão com outro nome
- **WHEN** o perfil já tem a biblioteca `/usr/lib/libcastle.so.1.0.0` registrada com o nome "Meu token"
- **THEN** o perfil não é alterado e aparece como "já configurado"

### Requirement: Perfil do Firefox em uso
O comando SHALL NOT alterar um perfil do Firefox que esteja aberto, detectado pelo arquivo de trava do perfil. Esse perfil SHALL aparecer como "em uso: feche o Firefox e rode de novo", e os outros bancos SHALL ser configurados normalmente. Se algum banco ficar pendente, o código de saída SHALL ser diferente de zero.

#### Scenario: Firefox aberto
- **WHEN** o Firefox está aberto com o perfil `abc.default-release`
- **THEN** esse perfil não é alterado, o `~/.pki/nssdb` é configurado, a mensagem pede para fechar o Firefox e o comando termina com código diferente de zero

### Requirement: Remoção
`epass2003 configurar-navegadores --remover` SHALL remover a biblioteca do driver dos mesmos bancos, qualquer que seja o nome do módulo, informando "removido" ou "não estava configurado" para cada um. Ele SHALL respeitar a mesma regra de perfil em uso e SHALL NOT apagar bancos NSS.

#### Scenario: Remover depois de configurar
- **WHEN** o comando é rodado sem e depois com `--remover`
- **THEN** nenhum banco continua com a biblioteca do driver e os bancos continuam existindo

### Requirement: Pré-condições
O comando SHALL recusar rodar como root, porque os bancos são do usuário. SHALL também recusar quando `modutil` ou `certutil` não estiverem instalados, ou quando a biblioteca do driver não existir, orientando a rodar `epass2003 instalar-driver`. Nesses casos, SHALL terminar com `Erro: <descrição>` e código diferente de zero, sem alterar nada.

#### Scenario: Driver não instalado
- **WHEN** `/usr/lib/libcastle.so.1.0.0` não existe
- **THEN** o comando termina com um erro orientando a rodar `epass2003 instalar-driver`

#### Scenario: Executado com sudo
- **WHEN** o comando é executado como root
- **THEN** ele termina com um erro pedindo para rodar como o usuário comum

### Requirement: Firefox Snap
Se existirem perfis do Firefox Snap (`~/snap/firefox/common/.mozilla/firefox`), o comando SHALL NOT alterá-los e SHALL avisar que o Snap exige a configuração manual descrita no `epass.md`.

#### Scenario: Perfil Snap encontrado
- **WHEN** existe um perfil em `~/snap/firefox/common/.mozilla/firefox`
- **THEN** o comando mostra um aviso sobre o Snap, não altera esse perfil e continua com os outros bancos
