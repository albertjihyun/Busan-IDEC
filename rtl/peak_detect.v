// 봉우리 검출. src/peak_simple.py 의 PeakDetector 를 그대로 옮긴 것.
//
// 입력: AFE를 지난 0 중심 부호 있는 샘플. i_valid 는 240 SPS 로 1클럭 펄스.
// 출력: o_peak 는 봉우리 확정 1클럭 펄스. o_delay 는 확정 시점이 봉우리보다 몇 샘플 늦은지.
//        봉우리 위치 = (지금 샘플 번호) - o_delay.
//
// 규칙 (파이썬 주석과 같은 번호)
//   1. 올라가다 꺾이는 샘플이 후보 (prev > x 이고 직전에 상승 중)
//   2. cand_v * THR_DEN >= level * THR_NUM
//   3. 직전 봉우리로부터 REFRACT 샘플 이상
//   4. 후보 뒤 DROP_WIN 샘플 안에 (cand_v - cand_min) * DROP_DEN >= cand_v * DROP_NUM 이면 확정
//   5. 확정 시 level += (cand_v - level) >>> LEVEL_SHIFT
//
// 곱셈은 상수 곱 셋(×5, ×3, ×2)뿐이라 시프트·덧셈으로 합성된다.

`timescale 1ns/1ps
`default_nettype none
module peak_detect #(
    parameter W          = 16,   // 샘플 폭
    parameter REFRACT    = 96,
    parameter THR_NUM    = 3,
    parameter THR_DEN    = 5,
    parameter DROP_WIN   = 24,
    parameter DROP_NUM   = 1,
    parameter DROP_DEN   = 2,
    parameter LEVEL_SHIFT = 3
)(
    input  wire                clk,
    input  wire                rst_n,
    input  wire                i_valid,
    input  wire signed [W-1:0] i_sample,
    output reg                 o_peak,
    output reg  [4:0]          o_delay
);
    reg signed [W-1:0] prev;
    reg                have_prev;
    reg                rising;
    reg signed [W-1:0] level;
    reg [9:0]          since_peak;   // 마지막 봉우리 이후 샘플 수. 포화
    reg                cand_valid;
    reg signed [W-1:0] cand_v;
    reg signed [W-1:0] cand_min;
    reg [4:0]          cand_age;     // 후보가 생긴 뒤 지난 샘플 수

    // 이번 샘플에서 후보 판정에 쓸 값들 (파이썬의 순서: 4번 먼저, 그 다음 1~3번)
    wire signed [W-1:0] min_now  = (i_sample < cand_min) ? i_sample : cand_min;
    wire [4:0]          age_now  = cand_age + 5'd1;
    wire signed [W+1:0] drop_lhs = (cand_v - min_now) * DROP_DEN;
    wire signed [W+1:0] drop_rhs = cand_v * DROP_NUM;
    wire                dropped  = cand_valid && (drop_lhs >= drop_rhs);
    wire                timeout  = cand_valid && !dropped && (age_now >= DROP_WIN);
    wire                higher   = cand_valid && !dropped && (i_sample > cand_v);
    wire                pend_clr = dropped | timeout | higher;

    // 확정 시 갱신될 값
    wire signed [W:0]   lvl_diff = cand_v - level;
    wire signed [W-1:0] level_nx = level + (lvl_diff >>> LEVEL_SHIFT);
    wire [9:0]          since_nx = dropped ? {5'd0, age_now}
                                 : (since_peak == 10'h3FF ? since_peak : since_peak + 10'd1);

    // 새 후보 조건. 문턱은 확정 직후면 갱신된 level 로, 불응기는 갱신된 since 로 본다 (파이썬과 같은 순서)
    wire signed [W-1:0] level_use = dropped ? level_nx : level;
    wire                turn      = have_prev && rising && (i_sample < prev);
    wire signed [W+2:0] thr_lhs   = prev * THR_DEN;
    wire signed [W+2:0] thr_rhs   = level_use * THR_NUM;
    wire                cand_ok   = turn && (thr_lhs >= thr_rhs)
                                 && (since_nx >= REFRACT + 1)          // (i-1) - last_peak >= REFRACT
                                 && (!cand_valid || pend_clr);          // 대기 중 후보가 없어야

    always @(posedge clk) begin
        o_peak <= 1'b0;
        if (!rst_n) begin
            prev <= 0; have_prev <= 1'b0; rising <= 1'b0; level <= 0;
            since_peak <= 10'h3FF; cand_valid <= 1'b0; cand_v <= 0; cand_min <= 0; cand_age <= 0;
            o_delay <= 0;
        end else if (i_valid) begin
            // 4. 대기 중 후보 처리
            if (cand_valid) begin
                cand_min <= min_now;
                cand_age <= age_now;
                if (dropped) begin
                    o_peak  <= 1'b1;
                    o_delay <= age_now;
                    level   <= level_nx;
                end
                if (pend_clr) cand_valid <= 1'b0;
            end
            since_peak <= since_nx;

            // 1~3. 꺾이는 지점 → 새 후보
            if (have_prev) begin
                if (i_sample > prev) rising <= 1'b1;
                else if (i_sample < prev) begin
                    rising <= 1'b0;
                    if (cand_ok) begin
                        cand_valid <= 1'b1;
                        cand_v     <= prev;
                        cand_min   <= i_sample;
                        cand_age   <= 5'd1;      // 후보는 직전 샘플. 지금 시점에서 1샘플 전
                    end
                end
            end
            prev      <= i_sample;
            have_prev <= 1'b1;
        end
    end
endmodule
`default_nettype wire
