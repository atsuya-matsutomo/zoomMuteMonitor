#!/usr/bin/env python3
"""
Zoom Mute Monitor
Zoomのミュート状態を監視して画面端に透過ウィンドウで表示
"""

import objc
import json
import os
import sys
from Foundation import NSObject, NSTimer, NSPoint, NSMakePoint, NSUserDefaults
from AppKit import (
    NSApplication, NSWindow, NSView, NSColor, NSTextField,
    NSFont, NSBackingStoreBuffered, NSWindowStyleMaskBorderless,
    NSScreen, NSMakeRect, NSMenu, NSMenuItem, NSAlert, NSAlertFirstButtonReturn,
    NSImage, NSImageView, NSCompositingOperationSourceOver, NSMakeSize, NSAppleScript,
    NSEvent
)
from Cocoa import (
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSFloatingWindowLevel,
    NSLeftMouseDown, NSLeftMouseDragged, NSRightMouseDown, NSLeftMouseUp
)
import subprocess


CONFIG_FILE = os.path.expanduser("~/Library/Application Support/ZoomMuteMonitor/config.json")

# .appバンドル内でもリソースを見つけられるようにする
if getattr(sys, 'frozen', False):
    # py2appでビルドされた場合
    SCRIPT_DIR = os.path.dirname(sys.executable)
    ICON_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'Resources', 'icon')
else:
    # 通常のPythonスクリプトとして実行された場合
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    ICON_DIR = os.path.join(SCRIPT_DIR, "icon")


class Config:
    """設定管理クラス"""

    def __init__(self):
        self.window_x = None
        self.window_y = None
        self.icon_size = 100
        self.muted_keyword = "オーディオのミュート解除"
        self.unmuted_keyword = "オーディオのミュート"
        self.check_interval = 200  # ミリ秒
        self.load()

    def load(self):
        """設定ファイルから読み込み"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.window_x = data.get('window_x')
                    self.window_y = data.get('window_y')
                    self.icon_size = data.get('icon_size', 100)
                    self.muted_keyword = data.get('muted_keyword', "オーディオのミュート解除")
                    self.unmuted_keyword = data.get('unmuted_keyword', "オーディオのミュート")
                    self.check_interval = data.get('check_interval', 200)
        except Exception as e:
            print(f"Failed to load config: {e}")

    def save(self):
        """設定ファイルに保存"""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                json.dump({
                    'window_x': self.window_x,
                    'window_y': self.window_y,
                    'icon_size': self.icon_size,
                    'muted_keyword': self.muted_keyword,
                    'unmuted_keyword': self.unmuted_keyword,
                    'check_interval': self.check_interval
                }, f, indent=2)
        except Exception as e:
            print(f"Failed to save config: {e}")


class MuteStatusView(NSView):
    """ミュート状態を表示するビュー"""

    def initWithFrame_monitor_(self, frame, monitor):
        self = objc.super(MuteStatusView, self).initWithFrame_(frame)
        if self is None:
            return None

        self.monitor = monitor
        self.drag_start = None

        # ラベルのサイズを計算
        label_size = frame.size.width - 20

        # 画像ビュー（画像アイコン用）
        self.imageView = NSImageView.alloc().initWithFrame_(NSMakeRect(10, 10, label_size, label_size))
        self.imageView.setImageScaling_(1)  # NSImageScaleProportionallyUpOrDown

        self.addSubview_(self.imageView)

        return self

    def updateStatus_(self, is_muted):
        """ミュート状態を更新"""
        # 状態に応じてアイコンファイルを選択
        if is_muted is None:
            # 不明 - unknown-512.png
            icon_path = os.path.join(ICON_DIR, "unknown-512.png")
        elif is_muted:
            # ミュート中 - micOff-512.png（赤）
            icon_path = os.path.join(ICON_DIR, "micOff-512.png")
        else:
            # ミュート解除 - micOn-512.png（緑）
            icon_path = os.path.join(ICON_DIR, "micOn-512.png")

        if not os.path.exists(icon_path):
            return

        # 画像を読み込み
        image = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if image is not None:
            # サイズを設定して表示
            new_size = NSMakeSize(self.monitor.config.icon_size, self.monitor.config.icon_size)
            image.setSize_(new_size)
            self.imageView.setImage_(image)

    def updateIconSize_(self, size):
        """アイコンサイズを更新"""
        # ウィンドウサイズも調整（アイコン + パディング）
        new_window_size = size + 40
        frame = self.window().frame()
        frame.size.width = new_window_size
        frame.size.height = new_window_size
        self.window().setFrame_display_(frame, True)

        # 画像ビューのサイズも調整
        new_size = new_window_size - 20
        image_frame = self.imageView.frame()
        image_frame.size.width = new_size
        image_frame.size.height = new_size
        self.imageView.setFrame_(image_frame)

    def mouseDown_(self, event):
        """マウスダウンイベント（ドラッグ開始）"""
        self.drag_start = event.locationInWindow()

    def mouseDragged_(self, event):
        """マウスドラッグイベント（ウィンドウ移動）"""
        if self.drag_start is None:
            return

        current_location = event.locationInWindow()
        window_frame = self.window().frame()

        # ドラッグ量を計算
        dx = current_location.x - self.drag_start.x
        dy = current_location.y - self.drag_start.y

        # 新しい位置を設定
        new_origin = NSMakePoint(
            window_frame.origin.x + dx,
            window_frame.origin.y + dy
        )

        self.window().setFrameOrigin_(new_origin)

    def mouseUp_(self, event):
        """マウスアップイベント（ドラッグ終了）"""
        if self.drag_start is not None:
            # ドラッグ終了時に設定を保存
            window_frame = self.window().frame()
            self.monitor.config.window_x = window_frame.origin.x
            self.monitor.config.window_y = window_frame.origin.y
            self.monitor.config.save()
            self.drag_start = None

    def rightMouseDown_(self, event):
        """右クリックメニューを表示"""
        menu = NSMenu.alloc().init()

        # アイコンサイズ設定（50px単位で500pxまで）
        size_menu = NSMenu.alloc().init()
        for size in [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"{size}px" + (" ✓" if size == self.monitor.config.icon_size else ""),
                "setIconSize:",
                ""
            )
            item.setTag_(size)
            item.setTarget_(self.monitor)
            size_menu.addItem_(item)

        size_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "アイコンサイズ", None, ""
        )
        size_item.setSubmenu_(size_menu)
        menu.addItem_(size_item)

        # 監視間隔設定
        interval_menu = NSMenu.alloc().init()
        for interval in [10, 30, 50, 100, 200, 300, 500, 1000]:
            label = f"{interval}ms" + (" ✓" if interval == self.monitor.config.check_interval else "")
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label,
                "setCheckInterval:",
                ""
            )
            item.setTag_(interval)
            item.setTarget_(self.monitor)
            interval_menu.addItem_(item)

        interval_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "監視間隔", None, ""
        )
        interval_item.setSubmenu_(interval_menu)
        menu.addItem_(interval_item)

        menu.addItem_(NSMenuItem.separatorItem())

        # キーワード設定
        muted_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "ミュート検知キーワード設定...",
            "setMutedKeyword:",
            ""
        )
        muted_item.setTarget_(self.monitor)
        menu.addItem_(muted_item)

        unmuted_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "ミュート解除検知キーワード設定...",
            "setUnmutedKeyword:",
            ""
        )
        unmuted_item.setTarget_(self.monitor)
        menu.addItem_(unmuted_item)

        menu.addItem_(NSMenuItem.separatorItem())

        # エラー表示（unknown状態の時のみ）
        if self.monitor.last_error is not None:
            error_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "エラー表示",
                "showError:",
                ""
            )
            error_item.setTarget_(self.monitor)
            menu.addItem_(error_item)

        # アクセシビリティ設定を開く
        accessibility_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "アクセシビリティ設定を開く",
            "openAccessibilitySettings:",
            ""
        )
        accessibility_item.setTarget_(self.monitor)
        menu.addItem_(accessibility_item)

        menu.addItem_(NSMenuItem.separatorItem())

        # ログイン時に自動起動
        is_login_item = self.monitor.isLoginItem()
        login_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "ログイン時に自動起動" + (" ✓" if is_login_item else ""),
            "toggleLoginItem:",
            ""
        )
        login_item.setTarget_(self.monitor)
        menu.addItem_(login_item)

        menu.addItem_(NSMenuItem.separatorItem())

        # バージョン表示
        version_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "ver 1.0.0",
            None,
            ""
        )
        version_item.setEnabled_(False)  # クリック不可
        menu.addItem_(version_item)

        menu.addItem_(NSMenuItem.separatorItem())

        # 終了
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "終了",
            "terminate:",
            "q"
        )
        quit_item.setTarget_(NSApplication.sharedApplication())
        menu.addItem_(quit_item)

        # メニューを表示
        menu.popUpMenuPositioningItem_atLocation_inView_(
            None,
            event.locationInWindow(),
            self
        )


class ZoomMuteMonitor(NSObject):
    """Zoomのミュート状態を監視"""

    def init(self):
        self = objc.super(ZoomMuteMonitor, self).init()
        if self is None:
            return None

        self.window = None
        self.view = None
        self.timer = None
        self.config = Config()
        self.last_error = None  # 最後のエラー情報を保存

        return self

    def setupWindow(self):
        """透過ウィンドウをセットアップ"""
        # 画面サイズを取得
        screen = NSScreen.mainScreen()
        screen_frame = screen.frame()

        # ウィンドウサイズを計算（アイコンサイズ + パディング）
        window_size = self.config.icon_size + 40

        # 保存された位置があればそれを使用、なければ右上隅に配置
        if self.config.window_x is not None and self.config.window_y is not None:
            x = self.config.window_x
            y = self.config.window_y
        else:
            x = screen_frame.size.width - window_size - 20
            y = screen_frame.size.height - window_size - 20

        window_frame = NSMakeRect(x, y, window_size, window_size)

        # ウィンドウを作成（枠なし）
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            window_frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False
        )

        # ウィンドウ設定
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setLevel_(NSFloatingWindowLevel)  # 常に最前面
        self.window.setIgnoresMouseEvents_(False)  # マウスイベントを受け取る
        self.window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorStationary
        )
        self.window.setAnimationBehavior_(2)  # NSWindowAnimationBehaviorNone = 2

        # ビューを作成
        self.view = MuteStatusView.alloc().initWithFrame_monitor_(window_frame, self)
        self.window.setContentView_(self.view)
        self.window.makeKeyAndOrderFront_(None)

    def checkMuteStatus(self):
        """AppleScriptでZoomのミュート状態をチェック"""
        script = f'''
tell application "System Events"
    set zoomProcName to missing value
    if (exists process "zoom.us") then
        set zoomProcName to "zoom.us"
    else if (exists process "Zoom") then
        set zoomProcName to "Zoom"
    else
        return "not_running"
    end if

    tell process zoomProcName
        try
            set mb to menu bar 1
            tell menu bar item "ミーティング" of mb
                set meetingMenuItems to name of menu items of menu 1
                set mutedKeyword to "{self.config.muted_keyword}"
                set unmutedKeyword to "{self.config.unmuted_keyword}"

                -- まずミュート状態をチェック（早期リターン）
                repeat with meetingItem in meetingMenuItems
                    if (meetingItem as text) is equal to mutedKeyword then
                        return "muted"
                    end if
                end repeat

                -- 次にミュート解除状態をチェック（早期リターン）
                repeat with meetingItem in meetingMenuItems
                    if (meetingItem as text) is equal to unmutedKeyword then
                        return "unmuted"
                    end if
                end repeat

                -- どちらも見つからなかった場合（デバッグ情報）
                set itemList to ""
                repeat with menuItem in meetingMenuItems
                    set itemList to itemList & (menuItem as text) & "|"
                end repeat
                return "unknown:" & itemList
            end tell
        on error errMsg
            -- メニューアクセスエラー（ミーティング外など）
            return "error:" & errMsg
        end try
    end tell
end tell
return "unknown"
'''

        try:
            # NSAppleScriptを使用（.appから実行する場合、アプリ自体に権限が付与される）
            applescript = NSAppleScript.alloc().initWithSource_(script)
            result, error = applescript.executeAndReturnError_(None)

            if error:
                # AppleScriptエラー
                error_msg = error.get('NSAppleScriptErrorMessage', str(error))
                self.last_error = f"AppleScriptエラー:\n{error_msg}\n\nアクセシビリティ権限を確認してください"
                return None

            status = str(result.stringValue()) if result else "unknown"

            if status == "muted":
                self.last_error = None
                return True
            elif status == "unmuted":
                self.last_error = None
                return False
            else:
                # エラー情報を記録（詳細版）
                if status == "not_running":
                    self.last_error = "Zoomが起動していません"
                elif status.startswith("unknown:"):
                    # デバッグ情報付きのunknown
                    menu_items = status[8:]  # "unknown:" の後の部分
                    error_details = f"キーワードが見つかりません\n\nミュートキーワード: {self.config.muted_keyword}\nミュート解除キーワード: {self.config.unmuted_keyword}\n\n画面上部ステータスバーのZoomアイコンを押した時に表示される項目を確認してください\n\n【実際のメニュー項目】\n"
                    for item in menu_items.split('|'):
                        if item:
                            error_details += f"- {item}\n"
                    self.last_error = error_details
                elif status.startswith("error:"):
                    # AppleScriptエラー
                    error_msg = status[6:]
                    self.last_error = f"AppleScriptエラー:\n{error_msg}\n\nアクセシビリティ権限を確認してください"
                elif status == "unknown":
                    self.last_error = f"キーワードが見つかりません\n\nミュートキーワード: {self.config.muted_keyword}\nミュート解除キーワード: {self.config.unmuted_keyword}\n\n画面上部ステータスバーのZoomアイコンを押した時に表示される項目を確認してください"
                else:
                    self.last_error = f"不明なステータス: {status}"
                return None
        except Exception as e:
            self.last_error = f"予期しないエラー:\n{type(e).__name__}: {str(e)}"
            return None

    def updateStatus_(self, timer):
        """定期的に呼ばれてステータスを更新"""
        is_muted = self.checkMuteStatus()
        self.view.updateStatus_(is_muted)

    def setIconSize_(self, sender):
        """アイコンサイズを変更"""
        size = sender.tag()
        self.config.icon_size = size
        self.config.save()
        self.view.updateIconSize_(size)

    def setCheckInterval_(self, sender):
        """監視間隔を変更"""
        interval = sender.tag()
        self.config.check_interval = interval
        self.config.save()

        # タイマーを再起動
        if self.timer:
            self.timer.invalidate()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            interval / 1000.0,  # ミリ秒を秒に変換
            self,
            'updateStatus:',
            None,
            True
        )

    def showError_(self, sender):
        """エラー情報を表示"""
        alert = NSAlert.alloc().init()
        alert.setMessageText_("エラー詳細")

        if self.last_error:
            alert.setInformativeText_(self.last_error)
        else:
            alert.setInformativeText_("エラー情報はありません")

        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def openAccessibilitySettings_(self, sender):
        """アクセシビリティ設定を開く"""
        subprocess.run([
            'open',
            'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'
        ])

    def isLoginItem(self):
        """ログイン項目に登録されているかチェック"""
        try:
            # アプリのパスを取得
            if getattr(sys, 'frozen', False):
                # .appとして実行されている場合
                app_path = os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))
            else:
                # スクリプトとして実行されている場合は機能しない
                return False

            # osascriptでログイン項目をチェック
            script = f'''
tell application "System Events"
    get the name of every login item
end tell
'''
            applescript = NSAppleScript.alloc().initWithSource_(script)
            result, error = applescript.executeAndReturnError_(None)

            if error or not result:
                return False

            login_items = str(result.stringValue())
            # ZoomMuteMonitorが含まれているかチェック
            return "ZoomMuteMonitor" in login_items
        except:
            return False

    def toggleLoginItem_(self, sender):
        """ログイン項目の登録/解除を切り替え"""
        try:
            # アプリのパスを取得
            if getattr(sys, 'frozen', False):
                # .appとして実行されている場合
                app_path = os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))
            else:
                # スクリプトとして実行されている場合
                alert = NSAlert.alloc().init()
                alert.setMessageText_("エラー")
                alert.setInformativeText_("この機能は.appとしてビルドされた場合のみ利用可能です。")
                alert.addButtonWithTitle_("OK")
                alert.runModal()
                return

            if self.isLoginItem():
                # 登録解除
                script = '''
tell application "System Events"
    delete login item "ZoomMuteMonitor"
end tell
'''
                applescript = NSAppleScript.alloc().initWithSource_(script)
                result, error = applescript.executeAndReturnError_(None)

                if error:
                    alert = NSAlert.alloc().init()
                    alert.setMessageText_("エラー")
                    alert.setInformativeText_("ログイン項目の解除に失敗しました。")
                    alert.addButtonWithTitle_("OK")
                    alert.runModal()
                else:
                    alert = NSAlert.alloc().init()
                    alert.setMessageText_("成功")
                    alert.setInformativeText_("ログイン時の自動起動を解除しました。")
                    alert.addButtonWithTitle_("OK")
                    alert.runModal()
            else:
                # 登録
                script = f'''
tell application "System Events"
    make login item at end with properties {{path:"{app_path}", hidden:false}}
end tell
'''
                applescript = NSAppleScript.alloc().initWithSource_(script)
                result, error = applescript.executeAndReturnError_(None)

                if error:
                    alert = NSAlert.alloc().init()
                    alert.setMessageText_("エラー")
                    alert.setInformativeText_("ログイン項目の登録に失敗しました。")
                    alert.addButtonWithTitle_("OK")
                    alert.runModal()
                else:
                    alert = NSAlert.alloc().init()
                    alert.setMessageText_("成功")
                    alert.setInformativeText_("ログイン時に自動起動するように設定しました。")
                    alert.addButtonWithTitle_("OK")
                    alert.runModal()
        except Exception as e:
            alert = NSAlert.alloc().init()
            alert.setMessageText_("エラー")
            alert.setInformativeText_(f"予期しないエラー: {str(e)}")
            alert.addButtonWithTitle_("OK")
            alert.runModal()

    def setMutedKeyword_(self, sender):
        """ミュート検知キーワードを設定"""
        alert = NSAlert.alloc().init()

        # アイコンを設定
        icon_path = os.path.join(ICON_DIR, "icon-200.png")
        if os.path.exists(icon_path):
            icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
            if icon:
                icon.setSize_(NSMakeSize(64, 64))
                alert.setIcon_(icon)

        alert.setMessageText_("ミュート検知キーワード")
        alert.setInformativeText_(f"現在: {self.config.muted_keyword}\n\n画面上部ステータスバーのZoomアイコンを押した時に表示される項目と完全一致で比較し、このキーワードが見つかった時にマイクOFFと判定します。\n\n新しいキーワード:")
        alert.addButtonWithTitle_("OK")
        alert.addButtonWithTitle_("キャンセル")

        input_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 24))
        input_field.setStringValue_(self.config.muted_keyword)
        alert.setAccessoryView_(input_field)

        response = alert.runModal()
        if response == NSAlertFirstButtonReturn:
            new_keyword = input_field.stringValue()
            if new_keyword:
                self.config.muted_keyword = new_keyword
                self.config.save()

    def setUnmutedKeyword_(self, sender):
        """ミュート解除検知キーワードを設定"""
        alert = NSAlert.alloc().init()

        # アイコンを設定
        icon_path = os.path.join(ICON_DIR, "icon-200.png")
        if os.path.exists(icon_path):
            icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
            if icon:
                icon.setSize_(NSMakeSize(64, 64))
                alert.setIcon_(icon)

        alert.setMessageText_("ミュート解除検知キーワード")
        alert.setInformativeText_(f"現在: {self.config.unmuted_keyword}\n\n画面上部ステータスバーのZoomアイコンを押した時に表示される項目と完全一致で比較し、このキーワードが見つかった時にマイクONと判定します。\n\n新しいキーワード:")
        alert.addButtonWithTitle_("OK")
        alert.addButtonWithTitle_("キャンセル")

        input_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 24))
        input_field.setStringValue_(self.config.unmuted_keyword)
        alert.setAccessoryView_(input_field)

        response = alert.runModal()
        if response == NSAlertFirstButtonReturn:
            new_keyword = input_field.stringValue()
            if new_keyword:
                self.config.unmuted_keyword = new_keyword
                self.config.save()

    def startMonitoring(self):
        """監視を開始"""
        self.setupWindow()

        # 設定された間隔でチェック
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            self.config.check_interval / 1000.0,  # ミリ秒を秒に変換
            self,
            'updateStatus:',
            None,
            True
        )

        # 初回チェック
        self.updateStatus_(None)


def main():
    """メイン関数"""
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory (Dockに表示しない)

    # アプリ名を設定
    from Foundation import NSBundle
    info = NSBundle.mainBundle().infoDictionary()
    if info:
        info["CFBundleName"] = "ZoomMuteMonitor"

    monitor = ZoomMuteMonitor.alloc().init()
    monitor.startMonitoring()

    app.run()


if __name__ == "__main__":
    main()
