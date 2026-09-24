// 고개 떨굼 규칙. 파이썬 기준 모델(imu_ref)과 비트 단위 일치.
//
// 입력은 신호처리 블록의 가속도 3축(16비트 signed, ±2 g = 16,384 LSB/g)과 갱신 펄스 i_imu_valid(100 Hz).
// 앞축(센서 Z, 숙이면 음이라 부호를 뒤집음)과 세로축(센서 Y, 절댓값)에 저역 IIR(>>>3, 약 2 Hz)을 걸고
//   tilt = (앞축 ≥ sin35°) && (|세로축| ≤ cos35°)
// 가 50샘플(0.5 s) 연속이면 o_nod 1클럭 펄스. 숙인 채 있으면 500샘플(5 s)마다 다시 펄스.
// 급제동은 앞축만 키우고 세로축은 1 g 그대로라 세로축 조건에서 걸러진다. 곱셈 없음.
// 축 번호·부호는 보드 도면에서 도출. 실물 장착 확인 뒤 파라미터만 바꾼다.

`timescale 1ns/1ps
`default_nettype none
module imu_rule #(
    parameter integer FWD_AXIS  = 2,       // 0=X 1=Y 2=Z. 보드 법선 = 앞(코)
    parameter integer FWD_SIGN  = -1,      // 숙이면 Z 가 음 → 뒤집어 양으로
    parameter integer VERT_AXIS = 1,       // 이마-턱 축. 부호는 절댓값으로 무시
    parameter integer TH_FWD    = 9397,    // sin35° × 16384
    parameter integer TH_VERT   = 13420,   // cos35° × 16384
    parameter integer LPF_SH    = 3,
    parameter integer N_HOLD    = 50,      // 0.5 s @ 100 Hz
    parameter integer N_REPEAT  = 500      // 5 s
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               i_imu_valid,
    input  wire signed [15:0] i_ax,
    input  wire signed [15:0] i_ay,
    input  wire signed [15:0] i_az,
    output reg                o_nod,       // 1클럭 펄스
    output reg                o_tilt       // 숙인 상태(관측용)
);
    // 축 선택과 부호. -32768 은 반전하면 자기 자신이라 32767 로 자른다 (파이썬 neg16 과 동일).
    reg signed [15:0] a_fwd_raw, a_fwd, a_vert;
    always @(*) begin
        case (FWD_AXIS)
            0: a_fwd_raw = i_ax;
            1: a_fwd_raw = i_ay;
            default: a_fwd_raw = i_az;
        endcase
        case (VERT_AXIS)
            0: a_vert = i_ax;
            1: a_vert = i_ay;
            default: a_vert = i_az;
        endcase
        a_fwd = (FWD_SIGN < 0) ? ((a_fwd_raw == -16'sd32768) ? 16'sd32767 : -a_fwd_raw) : a_fwd_raw;
    end

    // 저역 IIR. 차는 17비트, 결과는 두 입력 사이라 16비트 안에 든다.
    // 결합({})은 unsigned 라 식 전체가 unsigned 로 승격돼 >>> 가 논리 시프트가 된다. $signed 로 감싼다.
    reg  signed [15:0] lp_f, lp_v;
    wire signed [16:0] d_f = $signed({a_fwd[15], a_fwd}) - $signed({lp_f[15], lp_f});
    wire signed [16:0] d_v = $signed({a_vert[15], a_vert}) - $signed({lp_v[15], lp_v});
    wire signed [16:0] lp_f_w = $signed({lp_f[15], lp_f}) + (d_f >>> LPF_SH);
    wire signed [16:0] lp_v_w = $signed({lp_v[15], lp_v}) + (d_v >>> LPF_SH);
    wire signed [15:0] lp_f_n = lp_f_w[15:0];
    wire signed [15:0] lp_v_n = lp_v_w[15:0];
    wire signed [15:0] abs_v  = lp_v_n[15] ? ((lp_v_n == -16'sd32768) ? 16'sd32767 : -lp_v_n) : lp_v_n;

    localparam signed [15:0] TH_F_S = TH_FWD;
    localparam signed [15:0] TH_V_S = TH_VERT;
    wire tilt_n = (lp_f_n >= TH_F_S) && (abs_v <= TH_V_S);

    // 연속 샘플 카운터. N_HOLD 에 닿으면 펄스, N_HOLD+N_REPEAT 에 닿으면 펄스 후 N_HOLD 로.
    localparam integer CNT_TOP = N_HOLD + N_REPEAT;     // 550 < 1024
    reg [9:0] cnt;
    wire [9:0] cnt_inc = cnt + 10'd1;

    always @(posedge clk) begin
        if (!rst_n) begin
            lp_f <= 16'sd0; lp_v <= 16'sd0; cnt <= 10'd0;
            o_nod <= 1'b0; o_tilt <= 1'b0;
        end else begin
            o_nod <= 1'b0;
            if (i_imu_valid) begin
                lp_f   <= lp_f_n;
                lp_v   <= lp_v_n;
                o_tilt <= tilt_n;
                if (tilt_n) begin
                    if (cnt_inc == N_HOLD[9:0]) begin
                        o_nod <= 1'b1;
                        cnt   <= cnt_inc;
                    end else if (cnt_inc == CNT_TOP[9:0]) begin
                        o_nod <= 1'b1;
                        cnt   <= N_HOLD[9:0];
                    end else begin
                        cnt   <= cnt_inc;
                    end
                end else begin
                    cnt <= 10'd0;
                end
            end
        end
    end
endmodule
`default_nettype wire
