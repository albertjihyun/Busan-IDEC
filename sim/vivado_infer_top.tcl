# infer_top 합성·구현 (out-of-context). 실행:
#   vivado.bat -mode batch -nolog -nojournal -source sim/vivado_infer_top.tcl
# 한글이 든 경로에서 돌리면 Vivado 2026.1 이 RTL 정교화 직후 힙 손상(0xC0000374)으로 죽는다(9/20 확인).
# rtl/ 과 sim/ 을 C:/tmp 같은 ASCII 경로에 복사해서 돌리고 리포트만 가져온다. docs/hw-design.md 도구 절.
read_verilog {rtl/classifier.v rtl/imu_rule.v rtl/infer_top.v}
synth_design -top infer_top -part xc7a35tcpg236-1 -mode out_of_context
create_clock -period 83.333 -name clk [get_ports clk]
opt_design
place_design
route_design
report_utilization -file sim/reports/infer_top_util.rpt
report_timing_summary -file sim/reports/infer_top_timing.rpt
report_power -file sim/reports/infer_top_power.rpt
puts "INFER_SYNTH_OK"
