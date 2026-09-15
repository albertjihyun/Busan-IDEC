// rr_frontend 채점. sim/vectors/ 의 파이썬 정답과 비트 단위로 대조한다.
//
//   iverilog -g2012 -o sim/rr.vvp rtl/*.v sim/tb_rr_frontend.v && vvp -n sim/rr.vvp
//
// 세 단계로 센다: 봉우리 위치 → RR/SQI → 창 합. 앞이 틀리면 뒤는 의미 없다.
// 샘플 간격은 실제 5만 클럭 대신 8클럭으로 줄였다. 설계가 간격에 의존하지 않는다.

`timescale 1ns/1ps
module tb_rr_frontend;
    localparam N_SAMPLES = 28800;
    localparam GAP = 8;

    reg clk = 0, rst_n = 0, i_valid = 0;
    reg signed [15:0] i_sample = 0;
    always #5 clk = ~clk;

    wire        o_peak, o_rr_valid, o_rr_ok, o_win_valid;
    wire [4:0]  o_peak_delay;
    wire [9:0]  o_rr;
    wire [7:0]  o_n30, o_n60;
    wire [16:0] o_sum_rr30, o_sum_rr60;
    wire [24:0] o_sum_rr2_30, o_sum_rr2_60;
    wire signed [16:0] o_sum_d30, o_sum_d60;
    wire [23:0] o_sum_d2_30, o_sum_d2_60;

    rr_frontend dut (
        .clk(clk), .rst_n(rst_n), .i_valid(i_valid), .i_sample(i_sample),
        .o_peak(o_peak), .o_peak_delay(o_peak_delay),
        .o_rr_valid(o_rr_valid), .o_rr(o_rr), .o_rr_ok(o_rr_ok),
        .o_win_valid(o_win_valid),
        .o_n30(o_n30), .o_sum_rr30(o_sum_rr30), .o_sum_rr2_30(o_sum_rr2_30), .o_sum_d30(o_sum_d30), .o_sum_d2_30(o_sum_d2_30),
        .o_n60(o_n60), .o_sum_rr60(o_sum_rr60), .o_sum_rr2_60(o_sum_rr2_60), .o_sum_d60(o_sum_d60), .o_sum_d2_60(o_sum_d2_60)
    );

    reg [15:0] mem [0:N_SAMPLES-1];
    integer sample_idx = -1;
    integer f_pk, f_rr, f_win, rc;
    reg [8*200:1] line;
    integer n_pk = 0, e_pk = 0, n_rr = 0, e_rr = 0, n_win = 0, e_win = 0;
    integer x_peak, x_conf, x_rr, x_ok, x_end;
    integer x_n30, x_rr30, x_rr2_30, x_d30, x_d2_30, x_n60, x_rr60, x_rr2_60, x_d60, x_d2_60;
    integer i;

    initial begin
        $readmemh("sim/vectors/in.hex", mem);
        f_pk  = $fopen("sim/vectors/peaks.txt", "r");
        f_rr  = $fopen("sim/vectors/rr.txt", "r");
        f_win = $fopen("sim/vectors/windows.txt", "r");
        rc = $fgets(line, f_pk); rc = $fgets(line, f_rr); rc = $fgets(line, f_win);   // 헤더

        repeat (4) @(posedge clk);
        rst_n = 1;
        for (i = 0; i < N_SAMPLES; i = i + 1) begin
            @(posedge clk); i_sample <= $signed(mem[i]); i_valid <= 1; sample_idx <= i;
            @(posedge clk); i_valid <= 0;
            repeat (GAP - 2) @(posedge clk);
        end
        repeat (20) @(posedge clk);
        $display("peaks   : %0d checked, %0d mismatch", n_pk, e_pk);
        $display("rr/sqi  : %0d checked, %0d mismatch", n_rr, e_rr);
        $display("windows : %0d checked, %0d mismatch", n_win, e_win);
        if (e_pk + e_rr + e_win == 0) $display("PASS"); else $display("FAIL");
        $finish;
    end

    // 봉우리: o_peak 는 i_valid 다음 클럭에 뜬다. 그때 sample_idx 는 방금 처리한 샘플.
    always @(posedge clk) if (o_peak) begin
        rc = $fgets(line, f_pk);
        rc = $sscanf(line, "%d %d", x_peak, x_conf);
        n_pk = n_pk + 1;
        if (sample_idx - o_peak_delay !== x_peak || sample_idx !== x_conf) begin
            e_pk = e_pk + 1;
            if (e_pk <= 10) $display("peak #%0d: got pos %0d conf %0d, expected %0d %0d",
                                     n_pk, sample_idx - o_peak_delay, sample_idx, x_peak, x_conf);
        end
    end

    always @(posedge clk) if (o_rr_valid) begin
        rc = $fgets(line, f_rr);
        rc = $sscanf(line, "%d %d %d", x_conf, x_rr, x_ok);
        n_rr = n_rr + 1;
        if (o_rr !== x_rr || o_rr_ok !== x_ok[0]) begin
            e_rr = e_rr + 1;
            if (e_rr <= 10) $display("rr #%0d: got rr %0d ok %0d, expected %0d %0d", n_rr, o_rr, o_rr_ok, x_rr, x_ok);
        end
    end

    always @(posedge clk) if (o_win_valid) begin
        rc = $fgets(line, f_win);
        rc = $sscanf(line, "%d %d %d %d %d %d %d %d %d %d %d", x_end,
                     x_n30, x_rr30, x_rr2_30, x_d30, x_d2_30, x_n60, x_rr60, x_rr2_60, x_d60, x_d2_60);
        n_win = n_win + 1;
        if (o_n30 !== x_n30 || o_sum_rr30 !== x_rr30 || o_sum_rr2_30 !== x_rr2_30 || o_sum_d30 !== x_d30 || o_sum_d2_30 !== x_d2_30 ||
            o_n60 !== x_n60 || o_sum_rr60 !== x_rr60 || o_sum_rr2_60 !== x_rr2_60 || o_sum_d60 !== x_d60 || o_sum_d2_60 !== x_d2_60) begin
            e_win = e_win + 1;
            if (e_win <= 5) $display("win #%0d (end %0d): n30 %0d/%0d rr30 %0d/%0d rr2 %0d/%0d d30 %0d/%0d d2 %0d/%0d | n60 %0d/%0d rr60 %0d/%0d",
                n_win, x_end, o_n30, x_n30, o_sum_rr30, x_rr30, o_sum_rr2_30, x_rr2_30, o_sum_d30, x_d30, o_sum_d2_30, x_d2_30,
                o_n60, x_n60, o_sum_rr60, x_rr60);
        end
    end
endmodule
