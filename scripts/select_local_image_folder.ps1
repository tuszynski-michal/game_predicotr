$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class GamePredictorFolderPickerWindow {
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr windowHandle);
}
'@

$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Wybierz folder ze zdjęciami layoutów'
$dialog.ShowNewFolderButton = $false

$owner = New-Object System.Windows.Forms.Form
$owner.Text = 'Game Predictor - wybierz folder'
$owner.Width = 360
$owner.Height = 110
$owner.ControlBox = $false
$owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$owner.ShowInTaskbar = $true
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$owner.TopMost = $true

$message = New-Object System.Windows.Forms.Label
$message.Dock = [System.Windows.Forms.DockStyle]::Fill
$message.Text = 'Wybierz folder w otwartym oknie systemu Windows.'
$message.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$owner.Controls.Add($message)

try {
    [void]$owner.Show()
    $owner.BringToFront()
    [void]$owner.Activate()
    [System.Windows.Forms.Application]::DoEvents()
    [void][GamePredictorFolderPickerWindow]::SetForegroundWindow($owner.Handle)
    $result = $dialog.ShowDialog($owner)
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        @{ status = 'selected'; path = $dialog.SelectedPath } | ConvertTo-Json -Compress
    } else {
        @{ status = 'cancelled' } | ConvertTo-Json -Compress
    }
}
finally {
    $dialog.Dispose()
    $owner.Dispose()
}
