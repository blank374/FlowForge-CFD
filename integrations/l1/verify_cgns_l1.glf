package require PWI_Glyph
pw::Application reset
set path [lindex $argv 0]
if {![file exists $path]} { puts stderr "CGNS_VERIFY_ERROR=missing"; exit 2 }
if {[catch {set imported [pw::Grid import -type CGNS-UNSTR -format Binary $path]} err opts]} {
    puts stderr "CGNS_VERIFY_ERROR=$err"
    puts stderr "CGNS_VERIFY_TRACE=[dict get $opts -errorinfo]"
    exit 1
}
set blocks [pw::Grid getAll -type pw::BlockUnstructured]
puts "CGNS_IMPORT_RETURN_COUNT=[llength $imported]"
puts "CGNS_BLOCK_COUNT=[llength $blocks]"
puts "CGNS_TET_COUNT=[pw::Grid getElementCount Tet]"
puts "CGNS_PRISM_COUNT=[pw::Grid getElementCount Prism]"
set cells 0
foreach block $blocks { incr cells [$block getCellCount] }
puts "CGNS_BLOCK_CELL_COUNT=$cells"
if {[llength $blocks] != 1 || $cells < 100 || [pw::Grid getElementCount Tet] < 1} { puts stderr "CGNS_VERIFY_ERROR=volume block content missing"; exit 1 }
puts "CGNS_VERIFY_STATUS=ok"
exit 0
