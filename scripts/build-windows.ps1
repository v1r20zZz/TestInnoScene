$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'Сборка выполняется только в Windows.' }
python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Ошибка установки зависимостей' }
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest tests -q --junitxml=test-results-windows.xml
if ($LASTEXITCODE -ne 0) { throw 'Тесты не пройдены' }
python -m PyInstaller --clean --noconfirm ChessDiagram.spec
if ($LASTEXITCODE -ne 0) { throw 'Ошибка PyInstaller' }
$smoke = Start-Process '.\dist\ChessDiagramConstructor\ChessDiagramConstructor.exe' -ArgumentList '--smoke-test' -Wait -PassThru
if ($smoke.ExitCode -ne 0) { throw 'Приложение не запустилось' }
Remove-Item Env:QT_QPA_PLATFORM
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw 'Установите Inno Setup 6 на машине сборки.' }
& $iscc 'installer\setup.iss'
if ($LASTEXITCODE -ne 0) { throw 'Ошибка сборки установщика' }
Write-Host 'Установщик собран. Требуется проверка установки, работы и удаления на чистых Windows 10 и 11.'

$tempRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$installDir = Join-Path $tempRoot 'ChessDiagram-Проверка'
$setup = Start-Process '.\release\ChessDiagramConstructor_Setup.exe' -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$installDir`"") -Wait -PassThru
if ($setup.ExitCode -ne 0) { throw 'Installer failed' }
$env:QT_QPA_PLATFORM = 'offscreen'
$installed = Start-Process (Join-Path $installDir 'ChessDiagramConstructor.exe') -ArgumentList '--smoke-test' -Wait -PassThru
if ($installed.ExitCode -ne 0) { throw 'Installed application failed' }
$env:CHESS_FROZEN_TEST_DIR = Join-Path $tempRoot 'ChessDiagram-Export-Test'
@'
import json, os
from pathlib import Path
from chessdiagram.model import Document
root=Path(os.environ['CHESS_FROZEN_TEST_DIR']);root.mkdir(exist_ok=True)
Document().save(root/'project.chessdiagram')
(root/'job.json').write_text(json.dumps({'kind':'diagrams','outputs':[{'path':str(root/'installed.svg'),'index':0}]}),encoding='utf-8')
'@ | python -
if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare installed export check' }
$exportCheck = Start-Process (Join-Path $installDir 'ChessDiagramConstructor.exe') -ArgumentList @('--export-job', "`"$env:CHESS_FROZEN_TEST_DIR`"") -Wait -PassThru
if ($exportCheck.ExitCode -ne 0 -or -not (Test-Path (Join-Path $env:CHESS_FROZEN_TEST_DIR 'installed.svg'))) { throw 'Installed export worker failed' }
Write-Host 'Installed export worker check passed.'
$uninstall = Start-Process (Join-Path $installDir 'unins000.exe') -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw 'Uninstall failed' }
if (Test-Path (Join-Path $installDir 'ChessDiagramConstructor.exe')) { throw 'Application remains after uninstall' }
Write-Host 'Installer, installed application and uninstaller smoke checks passed.'
