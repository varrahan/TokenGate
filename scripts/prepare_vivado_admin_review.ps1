# Read diagnostics and create a local review package. No policy deployment.
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$outputPath=Join-Path $workspacePath 'build\admin-review\vivado-2025.2-kintexuplus'
if(Test-Path -LiteralPath $outputPath) { throw 'Administrator review package already exists; preserve it' }
$libraryPath='C:\AMDDesignTools\2025.2\Vivado\lib\win64.o\veam\kintexuplus\kintexuplus.dll'
$libraryFile=Get-Item -LiteralPath $libraryPath
$libraryHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $libraryPath).Hash
$signature=Get-AuthenticodeSignature -LiteralPath $libraryPath
$blockedEvent=Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-CodeIntegrity/Operational';Id=3077;StartTime=(Get-Date).AddHours(-3)} -MaxEvents 200 | Where-Object { $_.Message -like '*kintexuplus.dll*' } | Select-Object -First 1
if(-not $blockedEvent) { throw 'No current matching Code Integrity block event' }
[xml]$eventXml=$blockedEvent.ToXml()
$eventData=@{}
foreach($entry in $eventXml.Event.EventData.Data) { $eventData[$entry.Name]=$entry.InnerText }
if($eventData['SHA256 Flat Hash'] -ne $libraryHash) { throw 'Current library differs from blocked file' }
if($eventData['PolicyGUID'] -ne '{0283ac0f-fff1-49ae-ada1-8a933130cad6}' -or $eventData['PolicyName'] -ne 'VerifiedAndReputableDesktop') { throw 'Blocking policy changed; reassess supported review procedure' }
$osInfo=Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber
$sacState=(Get-ItemProperty -LiteralPath 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\CI\Policy' -Name VerifiedAndReputablePolicyState).VerifiedAndReputablePolicyState
$inventoryText=(& "$env:SystemRoot\System32\CiTool.exe" -lp -json | Out-String).Trim()
$policyInventory=$inventoryText | ConvertFrom-Json
$selectedData=@{}
foreach($field in @('File Name','Process Name','Status','SHA256 Hash','SHA256 Flat Hash','PolicyName','PolicyGUID','Requested Signing Level','Validated Signing Level','UserWriteable')) { $selectedData[$field]=$eventData[$field] }
$record=[ordered]@{
    phase='administrator_review_prepared_no_policy_deployed'
    created_utc=(Get-Date).ToUniversalTime().ToString('o')
    requested_scope='One exact Vivado 2025.2 device DLL, subject to administrator/vendor validation'
    library_path=$libraryPath
    library_bytes=$libraryFile.Length
    library_sha256_flat=$libraryHash
    code_integrity_sha256_hash=$eventData['SHA256 Hash']
    signature_status=$signature.Status.ToString()
    windows=$osInfo
    smart_app_control_registry_state=$sacState
    policy_name=$eventData['PolicyName']
    policy_guid=$eventData['PolicyGUID']
    policy_type='Windows-managed Smart App Control enforcement base'
    policy_inventory_result=$policyInventory
    configci_authoring_commands_available=[bool](Get-Command New-CIPolicyRule -ErrorAction SilentlyContinue)
    administrator_approved=$false
    policy_deployed=$false
    security_settings_changed=$false
    supported_rule_deployment_verified=$false
    source_script_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash
}
New-Item -ItemType Directory -Path $outputPath | Out-Null
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $outputPath 'request.json') -Encoding utf8
[ordered]@{event_id=$blockedEvent.Id;record_id=$blockedEvent.RecordId;created_utc=$blockedEvent.TimeCreated.ToUniversalTime().ToString('o');process_id=$eventXml.Event.System.Execution.ProcessID;fields=$selectedData} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputPath 'code-integrity-event.json') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $workspacePath 'docs\vivado-administrator-review.rst') -Destination (Join-Path $outputPath 'administrator-request.rst')
Copy-Item -LiteralPath (Join-Path $workspacePath 'build\parser_fpga_au15p_logical_partition_tx_witness-implementation.log') -Destination (Join-Path $outputPath 'parser-build.log')
Copy-Item -LiteralPath (Join-Path $workspacePath 'hs_err_pid21880.log') -Destination (Join-Path $outputPath 'parser-crash.log')
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $outputPath 'prepare_vivado_admin_review.ps1')
$packageHashes=[ordered]@{}
foreach($file in Get-ChildItem -LiteralPath $outputPath -File) { $packageHashes[$file.Name]=(Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash }
$packageHashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'SHA256SUMS.json') -Encoding utf8
Write-Output "ADMIN_REVIEW_PREPARED=$outputPath POLICY_DEPLOYED=0 SECURITY_SETTINGS_CHANGED=0"
