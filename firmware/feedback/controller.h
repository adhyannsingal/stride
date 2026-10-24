#pragma once
#include <stdint.h>
#include <algorithm>
#include <string>

// Portable policy; all time comparisons use local monotonic milliseconds.
namespace stride {
enum class Band { Unknown, Clear, Warning, Near, Stop };
enum class Pattern { None, Left, Right, Straight, Stop };
struct Output { bool motor; bool buzzer; Band band; };

class Controller {
 public:
  void sample(float cm, bool valid, uint32_t now) {
    lastSample = now;
    if (!valid || !(cm > 0 && cm <= 500)) {
      band = Band::Unknown;
      count = index = 0;
      cancel();
      return;
    }
    readings[index++ % 3] = cm;
    if (count < 3) ++count;
    if (count < 3) { band = Band::Unknown; return; }
    float sorted[3] = {readings[0],readings[1],readings[2]};
    std::sort(sorted,sorted+3);
    float d = sorted[1];
    distance = d;
    // Immediate escalation, 5 cm hysteresis when leaving a warning band.
    if (d < 30 || (band == Band::Stop && d < 35)) band = Band::Stop;
    else if (d < 60 || (band == Band::Near && d < 65)) band = Band::Near;
    else if (d < 100 || (band == Band::Warning && d < 105)) band = Band::Warning;
    else band = Band::Clear;
    if (band != Band::Clear) cancel();
  }

  // Caller validates authenticated session/generation/boot before acceptance.
  // Reserve IDs even on rejection, so blocked or expired cues cannot replay.
  bool command(const std::string& id, Pattern p, uint32_t ttl, uint32_t requestElapsed, uint32_t now) {
    if (id.empty() || id.size()>64 || seen.find("|"+id+"|") != std::string::npos) return false;
    if (id.find('|') != std::string::npos || seen.size()+id.size()+2 > 8192) return false;
    seen += "|"+id+"|";
    if (band != Band::Clear || ttl>1500 || ttl<=requestElapsed || p==Pattern::None) return false;
    pattern=p; started=now; remaining=ttl-requestElapsed;
    return true;
  }
  void cancel() { pattern=Pattern::None; }
  void linkLost() { cancel(); }
  Output tick(uint32_t now) {
    if (now-lastSample>300) { band=Band::Unknown; cancel(); }
    if (band==Band::Stop) return {now%1000<800, now%300<200,band};
    if (band==Band::Near) return {now%500<150,now%500<150,band};
    if (band==Band::Warning) return {now%1000<100,now%1000<100,band};
    if (band==Band::Unknown) return {false,now%2000<80,band};
    const uint32_t elapsed=now-started;
    if (elapsed>=remaining) cancel();
    bool on=false;
    switch(pattern) {
      case Pattern::Left: on=elapsed<200; if(elapsed>=200) cancel(); break;
      case Pattern::Right: on=elapsed<600 && elapsed%400<200; if(elapsed>=600) cancel(); break;
      case Pattern::Straight: on=elapsed<600 && elapsed%240<120; if(elapsed>=600) cancel(); break;
      case Pattern::Stop: on=elapsed<800; if(elapsed>=800) cancel(); break;
      default: break;
    }
    return {on,false,band};
  }
  float distanceCm() const { return distance; }
  bool remoteActive() const { return pattern != Pattern::None; }
  Band currentBand() const { return band; }
 private:
  float readings[3] = {};
  float distance=0;
  uint32_t index=0, count=0, lastSample=0, started=0, remaining=0;
  Band band=Band::Unknown;
  Pattern pattern=Pattern::None;
  std::string seen;
};
}
