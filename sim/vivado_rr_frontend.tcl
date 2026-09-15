read_verilog {rtl/peak_detect.v rtl/sqi.v rtl/window_acc.v rtl/rr_frontend.v}
synth_design -top rr_frontend -part xc7a35tcpg236-1 -mode out_of_context
create_clock -period 83.333 -name clk [get_ports clk]
opt_design
place_design
route_design
report_utilization -file sim/reports/rr_frontend_util.rpt
report_timing_summary -file sim/reports/rr_frontend_timing.rpt
report_power -file sim/reports/rr_frontend_power.rpt
puts "RR_SYNTH_OK"
