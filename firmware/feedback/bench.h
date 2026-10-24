#pragma once
// Compile with -DSTRIDE_SELF_TEST=1 (sensor), 2 (buzzer), or 3 (motor).
// Bench mode never starts networking or accepts remote commands.
#ifndef STRIDE_SELF_TEST
#define STRIDE_SELF_TEST 0
#endif
static_assert(STRIDE_SELF_TEST>=0 && STRIDE_SELF_TEST<=3,"STRIDE_SELF_TEST must be 0..3");

namespace stride {
// One 100 ms pulse after a 2 s settling interval; never repeats, even after wrap.
class BenchPulse {
 public:
  bool tick(uint32_t elapsed) {
    if(finished || elapsed>=2100) { finished=true; return false; }
    return elapsed>=2000;
  }
 private:
  bool finished=false;
};
}
