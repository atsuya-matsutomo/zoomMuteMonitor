#!/bin/bash
# Build.command
# Zoomマイク監視ツールを.app形式にビルドするスクリプト

set -e

cd "$(dirname "$0")"

echo "======================================"
echo "Zoomマイク監視ツール ビルドスクリプト"
echo "======================================"
echo ""

# py2appがインストールされているかチェック
if ! python3 -c "import py2app" 2>/dev/null; then
    echo "📦 py2appをインストールしています..."
    pip3 install py2app
    echo ""
fi

# PyObjCがインストールされているかチェック
if ! python3 -c "import objc" 2>/dev/null; then
    echo "📦 PyObjCをインストールしています..."
    pip3 install pyobjc-framework-Cocoa pyobjc-framework-ScriptingBridge
    echo ""
fi

# 既存のビルドをクリーンアップ
echo "🧹 クリーンアップ中..."
rm -rf build dist setup.py entitlements.plist
echo ""

# setup.pyを作成
echo "📝 setup.pyを生成中..."
cat > setup.py << 'EOF'
from setuptools import setup

APP = ['zoom_mute_monitor.py']
DATA_FILES = [
    ('icon', [
        'icon/micOff-512.png',
        'icon/micOn-512.png',
        'icon/unknown-512.png',
        'icon/icon-200.png'
    ])
]
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon/icon-200.png',
    'plist': {
        'CFBundleName': 'Zoomマイク監視ツール',
        'CFBundleDisplayName': 'Zoomマイク監視ツール',
        'CFBundleIdentifier': 'com.zoommonitor.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # Dockに表示しない
        'NSHighResolutionCapable': True,
    },
    'packages': ['objc', 'Foundation', 'AppKit', 'Cocoa'],
    'includes': ['subprocess', 'json', 'os'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
EOF

echo "✅ setup.py生成完了"
echo ""

# entitlements.plistを作成
echo "📝 entitlements.plistを生成中..."
cat > entitlements.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.automation.apple-events</key>
    <true/>
</dict>
</plist>
EOF
echo "✅ entitlements.plist生成完了"
echo ""

# .appをビルド
echo "🔨 .appをビルド中..."
python3 setup.py py2app
echo ""

# 自己署名証明書を確認・作成
CERT_NAME="ZoomMonitorAppSigner"
if ! security find-certificate -c "$CERT_NAME" >/dev/null 2>&1; then
    echo "📝 自己署名証明書を作成中..."
    # 証明書作成のためのテンポラリファイル
    cat > /tmp/cert_config.txt << 'EOF'
[ req ]
distinguished_name = req_distinguished_name
x509_extensions = v3_ca

[ req_distinguished_name ]

[ v3_ca ]
basicConstraints = CA:FALSE
keyUsage = digitalSignature
extendedKeyUsage = codeSigning
EOF

    # 証明書と秘密鍵を作成
    openssl req -x509 -newkey rsa:4096 -keyout /tmp/cert_key.pem -out /tmp/cert.pem -days 3650 -nodes -subj "/CN=ZoomMonitorAppSigner" -config /tmp/cert_config.txt

    # PKCS12形式に変換（パスワードなし）
    openssl pkcs12 -export -out /tmp/cert.p12 -inkey /tmp/cert_key.pem -in /tmp/cert.pem -passout pass:temporary

    # キーチェーンにインポート
    security import /tmp/cert.p12 -k ~/Library/Keychains/login.keychain-db -T /usr/bin/codesign -P temporary

    # 信頼設定
    security add-trusted-cert -d -r trustRoot -k ~/Library/Keychains/login.keychain-db /tmp/cert.pem

    # クリーンアップ
    rm -f /tmp/cert_config.txt /tmp/cert_key.pem /tmp/cert.pem /tmp/cert.p12

    echo "✅ 自己署名証明書を作成しました"
    echo ""
fi

# コード署名（entitlementsを明示的に指定）
echo "✍️  コード署名中..."
codesign --force --deep --sign "$CERT_NAME" --entitlements entitlements.plist "dist/Zoomマイク監視ツール.app"
echo ""

if [ -d "dist/Zoomマイク監視ツール.app" ]; then
    echo "✅ ビルド成功！"
    echo ""

    # Applicationsフォルダに移動
    echo "📦 Applicationsフォルダに更新中..."
    APP_NAME="Zoomマイク監視ツール.app"

    # 既存のアプリがある場合は、中身を置き換える（権限を保持）
    if [ -d "/Applications/$APP_NAME" ]; then
        echo "既存アプリの内容を更新中..."
        # 既存アプリを終了
        osascript -e 'tell application "Zoomマイク監視ツール" to quit' 2>/dev/null || true
        sleep 1

        # 中身を置き換え
        rm -rf "/Applications/$APP_NAME/Contents"
        cp -R "dist/$APP_NAME/Contents" "/Applications/$APP_NAME/"
    else
        # 新規インストール
        echo "新規インストール中..."
        cp -R "dist/$APP_NAME" "/Applications/"
    fi

    # distとbuildフォルダとビルドファイルを削除
    rm -rf dist build setup.py entitlements.plist

    echo "✅ /Applications/$APP_NAME に配置しました"
    echo ""
    echo "次のステップ:"
    echo "1. 初回起動時、アクセシビリティ権限を許可"
    echo "2. 右クリックで各種設定が可能"
    echo ""

    # Applicationsフォルダを開く
    echo "📂 Applicationsフォルダを開きます..."
    open /Applications
else
    echo "❌ ビルドに失敗しました"
    exit 1
fi

echo ""
echo "🎉 完了！"
echo ""
read -n 1 -s -p "Press any key to close..."
