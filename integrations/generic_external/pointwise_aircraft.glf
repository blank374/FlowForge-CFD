# Build and quality-check a spherical external flow volume from the ANSA STL.
package require PWI_Glyph
pw::Application reset

if {[llength $argv] < 2} {
    puts stderr "GENERIC_ERROR=usage: pointwise_l1.glf input.stl output_dir"
    exit 2
}
set stl [lindex $argv 0]
set outDir [lindex $argv 1]
set project [file join $outDir aircraft_volume.pw]
set cgns [file join $outDir aircraft_volume.cgns]
if {![file exists $stl] || [file exists $project] || [file exists $cgns]} {
    puts stderr "GENERIC_ERROR=STL missing or Pointwise output already exists"
    exit 3
}

if {[catch {
    set gridImported [pw::Grid import -type STL $stl]
    set dbImported [pw::Database import -type STL $stl]
    set domains [pw::Grid getAll -type pw::DomainUnstructured]
    puts "GRID_IMPORT_COUNT=[llength $gridImported]"
    puts "DATABASE_IMPORT_COUNT=[llength $dbImported]"
    puts "SURFACE_DOMAIN_COUNT=[llength $domains]"
    if {[llength $gridImported] < 1 || [llength $dbImported] < 1 || [llength $domains] < 1} {
        error "Expected imported surface domains and STL database"
    }
    set wallDomains $domains
    set beforeExtentList {}
    set aircraftExtent {}
    set surfaceCells 0
    set domainOrdinal 0
    foreach wall $wallDomains {
        incr domainOrdinal
        $wall setName "AIRCRAFT_SURFACE_$domainOrdinal"
        set ext [$wall getExtents]
        lappend beforeExtentList $ext
        if {$aircraftExtent eq ""} { set aircraftExtent $ext }
        set surfaceCells [expr {$surfaceCells + [$wall getCellCount]}]
        puts "ANSA_SURFACE_DOMAIN_$domainOrdinal=[list [$wall getName] [$wall getCellCount] $ext]"
    }
    if {$surfaceCells < 5000} { error "ANSA surface grid unexpectedly coarse" }
    puts "ANSA_SURFACE_CELLS=$surfaceCells"
    puts "DATABASE_COUNT=[llength $dbImported]"
    if {[llength $dbImported] < 1} { error "No STL surface database created" }
    foreach wall $wallDomains { $wall project -type ClosestPoint $dbImported }
    set databaseLinks 0
    foreach wall $wallDomains { incr databaseLinks [llength [$wall getDatabaseEntities]] }
    puts "DATABASE_LINK_COUNT=$databaseLinks"
    if {$databaseLinks < 1} { error "Surface projection did not constrain domains to database" }

    set surfaceExam [pw::Examine create DomainCellIntersection]
    $surfaceExam addEntity $wallDomains
    $surfaceExam examine
    set intersectionCount [$surfaceExam getCategoryCount Intersected]
    puts "SURFACE_INTERSECTIONS=$intersectionCount"
    if {$intersectionCount != 0} { error "Surface self-intersection gate failed" }

    pw::Application setCAESolver OpenFOAM 3
    puts "CAE_SOLVER=[pw::Application getCAESolver]"
    puts "CAE_BC_TYPES=[pw::BoundaryCondition getPhysicalTypes -usage CAE]"
    set wallBC [pw::BoundaryCondition create]
    $wallBC setName AIRCRAFT_WALL
    $wallBC setId 1
    $wallBC setPhysicalType wall
    $wallBC apply $wallDomains
    foreach wall $wallDomains { puts "WALL_BC=[$wall getName]:[[$wall getAutomaticBoundaryCondition] getName]" }

    # Pointwise 2024.1 active TRexCondition does not expose max-layer control.
    # Configure layer count on the resulting block after VolumeMesher creates it.
    set wallTrex [pw::TRexCondition create]
    $wallTrex setName AIRCRAFT_WALL_LAYER
    $wallTrex setConditionType Wall
    $wallTrex setGrowthRate 1.2
    $wallTrex setGrowthWallSpacing 2.0
    $wallTrex apply $wallDomains
    puts "WALL_TREX_TYPE=[$wallTrex getConditionType]"
    puts "WALL_TREX_INITIAL_SPACING=[$wallTrex getGrowthWallSpacing]"

    # External flow domain dimensions are based on the measured aircraft bounds.
    # The initial template uses a 6 m spherical farfield for a 1.51 m aircraft.
    set vm [pw::Application begin VolumeMesher $wallDomains]
    $vm setMeshType Unstructured
    $vm setFarfieldShapeType Sphere
    $vm setFarfieldRadius 6000.0
    $vm setFarfieldCenter {0.0 0.0 0.0}
    $vm setSizeFieldBackgroundSpacing 500.0
    $vm setBoundaryLayerType GeometricGrowth
    $vm setWallNormalSpacing 2.0
    $vm setGrowthRate 1.2
    $vm setBoundaryConditionFilterType "Boundary Layer" Wall
    $vm setBoundaryConditionFilterValue "Boundary Layer" 2.0
    puts "BL_FILTER_GROUP_COUNT=[llength [$vm getBoundaryConditionFilterGroups "Boundary Layer"]]"
    puts "BL_FILTER_TYPE=[$vm getBoundaryConditionFilterType "Boundary Layer"]"
    set created [$vm createGridEntities]
    $vm end
    puts "VOLUME_CREATED_COUNT=[llength $created]"

    set allDomains [pw::Grid getAll -type pw::DomainUnstructured]
    set farfieldDomains {}
    foreach domain $allDomains {
        if {[lsearch -exact $wallDomains $domain] < 0} { lappend farfieldDomains $domain }
    }
    if {[llength $farfieldDomains] < 1} { error "VolumeMesher created no farfield boundary domains" }
    set farBC [pw::BoundaryCondition create]
    $farBC setName FARFIELD
    $farBC setId 2
    $farBC setPhysicalType patch
    $farBC apply $farfieldDomains
    puts "FARFIELD_DOMAIN_COUNT=[llength $farfieldDomains]"
    puts "FARFIELD_BC=[$farBC getName]"
    set boundaryDomainCount [llength $allDomains]
    puts "BOUNDARY_DOMAIN_COUNT=$boundaryDomainCount"
    puts "WALL_BOUNDARY_DOMAIN_COUNT=[llength $wallDomains]"
    foreach domain $farfieldDomains {
        if {[[$domain getAutomaticBoundaryCondition] getName] ne "FARFIELD"} { error "Farfield boundary assignment incomplete" }
    }
    foreach domain $wallDomains {
        if {[[$domain getAutomaticBoundaryCondition] getName] ne "AIRCRAFT_WALL"} { error "Wall boundary assignment incomplete" }
    }
    if {$boundaryDomainCount != [llength $wallDomains] + [llength $farfieldDomains]} {
        error "One or more boundary domains are not labelled"
    }
    puts "BOUNDARY_LABELS_COMPLETE=1"

    set blocks [pw::Grid getAll -type pw::BlockUnstructured]
    if {[llength $blocks] != 1} { error "Expected one unstructured fluid block" }
    set block [lindex $blocks 0]
    $block setUnstructuredSolverAttribute TRexMaximumLayers 3
    $block setUnstructuredSolverAttribute TRexFullLayers 1
    $block setUnstructuredSolverAttribute TRexGrowthRate 1.2
    puts "BLOCK_BEFORE_CELLS=[$block getCellCount]"

    set solver [pw::Application begin UnstructuredSolver $blocks]
    $solver run Initialize
    $solver end
    puts "BLOCK_AFTER_CELLS=[$block getCellCount]"
    puts "BLOCK_EXTENTS=[$block getExtents]"
    puts "TET_COUNT=[pw::Grid getElementCount Tet]"
    puts "PRISM_COUNT=[pw::Grid getElementCount Prism]"
    puts "PYRAMID_COUNT=[pw::Grid getElementCount Pyramid]"
    puts "HEX_COUNT=[pw::Grid getElementCount Hex]"
    puts "BOUNDARY_LAYER_TYPE=GeometricGrowth"
    puts "BOUNDARY_LAYER_INITIAL_SPACING=2.0"

    set jacobianExam [pw::Examine create BlockJacobian]
    $jacobianExam addEntity $blocks
    $jacobianExam examine
    set negativeCount [$jacobianExam getCategoryCount Negative]
    set zeroCount [$jacobianExam getCategoryCount Zero]
    puts "JACOBIAN_NEGATIVE_COUNT=$negativeCount"
    puts "JACOBIAN_ZERO_COUNT=$zeroCount"
    puts "JACOBIAN_MIN=[$jacobianExam getMinimum]"
    if {$negativeCount != 0 || $zeroCount != 0} { error "Negative or zero-volume cells found" }

    set skewExam [pw::Examine create BlockFidelitySkewEquiangle]
    $skewExam addEntity $blocks
    $skewExam examine
    set skewMin [$skewExam getMinimum]
    set skewMax [$skewExam getMaximum]
    set skewAvg [$skewExam getAverage]
    puts "SKEW_EQUIANGLE_MIN=$skewMin"
    puts "SKEW_EQUIANGLE_MAX=$skewMax"
    puts "SKEW_EQUIANGLE_AVG=$skewAvg"
    if {$skewMax >= 1.0} { error "Worst equiangle skew reaches degenerate limit" }

    set afterExtentList {}
    set surfaceCellsAfter 0
    foreach wall $wallDomains {
        lappend afterExtentList [$wall getExtents]
        set surfaceCellsAfter [expr {$surfaceCellsAfter + [$wall getCellCount]}]
    }
    puts "SURFACE_EXTENTS_AFTER_VOLUME=$afterExtentList"
    if {$surfaceCellsAfter != $surfaceCells || $afterExtentList ne $beforeExtentList} {
        error "Volume mesher changed the imported three-dimensional body surface"
    }
    if {[$block getCellCount] < 100 || [pw::Grid getElementCount Tet] < 1} {
        error "Unstructured fluid volume contains too few cells"
    }
    # The volume solver creates block-face registers after the domain BCs were
    # assigned. Bind the farfield BC to those registers before saving the .pw.
    set unspecified [pw::BoundaryCondition getByName Unspecified]
    set farRegisters {}
    foreach register [$unspecified getRegisters] {
        if {[lsearch -exact $farfieldDomains [lindex $register 1]] >= 0} { lappend farRegisters $register }
    }
    if {[llength $farRegisters] != [llength $farfieldDomains]} { error "Farfield block-face registers are incomplete" }
    $farBC apply $farRegisters
    if {[llength [$farBC getRegisters]] != [llength $farfieldDomains]} { error "Farfield BC did not bind to volume boundary" }
    puts "FARFIELD_BOUNDARY_REGISTERS=[llength [$farBC getRegisters]]"
    pw::Application save $project
    pw::Grid export -type CGNS-UNSTR -format Binary $blocks $cgns
    if {![file exists $project] || ![file exists $cgns] || [file size $cgns] < 10000} {
        error "Pointwise project or volume mesh export missing"
    }
    puts "POINTWISE_PROJECT=$project"
    puts "POINTWISE_CGNS=$cgns"
    puts "CGNS_BYTES=[file size $cgns]"
    puts "GENERIC_POINTWISE_STATUS=ok"
} error options]} {
    puts stderr "GENERIC_POINTWISE_STATUS=error"
    puts stderr "GENERIC_POINTWISE_ERROR=$error"
    puts stderr "GENERIC_POINTWISE_TRACE=[dict get $options -errorinfo]"
    exit 1
}
exit 0
