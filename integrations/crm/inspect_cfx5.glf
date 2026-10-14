package require PWI_Glyph
pw::Application reset
set source [lindex $argv 0]
puts "CFX5_SOURCE=$source"
if {[catch {set imported [pw::Grid import -type "ANSYS CFX" $source]} message opts]} {
    puts "CFX5_IMPORT_ERROR=$message"
    puts "CFX5_IMPORT_OPTIONS=$opts"
    exit 1
}
puts "CFX5_IMPORT_ENTITIES=[llength $imported]"
set blocks [pw::Grid getAll -type pw::BlockUnstructured]
set domains [pw::Grid getAll -type pw::DomainUnstructured]
puts "CFX5_BLOCKS=[llength $blocks]"
puts "CFX5_DOMAINS=[llength $domains]"
foreach block $blocks {
    puts "CFX5_BLOCK=[list [$block getName] [$block getCellCount] [$block getExtents]]"
}
foreach domain $domains {
    puts "CFX5_DOMAIN=[list [$domain getName] [$domain getCellCount] [$domain getExtents]]"
}
puts "CFX5_TETS=[pw::Grid getElementCount Tet]"
puts "CFX5_PRISMS=[pw::Grid getElementCount Prism]"
puts "CFX5_HEXES=[pw::Grid getElementCount Hex]"
set jacobianExam [pw::Examine create BlockJacobian]
$jacobianExam addEntity $blocks
$jacobianExam examine
puts "CFX5_NEGATIVE_JACOBIAN=[$jacobianExam getCategoryCount Negative]"
puts "CFX5_ZERO_JACOBIAN=[$jacobianExam getCategoryCount Zero]"
puts "CFX5_MIN_JACOBIAN=[$jacobianExam getMinimum]"
set skewExam [pw::Examine create BlockFidelitySkewEquiangle]
$skewExam addEntity $blocks
$skewExam examine
puts "CFX5_MAX_EQUIANGLE_SKEW=[$skewExam getMaximum]"
puts "CFX5_AVG_EQUIANGLE_SKEW=[$skewExam getAverage]"
puts "CFX5_IMPORT_OK=1"
exit 0
