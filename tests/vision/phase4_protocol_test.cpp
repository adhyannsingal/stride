#include "../../firmware/feedback/phase4_protocol.h"
#include <cassert>
#include <iostream>
#include <sstream>
int main() {
  std::ostringstream input; input << std::cin.rdbuf();
  JsonDocument report;
  assert(!deserializeJson(report,input.str()));
  JsonObject c=report["events"][0]["firmware_command"];
  assert(!c.isNull());
  RemoteCue cue{};
  auto decode=[&](){return decodePhase4Command(c,"simulation-controller","simulation-session","simulation-boot",cue);};
  assert(decode()); assert(cue.pattern==stride::Pattern::Straight);
  assert(cue.ttl>0 && cue.ttl<=1500);
  c["boot_id"]="old-boot"; assert(!decode()); c["boot_id"]="simulation-boot";
  c["device_id"]="other"; assert(!decode()); c["device_id"]="simulation-controller";
  c["session_id"]="other"; assert(!decode()); c["session_id"]="simulation-session";
  c["remaining_ttl_ms"]=-1; assert(!decode());
  c["remaining_ttl_ms"]=0; assert(!decode());
  c["remaining_ttl_ms"]=1501; assert(!decode());
  c["remaining_ttl_ms"]=1000;
  c["state_revision"]=-1; assert(!decode()); c["state_revision"]=1;
  c["status"]="expired"; assert(!decode()); c["status"]="delivered";
  c["kind"]="unknown"; assert(!decode());
  c["kind"]="cancel"; assert(decode()); assert(cue.pattern==stride::Pattern::None);
  c["kind"]="stop"; assert(decode()); assert(cue.pattern==stride::Pattern::Stop);
  std::cout << "PASS: actual backend command decoded; identity, expiry, revision, kind and status guards\n";
}
