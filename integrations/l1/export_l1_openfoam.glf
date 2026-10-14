package require PWI_Glyph
if {[llength $argv] != 2} { error "usage: export_l1_openfoam.glf source.pw output_dir" }
set source [file normalize [lindex $argv 0]]
set outDir [file normalize [lindex $argv 1]]
if {![file isfile $source]} { error "Pointwise source project missing: $source" }
file mkdir $outDir
pw::Application reset
pw::Application load $source
pw::Application setCAESolver OpenFOAM 3
set domains [pw::Grid getAll -type pw::DomainUnstructured]
set wallDomains {}
set farDomains {}
foreach domain $domains {
    if {[string match "L1_SPHERE_WALL_*" [$domain getName]]} {
        lappend wallDomains $domain
    } else {
        lappend farDomains $domain
    }
}
if {[llength $wallDomains] < 1 || [llength $farDomains] < 1} { error "Cannot identify L1 wall and farfield domains" }
set farBC [pw::BoundaryCondition getByName L1_FARFIELD]
if {$farBC eq ""} { error "Saved Pointwise project lacks L1_FARFIELD boundary condition" }
$farBC setPhysicalType patch
set unspecified [pw::BoundaryCondition getByName Unspecified]
if {[llength [$farBC getRegisters]] == 0} {
    set farRegisters {}
    foreach register [$unspecified getRegisters] {
        if {[lsearch -exact $farDomains [lindex $register 1]] >= 0} { lappend farRegisters $register }
    }
    if {[llength $farRegisters] != [llength $farDomains]} { error "Cannot map all farfield block-face registers" }
    $farBC apply $farRegisters
}
if {[llength [$farBC getRegisters]] != [llength $farDomains]} { error "Farfield BC registers were not assigned" }
puts "FARFIELD_BOUNDARY_REGISTERS=[llength [$farBC getRegisters]]"
puts "UNSPECIFIED_BOUNDARY_REGISTERS=[llength [$unspecified getRegisters]]"
set exportReady [file join [file dirname $outDir] l1_export_ready.pw]
pw::Application save $exportReady
puts "EXPORT_READY_PROJECT=$exportReady"
puts "WALL_DOMAINS=[llength $wallDomains] FARFIELD_DOMAINS=[llength $farDomains]"
puts "POINTWISE_VERSION=[pw::Application getVersion]"
puts "CAE_SOLVER=[pw::Application getCAESolver]"
puts "CAE_EXTENSIONS=[pw::Application getCAESolverAttribute FileExtensions]"
puts "CAE_DESTINATION=[pw::Application getCAESolverAttribute FileDestination]"
puts "CAE_FORMATS=[pw::Application getCAESolverAttribute AllowedFileFormats]"
set blocks [pw::Entity sort [pw::Grid getAll -type pw::Block]]
if {[llength $blocks] != 1} { error "Expected one volume block, found [llength $blocks]" }
set block [lindex $blocks 0]
puts "BLOCK_CELLS=[$block getCellCount]"
puts "BLOCK_EXTENTS=[$block getExtents]"
set result [pw::Application export -precision Double $blocks $outDir]
puts "EXPORT_RESULT=$result"
set files [glob -nocomplain -directory $outDir *]
foreach f $files { if {[file isfile $f]} { puts "EXPORTED_FILE=[file tail $f]:[file size $f]" } }
if {[llength $files] < 1} { error "OpenFOAM exporter produced no files" }
puts "OPENFOAM_EXPORT_STATUS=ok"
exit 0
