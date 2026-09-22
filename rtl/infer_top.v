// 추론 최상위. 준용 블록(rr_frontend)의 창 합을 받아 판정하고 UART 로 넘길 경보 펄스 하나를 만든다.
// 인터페이스는 docs/datapath-request.md ⑧ 절. 9/22 에 출력을 drowsy/hold/head_nod/changed 넷에서 alert 하나로 바꿨다.
//
//   alert : 1클럭 펄스. 5초 판정이 졸림이고 보류 사유가 없을 때 1회, 고개 떨굼이 잡힌 순간 1회.
//           UART 는 이 펄스마다 바이트 하나를 보낸다. 상태는 밖으로 안 낸다.
//   ready : 기준선 확정됨. 보드 LED 등 상태 표시용. UART 로는 안 나간다.
//
// IMU 쪽(m_nod, m_busy)은 6단계 전까지 0 으로 묶는다. combine 논리는 alert 한 줄이 전부다.

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
    output reg         alert,
    output wire        ready
);
    wire c_valid, c_hold, c_drowsy;

    classifier #(.T_FIX(T_FIX), .FRAC(FRAC)) u_cls (
        .clk(clk), .rst_n(rst_n),
        .i_win_valid(i_win_valid), .i_n60(i_n60), .i_sum_rr60(i_sum_rr60),
        .o_valid(c_valid), .o_hold(c_hold), .o_drowsy(c_drowsy), .o_ready(ready)
    );

    // imu_rule 자리 (6단계). m_nod: 떨굼 펄스, m_busy: 움직임 과다 상태
    wire m_nod  = 1'b0;
    wire m_busy = 1'b0;

    // combine: 판정 갱신 클럭에 졸림이고 보류 아니면 1펄스, 떨굼은 그 순간 1펄스
    always @(posedge clk) begin
        if (!rst_n)
            alert <= 1'b0;
        else
            alert <= (c_valid & c_drowsy & ~c_hold & ~m_busy) | m_nod;
    end
endmodule
`default_nettype wire
