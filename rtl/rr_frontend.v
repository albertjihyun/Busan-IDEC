// 봉우리 검출 → SQI → 5초 누산을 묶은 것. 하드웨어 팀 블록의 참조 구현.
// 입력은 AFE 를 지난 0 중심 샘플, 출력은 datapath-request.md 3절의 재료 5개 × 2창.

`timescale 1ns/1ps
`default_nettype none
module rr_frontend (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               i_valid,
    input  wire signed [15:0] i_sample,
    // 디버그·검증용
    output wire               o_peak,
    output wire [4:0]         o_peak_delay,
    output wire               o_rr_valid,
    output wire [9:0]         o_rr,
    output wire               o_rr_ok,
    // 재료
    output wire               o_win_valid,
    output wire [7:0]         o_n30,
    output wire [16:0]        o_sum_rr30,
    output wire [24:0]        o_sum_rr2_30,
    output wire signed [16:0] o_sum_d30,
    output wire [23:0]        o_sum_d2_30,
    output wire [7:0]         o_n60,
    output wire [16:0]        o_sum_rr60,
    output wire [24:0]        o_sum_rr2_60,
    output wire signed [16:0] o_sum_d60,
    output wire [23:0]        o_sum_d2_60
);
    // peak_detect 는 i_valid 클럭에 등록 출력을 내므로 o_peak 는 한 클럭 뒤에 뜬다.
    // sqi 와 window_acc 에는 같은 클럭에 맞춘 valid 를 준다.
    reg valid_d;
    always @(posedge clk) valid_d <= rst_n & i_valid;

    peak_detect u_pk (
        .clk(clk), .rst_n(rst_n), .i_valid(i_valid), .i_sample(i_sample),
        .o_peak(o_peak), .o_delay(o_peak_delay)
    );
    sqi u_sqi (
        .clk(clk), .rst_n(rst_n), .i_valid(valid_d), .i_peak(o_peak), .i_delay(o_peak_delay),
        .o_rr_valid(o_rr_valid), .o_rr(o_rr), .o_ok(o_rr_ok)
    );
    reg valid_dd;
    always @(posedge clk) valid_dd <= rst_n & valid_d;
    window_acc u_acc (
        .clk(clk), .rst_n(rst_n), .i_valid(valid_dd), .i_rr_valid(o_rr_valid), .i_rr(o_rr), .i_ok(o_rr_ok),
        .o_win_valid(o_win_valid),
        .o_n30(o_n30), .o_sum_rr30(o_sum_rr30), .o_sum_rr2_30(o_sum_rr2_30), .o_sum_d30(o_sum_d30), .o_sum_d2_30(o_sum_d2_30),
        .o_n60(o_n60), .o_sum_rr60(o_sum_rr60), .o_sum_rr2_60(o_sum_rr2_60), .o_sum_d60(o_sum_d60), .o_sum_d2_60(o_sum_d2_60)
    );
endmodule
`default_nettype wire
