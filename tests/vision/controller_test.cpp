#include "../../firmware/feedback/controller.h"
#include <cassert>
#include "../../firmware/feedback/bench.h"
int main() {
  stride::BenchPulse pulse;
  assert(!pulse.tick(0)); assert(!pulse.tick(1999));
  assert(pulse.tick(2000)); assert(pulse.tick(2099));
  assert(!pulse.tick(2100)); assert(!pulse.tick(2000)); // Cannot replay after completion.
  stride::BenchPulse delayed;
  assert(!delayed.tick(5000)); assert(!delayed.tick(2000));

  stride::Controller c;
  assert(c.currentBand()==stride::Band::Unknown);
  for(int i=0;i<3;++i)c.sample(120,true,100);
  assert(c.currentBand()==stride::Band::Clear);
  assert(c.command("a",stride::Pattern::Right,1500,100,100));
  assert(c.tick(100).motor);
  assert(!c.tick(300).motor);
  c.sample(120,true,400);
  assert(c.tick(500).motor);
  assert(!c.command("a",stride::Pattern::Left,1500,0,500));
  c.linkLost(); assert(!c.tick(500).motor);
  for(int i=0;i<3;++i)c.sample(20,true,600);
  assert(c.currentBand()==stride::Band::Stop);
  assert(!c.command("b",stride::Pattern::Left,1500,0,600));
  for(int i=0;i<3;++i)c.sample(33,true,700);
  assert(c.currentBand()==stride::Band::Stop);
  for(int i=0;i<3;++i)c.sample(120,true,800);
  assert(c.currentBand()==stride::Band::Clear);
  assert(!c.command("b",stride::Pattern::Left,1500,0,800));
  assert(!c.command("c",stride::Pattern::Left,100,101,800));
  c.sample(0,false,900);
  assert(c.currentBand()==stride::Band::Unknown);
  for(int i=0;i<3;++i)c.sample(120,true,1000);
  assert(c.command("d",stride::Pattern::Left,100,0,1000));
  assert(!c.tick(1100).motor);
  assert(c.tick(1400).band==stride::Band::Unknown);
}
