// 심박 판정 보류(hold) 중 고개 떨굼 경보 누락 시험. infer_top 에 직접 입력을 넣는 자가 채점 시험.
//
//   iverilog -g2012 -o sim/hold_nod.vvp rtl/classifier.v rtl/imu_rule.v rtl/infer_top.v sim/tb_infer_hold_nod.v && vvp -n sim/hold_nod.vvp
//
// 목표: 심박 판정이 보류 중이어도 떨굼 사건 하나마다 alert 펄스가 나온다(누락 0).
//   A. 기준선 미완성 보류(리셋 직후, 좋은 1분 창 3개 전): 가속도 떨굼, o_nod_event, o_nod_sustained 상승 에지
//   B. 나쁜 창 보류(기준선 완성 뒤 n60 < 30 또는 3 × bad60 > n60): 같은 세 가지
//   C. 대조: 보류 중 떨굼 없이 졸림처럼 보이는 창만 넣으면 alert 0. 보류가 풀린 좋은 졸림 창은 alert 1(심박 경로가 살아 있음)
//   D. 부호 미확정(i_pitch_sign_ok = 0)이면 o_nod_event·o_nod_sustained 무시(설계 결정, 목표의 실패가 아님)
// 사건을 넣을 때마다 classifier 출력 o_hold 가 1인지 확인하고, 사건 뒤 alert 펄스 수를 기대값과 비교한다.
// 블록 간격은 실제 6만 클럭 대신 수백 클럭, IMU 샘플 간격은 12만 클럭 대신 4클럭. 설계가 간격에 의존하지 않는다.
// 가속도: ±2 g = 16,384 LSB/g. 앞축 = -Z, 세로축 = |Y|. 바로 선 자세 (0, 16384, 0), 50° 숙임 (0, 10531, -12551).

`timescale 1ns/1ps
module tb_infer_hold_nod;
    reg clk = 0, rst_n = 0;
    reg i_win_valid = 0;
    reg [7:0]  i_n60 = 0;
    reg [16:0] i_sum_rr60 = 0;
    reg [7:0]  i_bad60 = 0;
    reg i_imu_valid = 0;
    reg signed [15:0] i_ax = 0, i_ay = 0, i_az = 0;
    reg i_nod_event = 0, i_nod_sustained = 0, i_pitch_sign_ok = 1;
    always #5 clk = ~clk;

    wire alert, ready;
    infer_top dut (
        .clk(clk), .rst_n(rst_n),
        .i_win_valid(i_win_valid), .i_n60(i_n60), .i_sum_rr60(i_sum_rr60), .i_bad60(i_bad60),
        .i_imu_valid(i_imu_valid), .i_accel_x(i_ax), .i_accel_y(i_ay), .i_accel_z(i_az),
        .i_nod_event(i_nod_event), .i_nod_sustained(i_nod_sustained), .i_pitch_sign_ok(i_pitch_sign_ok),
        .alert(alert), .ready(ready));

    // alert 펄스 총수
    integer n_alert = 0;
    always @(posedge clk) if (rst_n && alert) n_alert = n_alert + 1;

    // 판정 출력 기록
    integer n_blk = 0, n_blk_hold = 0;
    always @(posedge clk) if (rst_n && dut.c_valid) begin
        n_blk = n_blk + 1;
        if (dut.c_hold) n_blk_hold = n_blk_hold + 1;
    end

    // 집계: 목표(보류 중 떨굼) / 대조 / 부호 미확정
    integer t_ev = 0, t_al = 0, t_miss = 0, t_extra = 0, t_notheld = 0;
    integer n_fail = 0;
    integer a0, d, i;

    task check(input [8*64:1] name, input integer exp, input integer got, input integer target);
        begin
            if (target) begin
                t_ev = t_ev + exp;
                t_al = t_al + got;
                if (got < exp) t_miss = t_miss + (exp - got);
                if (got > exp) t_extra = t_extra + (got - exp);
            end
            if (got == exp) $display("  PASS %0s: expected %0d, alert %0d", name, exp, got);
            else begin
                $display("  FAIL %0s: expected %0d, alert %0d", name, exp, got);
                n_fail = n_fail + 1;
            end
        end
    endtask

    task hold_must_be(input v);
        begin
            if (dut.c_hold !== v) begin
                $display("  FAIL precondition: o_hold=%b (want %b) ready=%b", dut.c_hold, v, ready);
                n_fail = n_fail + 1;
                t_notheld = t_notheld + 1;
            end
        end
    endtask

    // 5초 블록 하나. 판정 출력(3클럭 뒤)과 alert 까지 기다린다
    task block(input integer n, input integer sum, input integer bad);
        begin
            @(posedge clk); #1;
            i_n60 = n; i_sum_rr60 = sum; i_bad60 = bad; i_win_valid = 1;
            @(posedge clk); #1;
            i_win_valid = 0;
            repeat (20) @(posedge clk);
            #1;
        end
    endtask

    task imu(input integer ay, input integer az);
        begin
            @(posedge clk); #1;
            i_ax = 0; i_ay = ay; i_az = az; i_imu_valid = 1;
            @(posedge clk); #1;
            i_imu_valid = 0;
            repeat (2) @(posedge clk);
            #1;
        end
    endtask

    // 가속도 떨굼: 선 자세 40샘플 → 숙임 ns 샘플 → 선 자세 60샘플. alert 수 반환
    task accel_drop(input integer ns, output integer got);
        begin
            for (i = 0; i < 40; i = i + 1) imu(16384, 0);
            a0 = n_alert;
            for (i = 0; i < ns; i = i + 1) imu(10531, -12551);
            for (i = 0; i < 60; i = i + 1) imu(16384, 0);
            repeat (5) @(posedge clk); #1;
            got = n_alert - a0;
        end
    endtask

    task nod_event(output integer got);
        begin
            a0 = n_alert;
            @(posedge clk); #1; i_nod_event = 1;
            @(posedge clk); #1; i_nod_event = 0;
            repeat (10) @(posedge clk); #1;
            got = n_alert - a0;
        end
    endtask

    // 상태 신호: 200클럭 유지(그동안 에지 하나 = 펄스 하나여야 함) 뒤 내림
    task nod_sustained(output integer got);
        begin
            a0 = n_alert;
            @(posedge clk); #1; i_nod_sustained = 1;
            repeat (200) @(posedge clk); #1;
            i_nod_sustained = 0;
            repeat (10) @(posedge clk); #1;
            got = n_alert - a0;
        end
    endtask

    // 판정 펄스(c_valid)와 같은 클럭에 o_nod_event 가 겹치는 경우
    task nod_event_on_cvalid(input integer n, input integer sum, input integer bad, output integer got);
        begin
            a0 = n_alert;
            @(posedge clk); #1;
            i_n60 = n; i_sum_rr60 = sum; i_bad60 = bad; i_win_valid = 1;
            @(posedge clk); #1;
            i_win_valid = 0;
            while (dut.c_valid !== 1'b1) begin @(posedge clk); #1; end
            i_nod_event = 1;                   // c_valid 와 같은 클럭 경계에서 잡힌다
            @(posedge clk); #1; i_nod_event = 0;
            repeat (20) @(posedge clk); #1;
            got = n_alert - a0;
        end
    endtask

    // 창 값 (RR 단위 = 240 Hz 샘플). 평상 RR 1 s = 240
    localparam integer N_OK = 60, SUM_OK = 60 * 240;          // 기준선용 좋은 창
    localparam integer SUM_SLOW = 60 * 300;                  // mean_rb 1.25 (졸림 쪽, T 1.06 초과)
    integer k;

    initial begin
        rst_n = 0;
        repeat (4) @(posedge clk); #1;
        rst_n = 1;
        repeat (2) @(posedge clk); #1;

        // ---------------- A. 기준선 미완성 보류 ----------------
        $display("A. hold: baseline not complete (ready=0)");
        block(N_OK, SUM_SLOW, 0);                  // 첫 블록: 판정 hold, 기준선 창 아직 아님
        hold_must_be(1);
        accel_drop(100, d);         check("A1 accel drop 1.0 s", 1, d, 1);
        hold_must_be(1);
        accel_drop(620, d);         check("A2 accel drop 6.2 s (0.5 s + 5 s repeat)", 2, d, 1);
        hold_must_be(1);
        i_pitch_sign_ok = 1;
        nod_event(d);               check("A3 nod_event (sign_ok=1)", 1, d, 1);
        nod_sustained(d);           check("A4 nod_sustained rise (sign_ok=1)", 1, d, 1);
        nod_event_on_cvalid(N_OK, SUM_SLOW, 0, d);
                                    check("A5 nod_event on c_valid clock", 1, d, 1);
        // 대조: 나머지 기준선 블록. 기준선 전이라 r = 0, 비교식은 참이지만 hold 라 alert 0
        a0 = n_alert;
        for (k = 0; k < 34; k = k + 1) block(N_OK, SUM_OK, 0);
        d = n_alert - a0;           check("A6 control: 34 hold blocks, no IMU event", 0, d, 0);
        if (ready !== 1'b1) begin $display("  FAIL baseline not ready after 36 blocks"); n_fail = n_fail + 1; end
        else $display("  ready=1 after 36 good blocks (baseline complete)");

        // ---------------- B. 나쁜 창 보류 ----------------
        $display("B. hold: bad window (ready=1)");
        a0 = n_alert;
        block(20, 20 * 300, 0);                    // n60 < 30
        hold_must_be(1);
        block(60, SUM_SLOW, 30);                   // 3 x 30 > 60
        hold_must_be(1);
        d = n_alert - a0;           check("B0 control: 2 bad windows (drowsy-like), no IMU event", 0, d, 0);
        accel_drop(100, d);         check("B1 accel drop 1.0 s (bad60 hold)", 1, d, 1);
        hold_must_be(1);
        nod_event(d);               check("B2 nod_event (sign_ok=1)", 1, d, 1);
        nod_sustained(d);           check("B3 nod_sustained rise (sign_ok=1)", 1, d, 1);
        block(20, 20 * 300, 0);                    // n60 < 30 으로 바꿔서 한 번 더
        hold_must_be(1);
        accel_drop(100, d);         check("B4 accel drop 1.0 s (n60 hold)", 1, d, 1);
        nod_event(d);               check("B5 nod_event (sign_ok=1)", 1, d, 1);
        nod_sustained(d);           check("B6 nod_sustained rise (sign_ok=1)", 1, d, 1);
        nod_event_on_cvalid(20, 20 * 300, 0, d);
                                    check("B7 nod_event on c_valid clock", 1, d, 1);
        hold_must_be(1);

        // ---------------- C. 심박 경로 확인 ----------------
        $display("C. heart path sanity (hold released)");
        a0 = n_alert;
        block(N_OK, SUM_SLOW, 0);                  // 좋은 졸림 창
        hold_must_be(0);
        d = n_alert - a0;           check("C1 good drowsy window -> heart alert", 1, d, 0);
        block(10, 10 * 300, 0);                    // 다시 보류로
        hold_must_be(1);

        // ---------------- D. 부호 미확정 ----------------
        $display("D. pitch_sign_ok=0 (gyro nod ignored by design)");
        i_pitch_sign_ok = 0;
        nod_event(d);               check("D1 nod_event ignored (sign_ok=0)", 0, d, 0);
        nod_sustained(d);           check("D2 nod_sustained ignored (sign_ok=0)", 0, d, 0);
        accel_drop(100, d);         check("D3 accel drop still alerts (sign_ok=0, hold)", 1, d, 1);
        i_pitch_sign_ok = 1;

        $display("blocks %0d (hold %0d), total alert pulses %0d", n_blk, n_blk_hold, n_alert);
        $display("hold-nod: %0d/%0d alerts, missed %0d, extra %0d, not-in-hold %0d", t_al, t_ev, t_miss, t_extra, t_notheld);
        if (n_fail == 0 && t_miss == 0) $display("PASS"); else $display("FAIL (%0d checks)", n_fail);
        $finish;
    end
endmodule
