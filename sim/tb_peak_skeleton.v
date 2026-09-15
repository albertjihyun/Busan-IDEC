// 봉우리 검출 + 누산 블록 테스트벤치 뼈대.
// sim/vectors/in.hex 를 240 SPS 간격으로 밀어 넣고, DUT 출력을 정답과 비교한다.
// DUT 포트 이름은 하드웨어 담당이 정한 것으로 바꿔 쓴다. 여기서는 datapath-request.md 3절 이름.
//
//   iverilog -o sim.vvp rtl/*.v sim/tb_peak_skeleton.v && vvp -n sim.vvp
//
// 확인 순서: 봉우리 위치 → RR/SQI → 5초 블록 → 창 합. 앞이 틀리면 뒤는 볼 필요 없다.

`timescale 1ns/1ps
module tb_peak_skeleton;
  localparam N_SAMPLES = 28800;        // in.hex 줄 수. make_vectors.py 출력과 맞춘다
  localparam CLK_PER   = 83.333;       // 12 MHz
  localparam SAMPLE_PER_CLK = 50000;   // 12 MHz / 240 Hz

  reg clk = 0, rst_n = 0;
  reg signed [15:0] sample = 0;
  reg sample_valid = 0;
  always #(CLK_PER/2) clk = ~clk;

  // ---- DUT (이름·폭은 실제 모듈에 맞춰 수정) ----
  wire        o_peak;          // 봉우리 확정 1클럭 펄스
  wire [4:0]  o_peak_delay;    // 확정 시점이 봉우리보다 몇 샘플 늦은지 (0~24)
  wire        o_win_valid;
  wire [7:0]  o_n30;
  wire [16:0] o_sum_rr30;
  wire [24:0] o_sum_rr2_30;
  wire signed [16:0] o_sum_d30;
  wire [23:0] o_sum_d2_30;
  // dut u_dut (.clk(clk), .rst_n(rst_n), .i_sample(sample), .i_valid(sample_valid), ...);

  // ---- 입력 벡터 ----
  reg [15:0] mem [0:N_SAMPLES-1];
  integer i, n_peak = 0, n_win = 0, err_peak = 0, err_win = 0;
  integer f_peaks, f_win, exp_peak, exp_conf, exp_n30, exp_sum_rr30, dummy;

  initial begin
    $readmemh("sim/vectors/in.hex", mem);
    f_peaks = $fopen("sim/vectors/peaks.txt", "r");
    f_win   = $fopen("sim/vectors/windows.txt", "r");
    dummy = $fgets(dummy, f_peaks);  // 헤더 줄 버림 (구현에 따라 $fscanf로 문자열 소비)
    dummy = $fgets(dummy, f_win);

    #(CLK_PER*10) rst_n = 1;
    for (i = 0; i < N_SAMPLES; i = i + 1) begin
      @(posedge clk); sample <= mem[i]; sample_valid <= 1;
      @(posedge clk); sample_valid <= 0;
      repeat (SAMPLE_PER_CLK - 2) @(posedge clk);   // 실제 간격. 시뮬 시간이 길면 줄여도 됨
    end
    $display("peaks: %0d checked, %0d mismatches", n_peak, err_peak);
    $display("windows: %0d checked, %0d mismatches", n_win, err_win);
    $finish;
  end

  // ---- 봉우리 비교: 확정 펄스마다 정답 한 줄과 대조 ----
  // 정답 peak_i = 현재 샘플 번호 - o_peak_delay 여야 한다
  integer sample_idx = -1;
  always @(posedge clk) if (sample_valid) sample_idx <= sample_idx + 1;
  always @(posedge clk) if (o_peak) begin
    dummy = $fscanf(f_peaks, "%d %d\n", exp_peak, exp_conf);
    n_peak = n_peak + 1;
    if (sample_idx - o_peak_delay !== exp_peak) begin
      err_peak = err_peak + 1;
      $display("peak mismatch #%0d: got %0d expected %0d", n_peak, sample_idx - o_peak_delay, exp_peak);
    end
  end

  // ---- 창 비교: o_win_valid마다 30초 창 값 대조 (60초·나머지 필드도 같은 식으로) ----
  always @(posedge clk) if (o_win_valid) begin
    dummy = $fscanf(f_win, "%d %d %d %d %d %d %d %d %d %d %d\n",
                    dummy, exp_n30, exp_sum_rr30, dummy, dummy, dummy, dummy, dummy, dummy, dummy, dummy);
    n_win = n_win + 1;
    if (o_n30 !== exp_n30 || o_sum_rr30 !== exp_sum_rr30) begin
      err_win = err_win + 1;
      $display("window mismatch #%0d: n30 %0d/%0d sum_rr30 %0d/%0d", n_win, o_n30, exp_n30, o_sum_rr30, exp_sum_rr30);
    end
  end
endmodule
