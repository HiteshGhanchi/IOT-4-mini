#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo: sudo sh setup_mqtt_tls.sh" >&2
    exit 1
fi

command -v openssl >/dev/null 2>&1 || {
    echo "openssl is required; install it with: sudo apt install openssl" >&2
    exit 1
}
getent group mosquitto >/dev/null 2>&1 || {
    echo "Mosquitto is not installed; install it before running this script." >&2
    exit 1
}

cert_dir=/etc/mosquitto/certs/securebox
config_file=/etc/mosquitto/conf.d/securebox-tls.conf
stamp=$(date +%Y%m%d-%H%M%S)
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
trap 'exit 1' HUP INT TERM

install -d -o root -g root -m 0755 "$cert_dir"
openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
    -keyout "$work_dir/ca.key" \
    -out "$work_dir/ca.crt" \
    -subj "/CN=SecureBox Local MQTT CA"
openssl req -new -newkey rsa:2048 -nodes \
    -keyout "$work_dir/server.key" \
    -out "$work_dir/server.csr" \
    -subj "/CN=localhost"
cat > "$work_dir/server.ext" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:127.0.0.1,DNS:localhost
EOF
openssl x509 -req -sha256 -days 825 \
    -in "$work_dir/server.csr" \
    -CA "$work_dir/ca.crt" \
    -CAkey "$work_dir/ca.key" \
    -CAcreateserial \
    -out "$work_dir/server.crt" \
    -extfile "$work_dir/server.ext"

install -o root -g root -m 0644 "$work_dir/ca.crt" "$cert_dir/ca.crt"
install -o root -g root -m 0644 "$work_dir/server.crt" "$cert_dir/server.crt"
install -o root -g mosquitto -m 0640 "$work_dir/server.key" "$cert_dir/server.key"

cat > "$work_dir/securebox-tls.conf" <<'EOF'
per_listener_settings true
listener 8883 127.0.0.1
protocol mqtt
allow_anonymous true
cafile /etc/mosquitto/certs/securebox/ca.crt
certfile /etc/mosquitto/certs/securebox/server.crt
keyfile /etc/mosquitto/certs/securebox/server.key
tls_version tlsv1.2
EOF

if [ -e "$config_file" ]; then
    cp -a "$config_file" "$config_file.backup.$stamp"
    echo "Backed up existing broker config to $config_file.backup.$stamp"
fi

install -o root -g root -m 0644 "$work_dir/securebox-tls.conf" "$config_file"
if ! systemctl restart mosquitto; then
    echo "Mosquitto failed to restart; restoring the previous TLS config." >&2
    if [ -e "$config_file.backup.$stamp" ]; then
        cp -a "$config_file.backup.$stamp" "$config_file"
    else
        rm -f "$config_file"
    fi
    systemctl restart mosquitto || true
    exit 1
fi

echo "SecureBox MQTT/TLS listener is active on 127.0.0.1:8883."
echo "CA certificate: $cert_dir/ca.crt"
