#!/usr/bin/env bash
#
# Instala o driver PKCS#11 (libcastle) e o serviço PC/SC do token ePass2003 (Soluti)
# no Debian / Ubuntu, conforme epass.md.
#
# Uso: epass2003 instalar-driver   (ou: sudo bash instalar-driver.sh)

set -euo pipefail

URL="https://site.solutinet.com.br/drivers/Token/ePass2003/Linux/ePass2003_Castle_20141128.tar.gz"
SHA256="00fbb5756b1b01222fe6825ad7ca43da0b662d1f7e2d06584ea7c3c7be490a23"
PASTA_TAR="ePass2003-Castle-20141128"
DESTINO="/usr/lib/ePass2003-Linux-x64"
LIB="/usr/lib/libcastle.so.1.0.0"
REGRA_UDEV="/etc/udev/rules.d/epass_token-1.rules"

info() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
erro() { printf '\033[1;31mErro: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || erro "execute como root: sudo epass2003 instalar-driver"
command -v apt-get >/dev/null || erro "este script é para Debian/Ubuntu (apt não encontrado)"
[[ $(uname -m) == x86_64 ]] || erro "somente x86_64 é suportado (arquitetura atual: $(uname -m))"

# 0. O pacote "awp" (driver Oberthur/IDEMIA, link errado no site da Soluti) trava o ePass2003
if dpkg -s awp &>/dev/null; then
    info "Removendo pacote awp, que conflita com o ePass2003"
    apt-get remove -y awp
fi

# 1. Dependências do sistema
info "Instalando dependências (pcscd, opensc, ccid...)"
apt-get update
apt-get install -y curl usbutils pcscd libpcsclite1 libccid pcsc-tools opensc libnss3-tools

# 2. Download e verificação do driver
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

info "Baixando driver ePass2003"
curl -fL --retry 3 -o "$TMP/epass.tar.gz" "$URL"
echo "$SHA256  $TMP/epass.tar.gz" | sha256sum -c --quiet - \
    || erro "checksum do arquivo baixado não confere"
tar -xzf "$TMP/epass.tar.gz" -C "$TMP"

# 3. Cópia para /usr/lib (caminho que o Assinador Serpro reconhece) e link da biblioteca
info "Instalando driver em $DESTINO"
rm -rf "$DESTINO"
cp -r "$TMP/$PASTA_TAR" "$DESTINO"
install -m 0755 "$DESTINO/x86_64/redist/libcastle.so.1.0.0" "$LIB"
ln -sf "$LIB" /usr/lib/libcastle.so
ldconfig

# 4. Regra udev para usuários comuns acessarem o token. É o mesmo que o config.sh do
#    fabricante faz, sem a segunda regra dele (sintaxe BUS/SYSFS, obsoleta no udev atual).
info "Configurando regra udev"
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="096e", MODE="0666"' > "$REGRA_UDEV"
rm -f /etc/udev/rules.d/epass_token-2.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --attr-match=idVendor=096e || true

# 5. Serviço PC/SC
info "Ativando serviço pcscd"
systemctl enable --now pcscd.socket
systemctl restart pcscd

# 6. Teste
info "Testando comunicação com o token"
if lsusb -d 096e: &>/dev/null; then
    timeout 20 pkcs11-tool --module "$LIB" -L \
        || echo "Falha ao listar o token. Tente replugá-lo e rode: pkcs11-tool --module $LIB -L"
else
    echo "Token não detectado na USB. Plugue-o e rode: pkcs11-tool --module $LIB -L"
fi

info "Instalação concluída. Biblioteca PKCS#11: $LIB"
