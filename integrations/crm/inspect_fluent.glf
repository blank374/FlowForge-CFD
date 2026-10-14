package require PWI_Glyph
pw::Application reset
set source [lindex $argv 0]
puts "CRM_FLUENT_SOURCE=$source"
if {[catch {
    set imported [pw::Grid import -type "ANSYS Fluent" $source]
    set blocks [pw::Grid getAll -type pw::BlockUnstructured]
    set domains [pw::Grid getAll -type pw::DomainUnstructured]
    puts "CRM_IMPORT_ENTITIES=[llength $imported]"
    puts "CRM_BLOCKS=[llength $blocks]"
    puts "CRM_DOMAINS=[llength $domains]"
    foreach block $blocks {
        puts "CRM_BLOCK=[list [$block getName] [$block getCellCount] [$block getExtents]]"
    }
    foreach domain $domains {
        puts "CRM_DOMAIN=[list [$domain getName] [$domain getCellCount] [$domain getExtents]]"
    }
    puts "CRM_TETS=[pw::Grid getElementCount Tet]"
    puts "CRM_PRISMS=[pw::Grid getElementCount Prism]"
    puts "CRM_HEXES=[pw::Grid getElementCount Hex]"
    puts "CRM_PYRAMIDS=[pw::Grid getElementCount Pyramid]"
    set jacobianExam [pw::Examine create BlockJacobian]
    $jacobianExam addEntity $blocks
    $jacobianExam examine
    puts "CRM_NEGATIVE_JACOBIAN=[$jacobianExam getCategoryCount Negative]"
    puts "CRM_ZERO_JACOBIAN=[$jacobianExam getCategoryCount Zero]"
    puts "CRM_MIN_JACOBIAN=[$jacobianExam getMinimum]"
    set skewExam [pw::Examine create BlockFidelitySkewEquiangle]
    $skewExam addEntity $blocks
    $skewExam examine
    puts "CRM_MAX_EQUIANGLE_SKEW=[$skewExam getMaximum]"
    puts "CRM_IMPORT_OK=1"
} message opts]} {
    puts stderr "CRM_IMPORT_ERROR=$message"
    puts stderr "CRM_IMPORT_TRACE=[dict get $opts -errorinfo]"
    exit 1
}
exit 0
