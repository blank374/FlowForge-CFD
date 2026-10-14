package require PWI_Glyph
pw::Application reset
pw::Application load [lindex $argv 0]
pw::Application setCAESolver OpenFOAM 3
set far [pw::BoundaryCondition getByName L1_FARFIELD]
set un [pw::BoundaryCondition getByName Unspecified]
puts "FAR_REGISTERS=[$far getRegisters]"
puts "UN_REGISTERS=[$un getRegisters]"
puts "UN_FREE=[$un getFreeEntities]"
puts "FAR_FREE=[$far getFreeEntities]"
foreach command [list [list $far help] [list $far apply] [list $un remove] [list $un unapply]] {
    puts "PROBE=$command:[catch {eval $command} output]:$output"
}
exit 0
