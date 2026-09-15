// RR 계산과 SQI. src/peak_simple.py 의 SQI 를 옮긴 것.
//
// 봉우리 위치 = 확정 시점 - delay 이므로
//   RR = (이번 확정 - 직전 확정) + 직전 delay - 이번 delay
// 확정 사이 샘플 수를 세는 카운터 하나와 직전 delay 하나면 절대 위치 없이 계산된다.
//
// 규칙
//   6. RR_MIN <= RR <= RR_MAX 이어야 범위 안
//   7. |RR - last_rr| * JUMP_DEN <= last_rr * JUMP_NUM. 첫 RR은 기준이 없어 탈락
//   last_rr 은 급변 판정과 무관하게 '범위 안인 마지막 RR' 로 갱신한다. (연쇄 탈락 방지)

`timescale 1ns/1ps
`default_nettype none
module sqi #(
    parameter RR_MIN   = 72,
    parameter RR_MAX   = 360,
    parameter JUMP_NUM = 1,
    parameter JUMP_DEN = 4
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire       i_valid,     // 샘플 펄스
    input  wire       i_peak,      // 봉우리 확정 펄스 (i_valid 와 같은 클럭)
    input  wire [4:0] i_delay,
    output reg        o_rr_valid,  // RR 하나 나옴 (첫 봉우리는 안 나옴)
    output reg  [9:0] o_rr,
    output reg        o_ok
);
    reg [9:0] count;        // 직전 확정 이후 샘플 수. 포화
    reg [4:0] last_delay;
    reg       have_last;    // 봉우리를 하나라도 봤나
    reg [9:0] last_rr;
    reg       have_last_rr;

    // count 는 직전 확정 다음 샘플부터 셌으므로 확정 샘플 자체(+1)를 더한다
    wire [10:0] rr_full  = {1'b0, count} + 11'd1 + {6'd0, last_delay} - {6'd0, i_delay};
    wire [9:0]  rr       = rr_full[9:0];
    wire        in_range = (rr_full >= RR_MIN) && (rr_full <= RR_MAX);
    wire [10:0] diff     = (rr > last_rr) ? (rr - last_rr) : (last_rr - rr);
    wire [12:0] jump_lhs = diff * JUMP_DEN;
    wire [12:0] jump_rhs = last_rr * JUMP_NUM;
    wire        ok       = in_range && have_last_rr && (jump_lhs <= jump_rhs);

    always @(posedge clk) begin
        o_rr_valid <= 1'b0;
        if (!rst_n) begin
            count <= 0; last_delay <= 0; have_last <= 1'b0; last_rr <= 0; have_last_rr <= 1'b0;
            o_rr <= 0; o_ok <= 1'b0;
        end else if (i_valid) begin
            if (i_peak) begin
                if (have_last) begin
                    o_rr_valid <= 1'b1;
                    o_rr       <= rr;
                    o_ok       <= ok;
                    if (in_range) begin
                        last_rr      <= rr;
                        have_last_rr <= 1'b1;
                    end
                end
                have_last  <= 1'b1;
                count      <= 0;
                last_delay <= i_delay;
            end else if (count != 10'h3FF) begin
                count <= count + 10'd1;
            end
        end
    end
endmodule
`default_nettype wire
