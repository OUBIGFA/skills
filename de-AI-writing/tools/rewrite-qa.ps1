param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Path,

    [Parameter(Mandatory = $true, Position = 1)]
    [string]$SourcePath,

    [int]$HeadingMinParagraphs = 2,
    [double]$FirstParagraphSimilarityMax = 0.90,
    [string[]]$BannedPatterns = @(
        "\u8206\u8bba\u573a",
        "\u8bdd\u8bed\u573a",
        "\u6743\u529b\u573a",
        "\u516c\u5171\u573a\u57df",
        "\u5b8f\u5927\u53d9\u4e8b",
        "\u5b98\u65b9\u53d9\u4e8b",
        "\u644a\u5f00\u6765\u770b",
        "\u644a\u5f00\u6765\u8bf4",
        "\u628a.{0,20}\u644a\u5f00\u6765",
        "(\u4e0d\u662f|\u5e76\u975e|\u4e0d\u5728\u4e8e).{0,24}(\u800c\u662f|\u800c\u5728\u4e8e)",
        "(\u6700\u6b8b\u9177|\u6700\u53ef\u6015|\u6700\u8bbd\u523a|\u6700\u8352\u8c2c)\u7684\u5730\u65b9(\u5728\u4e8e|\u662f)",
        "\u771f\u6b63(\u53ef\u6015|\u6b8b\u9177|\u8bbd\u523a)\u7684\u662f"
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function U([string]$escaped) {
    return [regex]::Unescape($escaped)
}

$BannedPatterns = @($BannedPatterns | ForEach-Object { U $_ })

function Get-BodyText([string]$text) {
    if ($text -match "(?s)^---\r?\n.*?\r?\n---\r?\n") {
        return $text.Substring($matches[0].Length)
    }
    return $text
}

function Get-Paragraphs([string]$text) {
    $body = Get-BodyText $text
    $parts = [regex]::Split($body.Trim(), "\r?\n\s*\r?\n")
    $result = @()
    foreach ($p in $parts) {
        $t = $p.Trim()
        if ($t.Length -eq 0) { continue }
        if ($t -match "^#{1,6}\s+") { continue }
        $result += $t
    }
    return @($result)
}

function Get-FirstParagraph([string]$text) {
    $paras = @(Get-Paragraphs $text)
    if ($paras.Count -gt 0) { return $paras[0] }
    return ""
}

function Get-Bigrams([string]$s) {
    $norm = ($s -replace "\s+", "").Trim()
    if ($norm.Length -lt 2) { return @{} }
    $map = @{}
    for ($i = 0; $i -lt $norm.Length - 1; $i++) {
        $bg = $norm.Substring($i, 2)
        if ($map.ContainsKey($bg)) {
            $map[$bg] += 1
        } else {
            $map[$bg] = 1
        }
    }
    return $map
}

function Get-DiceSimilarity([string]$a, [string]$b) {
    $aMap = Get-Bigrams $a
    $bMap = Get-Bigrams $b
    $aTotal = 0
    $bTotal = 0
    foreach ($v in $aMap.Values) { $aTotal += $v }
    foreach ($v in $bMap.Values) { $bTotal += $v }
    if ($aTotal -eq 0 -and $bTotal -eq 0) { return 1.0 }
    if ($aTotal -eq 0 -or $bTotal -eq 0) { return 0.0 }

    $overlap = 0
    foreach ($k in $aMap.Keys) {
        if ($bMap.ContainsKey($k)) {
            $overlap += [Math]::Min([int]$aMap[$k], [int]$bMap[$k])
        }
    }
    return (2.0 * $overlap) / ($aTotal + $bTotal)
}

function Test-HeadingDensity([string]$text, [int]$minParagraphsPerHeading) {
    $body = Get-BodyText $text
    $lines = @([regex]::Split($body, "\r?\n"))
    $headingIndex = @()
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^##\s+") {
            $headingIndex += $i
        }
    }

    if ($headingIndex.Count -eq 0) {
        return @{
            pass = $true
            message = "no H2 headings"
            headingCount = 0
        }
    }

    $failItems = @()
    for ($h = 0; $h -lt $headingIndex.Count; $h++) {
        $start = $headingIndex[$h] + 1
        $end = if ($h -lt $headingIndex.Count - 1) { $headingIndex[$h + 1] - 1 } else { $lines.Count - 1 }
        $block = ($lines[$start..$end] -join "`n").Trim()
        $paras = @([regex]::Split($block, "\r?\n\s*\r?\n") | Where-Object {
            $t = $_.Trim()
            $t.Length -gt 0 -and $t -notmatch "^#{1,6}\s+"
        })
        if ($paras.Count -lt $minParagraphsPerHeading) {
            $failItems += "heading at line $($headingIndex[$h] + 1) has $($paras.Count) paragraph(s)"
        }
    }

    $allParas = @(Get-Paragraphs $text)
    $ratioPass = $headingIndex.Count -le [Math]::Max(1, [Math]::Floor($allParas.Count / [Math]::Max(1, $minParagraphsPerHeading)))
    if (-not $ratioPass) {
        $failItems += "heading/paragraph ratio too dense (headings=$($headingIndex.Count), paragraphs=$($allParas.Count))"
    }

    if ($failItems.Count -eq 0) {
        return @{ pass = $true; message = "ok"; headingCount = $headingIndex.Count }
    }
    return @{ pass = $false; message = ($failItems -join "; "); headingCount = $headingIndex.Count }
}

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Error "File not found: $Path"
    exit 1
}
if (-not (Test-Path -LiteralPath $SourcePath)) {
    Write-Error "Source file not found: $SourcePath"
    exit 1
}

$targetText = Get-Content -LiteralPath $Path -Encoding utf8 -Raw
$sourceText = Get-Content -LiteralPath $SourcePath -Encoding utf8 -Raw

$issues = @()

# 1) Heading density
$headingCheck = Test-HeadingDensity -text $targetText -minParagraphsPerHeading $HeadingMinParagraphs
if (-not $headingCheck.pass) {
    $issues += "heading_density: $($headingCheck.message)"
}

# 2) First paragraph repetition
$srcFirst = Get-FirstParagraph $sourceText
$dstFirst = Get-FirstParagraph $targetText
$sim = Get-DiceSimilarity $srcFirst $dstFirst
if ($sim -gt $FirstParagraphSimilarityMax) {
    $issues += "first_paragraph_similarity: $([Math]::Round($sim, 4)) > $FirstParagraphSimilarityMax"
}

# 3) Banned pattern hits
$body = Get-BodyText $targetText
$bannedHits = @()
foreach ($pat in $BannedPatterns) {
    $count = ([regex]::Matches($body, $pat)).Count
    if ($count -gt 0) {
        $bannedHits += "$pat x$count"
    }
}
if (@($bannedHits).Count -gt 0) {
    $issues += "banned_hits: " + ($bannedHits -join ", ")
}

Write-Output "===== Rewrite QA ====="
Write-Output "Target: $Path"
Write-Output "Source: $SourcePath"
Write-Output "Heading check: $($headingCheck.message)"
Write-Output "First paragraph similarity: $([Math]::Round($sim, 4))"
Write-Output ""

if ($issues.Count -eq 0) {
    Write-Output "Result: PASS"
    exit 0
}

Write-Output "Result: FAIL"
foreach ($i in $issues) {
    Write-Output "- $i"
}
exit 2
