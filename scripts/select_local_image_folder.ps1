$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

Add-Type -AssemblyName System.Windows.Forms

$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Wybierz folder ze zdjęciami layoutów'
$dialog.ShowNewFolderButton = $false

$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    @{ status = 'selected'; path = $dialog.SelectedPath } | ConvertTo-Json -Compress
} else {
    @{ status = 'cancelled' } | ConvertTo-Json -Compress
}

$dialog.Dispose()
