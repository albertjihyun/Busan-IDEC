// infer_top(classifier) 채점. 판정 벡터 파일의 파이썬 정수 정답(infer_ref)과 비트 단위로 대조.
//
//   iverilog -g2012 -o sim/infer.vvp rtl/classifier.v rtl/imu_rule.v rtl/infer_top.v sim/tb_classifier.v && vvp -n sim/infer.vvp
//
// 입력 줄: block n60 sum_rr60 bad60 hold drowsy. 50명 파일(NN.txt)은 사람마다 리셋하고 블록 75,186개를 전부 넣는다. edge.txt 는 case 이름이 바뀔 때 리셋.
// 블록 간격은 실제 6만 클럭 대신 8클럭. 설계가 간격에 의존하지 않는다.
// alert 도 같이 센다: 판정 하나에 펄스가 정확히 drowsy 개(0 또는 1)여야 한다. hold·drowsy 는 classifier 출력을 계층 참조로 본다.

`timescale 1ns/1ps
module tb_classifier;
    reg clk = 0, rst_n = 0, i_win_valid = 0;
    reg [7:0]  i_n60 = 0;
    reg [16:0] i_sum_rr60 = 0;
    reg [7:0]  i_bad60 = 0;
    always #5 clk = ~clk;

    wire alert, ready;
    infer_top dut (
        .clk(clk), .rst_n(rst_n), .i_win_valid(i_win_valid), .i_n60(i_n60), .i_sum_rr60(i_sum_rr60), .i_bad60(i_bad60),
        .i_imu_valid(1'b0), .i_accel_x(16'sd0), .i_accel_y(16'sd0), .i_accel_z(16'sd0),
        .i_nod_event(1'b0), .i_nod_sustained(1'b0),
        .alert(alert), .ready(ready)
    );
    wire drowsy = dut.c_drowsy;
    wire hold   = dut.c_hold;

    integer f, rc, sid;
    reg [8*200:1] line;
    reg [8*32:1]  cname, cname_prev;
    integer x_blk, x_n, x_s, x_b, x_hold, x_drowsy;
    integer n_chk = 0, n_err = 0, n_alert_err = 0, n_files = 0;
    integer sub_err;
    integer n_alert;
    reg [8*40:1] fname;

    task do_reset;
        begin
            rst_n = 0; i_win_valid = 0;
            repeat (3) @(posedge clk);
            #1 rst_n = 1;
            @(posedge clk);
        end
    endtask

    // 블록 하나 넣고 판정(3클럭 뒤)을 정답과 비교
    task push_block(input integer n, input integer s, input integer bd, input integer e_hold, input integer e_drowsy, input [8*40:1] tag, input integer blk);
        integer k;
        begin
            @(posedge clk); #1;
            i_n60 = n; i_sum_rr60 = s; i_bad60 = bd; i_win_valid = 1;
            @(posedge clk); #1;
            i_win_valid = 0;
            n_alert = 0;
            for (k = 0; k < 4; k = k + 1) begin
                @(posedge clk); #1;
                if (alert) n_alert = n_alert + 1;
            end
            n_chk = n_chk + 1;
            if (hold !== e_hold[0] || drowsy !== e_drowsy[0]) begin
                n_err = n_err + 1; sub_err = sub_err + 1;
                if (n_err <= 10)
                    $display("MISMATCH %0s blk %0d: n60=%0d sum=%0d bad=%0d  exp hold=%0d drowsy=%0d  got hold=%0d drowsy=%0d",
                             tag, blk, n, s, bd, e_hold, e_drowsy, hold, drowsy);
            end
            if (n_alert !== e_drowsy) begin
                n_alert_err = n_alert_err + 1;
                if (n_alert_err <= 5)
                    $display("ALERT    %0s blk %0d: exp %0d pulse got %0d", tag, blk, e_drowsy, n_alert);
            end
            repeat (2) @(posedge clk);
        end
    endtask

    initial begin
        // 50명
        for (sid = 1; sid <= 50; sid = sid + 1) begin
            $sformat(fname, "sim/vectors/infer/%02d.txt", sid);
            f = $fopen(fname, "r");
            if (f == 0) begin
                $display("cannot open %0s", fname);
            end else begin
                n_files = n_files + 1;
                rc = $fgets(line, f);                 // 헤더
                do_reset;
                sub_err = 0;
                while (!$feof(f)) begin
                    rc = $fscanf(f, "%d %d %d %d %d %d\n", x_blk, x_n, x_s, x_b, x_hold, x_drowsy);
                    if (rc == 6) push_block(x_n, x_s, x_b, x_hold, x_drowsy, fname, x_blk);
                end
                $fclose(f);
                if (sub_err) $display("subject %02d: %0d mismatch", sid, sub_err);
            end
        end
        // 경계 사례
        f = $fopen("sim/vectors/infer/edge.txt", "r");
        if (f == 0) $display("cannot open edge.txt");
        else begin
            n_files = n_files + 1;
            rc = $fgets(line, f);
            cname_prev = "";
            sub_err = 0;
            while (!$feof(f)) begin
                rc = $fscanf(f, "%s %d %d %d %d %d %d\n", cname, x_blk, x_n, x_s, x_b, x_hold, x_drowsy);
                if (rc == 7) begin
                    if (cname != cname_prev) begin
                        do_reset;
                        cname_prev = cname;
                    end
                    push_block(x_n, x_s, x_b, x_hold, x_drowsy, cname, x_blk);
                end
            end
            $fclose(f);
            if (sub_err) $display("edge: %0d mismatch", sub_err);
        end
        $display("files %0d, blocks %0d checked, %0d mismatch, alert %0d mismatch", n_files, n_chk, n_err, n_alert_err);
        if (n_err == 0 && n_alert_err == 0 && n_files == 51) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
