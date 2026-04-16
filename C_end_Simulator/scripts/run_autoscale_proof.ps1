param(
    [string]$ProjectRoot = "D:\bot\PetNode\C_end_Simulator",
    [string]$JMeterBat = "D:\JMeter\apache-jmeter-5.6.3\bin\jmeter.bat",
    [string]$PythonExe = "python",
    [string]$JavaHome = "C:\Users\Lenovo\AppData\Local\Programs\Microsoft\jdk-17.0.10.7-hotspot",
    [int]$MinReplicas = 1,
    [int]$MaxReplicas = 4,
    [int]$TargetMessagesPerWorker = 30,
    [int]$PollIntervalSec = 2,
    [int]$CooldownSec = 8,
    [int]$MonitorDurationSec = 180,
    [int]$JMeterThreads = 80,
    [int]$JMeterLoops = 300,
    [string]$ApiKey = "petnode_secret_key_2026",
    [string]$HmacKey = "petnode_hmac_secret_2026",
    [string]$QueueName = "petnode.records"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$message) {
    Write-Host "[INFO] $message" -ForegroundColor Cyan
}

function Write-Step([string]$message) {
    Write-Host "[STEP] $message" -ForegroundColor Green
}

function Assert-Path([string]$path, [string]$name) {
    if (-not (Test-Path $path)) {
        throw "$name not found: $path"
    }
}

function Get-P95([int[]]$values) {
    if ($values.Count -eq 0) { return 0 }
    $sorted = $values | Sort-Object
    $idx = [Math]::Floor(($sorted.Count - 1) * 0.95)
    return $sorted[$idx]
}

Write-Step "Validate environment"
Assert-Path $ProjectRoot "ProjectRoot"
Assert-Path $JMeterBat "JMeter"

if (Test-Path $JavaHome) {
    $env:JAVA_HOME = $JavaHome
    $env:Path = "$JavaHome\\bin;" + $env:Path
}

Push-Location $ProjectRoot
try {
    $runId = Get-Date -Format "yyyyMMdd_HHmmss"
    $proofDir = Join-Path $ProjectRoot "output_data\proof_$runId"
    New-Item -ItemType Directory -Path $proofDir -Force | Out-Null

    $jmxPath = Join-Path $proofDir "mq_publish_proof.jmx"
    $jtlPath = Join-Path $proofDir "jmeter_result.jtl"
    $reportDir = Join-Path $proofDir "jmeter_report"
    $monitorCsv = Join-Path $proofDir "autoscale_monitor.csv"
    $autoscalerLog = Join-Path $proofDir "autoscaler.log"
    $summaryMd = Join-Path $proofDir "PROOF_SUMMARY.md"

    Write-Step "Build publish payload with valid HMAC"
    $payloadObj = [ordered]@{
        user_id = "proof_user"
        device_id = "proofdevice01"
        timestamp = "2026-04-16T08:00:00"
        behavior = "walking"
        heart_rate = 88.1
        resp_rate = 18.3
        temperature = 38.4
        steps = 120
        battery = 100
        gps_lat = 29.57
        gps_lng = 106.45
        event = $null
        event_phase = $null
    }

    $payloadJson = $payloadObj | ConvertTo-Json -Compress

    $hmac = [System.Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($HmacKey))
    try {
        $hashBytes = $hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($payloadJson))
    }
    finally {
        $hmac.Dispose()
    }
    $signature = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })

    $publishObj = [ordered]@{
        properties = [ordered]@{
            delivery_mode = 2
            headers = [ordered]@{
                Authorization = "Bearer $ApiKey"
                "X-Signature" = $signature
            }
        }
        routing_key = $QueueName
        payload = $payloadJson
        payload_encoding = "string"
    }
    $publishJson = $publishObj | ConvertTo-Json -Compress

    # XML escape for JMX body block
    $publishEscaped = $publishJson.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;")

    Write-Step "Generate JMeter plan"
    $jmx = @"
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="MQ Publish Proof Plan" enabled="true">
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>
      <stringProp name="TestPlan.comments">Auto generated proof plan</stringProp>
    </TestPlan>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Burst Load" enabled="true">
        <stringProp name="ThreadGroup.num_threads">$JMeterThreads</stringProp>
        <stringProp name="ThreadGroup.ramp_time">5</stringProp>
        <boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp>
        <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
          <stringProp name="LoopController.loops">$JMeterLoops</stringProp>
          <boolProp name="LoopController.continue_forever">false</boolProp>
        </elementProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Publish to RabbitMQ" enabled="true">
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
            <collectionProp name="Arguments.arguments">
              <elementProp name="" elementType="HTTPArgument">
                <boolProp name="HTTPArgument.always_encode">false</boolProp>
                <stringProp name="Argument.value">$publishEscaped</stringProp>
                <stringProp name="Argument.metadata">=</stringProp>
              </elementProp>
            </collectionProp>
          </elementProp>
          <stringProp name="HTTPSampler.domain">127.0.0.1</stringProp>
          <stringProp name="HTTPSampler.port">15672</stringProp>
          <stringProp name="HTTPSampler.protocol">http</stringProp>
          <stringProp name="HTTPSampler.path">/api/exchanges/%2F/amq.default/publish</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
          <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
          <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
          <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
          <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
          <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
        </HTTPSamplerProxy>
        <hashTree>
          <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Headers" enabled="true">
            <collectionProp name="HeaderManager.headers">
              <elementProp name="Content-Type" elementType="Header">
                <stringProp name="Header.name">Content-Type</stringProp>
                <stringProp name="Header.value">application/json</stringProp>
              </elementProp>
              <elementProp name="Authorization" elementType="Header">
                <stringProp name="Header.name">Authorization</stringProp>
                <stringProp name="Header.value">Basic Z3Vlc3Q6Z3Vlc3Q=</stringProp>
              </elementProp>
            </collectionProp>
          </HeaderManager>
          <hashTree/>
        </hashTree>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"@
    [IO.File]::WriteAllText($jmxPath, $jmx, [Text.UTF8Encoding]::new($false))

    Write-Step "Start docker services"
    docker compose up -d rabbitmq mongodb flask-server mq-worker engine | Out-Host

    Write-Step "Start autoscaler background job"
    $autoscalerJob = Start-Job -ScriptBlock {
      param(
        [string]$root,
        [string]$py,
        [string]$queue,
        [int]$minR,
        [int]$maxR,
        [int]$targetPer,
        [int]$pollSec,
        [int]$coolSec,
        [string]$logPath
      )
      Set-Location $root
      & $py .\scripts\mq_autoscaler.py --compose-file .\docker-compose.yml --service mq-worker --queue $queue --min-replicas $minR --max-replicas $maxR --target-messages-per-worker $targetPer --poll-interval $pollSec --cooldown $coolSec 2>&1 |
        Tee-Object -FilePath $logPath -Append
    } -ArgumentList $ProjectRoot, $PythonExe, $QueueName, $MinReplicas, $MaxReplicas, $TargetMessagesPerWorker, $PollIntervalSec, $CooldownSec, $autoscalerLog

    Write-Step "Start monitor background job"
    $monitorJob = Start-Job -ScriptBlock {
      param(
        [string]$root,
        [string]$queue,
        [int]$durationSec,
        [string]$csvPath
      )
      Set-Location $root
      "timestamp,workers,messages_ready,messages_unack" | Out-File -FilePath $csvPath -Encoding utf8
      $endTime = (Get-Date).AddSeconds($durationSec)
      while ((Get-Date) -lt $endTime) {
        $t = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $workers = (docker compose -f .\docker-compose.yml ps mq-worker --status running -q | Measure-Object).Count
        $line = docker exec petnode-rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged | Select-String $queue
        $ready = 0
        $unack = 0
        if ($line) {
          $parts = (($line.ToString() -replace "\s+", " ").Trim().Split(" "))
          if ($parts.Count -ge 3) {
            $ready = [int]$parts[1]
            $unack = [int]$parts[2]
          }
        }
        "$t,$workers,$ready,$unack" | Out-File -FilePath $csvPath -Append -Encoding utf8
        Start-Sleep -Seconds 2
      }
    } -ArgumentList $ProjectRoot, $QueueName, $MonitorDurationSec, $monitorCsv

    Write-Step "Run JMeter load test"
    if (Test-Path $reportDir) {
        Remove-Item -Recurse -Force $reportDir
    }
    & $JMeterBat -n -t $jmxPath -l $jtlPath -e -o $reportDir | Out-Host

    Write-Info "JMeter completed. Waiting monitor to finish..."
    Wait-Job -Id $monitorJob.Id | Out-Null

    Write-Step "Stop autoscaler background job"
    Stop-Job -Id $autoscalerJob.Id -ErrorAction SilentlyContinue | Out-Null
    Receive-Job -Id $autoscalerJob.Id -Keep -ErrorAction SilentlyContinue | Out-Null

    Write-Step "Build summary"
    $rows = Import-Csv $jtlPath
    $total = $rows.Count
    $ok = ($rows | Where-Object { $_.success -eq "true" }).Count
    $err = $total - $ok
    $avg = if ($total -gt 0) { [Math]::Round((($rows | Measure-Object -Property elapsed -Average).Average), 2) } else { 0 }
    $p95 = if ($total -gt 0) { Get-P95 (($rows | ForEach-Object { [int]$_.elapsed })) } else { 0 }

    $mRows = Import-Csv $monitorCsv
    $maxWorkers = if ($mRows.Count -gt 0) { ($mRows | Measure-Object -Property workers -Maximum).Maximum } else { 0 }
    $maxReady = if ($mRows.Count -gt 0) { ($mRows | Measure-Object -Property messages_ready -Maximum).Maximum } else { 0 }
    $maxUnack = if ($mRows.Count -gt 0) { ($mRows | Measure-Object -Property messages_unack -Maximum).Maximum } else { 0 }

    $proof = @"
# AutoScale Proof Summary

## Run
- run_id: $runId
- proof_dir: $proofDir

## JMeter
- total_requests: $total
- success_requests: $ok
- error_requests: $err
- avg_elapsed_ms: $avg
- p95_elapsed_ms: $p95

## AutoScale Evidence
- max_workers: $maxWorkers
- max_messages_ready: $maxReady
- max_messages_unack: $maxUnack

## Files
- JMeter JTL: $jtlPath
- JMeter Report: $reportDir
- Monitor CSV: $monitorCsv
- AutoScaler Log: $autoscalerLog

## Pass Criteria
1. Scale-up observed: max_workers > $MinReplicas
2. Queue pressure observed: max_messages_ready or max_messages_unack > 0
3. High request success: success rate >= 95%
"@
    [IO.File]::WriteAllText($summaryMd, $proof, [Text.UTF8Encoding]::new($false))

    Write-Step "Done"
    Write-Host "Summary: $summaryMd" -ForegroundColor Yellow
    Write-Host "Report : $reportDir\\index.html" -ForegroundColor Yellow
}
finally {
    Pop-Location
}
