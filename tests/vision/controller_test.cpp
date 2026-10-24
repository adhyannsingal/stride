#include "../../firmware/feedback/controller.h"
#include <cassert>
int main() {
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
