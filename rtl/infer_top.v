// 추론 최상위. 준용 블록(rr_frontend)의 창 합을 받아 판정하고 UART/BLE 제어로 넘길 신호를 만든다.
// 인터페이스는 docs/datapath-request.md "신호" 절. IMU(head_nod) 는 6단계까지 0 으로 묶는다.
//
//   drowsy  : 각성도 저하 판정. 5초마다 갱신. hold 면 0
//   hold    : 워밍업 중이거나 창 안 박동이 30개 미만 (신호 불량)
//   head_nod: 고개 떨굼. 아직 0
//   changed : 위 셋 중 하나라도 바뀐 클럭에 1펄스. UART 전송 트리거

`timescale 1ns/1ps
`default_nettype none
module infer_top #(
    parameter T_FIX = 1086,
    parameter FRAC  = 10
)(
    input  wire        clk,
    input  wire        rst_n,
    input  wire        i_win_valid,
    input  wire [7:0]  i_n60,
    input  wire [16:0] i_sum_rr60,
    output wire        drowsy,
    output wire        hold,
    output wire        head_nod,
    output reg         changed,
    output wire        ready           // 기준선 확정됨 (상태 표시용)
);
    wire c_valid, c_hold, c_drowsy;

    classifier #(.T_FIX(T_FIX), .FRAC(FRAC)) u_cls (
        .clk(clk), .rst_n(rst_n),
        .i_win_valid(i_win_valid), .i_n60(i_n60), .i_sum_rr60(i_sum_rr60),
        .o_valid(c_valid), .o_hold(c_hold), .o_drowsy(c_drowsy), .o_ready(ready)
    );

    assign drowsy   = c_drowsy;
    assign hold     = c_hold;
    assign head_nod = 1'b0;

    // 판정이 갱신된 클럭에 이전 값과 비교
    reg prev_drowsy, prev_hold;
    always @(posedge clk) begin
        changed <= 1'b0;
        if (!rst_n) begin
            prev_drowsy <= 1'b0;
            prev_hold   <= 1'b1;
        end else if (c_valid) begin
            prev_drowsy <= c_drowsy;
            prev_hold   <= c_hold;
            changed     <= (c_drowsy != prev_drowsy) || (c_hold != prev_hold);
        end
    end
endmodule
`default_nettype wire
