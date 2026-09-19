// infer_top(classifier) 채점. sim/vectors/infer/ 의 파이썬 정수 정답(src/infer_ref.py)과 비트 단위로 대조.
//
//   iverilog -g2012 -o sim/infer.vvp rtl/classifier.v rtl/infer_top.v sim/tb_classifier.v && vvp -n sim/infer.vvp
//
// 50명 파일(NN.txt)은 사람마다 리셋하고 블록 75,186개를 전부 넣는다. edge.txt 는 case 이름이 바뀔 때 리셋.
// 블록 간격은 실제 6만 클럭 대신 8클럭. 설계가 간격에 의존하지 않는다.
// changed 도 같이 센다: drowsy 나 hold 가 직전 판정과 다를 때만 1펄스여야 한다.

`timescale 1ns/1ps
module tb_classifier;
    reg clk = 0, rst_n = 0, i_win_valid = 0;
    reg [7:0]  i_n60 = 0;
    reg [16:0] i_sum_rr60 = 0;
    always #5 clk = ~clk;

    wire drowsy, hold, head_nod, changed, ready;
    infer_top dut (
        .clk(clk), .rst_n(rst_n), .i_win_valid(i_win_valid), .i_n60(i_n60), .i_sum_rr60(i_sum_rr60),
        .drowsy(drowsy), .hold(hold), .head_nod(head_nod), .changed(changed), .ready(ready)
    );

    integer f, rc, sid;
    reg [8*200:1] line;
    reg [8*32:1]  cname, cname_prev;
    integer x_blk, x_n, x_s, x_hold, x_drowsy;
    integer n_chk = 0, n_err = 0, n_chg_err = 0, n_files = 0;
    integer sub_err;
    reg prev_drowsy, prev_hold, exp_changed, seen_changed;
    reg [8*40:1] fname;

    task do_reset;
        begin
            rst_n = 0; i_win_valid = 0;
            repeat (3) @(posedge clk);
            #1 rst_n = 1;
            @(posedge clk);
            prev_drowsy = 0; prev_hold = 1;
        end
    endtask

    // 블록 하나 넣고 판정(3클럭 뒤)을 정답과 비교
    task push_block(input integer n, input integer s, input integer e_hold, input integer e_drowsy, input [8*40:1] tag, input integer blk);
        integer k;
        begin
            @(posedge clk); #1;
            i_n60 = n; i_sum_rr60 = s; i_win_valid = 1;
            @(posedge clk); #1;
            i_win_valid = 0;
            seen_changed = 0;
            for (k = 0; k < 4; k = k + 1) begin
                @(posedge clk); #1;
                if (changed) seen_changed = 1;
            end
            n_chk = n_chk + 1;
            if (hold !== e_hold[0] || drowsy !== e_drowsy[0]) begin
                n_err = n_err + 1; sub_err = sub_err + 1;
                if (n_err <= 10)
                    $display("MISMATCH %0s blk %0d: n60=%0d sum=%0d  exp hold=%0d drowsy=%0d  got hold=%0d drowsy=%0d",
                             tag, blk, n, s, e_hold, e_drowsy, hold, drowsy);
            end
            exp_changed = (hold != prev_hold) || (drowsy != prev_drowsy);
            if (seen_changed !== exp_changed) begin
                n_chg_err = n_chg_err + 1;
                if (n_chg_err <= 5)
                    $display("CHANGED  %0s blk %0d: exp %0d got %0d", tag, blk, exp_changed, seen_changed);
            end
            prev_hold = hold; prev_drowsy = drowsy;
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
                    rc = $fscanf(f, "%d %d %d %d %d\n", x_blk, x_n, x_s, x_hold, x_drowsy);
                    if (rc == 5) push_block(x_n, x_s, x_hold, x_drowsy, fname, x_blk);
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
                rc = $fscanf(f, "%s %d %d %d %d %d\n", cname, x_blk, x_n, x_s, x_hold, x_drowsy);
                if (rc == 6) begin
                    if (cname != cname_prev) begin
                        do_reset;
                        cname_prev = cname;
                    end
                    push_block(x_n, x_s, x_hold, x_drowsy, cname, x_blk);
                end
            end
            $fclose(f);
            if (sub_err) $display("edge: %0d mismatch", sub_err);
        end
        $display("files %0d, blocks %0d checked, %0d mismatch, changed %0d mismatch", n_files, n_chk, n_err, n_chg_err);
        if (n_err == 0 && n_chg_err == 0 && n_files == 51) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
