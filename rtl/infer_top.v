// 추론 최상위. 준용 블록(ppg_soc_top)의 창 합과 IMU 신호를 받아 판정하고 UART 로 넘길 경보 펄스 하나를 만든다.
// 인터페이스는 docs/datapath-request.md ⑧ 절. 9/22 에 출력을 alert 하나로, 9/23 에 IMU 입력을 붙였다.
//
//   alert : 1클럭 펄스. 다음 셋 중 하나라도 있으면 1회.
//           - 5초 판정이 졸림이고 보류(워밍업·박동 부족) 아님            classifier
//           - 고개를 35° 넘게 숙인 채 0.5 s (숙인 채 있으면 5 s 마다)   imu_rule   (가속도, 자세)
//           - 준용 imu_feature 의 끄덕임(o_nod_event) / 떨군 채 유지(o_nod_sustained 상승 에지)   (자이로, 동작)
//           UART 는 이 펄스마다 바이트 하나를 보낸다. 상태는 밖으로 안 낸다.
//   ready : 기준선 확정됨. 보드 LED 등 상태 표시용.
//
// 떨굼은 심박과 무관하므로 워밍업·보류 중에도 울린다. 움직임 과다 보류(m_busy)는 넣지 않는다
// (docs/imu-rule-design.md 9절: 준용 SQI 의 모션 게이트가 이미 그 일을 한다).

`timescale 1ns/1ps
`default_nettype none
module infer_top #(
    parameter T_FIX = 1093,
    parameter FRAC  = 10
)(
    input  wire        clk,
    input  wire        rst_n,
    // 준용 → 5초 창 합
    input  wire        i_win_valid,
    input  wire [7:0]  i_n60,
    input  wire [16:0] i_sum_rr60,
    // 준용 → IMU 원시값 (o_accel_x/y/z, o_imu_valid, 100 Hz)
    input  wire        i_imu_valid,
    input  wire signed [15:0] i_accel_x,
    input  wire signed [15:0] i_accel_y,
    input  wire signed [15:0] i_accel_z,
    // 준용 imu_feature → 끄덕임 (o_nod_event 1클럭 펄스, o_nod_sustained 상태)
    input  wire        i_nod_event,
    input  wire        i_nod_sustained,
    output reg         alert,
    output wire        ready
);
    wire c_valid, c_hold, c_drowsy;

    classifier #(.T_FIX(T_FIX), .FRAC(FRAC)) u_cls (
        .clk(clk), .rst_n(rst_n),
        .i_win_valid(i_win_valid), .i_n60(i_n60), .i_sum_rr60(i_sum_rr60),
        .o_valid(c_valid), .o_hold(c_hold), .o_drowsy(c_drowsy), .o_ready(ready)
    );

    // 우리 자세 규칙 (35°, 0.5 s, 5 s 반복)
    wire m_nod_pose;
    imu_rule u_imu (
        .clk(clk), .rst_n(rst_n),
        .i_imu_valid(i_imu_valid), .i_ax(i_accel_x), .i_ay(i_accel_y), .i_az(i_accel_z),
        .o_nod(m_nod_pose), .o_tilt()
    );

    // 준용 nod_sustained 는 상태라 상승 에지에서 한 번만
    reg sus_d;
    always @(posedge clk) begin
        if (!rst_n) sus_d <= 1'b0;
        else        sus_d <= i_nod_sustained;
    end
    wire m_nod = m_nod_pose | i_nod_event | (i_nod_sustained & ~sus_d);

    // combine: 판정 갱신 클럭에 졸림이고 보류 아니면 1펄스, 떨굼은 그 순간 1펄스
    always @(posedge clk) begin
        if (!rst_n)
            alert <= 1'b0;
        else
            alert <= (c_valid & c_drowsy & ~c_hold) | m_nod;
    end
endmodule
`default_nettype wire
