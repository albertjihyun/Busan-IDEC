// 각성도 저하 판정. src/infer_ref.py 를 옮긴 것. 설계는 docs/integer-inference-design.md,
// 기준선·창 품질 규칙은 docs/stage5-ppg-transfer.md.
//
//   mean_rb = (sum_rr60 / n60) / (base_sum / base_n) >= T
//   양변에 n60 × base_n × 2^FRAC 를 곱해 나눗셈을 없앤다:
//   (sum_rr60 × base_n) << FRAC  >=  (T_FIX × base_sum) × n60
//
//   - 창 품질: 좋은 창 = n60 ≥ MIN_N60 이고 KEEP_K × bad60 ≤ n60 (살린 박동 비율 ≥ K/(K+1), K=3 이면 75%).
//     KEEP_K = 0 이면 탈락 수는 안 본다. KEEP_K 는 보드 실측으로 조정할 파라미터다.
//   - 기준선: 블록 12개(1분)마다 창 하나를 보고, 좋은 창이면 그 창 합을 기준선에 더한다.
//     좋은 창 3개가 모이면 완성. 1분 창은 서로 겹치지 않는다.
//   - hold = 기준선 미완성 또는 좋지 않은 창. hold 면 drowsy = 0.
//   - 이력(hysteresis)·연속 규칙 없음. 5초 판정을 그대로 낸다.
//
// 타이밍: i_win_valid 클럭에 입력을 잡고 기준선을 갱신(A), 다음 클럭에 곱셈(B), 그 다음 클럭에 비교·출력(C).
// o_valid 는 i_win_valid 로부터 3클럭 뒤. 블록 간격이 6만 클럭이라 문제 없다.

`timescale 1ns/1ps
`default_nettype none
module classifier #(
    parameter T_FIX      = 1086,   // T = T_FIX / 2^FRAC = 1.0605 (헛경보 4회/h)
    parameter FRAC       = 10,
    parameter WIN_BLOCKS = 12,     // 60초 창 = 블록 12개
    parameter BASE_WINS  = 3,      // 기준선 = 좋은 1분 창 3개
    parameter MIN_N60    = 30,
    parameter KEEP_K     = 3       // 3 = 살린 비율 75%, 2 = 67%, 1 = 50%, 0 = 끔 (0..3)
)(
    input  wire        clk,
    input  wire        rst_n,
    input  wire        i_win_valid,     // 5초마다 1클럭. 아래 셋이 갱신됨
    input  wire [7:0]  i_n60,
    input  wire [16:0] i_sum_rr60,
    input  wire [7:0]  i_bad60,         // 60초 창의 탈락 박동 수 (준용 o_bad60)
    output reg         o_valid,         // 판정 갱신 펄스
    output reg         o_hold,
    output reg         o_drowsy,
    output reg         o_ready          // 기준선 확정됨
);
    localparam W_BASE_N   = 10;                      // 3 × 255 = 765 최대
    localparam W_BASE_SUM = 16;                      // 3 × (60 s × 240 + 360) = 44,280 최대
    localparam W_TFIX     = 11;
    localparam W_R        = W_TFIX + W_BASE_SUM;     // 27
    localparam W_LHS      = 17 + W_BASE_N + FRAC;    // 37
    localparam W_RHS      = W_R + 8;                 // 35
    localparam [W_TFIX-1:0] TF = T_FIX;

    reg [3:0]            win_cnt;       // 0..WIN_BLOCKS-1. WIN_BLOCKS-1 에서 창 하나를 기준선 후보로 본다
    reg [1:0]            good_cnt;      // 기준선에 넣은 좋은 창 수
    reg [W_BASE_N-1:0]   base_n;
    reg [W_BASE_SUM-1:0] base_sum;
    reg [W_R-1:0]        r;             // T_FIX × base_sum

    reg [7:0]            n60_r;
    reg [16:0]           sum_r;
    reg                  hold_r;
    reg                  pend_b, pend_c;
    reg [W_LHS-1:0]      lhs;
    reg [W_RHS-1:0]      rhs;

    // KEEP_K × bad60 을 시프트·덧셈으로(합성기가 상수 곱을 DSP 로 보내지 않게). KEEP_K 는 0..3
    wire [9:0]            bad_k       = ((KEEP_K & 2) ? {1'b0, i_bad60, 1'b0} : 10'd0) + ((KEEP_K & 1) ? {2'b0, i_bad60} : 10'd0);
    wire                  good        = (i_n60 >= MIN_N60) && (KEEP_K == 0 || bad_k <= {2'd0, i_n60});
    wire                  pick        = (win_cnt == WIN_BLOCKS - 1);
    wire                  take        = pick && good;
    wire                  base_done   = take && (good_cnt == BASE_WINS - 1);
    wire [W_BASE_N-1:0]   base_n_nx   = base_n   + {2'd0, i_n60};
    wire [W_BASE_SUM-1:0] base_sum_nx = base_sum + i_sum_rr60[W_BASE_SUM-1:0];
    wire [W_R-1:0]        r_nx        = TF * base_sum_nx;
    wire [26:0]           prod_l      = sum_r * base_n;   // 17 × 10

    always @(posedge clk) begin
        o_valid <= 1'b0;
        pend_b  <= 1'b0;
        pend_c  <= 1'b0;
        if (!rst_n) begin
            win_cnt <= 0; good_cnt <= 0; base_n <= 0; base_sum <= 0; r <= 0; o_ready <= 1'b0;
            n60_r <= 0; sum_r <= 0; hold_r <= 1'b1; lhs <= 0; rhs <= 0;
            o_hold <= 1'b1; o_drowsy <= 1'b0;
        end else begin
            // A. 입력 잡기 + 기준선
            if (i_win_valid) begin
                n60_r  <= i_n60;
                sum_r  <= i_sum_rr60;
                hold_r <= !o_ready || !good;     // ready 는 갱신 전 값: 기준선이 완성되는 블록도 hold
                pend_b <= 1'b1;
                if (!o_ready) begin
                    win_cnt <= pick ? 4'd0 : win_cnt + 4'd1;
                    if (take) begin
                        base_n   <= base_n_nx;
                        base_sum <= base_sum_nx;
                        good_cnt <= good_cnt + 2'd1;
                        if (base_done) begin
                            o_ready <= 1'b1;
                            r       <= r_nx;
                        end
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
