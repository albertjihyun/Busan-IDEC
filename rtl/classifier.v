// 각성도 저하 판정. src/infer_ref.py 를 옮긴 것. 설계는 docs/integer-inference-design.md.
//
//   mean_rb = (sum_rr60 / n60) / (base_sum / base_n) >= T
//   양변에 n60 × base_n × 2^FRAC 를 곱해 나눗셈을 없앤다:
//   (sum_rr60 × base_n) << FRAC  >=  (T_FIX × base_sum) × n60
//
//   - 워밍업 36블록(3분). 기준선은 12·24·36번째 블록의 60초 창 합을 더해 만든다(창 셋이 겹치지 않음).
//   - 36번째 블록 끝에 base_n < MIN_BASE_N 이면 기준선을 버리고 워밍업을 다시 한다.
//   - hold = 워밍업 중 또는 n60 < MIN_N60. hold 면 drowsy = 0.
//   - 이력(hysteresis)·연속 규칙 없음. 5초 판정을 그대로 낸다.
//
// 타이밍: i_win_valid 클럭에 입력을 잡고 기준선을 갱신(A), 다음 클럭에 곱셈(B), 그 다음 클럭에 비교·출력(C).
// o_valid 는 i_win_valid 로부터 3클럭 뒤. 블록 간격이 6만 클럭이라 문제 없다.

`timescale 1ns/1ps
`default_nettype none
module classifier #(
    parameter T_FIX       = 1086,   // T = T_FIX / 2^FRAC = 1.0605 (헛경보 4회/h)
    parameter FRAC        = 10,
    parameter WARM_BLOCKS = 36,     // 3분
    parameter WIN_BLOCKS  = 12,     // 60초 창 = 블록 12개
    parameter MIN_N60     = 30,
    parameter MIN_BASE_N  = 45
)(
    input  wire        clk,
    input  wire        rst_n,
    input  wire        i_win_valid,     // 5초마다 1클럭. 아래 둘이 갱신됨
    input  wire [7:0]  i_n60,
    input  wire [16:0] i_sum_rr60,
    output reg         o_valid,         // 판정 갱신 펄스
    output reg         o_hold,
    output reg         o_drowsy,
    output reg         o_ready          // 기준선 확정됨
);
    localparam W_BASE_N   = 10;                      // 594 최대
    localparam W_BASE_SUM = 16;                      // 43,560 최대
    localparam W_TFIX     = 11;
    localparam W_R        = W_TFIX + W_BASE_SUM;     // 27
    localparam W_LHS      = 17 + W_BASE_N + FRAC;    // 37
    localparam W_RHS      = W_R + 8;                 // 35
    localparam [W_TFIX-1:0] TF = T_FIX;

    reg [5:0]            warm_cnt;      // 워밍업 안에서 지나온 블록 0..WARM_BLOCKS-1
    reg [3:0]            win_cnt;       // 0..WIN_BLOCKS-1. WIN_BLOCKS-1 에서 창 합을 기준선에 더한다
    reg [W_BASE_N-1:0]   base_n;
    reg [W_BASE_SUM-1:0] base_sum;
    reg [W_R-1:0]        r;             // T_FIX × base_sum

    // A 단계에서 잡은 입력과 hold
    reg [7:0]            n60_r;
    reg [16:0]           sum_r;
    reg                  hold_r;
    reg                  pend_b, pend_c;
    // B 단계 곱
    reg [W_LHS-1:0]      lhs;
    reg [W_RHS-1:0]      rhs;

    // 워밍업 갱신값 (조합). 더한 뒤의 값으로 하한을 본다 (파이썬과 같은 순서)
    wire                  pick      = (win_cnt == WIN_BLOCKS - 1);
    wire                  warm_done = (warm_cnt == WARM_BLOCKS - 1);
    wire [W_BASE_N-1:0]   base_n_nx   = pick ? base_n   + {2'd0, i_n60}      : base_n;
    wire [W_BASE_SUM-1:0] base_sum_nx = pick ? base_sum + i_sum_rr60[W_BASE_SUM-1:0] : base_sum;
    wire [W_R-1:0]        r_nx        = TF * base_sum_nx;
    wire [26:0]           prod_l      = sum_r * base_n;   // 17 × 10

    always @(posedge clk) begin
        o_valid <= 1'b0;
        pend_b  <= 1'b0;
        pend_c  <= 1'b0;
        if (!rst_n) begin
            warm_cnt <= 0; win_cnt <= 0; base_n <= 0; base_sum <= 0; r <= 0; o_ready <= 1'b0;
            n60_r <= 0; sum_r <= 0; hold_r <= 1'b1; lhs <= 0; rhs <= 0;
            o_hold <= 1'b1; o_drowsy <= 1'b0;
        end else begin
            // A. 입력 잡기 + 워밍업
            if (i_win_valid) begin
                n60_r  <= i_n60;
                sum_r  <= i_sum_rr60;
                hold_r <= !o_ready || (i_n60 < MIN_N60);   // ready 는 갱신 전 값: 36번째 블록도 hold
                pend_b <= 1'b1;
                if (!o_ready) begin
                    base_n   <= base_n_nx;
                    base_sum <= base_sum_nx;
                    if (warm_done) begin
                        warm_cnt <= 0;
                        win_cnt  <= 0;
                        if (base_n_nx >= MIN_BASE_N) begin
                            o_ready <= 1'b1;
                            r       <= r_nx;
                        end else begin
                            base_n   <= 0;          // 재시작
                            base_sum <= 0;
                        end
                    end else begin
                        warm_cnt <= warm_cnt + 6'd1;
                        win_cnt  <= pick ? 4'd0 : win_cnt + 4'd1;
                    end
                end
            end
            // B. 곱셈
            if (pend_b) begin
                lhs    <= prod_l << FRAC;      // 좌변은 문맥 폭(37)으로 늘어난 뒤 시프트
                rhs    <= r * n60_r;
                pend_c <= 1'b1;
            end
            // C. 비교·출력
            if (pend_c) begin
                o_hold   <= hold_r;
                o_drowsy <= !hold_r && (lhs >= rhs);
                o_valid  <= 1'b1;
            end
        end
    end
endmodule
`default_nettype wire
