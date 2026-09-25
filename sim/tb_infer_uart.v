// 판정 → 통신 채점. MPD-DF 50명 판정 벡터를 infer_top 에 넣고, 통신 블록(uart_tx_ble)이 보낸 바이트를 UART 수신기로 받는다.
//
//   iverilog -g2012 -o sim/infer_uart.vvp rtl/classifier.v rtl/imu_rule.v rtl/infer_top.v rtl/uart_tx.v rtl/uart_tx_ble.v sim/tb_infer_uart.v && vvp -n sim/infer_uart.vvp
//   (통신 블록 원본은 data/communication_module/ 에 있다)
//
// 블록마다 hold·drowsy·alert 를 정답(infer_ref, 30초 간격 규칙 포함)과 대조하고, 그 블록 동안 받은 바이트 수가 alert 와 같은지,
// 바이트가 전부 0x01 이고 프레이밍이 맞는지 센다. UART 는 CLKS_PER_BIT 8 로 줄이고 블록 간격을 200클럭(한 프레임 80클럭보다 넓게) 둔다.

`timescale 1ns/1ps
module tb_infer_uart;
    localparam integer CPB = 8;
    reg clk = 0, rst_n = 0, i_win_valid = 0;
    reg [7:0]  i_n60 = 0;
    reg [16:0] i_sum_rr60 = 0;
    reg [7:0]  i_bad60 = 0;
    always #5 clk = ~clk;

    wire alert, ready, tx, ble_wake;
    infer_top dut (
        .clk(clk), .rst_n(rst_n), .i_win_valid(i_win_valid), .i_n60(i_n60), .i_sum_rr60(i_sum_rr60), .i_bad60(i_bad60),
        .i_imu_valid(1'b0), .i_accel_x(16'sd0), .i_accel_y(16'sd0), .i_accel_z(16'sd0),
        .i_nod_event(1'b0), .i_nod_sustained(1'b0), .i_pitch_sign_ok(1'b1),
        .alert(alert), .ready(ready));
    uart_tx_ble #(.CLKS_PER_BIT(CPB)) u_ble (.clk(clk), .rst_n(rst_n), .alert(alert), .tx(tx), .BLE_WAKE(ble_wake));

    // UART 수신기 (8N1, LSB 먼저)
    integer n_byte = 0, n_bad_byte = 0, n_frame_err = 0, bi;
    reg [7:0] rb;
    initial forever begin
        @(negedge tx);
        repeat (CPB / 2) @(posedge clk);
        if (tx !== 1'b0) n_frame_err = n_frame_err + 1;
        for (bi = 0; bi < 8; bi = bi + 1) begin repeat (CPB) @(posedge clk); rb[bi] = tx; end
        repeat (CPB) @(posedge clk);
        if (tx !== 1'b1) n_frame_err = n_frame_err + 1;
        n_byte = n_byte + 1;
        if (rb !== 8'h01) n_bad_byte = n_bad_byte + 1;
    end
    integer n_wake_low = 0;
    always @(posedge clk) if (rst_n && ble_wake !== 1'b1) n_wake_low = n_wake_low + 1;

    integer f, rc, sid, k;
    reg [8*200:1] line;
    reg [8*40:1]  fname;
    integer x_blk, x_n, x_s, x_b, x_hold, x_drowsy, x_alert;
    integer n_chk = 0, n_err = 0, n_alert = 0, n_exp = 0, n_alert_err = 0, n_byte_err = 0, n_pulse, byte0;

    task do_reset;
        begin
            rst_n = 0; i_win_valid = 0;
            repeat (3) @(posedge clk);
            #1 rst_n = 1;
            @(posedge clk);
        end
    endtask

    initial begin
        for (sid = 1; sid <= 50; sid = sid + 1) begin
            $sformat(fname, "sim/vectors/infer/%02d.txt", sid);
            f = $fopen(fname, "r");
            if (f == 0) begin $display("cannot open %0s", fname); $display("FAIL"); $finish; end
            rc = $fgets(line, f);                 // 헤더
            do_reset;
            while (!$feof(f)) begin
                rc = $fscanf(f, "%d %d %d %d %d %d %d\n", x_blk, x_n, x_s, x_b, x_hold, x_drowsy, x_alert);
                if (rc == 7) begin
                    byte0 = n_byte;
                    @(posedge clk); #1;
                    i_n60 = x_n; i_sum_rr60 = x_s; i_bad60 = x_b; i_win_valid = 1;
                    @(posedge clk); #1;
                    i_win_valid = 0;
                    n_pulse = 0;
                    for (k = 0; k < 200; k = k + 1) begin @(posedge clk); #1; if (alert) n_pulse = n_pulse + 1; end
                    n_chk = n_chk + 1; n_alert = n_alert + n_pulse; n_exp = n_exp + x_alert;
                    if (dut.c_hold !== x_hold[0] || dut.c_drowsy !== x_drowsy[0]) n_err = n_err + 1;
                    if (n_pulse !== x_alert) n_alert_err = n_alert_err + 1;
                    if (n_byte - byte0 !== x_alert) n_byte_err = n_byte_err + 1;
                end
            end
            $fclose(f);
        end
        $display("blocks %0d, hold/drowsy mismatch %0d, alert %0d (expected %0d, per-block mismatch %0d)",
                 n_chk, n_err, n_alert, n_exp, n_alert_err);
        $display("uart bytes %0d (per-block mismatch %0d), not 0x01 %0d, framing err %0d, ble_wake low clocks %0d",
                 n_byte, n_byte_err, n_bad_byte, n_frame_err, n_wake_low);
        if (n_err == 0 && n_alert_err == 0 && n_byte_err == 0 && n_byte == n_exp && n_bad_byte == 0 &&
            n_frame_err == 0 && n_wake_low == 0 && n_chk > 0) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
