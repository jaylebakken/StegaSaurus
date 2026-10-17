param(
    [string]$Profile = "saurus-alpha-admin",
    [string]$Domain = "saurus-audio.com",
    [string]$HostedZoneId = "",
    [string]$RecordName = "_b6776ef416532d3eed22ff04e66d93a3.registry-alpha.saurus-audio.com.",
    [string]$RecordValue = "_b79db264054430dacd5b49364bf5ad60.wzccmgtwzk.acm-validations.aws.",
    [switch]$ListZonesOnly
)

$ErrorActionPreference = "Stop"

function Normalize-Name {
    param([string]$Name)
    return $Name.TrimEnd(".").ToLowerInvariant()
}

Write-Host "Checking AWS identity for profile '$Profile'..."
aws sts get-caller-identity --profile $Profile --output table

Write-Host ""
Write-Host "Reading public nameservers for $Domain..."
$publicNs = Resolve-DnsName -Type NS $Domain |
    Where-Object { $_.NameHost } |
    ForEach-Object { Normalize-Name $_.NameHost } |
    Sort-Object

if (-not $publicNs) {
    throw "Could not resolve public NS records for $Domain."
}

$publicNs | ForEach-Object { Write-Host "  $_" }

Write-Host ""
Write-Host "Finding matching Route 53 hosted zone..."
$zones = aws route53 list-hosted-zones-by-name `
    --profile $Profile `
    --dns-name $Domain `
    --output json | ConvertFrom-Json

$visibleZones = @()
$matchingZone = $null
foreach ($zone in $zones.HostedZones) {
    if ((Normalize-Name $zone.Name) -ne (Normalize-Name $Domain)) {
        continue
    }

    $zoneId = ($zone.Id -replace "^/hostedzone/", "")
    $recordSets = aws route53 list-resource-record-sets `
        --profile $Profile `
        --hosted-zone-id $zoneId `
        --query "ResourceRecordSets[?Type=='NS' && Name=='$Domain.']" `
        --output json | ConvertFrom-Json

    if (-not $recordSets) {
        continue
    }

    $zoneNs = $recordSets[0].ResourceRecords |
        ForEach-Object { Normalize-Name $_.Value } |
        Sort-Object

    $visibleZones += [pscustomobject]@{
        HostedZoneId = $zoneId
        Name = $zone.Name
        PrivateZone = $zone.Config.PrivateZone
        NameServers = ($zoneNs -join ", ")
    }

    if (($zoneNs -join "|") -eq ($publicNs -join "|")) {
        $matchingZone = @{
            Id = $zoneId
            Name = $zone.Name
        }
        break
    }
}

if ($HostedZoneId) {
    $matchingZone = @{
        Id = ($HostedZoneId -replace "^/hostedzone/", "")
        Name = "$Domain."
    }
    Write-Host ""
    Write-Host "Using requested hosted zone $($matchingZone.Id)."
}

if ($ListZonesOnly) {
    if (-not $visibleZones) {
        Write-Host "No hosted zones named $Domain were visible to this profile."
    } else {
        $visibleZones | Format-Table -AutoSize
    }
    exit 0
}

if (-not $matchingZone) {
    Write-Host ""
    Write-Host "Hosted zones visible to this profile:"
    if (-not $visibleZones) {
        Write-Host "  None named $Domain."
    } else {
        $visibleZones | Format-Table -AutoSize
    }
    Write-Host ""
    throw "No Route 53 hosted zone matched the public nameservers for $Domain."
}

Write-Host "Matched hosted zone $($matchingZone.Id) ($($matchingZone.Name))."

$changeBatch = @{
    Comment = "ACM DNS validation for registry-alpha.saurus-audio.com"
    Changes = @(
        @{
            Action = "UPSERT"
            ResourceRecordSet = @{
                Name = $RecordName
                Type = "CNAME"
                TTL = 300
                ResourceRecords = @(
                    @{ Value = $RecordValue }
                )
            }
        }
    )
} | ConvertTo-Json -Depth 10

$batchPath = Join-Path $env:TEMP "saurus-acm-validation-change.json"
$changeBatch | Set-Content -Path $batchPath -Encoding ascii

Write-Host ""
Write-Host "Upserting ACM validation CNAME..."
aws route53 change-resource-record-sets `
    --profile $Profile `
    --hosted-zone-id $matchingZone.Id `
    --change-batch "file://$batchPath" `
    --output table

Write-Host ""
Write-Host "Checking public DNS..."
Resolve-DnsName -Type CNAME $RecordName -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done. Once the CNAME resolves publicly, ACM should move from PENDING_VALIDATION to ISSUED."
