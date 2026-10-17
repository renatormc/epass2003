# Guia Completo: Instalação e Uso do Token ePass 2003 (Soluti) no Ubuntu / Debian

> **Atenção sobre o site da Soluti:** Na página de suporte da Soluti, o botão *"Epass Linux Debian - Ubuntu"* está com o link incorreto apontando para `AWP_Debian_Ubuntu_x64_5.2.0_SR2_amd64.zip` (que é o driver de cartões Oberthur/IDEMIA e **trava** a leitura do ePass 2003). Caso tenha instalado o pacote `awp`, remova-o com `sudo apt remove -y awp`.

---

## 1. Instalar dependências do sistema (Serviço PC/SC e ferramentas)

Abra o terminal e instale os pacotes responsáveis pela comunicação USB com tokens criptográficos:

```bash
sudo apt update
sudo apt install -y pcscd libpcsclite1 libccid pcsc-tools opensc libnss3-tools
```

---

## 2. Baixar e instalar o driver correto do ePass 2003 (`libcastle`)

O link direto do driver verdadeiro para Linux no servidor da Soluti é o `ePass2003_Castle_20141128.tar.gz`. Execute os comandos abaixo para baixá-lo e instalá-lo no caminho padrão (que o **Assinador Serpro** reconhece automaticamente):

```bash
cd ~/Downloads

# 1. Baixar e extrair o pacote oficial do ePass 2003
curl -O "https://site.solutinet.com.br/drivers/Token/ePass2003/Linux/ePass2003_Castle_20141128.tar.gz"
tar -zxvf ePass2003_Castle_20141128.tar.gz

# 2. Copiar para /usr/lib no formato esperado pelo Assinador Serpro
sudo rm -rf /usr/lib/ePass2003-Linux-x64
sudo cp -rf ~/Downloads/ePass2003-Castle-20141128 /usr/lib/ePass2003-Linux-x64

# 3. Criar atalhos da biblioteca PKCS#11 (libcastle.so.1.0.0) em /usr/lib
sudo cp /usr/lib/ePass2003-Linux-x64/x86_64/redist/libcastle.so.1.0.0 /usr/lib/
sudo ln -sf /usr/lib/libcastle.so.1.0.0 /usr/lib/libcastle.so

# 4. Configurar regras USB (udev) e reiniciar o daemon pcscd
sudo sh /usr/lib/ePass2003-Linux-x64/x86_64/config/config.sh
sudo systemctl enable --now pcscd.socket
sudo systemctl restart pcscd
```

### Como testar no terminal se o token e o certificado foram reconhecidos:
Com o token plugado na USB, rode:
```bash
pkcs11-tool --module /usr/lib/libcastle.so.1.0.0 -L
pkcs11-tool --module /usr/lib/libcastle.so.1.0.0 -O --type cert
```

---

## 3. Configurar nos Navegadores (e no Okular)

### Forma automática (recomendada)

Com o Firefox fechado, rode na pasta do projeto:

```bash
uv run epass2003 configurar-navegadores
```

O comando registra o driver (`/usr/lib/libcastle.so.1.0.0`) em todos os perfis do Firefox e no `~/.pki/nssdb`, que é usado pelo Chrome/Chromium/Brave, pelo LibreOffice e pelo Okular. Ele não duplica o registro e não mexe em perfis com o Firefox aberto. Para desfazer, use `--remover`. As seções abaixo mostram como fazer o mesmo à mão.

### A) Mozilla Firefox (`.deb` ou tarball)
Nas versões recentes, o perfil fica em `~/.config/mozilla/firefox/<perfil>`. Nas antigas, fica em `~/.mozilla/firefox/<perfil>`.

1. Acesse **Configurações** > **Privacidade e Segurança** > role até **Certificados** e clique em **Dispositivos de Segurança...**
2. Clique em **Carregar** (Load) e preencha:
   * **Nome do módulo:** `Token ePass 2003`
   * **Nome do arquivo do módulo:** `/usr/lib/libcastle.so.1.0.0`
3. Clique em **OK**.

Pelo terminal, com o Firefox fechado:
```bash
modutil -force -dbdir sql:$HOME/.config/mozilla/firefox/<perfil> -add "Token ePass 2003" -libfile /usr/lib/libcastle.so.1.0.0
```

> **Firefox Snap** (padrão do Ubuntu): o Snap bloqueia o acesso ao `/usr/lib` e ao `pcscd`. Rode `sudo snap connect firefox:pcscd`, copie a biblioteca com `cp /usr/lib/libcastle.so.1.0.0 ~/snap/firefox/common/` e carregue esse arquivo copiado em **Dispositivos de Segurança**. O comando automático não configura o Snap. O mais simples é instalar o Firefox `.deb` do repositório da Mozilla.

### B) Google Chrome / Chromium / Brave e LibreOffice
Esses programas usam o banco `~/.pki/nssdb` da sua pasta de usuário. Se ele não existir, crie e registre o módulo com o navegador fechado:

```bash
mkdir -p ~/.pki/nssdb
certutil -N -d sql:$HOME/.pki/nssdb --empty-password
modutil -force -dbdir sql:$HOME/.pki/nssdb -add "Token ePass 2003" -libfile /usr/lib/libcastle.so.1.0.0
```

### C) Okular
O Okular assina pelo banco NSS. Por padrão, ele usa o perfil do Firefox em `~/.mozilla/firefox` ou, se não houver, o `~/.pki/nssdb`. Os dois são configurados pelo comando automático. Se o seu Firefox usa o caminho novo (`~/.config/mozilla/firefox`) e você prefere usar esse perfil, vá em **Configurações** > **Configurar backends** > **PDF** e aponte o banco de certificados para a pasta do perfil.

Para conferir se o certificado aparece (o PIN é pedido):
```bash
certutil -d sql:$HOME/.pki/nssdb -L -h all
```

---

## 4. Como Assinar Arquivos PDF

### Opção 1: Assinador Serpro (Recomendado para padrão ICP-Brasil / Gov.br)
1. Baixe o instalador `.deb` para Linux no site oficial: [Assinador Serpro](https://www.serpro.gov.br/links-fixos-superiores/assinador-digital/assinador-serpro)
2. Instale com:
   ```bash
   sudo apt install ./assinador-serpro_*.deb
   ```
3. Abra o **Assinador Serpro** pelo menu de aplicativos (sempre com seu usuário normal, sem `sudo`). Ele detectará automaticamente o driver em `/usr/lib/ePass2003-Linux-x64/x86_64/redist/libcastle.so.1.0.0`.
4. Clique em **Assinar PDF**, escolha o documento, selecione o seu certificado e informe o PIN.

### Opção 2: LibreOffice Draw / Writer
1. Certifique-se de ter configurado o token no Firefox ou no `nssdb` (Passo 3).
2. Abra o **LibreOffice** e acesse **Arquivo > Assinaturas Digitais > Assinar PDF existente...**
3. Selecione o arquivo PDF, clique em **Assinar Documento** na barra superior, escolha seu certificado e digite o PIN do token.
