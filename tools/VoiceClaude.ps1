#Requires -Version 5.0
# VoiceClaude.ps1 — Push-to-talk voice chat with Claude
#
# SETUP (one-time):
#   1. Enable Windows Speech Recognition:
#      Start → Settings → Time & Language → Speech → "Get started"
#   2. Set your API key in PowerShell:
#      $env:ANTHROPIC_API_KEY = "sk-ant-api03-..."
#      (Add to your PowerShell profile to make it permanent)
#   3. Run:
#      powershell -ExecutionPolicy Bypass -File VoiceClaude.ps1
#
# USAGE:
#   Hold the blue HOLD TO TALK button → speak → release.
#   Claude's reply appears in the window AND is spoken aloud.
#   Press Clear Chat to start a fresh conversation.

param(
    [string] $ApiKey  = $env:ANTHROPIC_API_KEY,
    [string] $Model   = "claude-opus-4-6",
    [int]    $TtsRate = 1          # -10 slowest … 10 fastest
)

if (!$ApiKey) { $ApiKey = Read-Host "Anthropic API key" }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Speech

# ─── Speech I/O ───────────────────────────────────────────────────────────────
try {
    $rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine(
               [System.Globalization.CultureInfo]::CurrentCulture)
    $rec.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
    $rec.SetInputToDefaultAudioDevice()
} catch {
    [System.Windows.Forms.MessageBox]::Show(
        "Microphone unavailable.`n`n$($_.Exception.Message)",
        "VoiceClaude", "OK", "Error") | Out-Null
    exit 1
}

$tts      = New-Object System.Speech.Synthesis.SpeechSynthesizer
$tts.Rate = $TtsRate

$script:heard   = ""
$script:history = [System.Collections.Generic.List[hashtable]]::new()

$rec.add_SpeechRecognized({ param($s, $e) $script:heard += " " + $e.Result.Text })

# ─── Form ─────────────────────────────────────────────────────────────────────
$form             = New-Object System.Windows.Forms.Form
$form.Text        = "Voice Claude"
$form.ClientSize  = New-Object System.Drawing.Size(420, 640)
$form.StartPosition = "CenterScreen"
$form.BackColor   = [System.Drawing.Color]::FromArgb(18, 18, 20)
$form.TopMost     = $true

$chat             = New-Object System.Windows.Forms.RichTextBox
$chat.SetBounds(6, 6, 408, 498)
$chat.BackColor   = [System.Drawing.Color]::FromArgb(26, 26, 30)
$chat.ForeColor   = [System.Drawing.Color]::WhiteSmoke
$chat.Font        = New-Object System.Drawing.Font("Consolas", 9.5)
$chat.ReadOnly    = $true
$chat.BorderStyle = "None"
$chat.ScrollBars  = "Vertical"
$form.Controls.Add($chat)

$status           = New-Object System.Windows.Forms.Label
$status.SetBounds(6, 510, 408, 20)
$status.Text      = "Hold the button and speak, release to send"
$status.ForeColor = [System.Drawing.Color]::Silver
$status.Font      = New-Object System.Drawing.Font("Segoe UI", 9)
$status.TextAlign = "MiddleCenter"
$form.Controls.Add($status)

$talkBtn          = New-Object System.Windows.Forms.Button
$talkBtn.SetBounds(6, 534, 408, 72)
$talkBtn.Text     = "HOLD TO TALK"
$talkBtn.Font     = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$talkBtn.BackColor = [System.Drawing.Color]::FromArgb(37, 99, 235)
$talkBtn.ForeColor = [System.Drawing.Color]::White
$talkBtn.FlatStyle = "Flat"
$talkBtn.FlatAppearance.BorderSize = 0
$form.Controls.Add($talkBtn)

$clearBtn         = New-Object System.Windows.Forms.Button
$clearBtn.SetBounds(6, 612, 90, 22)
$clearBtn.Text    = "Clear Chat"
$clearBtn.Font    = New-Object System.Drawing.Font("Segoe UI", 8)
$clearBtn.BackColor = [System.Drawing.Color]::FromArgb(50, 50, 58)
$clearBtn.ForeColor = [System.Drawing.Color]::White
$clearBtn.FlatStyle = "Flat"
$clearBtn.FlatAppearance.BorderSize = 0
$clearBtn.Add_Click({
    $chat.Clear()
    $script:history.Clear()
    $status.Text = "Chat cleared"
})
$form.Controls.Add($clearBtn)

# ─── Helpers ──────────────────────────────────────────────────────────────────
function Write-Chat([string]$who, [string]$msg, [string]$hex) {
    $col = [System.Drawing.ColorTranslator]::FromHtml($hex)
    $chat.SelectionStart  = $chat.TextLength
    $chat.SelectionLength = 0
    $chat.SelectionColor  = $col
    $chat.AppendText("[$who]`n$msg`n`n")
    $chat.ScrollToCaret()
}

function Send-ToAPI([string]$text) {
    $script:history.Add(@{ role = "user"; content = $text })
    $payload = @{
        model      = $Model
        max_tokens = 1500
        messages   = @($script:history)
    } | ConvertTo-Json -Depth 10

    $r = Invoke-RestMethod "https://api.anthropic.com/v1/messages" -Method Post `
        -Headers @{
            "x-api-key"         = $ApiKey
            "anthropic-version" = "2023-06-01"
            "content-type"      = "application/json"
        } -Body $payload

    $reply = $r.content[0].text
    $script:history.Add(@{ role = "assistant"; content = $reply })
    return $reply
}

# ─── Button Events ────────────────────────────────────────────────────────────
$talkBtn.Add_MouseDown({
    $tts.SpeakAsyncCancelAll()
    $script:heard      = ""
    $talkBtn.BackColor = [System.Drawing.Color]::FromArgb(220, 38, 38)
    $talkBtn.Text      = "LISTENING..."
    $status.Text       = "Listening — speak now"
    $rec.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
})

$talkBtn.Add_MouseUp({
    $rec.RecognizeAsyncStop()
    $talkBtn.BackColor = [System.Drawing.Color]::FromArgb(37, 99, 235)
    $talkBtn.Text      = "HOLD TO TALK"

    # Let the engine finalize the last word before we grab the text
    [System.Windows.Forms.Application]::DoEvents()
    Start-Sleep -Milliseconds 700
    [System.Windows.Forms.Application]::DoEvents()

    $text = $script:heard.Trim()
    if (!$text) {
        $status.Text = "Nothing heard — try again"
        return
    }

    Write-Chat "You" $text "#86efac"
    $status.Text     = "Thinking..."
    $talkBtn.Enabled = $false
    [System.Windows.Forms.Application]::DoEvents()

    try {
        $reply = Send-ToAPI $text
        Write-Chat "Claude" $reply "#93c5fd"
        $status.Text = "Speaking..."
        [System.Windows.Forms.Application]::DoEvents()
        $tts.Speak($reply)   # synchronous — blocks until speech is fully done
    } catch {
        Write-Chat "Error" $_.Exception.Message "#fca5a5"
        $status.Text = "Error — check API key / internet connection"
    }

    $talkBtn.Enabled = $true
    $status.Text     = "Hold the button and speak, release to send"
})

$form.Add_FormClosing({ $rec.Dispose(); $tts.Dispose() })

# ─── Launch ───────────────────────────────────────────────────────────────────
$tts.Speak("Voice Claude ready. Hold the button to speak.")
[System.Windows.Forms.Application]::Run($form)
