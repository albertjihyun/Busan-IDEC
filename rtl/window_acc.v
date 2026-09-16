// 5초 블록 누산기와 30초·60초 창 합. src/window_acc.py 를 옮긴 것.
//
//   - SQI 통과 RR 만 누산. d = RR - rr_prev (rr_prev 는 직전 누산 RR, 블록 경계를 넘어 이어짐)
//   - 1200 샘플마다 블록을 닫아 12벌 시프트 레지스터에 넣고 누산기를 0으로
//   - 창 합은 증분으로 유지: win += 새 블록 - 창에서 빠지는 블록
//
// 블록 닫기는 1200번째 샘플의 RR 반영 다음 클럭에 한다 (비동기 갱신 순서 때문). 샘플 간격이
// 5만 클럭이라 한 클럭 지연은 보이지 않는다.

`timescale 1ns/1ps
`default_nettype none
module window_acc #(
    parameter BLOCK = 1200,
    parameter DEPTH = 12,
    parameter W30   = 6
)(
    input  wire        clk,
    input  wire        rst_n,
    input  wire        i_valid,      // 샘플 펄스
    input  wire        i_rr_valid,   // RR 하나 (i_valid 와 같은 클럭)
    input  wire [9:0]  i_rr,
    input  wire        i_ok,
    output reg         o_win_valid,  // 블록 닫힘. 아래 값 갱신됨
    output reg  [7:0]  o_n30,
    output reg  [16:0] o_sum_rr30,
    output reg  [24:0] o_sum_rr2_30,
    output reg signed [16:0] o_sum_d30,
    output reg  [23:0] o_sum_d2_30,
    output reg  [7:0]  o_n60,
    output reg  [16:0] o_sum_rr60,
    output reg  [24:0] o_sum_rr2_60,
    output reg signed [16:0] o_sum_d60,
    output reg  [23:0] o_sum_d2_60
);
    // 현재 블록 누산기
    reg [7:0]         n;
    reg [16:0]        sum_rr;
    reg [24:0]        sum_rr2;
    reg signed [16:0] sum_d;
    reg [23:0]        sum_d2;
    reg [9:0]         rr_prev;
    reg               have_prev;
    reg [10:0]        cnt;          // 0..BLOCK-1
    reg               close_pend;

    // 12벌 이력. 0이 최신
    reg [7:0]         h_n     [0:DEPTH-1];
    reg [16:0]        h_rr    [0:DEPTH-1];
    reg [24:0]        h_rr2   [0:DEPTH-1];
    reg signed [16:0] h_d     [0:DEPTH-1];
    reg [23:0]        h_d2    [0:DEPTH-1];

    wire signed [10:0] d    = $signed({1'b0, i_rr}) - $signed({1'b0, rr_prev});
    wire [19:0]        rr2  = i_rr * i_rr;
    wire [10:0]        dabs = d[10] ? -d : d;        // |d| ≤ 288
    wire [23:0]        d2   = dabs * dabs;

    integer k;
    always @(posedge clk) begin
        o_win_valid <= 1'b0;
        if (!rst_n) begin
            n <= 0; sum_rr <= 0; sum_rr2 <= 0; sum_d <= 0; sum_d2 <= 0;
            rr_prev <= 0; have_prev <= 1'b0; cnt <= 0; close_pend <= 1'b0;
            o_n30 <= 0; o_sum_rr30 <= 0; o_sum_rr2_30 <= 0; o_sum_d30 <= 0; o_sum_d2_30 <= 0;
            o_n60 <= 0; o_sum_rr60 <= 0; o_sum_rr2_60 <= 0; o_sum_d60 <= 0; o_sum_d2_60 <= 0;
            for (k = 0; k < DEPTH; k = k + 1) begin
                h_n[k] <= 0; h_rr[k] <= 0; h_rr2[k] <= 0; h_d[k] <= 0; h_d2[k] <= 0;
            end
        end else begin
            if (i_valid) begin
                if (i_rr_valid && i_ok) begin
                    n       <= n + 8'd1;
                    sum_rr  <= sum_rr + {7'd0, i_rr};
                    sum_rr2 <= sum_rr2 + {5'd0, rr2};
                    if (have_prev) begin
                        sum_d  <= sum_d + {{6{d[10]}}, d};
                        sum_d2 <= sum_d2 + d2;
                    end
                    rr_prev   <= i_rr;
                    have_prev <= 1'b1;
                end
                if (cnt == BLOCK - 1) begin
                    cnt <= 0;
                    close_pend <= 1'b1;
                end else begin
                    cnt <= cnt + 11'd1;
                end
            end

            if (close_pend) begin
                close_pend <= 1'b0;
                o_win_valid <= 1'b1;
                // 창 합 증분 갱신
                o_n30        <= o_n30        + n       - h_n[W30-1];
                o_sum_rr30   <= o_sum_rr30   + sum_rr  - h_rr[W30-1];
                o_sum_rr2_30 <= o_sum_rr2_30 + sum_rr2 - h_rr2[W30-1];
                o_sum_d30    <= o_sum_d30    + sum_d   - h_d[W30-1];
                o_sum_d2_30  <= o_sum_d2_30  + sum_d2  - h_d2[W30-1];
                o_n60        <= o_n60        + n       - h_n[DEPTH-1];
                o_sum_rr60   <= o_sum_rr60   + sum_rr  - h_rr[DEPTH-1];
                o_sum_rr2_60 <= o_sum_rr2_60 + sum_rr2 - h_rr2[DEPTH-1];
                o_sum_d60    <= o_sum_d60    + sum_d   - h_d[DEPTH-1];
                o_sum_d2_60  <= o_sum_d2_60  + sum_d2  - h_d2[DEPTH-1];
                // 이력 시프트
                for (k = DEPTH - 1; k > 0; k = k - 1) begin
                    h_n[k] <= h_n[k-1]; h_rr[k] <= h_rr[k-1]; h_rr2[k] <= h_rr2[k-1];
                    h_d[k] <= h_d[k-1]; h_d2[k] <= h_d2[k-1];
                end
                h_n[0] <= n; h_rr[0] <= sum_rr; h_rr2[0] <= sum_rr2; h_d[0] <= sum_d; h_d2[0] <= sum_d2;
                // 누산기 초기화. rr_prev 는 유지
                n <= 0; sum_rr <= 0; sum_rr2 <= 0; sum_d <= 0; sum_d2 <= 0;
            end
        end
    end
endmodule
`default_nettype wire
