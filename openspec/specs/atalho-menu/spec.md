# atalho-menu Specification

## Purpose

Põe o assinador local no menu de aplicativos do desktop Linux do usuário. Assim ele pode ser aberto, já ligado, sem precisar de um terminal, a partir da pasta onde o projeto foi clonado.

## Requirements

### Requirement: Criação do atalho
`epass2003 instalar-atalho` SHALL gravar o arquivo `epass2003-assinador.desktop` em `$XDG_DATA_HOME/applications`, ou em `~/.local/share/applications` se `XDG_DATA_HOME` não estiver definido, criando a pasta se preciso. Se o atalho já existir, SHALL substituí-lo. Ao terminar, SHALL imprimir o caminho do arquivo.

#### Scenario: Primeira instalação
- **WHEN** o usuário roda `uv run epass2003 instalar-atalho` na pasta clonada
- **THEN** é criado `~/.local/share/applications/epass2003-assinador.desktop` e o comando imprime esse caminho

#### Scenario: Reinstalação depois de mover a pasta
- **WHEN** o projeto foi movido para outra pasta e o comando é rodado de novo
- **THEN** o atalho é reescrito apontando para a nova pasta

### Requirement: Conteúdo do atalho
O atalho SHALL ser uma entrada `Type=Application` válida, com `Name=Assinador ePass2003`, um `Comment`, `Terminal=false`, `Categories=Office;` (uma única categoria principal, para não aparecer duas vezes no menu) e um ícone do tema do sistema. O `Exec` SHALL rodar o assinador já ligado (`--ligado`) pelo `uv`, com o caminho absoluto do executável `uv` e da pasta do projeto, para funcionar mesmo que o menu não tenha `~/.local/bin` no `PATH`.

#### Scenario: Abrir pelo menu
- **WHEN** o usuário escolhe "Assinador ePass2003" no menu de aplicativos
- **THEN** a janela do assinador abre, sem terminal, já escutando em `localhost:3399`

#### Scenario: Caminho com espaços
- **WHEN** a pasta do projeto tem espaços no nome
- **THEN** o `Exec` põe os argumentos entre aspas, conforme a especificação de Desktop Entry, e o atalho continua funcionando

### Requirement: Remoção do atalho
`epass2003 instalar-atalho --remover` SHALL apagar o atalho, se ele existir, e informar o que foi feito. Se o atalho não existir, SHALL informar isso e terminar com sucesso.

#### Scenario: Remover atalho existente
- **WHEN** o atalho existe e o usuário roda `instalar-atalho --remover`
- **THEN** o arquivo é apagado e o assinador some do menu

#### Scenario: Remover sem atalho
- **WHEN** o atalho não existe
- **THEN** o comando informa que não havia atalho e termina com código 0

### Requirement: Pré-condições do atalho
O comando SHALL recusar a execução como root, porque o atalho é do usuário. SHALL também recusar a instalação quando não encontrar o executável `uv` ou quando o pacote não estiver rodando de uma pasta clonada do projeto (sem `pyproject.toml`). Em todos esses casos, SHALL terminar com `Erro: <descrição>` e código diferente de zero, sem gravar nada.

#### Scenario: Executado com sudo
- **WHEN** o comando é executado como root
- **THEN** ele termina com um erro pedindo para rodar como o usuário comum

#### Scenario: uv não encontrado
- **WHEN** não há `uv` no `PATH`
- **THEN** ele termina com um erro orientando a instalar o `uv`

#### Scenario: Fora de uma pasta clonada
- **WHEN** o pacote não está dentro de uma pasta com o `pyproject.toml` do projeto
- **THEN** ele termina com um erro dizendo que o atalho exige o projeto clonado com git
