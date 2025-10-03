#!/bin/bash
# StartZoomMonitor.command
# ダブルクリックでZoomミュート監視ツールを起動

cd "$(dirname "$0")"

# PyObjCがインストールされているかチェック
if ! python3 -c "import objc" 2>/dev/null; then
    echo "PyObjC not found. Installing..."
    pip3 install pyobjc-framework-Cocoa pyobjc-framework-ScriptingBridge
    echo ""
fi

echo "Starting Zoom Mute Monitor..."
echo "Press Ctrl+C to quit"
echo ""

python3 zoom_mute_monitor.py
