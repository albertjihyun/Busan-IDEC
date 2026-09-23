// imu_rule 채점. sim/vectors/imu/cases.txt (scripts/make_imu_vectors.py, 정답은 src/imu_ref.py)와 비트 단위로 대조.
//
//   iverilog -g2012 -o sim/imu.vvp rtl/imu_rule.v sim/tb_imu_rule.v && vvp -n sim/imu.vvp
//   iverilog -g2012 -Ptb_imu_rule.FWD_SIGN=1 -Ptb_imu_rule.VERT_AXIS=0 -o sim/imu_chest.vvp rtl/imu_rule.v sim/tb_imu_rule.v
//   vvp -n sim/imu_chest.vvp +vec=data/processed/stage6/imu_dalia_S1.txt      (DaLiA 가슴 축: 앞=+Z 세로=X)
//
// 줄 형식: case k ax ay az nod lp_f lp_v cnt.  case 가 바뀌면 리셋. 샘플 간격은 실제 12만 클럭 대신 8클럭.
// 샘플마다 필터·카운터 레지스터(계층 참조)와 그 샘플 뒤 4클럭 안의 o_nod 펄스 수를 정답과 비교한다.

`timescale 1ns/1ps
module tb_imu_rule #(
    // 축 매핑. DaLiA 가슴 파일은 앞=+Z 세로=X 로 만들었으므로
    //   iverilog -g2012 -Ptb_imu_rule.FWD_SIGN=1 -Ptb_imu_rule.VERT_AXIS=0 ...
    parameter integer FWD_AXIS = 2, FWD_SIGN = -1, VERT_AXIS = 1
);
    reg clk = 0, rst_n = 0, i_imu_valid = 0;
    reg signed [15:0] i_ax = 0, i_ay = 0, i_az = 0;
    always #5 clk = ~clk;

    wire o_nod, o_tilt;
    imu_rule #(.FWD_AXIS(FWD_AXIS), .FWD_SIGN(FWD_SIGN), .VERT_AXIS(VERT_AXIS)) dut (
        .clk(clk), .rst_n(rst_n), .i_imu_valid(i_imu_valid),
        .i_ax(i_ax), .i_ay(i_ay), .i_az(i_az), .o_nod(o_nod), .o_tilt(o_tilt)
    );

    integer f, rc, k;
    reg [8*400:1] line;
    reg [8*64:1]  cname, cname_prev, vec;
    integer x_k, x_ax, x_ay, x_az, x_nod, x_lpf, x_lpv, x_cnt;
    integer n_chk = 0, n_err = 0, n_nod_exp = 0, n_nod_got = 0, n_cases = 0;
    integer n_pulse;

    task do_reset;
        begin
            rst_n = 0; i_imu_valid = 0;
            repeat (3) @(posedge clk);
            #1 rst_n = 1;
            @(posedge clk);
        end
    endtask

    task push_sample;
        begin
            @(posedge clk); #1;
            i_ax = x_ax; i_ay = x_ay; i_az = x_az; i_imu_valid = 1;
            @(posedge clk); #1;
            i_imu_valid = 0;
            n_pulse = 0;
            if (o_nod) n_pulse = n_pulse + 1;          // 펄스는 valid 다음 클럭에 선다
            for (k = 0; k < 3; k = k + 1) begin
                @(posedge clk); #1;
                if (o_nod) n_pulse = n_pulse + 1;
            end
            n_chk = n_chk + 1;
            n_nod_exp = n_nod_exp + x_nod;
            n_nod_got = n_nod_got + n_pulse;
            if ($signed(dut.lp_f) !== x_lpf || $signed(dut.lp_v) !== x_lpv || dut.cnt !== x_cnt || n_pulse !== x_nod) begin
                n_err = n_err + 1;
                if (n_err <= 10)
                    $display("MISMATCH %0s k=%0d a=(%0d,%0d,%0d) exp lp_f=%0d lp_v=%0d cnt=%0d nod=%0d  got lp_f=%0d lp_v=%0d cnt=%0d nod=%0d",
                             cname, x_k, x_ax, x_ay, x_az, x_lpf, x_lpv, x_cnt, x_nod,
                             $signed(dut.lp_f), $signed(dut.lp_v), dut.cnt, n_pulse);
            end
        end
    endtask

    initial begin
        if (!$value$plusargs("vec=%s", vec)) vec = "sim/vectors/imu/cases.txt";
        f = $fopen(vec, "r");
        if (f == 0) begin $display("cannot open %0s", vec); $display("FAIL"); $finish; end
        rc = $fgets(line, f);                     // 헤더
        cname_prev = "";
        while (!$feof(f)) begin
            rc = $fscanf(f, "%s %d %d %d %d %d %d %d %d\n", cname, x_k, x_ax, x_ay, x_az, x_nod, x_lpf, x_lpv, x_cnt);
            if (rc == 9) begin
                if (cname != cname_prev) begin
                    do_reset;
                    cname_prev = cname;
                    n_cases = n_cases + 1;
                end
                push_sample;
            end
        end
        $fclose(f);
        $display("%0s: cases %0d, samples %0d checked, %0d mismatch, nod pulses exp %0d got %0d",
                 vec, n_cases, n_chk, n_err, n_nod_exp, n_nod_got);
        if (n_err == 0 && n_chk > 0) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
