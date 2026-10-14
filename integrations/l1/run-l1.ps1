[CmdletBinding()]
param(
    [string]$AnsaBat = 'C:\Users\Lenovo1\AppData\Local\Apps\BETA_CAE_Systems\ansa_v20.1.6\ansa64.bat',
    [string]$PointwiseTcl = 'F:\Point\FidelityPointwise2024.1\win64\bin\tclsh.exe',
    [string]$Python = (Join-Path $PSScriptRoot '..\..\.venv\Scripts\python.exe'),
    [string]$RunDir,
    [string]$CadInput
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$fixtureDir = Join-Path $PSScriptRoot 'inputs\L1'
$fixture = if ($CadInput) { (Resolve-Path -LiteralPath $CadInput).Path } else { Join-Path $fixtureDir 'TEST_DATA_sphere_r10mm_v2.ansa' }
$runDir = if ($RunDir) { $RunDir } else { Join-Path (Join-Path $PSScriptRoot 'runs\L1') ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)) }
if (Test-Path -LiteralPath (Join-Path $runDir 'run_summary.json')) { throw "Refusing to overwrite existing run: $runDir" }
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$summaryPath = Join-Path $runDir 'run_summary.json'
$summary = [ordered]@{
    schema = 'ansa-pointwise-mvp/v0.1'
    level = 'L1'
    status = 'running'
    test_data = (-not [bool]$CadInput)
    fixture = $fixture
    run_dir = $runDir
    stages = @()
    geometry = $null
    surface_quality = $null
    volume_quality = $null
    error = $null
}
function Save-Summary { $summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $summaryPath -Encoding utf8 }
function Add-Stage([string]$Name, [string]$Status, [string]$Log, [string]$Report = $null, [int]$ExitCode = 0) {
    $summary.stages += [ordered]@{ name = $Name; status = $Status; log = $Log; report = $Report; exit_code = $ExitCode }
    Save-Summary
}

try {
    foreach ($tool in @($AnsaBat, $PointwiseTcl, $Python)) { if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Required tool not found: $tool" } }
    if ($CadInput -and ([IO.Path]::GetExtension($fixture).ToLowerInvariant() -notin @('.igs', '.iges'))) { throw 'L1 uploaded input must be IGES' }
    if ($CadInput -and -not (Test-Path -LiteralPath $fixture -PathType Leaf)) { throw 'Uploaded IGES missing' }
    if (-not $CadInput -and -not (Test-Path -LiteralPath $fixture -PathType Leaf)) {
        $env:ANSA_L1_ACTION = 'generate'; $env:ANSA_L1_OUTPUT_DIR = $runDir; $env:ANSA_L1_FIXTURE_DIR = $fixtureDir
        $generateScript = (Join-Path $PSScriptRoot 'ansa_l1.py').Replace('\', '/')
        $generateLog = Join-Path $runDir 'ansa_generate.log'
        & $AnsaBat -exec "load_script: '$generateScript'" -exec 'main()' -nogui *> $generateLog
        $ec = $LASTEXITCODE; $generateReportPath = Join-Path $runDir 'ansa_generate.json'
        if ($ec -ne 0 -or -not (Test-Path $generateReportPath) -or (Get-Content $generateReportPath -Raw | ConvertFrom-Json).status -ne 'ok') { Add-Stage 'ansa_test_geometry' 'failed' $generateLog $generateReportPath $ec; throw 'ANSA test sphere generation failed.' }
        Add-Stage 'ansa_test_geometry' 'passed' $generateLog $generateReportPath $ec
    } else {
        Add-Stage 'ansa_cad_input' $(if ($CadInput) { 'passed_uploaded_iges' } else { 'passed_existing_test_fixture' }) $null $fixture
    }

    $env:ANSA_L1_ACTION = 'mesh'; $env:ANSA_L1_OUTPUT_DIR = $runDir; $env:ANSA_L1_FIXTURE_DIR = $fixtureDir; $env:ANSA_L1_CAD_INPUT = $fixture
    $meshScript = (Join-Path $PSScriptRoot 'ansa_l1.py').Replace('\', '/')
    $ansaLog = Join-Path $runDir 'ansa_mesh.log'
    & $AnsaBat -exec "load_script: '$meshScript'" -exec 'main()' -nogui *> $ansaLog
    $ec = $LASTEXITCODE; $ansaReportPath = Join-Path $runDir 'ansa_mesh.json'
    if ($ec -ne 0 -or -not (Test-Path $ansaReportPath)) { Add-Stage 'ansa_surface_mesh' 'failed' $ansaLog $ansaReportPath $ec; throw 'ANSA surface mesh stage failed.' }
    $ansaReport = Get-Content $ansaReportPath -Raw | ConvertFrom-Json
    if ($ansaReport.status -ne 'ok') { Add-Stage 'ansa_surface_mesh' 'failed' $ansaLog $ansaReportPath $ec; throw 'ANSA did not report a valid surface mesh.' }
    Add-Stage 'ansa_surface_mesh' 'passed' $ansaLog $ansaReportPath $ec

    $stlPath = $ansaReport.stl
    $env:ANSA_STL_SOURCE = $stlPath; $env:ANSA_STL_REPORT = Join-Path $runDir 'ansa_surface_quality.json'
    $qualityLog = Join-Path $runDir 'ansa_surface_quality.log'
    & $Python (Join-Path $PSScriptRoot 'analyze_stl.py') *> $qualityLog
    $ec = $LASTEXITCODE; Remove-Item Env:ANSA_STL_SOURCE, Env:ANSA_STL_REPORT -ErrorAction SilentlyContinue
    $surfacePath = Join-Path $runDir 'ansa_surface_quality.json'
    if ($ec -ne 0 -or -not (Test-Path $surfacePath)) { Add-Stage 'surface_quality' 'failed' $qualityLog $surfacePath $ec; throw 'Surface quality analyzer failed.' }
    $surface = Get-Content $surfacePath -Raw | ConvertFrom-Json
    $dims = @(); for ($i=0; $i -lt 3; $i++) { $dims += [double]$surface.bounding_box_max_mm[$i] - [double]$surface.bounding_box_min_mm[$i] }
    $dimErrors = @($dims | ForEach-Object { [math]::Abs($_ - 20.0) / 20.0 })
    $sphereGate = ($surface.radius_min_mm -gt 9.7 -and $surface.radius_max_mm -lt 10.3 -and $surface.surface_area_mm2 -gt 1200 -and $surface.surface_area_mm2 -lt 1300 -and @($surface.radius_center_mm | Where-Object { [math]::Abs($_) -gt 0.5 }).Count -eq 0)
    $summary.geometry = [ordered]@{ nominal_sphere_diameter_mm = 20.0; measured_surface_dimensions_mm = $dims; relative_dimension_error = $dimErrors; surface_is_3d = (@($dims | Where-Object { $_ -gt 0.1 }).Count -eq 3); dimension_gate = (@($dimErrors | Where-Object { $_ -gt 0.01 }).Count -eq 0); sphere_gate = $sphereGate; radius_min_mm = $surface.radius_min_mm; radius_mean_mm = $surface.radius_mean_mm; radius_max_mm = $surface.radius_max_mm; surface_area_mm2 = $surface.surface_area_mm2 }
    $summary.surface_quality = [ordered]@{ facets = $surface.facets; connected_components = $surface.connected_components; boundary_edges = $surface.boundary_edges; nonmanifold_edges = $surface.nonmanifold_edges; degenerate_facets = $surface.degenerate_facets; self_intersections_pointwise = $null }
    if (-not $summary.geometry.surface_is_3d -or -not $summary.geometry.dimension_gate -or -not $sphereGate -or $surface.connected_components -ne 1 -or $surface.boundary_edges -ne 0 -or $surface.nonmanifold_edges -ne 0 -or $surface.degenerate_facets -ne 0) { Add-Stage 'surface_quality' 'failed' $qualityLog $surfacePath $ec; throw 'Sphere dimensions/topology quality gate failed.' }
    Add-Stage 'surface_quality' 'passed' $qualityLog $surfacePath $ec

    $pointwiseLog = Join-Path $runDir 'pointwise.log'
    $glf = Join-Path $PSScriptRoot 'pointwise_l1.glf'
    & $PointwiseTcl $glf.Replace('\','/') $stlPath.Replace('\','/') $runDir.Replace('\','/') *> $pointwiseLog
    $ec = $LASTEXITCODE
    if ($ec -ne 0) { Add-Stage 'pointwise_volume_mesh' 'failed' $pointwiseLog $null $ec; throw 'Pointwise volume generation/quality checks failed.' }
    $pwText = Get-Content $pointwiseLog -Raw
    foreach ($required in @('SURFACE_INTERSECTIONS=0','JACOBIAN_NEGATIVE_COUNT=0','JACOBIAN_ZERO_COUNT=0','L1_POINTWISE_STATUS=ok')) { if (-not $pwText.Contains($required)) { throw "Pointwise quality marker missing: $required" } }
    function Read-Metric([string]$Name) { $m = [regex]::Match($pwText, '(?m)^' + [regex]::Escape($Name) + '=([^\r\n]+)'); if (-not $m.Success) { throw "Pointwise metric missing: $Name" }; return $m.Groups[1].Value.Trim() }
    $cellCount = [int](Read-Metric 'BLOCK_AFTER_CELLS'); $tetCount = [int](Read-Metric 'TET_COUNT'); $prismCount = [int](Read-Metric 'PRISM_COUNT')
    $jacMin = [double](Read-Metric 'JACOBIAN_MIN'); $skewMax = [double](Read-Metric 'SKEW_EQUIANGLE_MAX')
    $domainNumbers = @([regex]::Matches((Read-Metric 'BLOCK_EXTENTS'), '-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?') | ForEach-Object { [double]$_.Value })
    if ($domainNumbers.Count -ne 6) { throw 'Could not read all six Pointwise fluid-domain extents.' }
    $domainDims = @(); for ($i=0; $i -lt 3; $i++) { $domainDims += $domainNumbers[$i + 3] - $domainNumbers[$i] }
    if (@($domainDims | Where-Object { $_ -gt 20.0 }).Count -ne 3) { throw 'Pointwise fluid volume is not three-dimensional or does not enclose the 20 mm sphere.' }
    $boundaryCount = [int](Read-Metric 'BOUNDARY_DOMAIN_COUNT')
    if ((Read-Metric 'BOUNDARY_LABELS_COMPLETE') -ne '1' -or $boundaryCount -ne ([int](Read-Metric 'WALL_BOUNDARY_DOMAIN_COUNT') + [int](Read-Metric 'FARFIELD_DOMAIN_COUNT'))) { throw 'Pointwise boundary labels are incomplete.' }
    $summary.surface_quality.self_intersections_pointwise = [int](Read-Metric 'SURFACE_INTERSECTIONS')
    $cgnsPath = (Read-Metric 'POINTWISE_CGNS').Replace('/', '\'); $cgnsBytes = [IO.File]::ReadAllBytes($cgnsPath)
    if ($cgnsBytes.Length -lt 10000 -or [Convert]::ToHexString($cgnsBytes[0..7]) -ne '894844460D0A1A0A') { throw 'CGNS output missing, truncated, or not an HDF5 CGNS file.' }
    $summary.geometry.fluid_domain_dimensions_mm = $domainDims
    $summary.geometry.fluid_domain_is_3d = $true
    $summary.surface_quality.boundary_domain_count = $boundaryCount
    $summary.surface_quality.wall_boundary_domains = [int](Read-Metric 'WALL_BOUNDARY_DOMAIN_COUNT')
    $summary.surface_quality.farfield_boundary_domains = [int](Read-Metric 'FARFIELD_DOMAIN_COUNT')
    $summary.surface_quality.boundary_labels_complete = $true
    $summary.volume_quality = [ordered]@{ status = 'passed'; pointwise_project = (Read-Metric 'POINTWISE_PROJECT'); cgns_volume_mesh = $cgnsPath; cgns_container = 'HDF5 signature verified'; cgns_bytes = $cgnsBytes.Length; fluid_domain_dimensions_mm = $domainDims; volume_cells = $cellCount; tetrahedra = $tetCount; prisms = $prismCount; negative_jacobian_cells = [int](Read-Metric 'JACOBIAN_NEGATIVE_COUNT'); zero_jacobian_cells = [int](Read-Metric 'JACOBIAN_ZERO_COUNT'); minimum_jacobian = $jacMin; maximum_equiangle_skew = $skewMax; boundary_layer = [ordered]@{ type = 'GeometricGrowth'; initial_spacing_mm = [double](Read-Metric 'BOUNDARY_LAYER_INITIAL_SPACING'); generated_prism_cells = $prismCount } }
    if ($cellCount -lt 100 -or $tetCount -lt 1 -or $prismCount -lt 1 -or $jacMin -le 0 -or $skewMax -ge 1 -or $summary.volume_quality.cgns_bytes -lt 10000) { throw 'Volume mesh quality gate failed.' }
    Add-Stage 'pointwise_volume_mesh' 'passed' $pointwiseLog $summary.volume_quality.cgns_volume_mesh $ec

    $verifyLog = Join-Path $runDir 'cgns_readback.log'
    & $PointwiseTcl (Join-Path $PSScriptRoot 'verify_cgns_l1.glf').Replace('\','/') $cgnsPath.Replace('\','/') *> $verifyLog
    $verifyExit = $LASTEXITCODE; $verifyText = Get-Content $verifyLog -Raw
    if ($verifyExit -ne 0 -or -not $verifyText.Contains('CGNS_VERIFY_STATUS=ok')) { Add-Stage 'cgns_readback' 'failed' $verifyLog $cgnsPath $verifyExit; throw 'Pointwise could not independently re-import the exported CGNS volume mesh.' }
    foreach ($metric in @(@('CGNS_BLOCK_CELL_COUNT',$cellCount),@('CGNS_TET_COUNT',$tetCount),@('CGNS_PRISM_COUNT',$prismCount))) {
        $m = [regex]::Match($verifyText, '(?m)^' + [regex]::Escape($metric[0]) + '=(\d+)')
        if (-not $m.Success -or [int]$m.Groups[1].Value -ne [int]$metric[1]) { throw "CGNS read-back mismatch: $($metric[0])" }
    }
    $summary.volume_quality.independent_pointwise_readback = 'passed'
    Add-Stage 'cgns_readback' 'passed' $verifyLog $cgnsPath $verifyExit
    $summary.status = 'passed'
} catch {
    $summary.status = 'failed'; $summary.error = $_.Exception.Message
} finally {
    $summary.finished_at = (Get-Date).ToString('o'); Save-Summary
}
Write-Output "LEVEL=L1 STATUS=$($summary.status)"
Write-Output "SUMMARY=$summaryPath"
if ($summary.status -ne 'passed') { Write-Error $summary.error; exit 1 }

