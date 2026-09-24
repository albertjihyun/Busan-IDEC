// 추론 최상위. 신호처리 블록(ppg_soc_top)의 창 합과 IMU 신호를 받아 판정하고 UART 로 넘길 경보 펄스 하나를 만든다.
//
//   alert : 1클럭 펄스. 다음 셋 중 하나라도 있으면 1회.
//           - 5초 판정이 졸림이고 보류(기준선 준비 중·박동 부족·탈락 과다) 아님   classifier
//           - 고개를 35° 넘게 숙인 채 0.5 s (숙인 채 있으면 5 s 마다)   imu_rule   (가속도, 자세)
//           - 신호처리 블록 imu_feature 의 끄덕임(o_nod_event) / 떨군 채 유지(o_nod_sustained 상승 에지)   (자이로, 동작)
//             단 자이로 부호가 확정된 뒤(o_pitch_sign_ok = 1)에만 받는다. 확정 전에는 imu_feature 가 부호를
//             +1 로 가정하고 돌기 때문에 밴드를 반대로 쓰면 꾸벅임을 놓치거나 고개를 든 자세에서 울린다.
//             그 구간(착용 뒤 고개를 두세 번 움직일 때까지)은 가속도 자세 규칙과 심박 판정만 돈다.
//           UART 는 이 펄스마다 바이트 하나를 보낸다. 상태는 밖으로 안 낸다.
//   ready : 기준선 확정됨. 보드 LED 등 상태 표시용.
//
// 떨굼은 심박과 무관하므로 워밍업·보류 중에도 울린다. 움직임 과다 보류(m_busy)는 넣지 않는다
// (신호처리 블록 SQI 의 모션 게이트가 이미 그 일을 한다).

`timescale 1ns/1ps
`default_nettype none
module infer_top #(
    parameter T_FIX = 1086,
    parameter FRAC  = 10
)(
    input  wire        clk,
    input  wire        rst_n,
    // 신호처리 블록 → 5초 창 합 (o_win_valid, o_n60, o_sum_rr60, o_bad60)
    input  wire        i_win_valid,
    input  wire [7:0]  i_n60,
    input  wire [16:0] i_sum_rr60,
    input  wire [7:0]  i_bad60,      // 60초 창 탈락 박동 수 (o_bad60). 창 품질·기준선 규칙에 쓴다
    // 신호처리 블록 → IMU 원시값 (o_accel_x/y/z, o_imu_valid, 100 Hz)
    input  wire        i_imu_valid,
    input  wire signed [15:0] i_accel_x,
    input  wire signed [15:0] i_accel_y,
    input  wire signed [15:0] i_accel_z,
    // 신호처리 블록 imu_feature → 끄덕임 (o_nod_event 1클럭 펄스, o_nod_sustained 상태)
    input  wire        i_nod_event,
    input  wire        i_nod_sustained,
    input  wire        i_pitch_sign_ok, // 자이로 부호 확정됨 (o_pitch_sign_ok). 0 이면 위 둘을 무시
    output reg         alert,
    output wire        ready
);
    wire c_valid, c_hold, c_drowsy;

    classifier #(.T_FIX(T_FIX), .FRAC(FRAC)) u_cls (
        .clk(clk), .rst_n(rst_n),
        .i_win_valid(i_win_valid), .i_n60(i_n60), .i_sum_rr60(i_sum_rr60), .i_bad60(i_bad60),
        .o_valid(c_valid), .o_hold(c_hold), .o_drowsy(c_drowsy), .o_ready(ready)
    );

    // 가속도 자세 규칙 (35°, 0.5 s, 5 s 반복)
    wire m_nod_pose;
    imu_rule u_imu (
        .clk(clk), .rst_n(rst_n),
        .i_imu_valid(i_imu_valid), .i_ax(i_accel_x), .i_ay(i_accel_y), .i_az(i_accel_z),
        .o_nod(m_nod_pose), .o_tilt()
    );

    // nod_sustained 는 상태라 상승 에지에서 한 번만
    reg sus_d;
    always @(posedge clk) begin
        if (!rst_n) sus_d <= 1'b0;
        else        sus_d <= i_nod_sustained;
    end
    wire m_nod = m_nod_pose | (i_pitch_sign_ok & (i_nod_event | (i_nod_sustained & ~sus_d)));

    // combine: 판정 갱신 클럭에 졸림이고 보류 아니면 1펄스, 떨굼은 그 순간 1펄스
    always @(posedge clk) begin
        if (!rst_n)
            alert <= 1'b0;
        else
            alert <= (c_valid & c_drowsy & ~c_hold) | m_nod;
    end
endmodule
`default_nettype wire
