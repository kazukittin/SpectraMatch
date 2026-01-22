@echo off
chcp 65001 > nul
echo ============================================================
echo    SpectraMatch EXE Builder
echo ============================================================
echo.

REM カレントディレクトリをスクリプトの場所に移動
cd /d "%~dp0"

echo [1/3] 環境を確認中...
python --version
if errorlevel 1 (
    echo.
    echo ❌ エラー: Python が見つかりません
    echo    Python をインストールしてPATHに追加してください
    pause
    exit /b 1
)

echo.
echo [2/3] PyInstaller を確認中...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo    PyInstaller がインストールされていません。インストールします...
    pip install pyinstaller
    if errorlevel 1 (
        echo ❌ PyInstaller のインストールに失敗しました
        pause
        exit /b 1
    )
)
echo    ✅ PyInstaller OK

echo.
echo [3/5] 古いビルドキャッシュを削除中...
if exist "build" (
    echo    - build フォルダを削除しています...
    rmdir /s /q "build"
)
if exist "dist" (
    echo    - dist フォルダを削除しています...
    rmdir /s /q "dist"
)
echo    ✅ キャッシュを削除しました

echo.
echo [4/5] 古い .spec キャッシュをクリーンアップ中...
REM PyInstallerの内部キャッシュもクリーンアップ
if exist "SpectraMatch.spec" (
    echo    ✅ specファイルを使用してビルドします
)

echo.
echo [5/5] EXE をビルド中...（数分かかります）
echo.
python build_exe.py

if errorlevel 1 (
    echo.
    echo ❌ ビルドに失敗しました
    pause
    exit /b 1
)

echo.
echo ============================================================
echo ✅ ビルド完了!
echo.
echo    EXE の場所: dist\SpectraMatch\SpectraMatch.exe
echo.
echo    ※ dist\SpectraMatch フォルダごと配布してください
echo ============================================================
echo.

REM ビルド完了後、dist フォルダを開く
explorer dist\SpectraMatch

pause
